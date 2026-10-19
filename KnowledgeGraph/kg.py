"""
Knowledge graph built from ``(from_entity, relationship, to_entity, weight)``
tuples, persisted in Neo4j Aura.

    from augmentation import ExponentialMovingAverage
    from config import load_credentials
    from kg import KnowledgeGraph
    from neo4j_gdb import Neo4JGDB

    creds = load_credentials()
    with Neo4JGDB(creds.uri, creds.auth) as db:
        with KnowledgeGraph(db, ExponentialMovingAverage(0.9, 0.1)) as kg:
            kg.add("user", "can view", "dashboard", 0.82)
            kg.add("user", "can view", "dashboard", 0.60)   # duplicate -> augmented

The augmentation rule is a constructor argument, so swapping how the graph
learns is a one-line change; see ``augmentation.py`` for the built-in rules and
for how to plug in your own model.

Graph model
-----------
Every entity is a ``:Entity`` node keyed on ``entity``, with optional role labels
(``:User``, ``:PostCondition``, ...) layered on top.  Keying on one label means a
single uniqueness constraint indexes every MERGE, and an entity that appears on
both sides of a tuple is one node rather than two.  Relationships are
``:RELATED_TO`` edges carrying ``relationship``, ``weight``, ``observations``,
``first_seen`` and ``last_seen``; ``relationship`` is part of the merge key, so
distinct relations between the same pair are distinct edges.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import replace
from typing import Any, Callable, Iterable, Mapping, Sequence

from augmentation import AugmentStrategy, EdgeState, Triple, as_strategy
from graph_database import DatabaseAPI
from neo4j_gdb import BASE_LABEL


class KnowledgeGraph:
    """Ingests tuples, applying an augmentation strategy to every one of them.

    Tuples are buffered and written in batches because a round trip to Aura
    dominates the cost of the write itself.  ``batch_size=1`` restores strict
    write-through semantics at roughly two orders of magnitude less throughput.

    Provenance passed as keyword arguments to :meth:`add` is stored on the edge.
    By default a second observation overwrites it, which loses the trail on any
    edge asserted more than once; naming those keys in ``accumulate`` stores them
    as list properties gathering every distinct value instead::

        KnowledgeGraph(db, strategy, accumulate=("section", "source"))
        kg.add("a", "R", "b", 0.9, section="16(c)", source="semantic")
        kg.add("a", "R", "b", 0.6, section="19(b)", source="naive")
        # -> r.sections = ["16(c)", "19(b)"], r.sources = ["semantic", "naive"]

    Pass a mapping to choose the property names, e.g. ``{"section": "cited_in"}``.
    """

    def __init__(
        self,
        db: DatabaseAPI,
        strategy: AugmentStrategy | Callable | str | None = None,
        *,
        batch_size: int = 500,
        base_label: str = BASE_LABEL,
        rel_type: str = "RELATED_TO",
        default_from_type: str | None = None,
        default_to_type: str | None = None,
        prefer_cypher: bool = True,
        accumulate: Sequence[str] | Mapping[str, str] | None = None,
    ):
        self.db = db
        self.strategy = as_strategy(strategy)
        self.batch_size = max(1, int(batch_size))
        self.base_label = base_label
        self.rel_type = rel_type
        self.default_from_type = default_from_type
        self.default_to_type = default_to_type
        self.prefer_cypher = prefer_cypher
        self.accumulate = self._normalise_accumulate(accumulate)
        self._buffer: list[Triple] = []
        self.stats = {"tuples": 0, "written": 0, "created": 0, "batches": 0, "queries": 0}

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "KnowledgeGraph":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.flush()

    @property
    def uses_cypher_path(self) -> bool:
        """True when the strategy is being evaluated inside the database."""
        return (
            self.prefer_cypher
            and self.strategy.supports_cypher
            and getattr(self.db, "supports_cypher_augment", True)
        )

    def ensure_schema(self) -> None:
        self.db.ensure_schema(self.base_label)

    def set_strategy(self, strategy: AugmentStrategy | Callable | str) -> None:
        """Swap the augmentation rule mid-stream (flushes anything buffered)."""
        self.flush()
        self.strategy = as_strategy(strategy)

    # ------------------------------------------------------------------ #
    # Ingestion
    # ------------------------------------------------------------------ #

    def add(
        self,
        from_entity: str,
        relationship: str,
        to_entity: str,
        weight: float = 1.0,
        *,
        from_type: str | None = None,
        to_type: str | None = None,
        timestamp: float | None = None,
        **meta: Any,
    ) -> None:
        """Add one tuple.  The augmentation strategy decides the stored weight."""
        self.add_triple(
            Triple(
                from_entity=from_entity,
                relationship=relationship,
                to_entity=to_entity,
                weight=float(weight),
                from_type=from_type,
                to_type=to_type,
                timestamp=timestamp,
                meta=meta,
            )
        )

    def add_triple(self, triple: Triple) -> None:
        # Defaults are applied here rather than in add(), so tuples arriving via
        # add_many() or as bare Triples pick up the same role labels.
        if triple.from_type is None and self.default_from_type is not None:
            triple = replace(triple, from_type=self.default_from_type)
        if triple.to_type is None and self.default_to_type is not None:
            triple = replace(triple, to_type=self.default_to_type)
        self._buffer.append(triple)
        self.stats["tuples"] += 1
        if len(self._buffer) >= self.batch_size:
            self.flush()

    def add_many(self, tuples: Iterable[Sequence | Triple], **defaults: Any) -> dict[str, int]:
        """Add an iterable of ``(from, relationship, to, weight)`` tuples."""
        for item in tuples:
            if isinstance(item, Triple):
                self.add_triple(item)
            else:
                self.add_triple(Triple.from_tuple(item, **defaults))
        return self.stats

    # ------------------------------------------------------------------ #
    # Flushing
    # ------------------------------------------------------------------ #

    def flush(self) -> dict[str, int]:
        """Apply the strategy to everything buffered and write it out."""
        if not self._buffer:
            return self.stats
        buffered, self._buffer = self._buffer, []
        self.stats["batches"] += 1

        # Role labels are interpolated into the query, so rows are grouped by
        # label pair; in practice that is one or two groups.
        groups: dict[tuple[str | None, str | None], list[Triple]] = defaultdict(list)
        for triple in buffered:
            groups[(triple.from_type, triple.to_type)].append(triple)

        for (from_type, to_type), group in groups.items():
            if self.uses_cypher_path:
                self._flush_via_cypher(group, from_type, to_type)
            else:
                self._flush_via_python(group, from_type, to_type)
        return self.stats

    def _flush_via_cypher(
        self, group: list[Triple], from_type: str | None, to_type: str | None
    ) -> None:
        """One query per wave; the strategy's rule runs inside the database.

        A key may only appear once per query, otherwise the planner is free to
        read every row's pre-update weight before applying any of the writes and
        duplicates within the batch would collapse into a single update.  Splitting
        into waves - first occurrence of each key, then second, and so on -
        preserves the semantics of applying the rule once per tuple, in order.
        """
        for wave in self._unique_waves(group):
            rows = []
            for t in wave:
                # Provenance travels with the tuple down both paths; the strategy's
                # own output still wins on `weight`.
                scalar, appended = self._split_meta(t)
                rows.append(
                    {
                        "from_entity": t.from_entity,
                        "relationship": t.relationship,
                        "to_entity": t.to_entity,
                        "weight": t.weight,
                        "props": scalar,
                        "acc": appended,
                        "now": t.timestamp if t.timestamp is not None else self._now(),
                    }
                )
            result = self.db.augment_edges(
                rows,
                first_expression=self.strategy.cypher_first,
                update_expression=self.strategy.cypher_update,
                from_label=from_type,
                to_label=to_type,
                base_label=self.base_label,
                rel_type=self.rel_type,
                accumulate=self.accumulate,
            )
            self._record(result)

    def _flush_via_python(
        self, group: list[Triple], from_type: str | None, to_type: str | None
    ) -> None:
        """Read current state, run the strategy in Python, write the result back.

        Two round trips per batch regardless of how many tuples it holds.  In-batch
        duplicates are folded here, so the strategy sees each tuple in order with
        the state produced by the previous one.
        """
        keys = list(dict.fromkeys(t.key for t in group))
        stored = self.db.fetch_edges(keys, base_label=self.base_label, rel_type=self.rel_type)
        states: dict[tuple[str, str, str], EdgeState] = {
            key: EdgeState(
                weight=self._weight_of(row),
                observations=row.get("observations") or 0,
                first_seen=row.get("first_seen"),
                last_seen=row.get("last_seen"),
                props=row.get("props") or {},
            )
            for key, row in stored.items()
        }

        pending: dict[tuple[str, str, str], dict[str, Any]] = {}
        for triple in group:
            now = triple.timestamp if triple.timestamp is not None else self._now()
            current = states.get(triple.key)
            scalar, appended = self._split_meta(triple)
            existing_props = current.props if current else {}
            props = self._as_props(self.strategy(current, triple), scalar)
            props = self._merge_accumulators(props, appended, existing_props)

            states[triple.key] = EdgeState(
                weight=props["weight"],
                observations=(current.observations if current else 0) + 1,
                first_seen=current.first_seen if current and current.first_seen else now,
                last_seen=now,
                # Carry forward properties this tuple did not touch, so a later
                # duplicate in the same batch still sees the full accumulator.
                props={**existing_props, **props},
            )
            row = pending.setdefault(
                triple.key,
                {
                    "from_entity": triple.from_entity,
                    "relationship": triple.relationship,
                    "to_entity": triple.to_entity,
                    "observations": 0,
                },
            )
            row["props"] = props
            row["observations"] += 1
            row["now"] = now

        self._record(
            self.db.upsert_edges(
                list(pending.values()),
                from_label=from_type,
                to_label=to_type,
                base_label=self.base_label,
                rel_type=self.rel_type,
            )
        )

    # ------------------------------------------------------------------ #
    # Reading back
    # ------------------------------------------------------------------ #

    def weight(self, from_entity: str, relationship: str, to_entity: str) -> float | None:
        """Current weight of one edge, or None if it does not exist."""
        self.flush()
        found = self.db.fetch_edges(
            [(from_entity, relationship, to_entity)],
            base_label=self.base_label,
            rel_type=self.rel_type,
        )
        row = found.get((from_entity, relationship, to_entity))
        return None if row is None else self._weight_of(row)

    def edge(self, from_entity: str, relationship: str, to_entity: str) -> dict[str, Any] | None:
        """Full stored state of one edge."""
        self.flush()
        return self.db.fetch_edges(
            [(from_entity, relationship, to_entity)],
            base_label=self.base_label,
            rel_type=self.rel_type,
        ).get((from_entity, relationship, to_entity))

    def neighbours(self, entity: str) -> list[dict[str, Any]]:
        """Everything connected to ``entity``, strongest edge first."""
        self.flush()
        return self.db.list_relationships(self.base_label, entity)

    def top_edges(self, limit: int = 20) -> list[dict[str, Any]]:
        self.flush()
        return self.db.top_edges(limit, rel_type=self.rel_type)

    def counts(self) -> dict[str, int]:
        self.flush()
        return self.db.counts()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _now() -> float:
        return time.time()

    @staticmethod
    def _normalise_accumulate(
        accumulate: Sequence[str] | Mapping[str, str] | None,
    ) -> dict[str, str]:
        """Resolve the accumulator spec into ``{meta key: list property}``.

        A bare sequence of keys gets the conventional plural property name, so
        ``("section", "source")`` writes ``sections`` and ``sources``.
        """
        if not accumulate:
            return {}
        if isinstance(accumulate, Mapping):
            return dict(accumulate)
        return {key: f"{key}s" for key in accumulate}

    def _split_meta(self, triple: Triple) -> tuple[dict[str, Any], dict[str, Any]]:
        """Separate a tuple's provenance into overwriting props and appended values."""
        if not self.accumulate:
            return dict(triple.meta), {}
        scalar: dict[str, Any] = {}
        appended: dict[str, Any] = {}
        for key, value in triple.meta.items():
            if key in self.accumulate and value is not None and value != "":
                appended[key] = value
            else:
                scalar[key] = value
        return scalar, appended

    def _merge_accumulators(
        self,
        props: dict[str, Any],
        appended: Mapping[str, Any],
        existing: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Python-side twin of the Cypher accumulator update: append if new."""
        for key, value in appended.items():
            prop = self.accumulate[key]
            values = list(existing.get(prop) or [])
            if value not in values:
                values.append(value)
            props[prop] = values
        return props

    @staticmethod
    def _weight_of(row: Mapping[str, Any]) -> float:
        """Edge weight, falling back to the legacy ``strength`` property."""
        weight = row.get("weight")
        if weight is None:
            weight = (row.get("props") or {}).get("strength", 0.0)
        return float(weight)

    @staticmethod
    def _as_props(
        result: float | Mapping[str, Any], meta: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """Normalise a strategy's return value into a property map."""
        if isinstance(result, Mapping):
            props = dict(result)
            if "weight" not in props:
                raise ValueError(f"strategy returned {result!r} without a 'weight' key")
        else:
            props = {"weight": result}
        props["weight"] = float(props["weight"])
        if meta:
            props = {**meta, **props}
        return props

    @staticmethod
    def _unique_waves(triples: Sequence[Triple]) -> list[list[Triple]]:
        """Split into ordered groups in which every edge key appears at most once."""
        waves: list[list[Triple]] = []
        seen: list[set[tuple[str, str, str]]] = []
        for triple in triples:
            for wave, keys in zip(waves, seen):
                if triple.key not in keys:
                    wave.append(triple)
                    keys.add(triple.key)
                    break
            else:
                waves.append([triple])
                seen.append({triple.key})
        return waves

    def _record(self, result: Mapping[str, int]) -> None:
        self.stats["queries"] += 1
        self.stats["written"] += result.get("written", 0) or 0
        self.stats["created"] += result.get("created", 0) or 0
