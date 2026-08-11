"""
Load the PrivacyPolicyTuples CSVs into ``(from, relationship, to, weight)`` tuples.

The folder holds two extractions of the same 94 statements from Privacy
Regulations 2025:

* ``*_semantic_tuples.csv``    - subject, relation, object + conditions, purpose,
  exceptions.  Relations are a normalised vocabulary (``PRESCRIBED_AS``,
  ``DEFINED_AS``, ...), 18 of them.
* ``*_naive_ollie_tuples.csv`` - arg1, relation, arg2 with the raw surface
  relation (``is prescribed``, ``means``, ...), 20 of them.

The two files are row-aligned: row *i* of each is the same statement, and the
``section`` column matches pairwise for all 94.  Endpoints are identical for
77 of them; in the other 17 the semantic extractor restructured the claim rather
than just renaming it, so those are not treated as the same fact.

Neither file has a confidence column, so the weight has to come from somewhere -
see :func:`tuple_weight` and the ``weight_mode`` argument.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable, Sequence

from augmentation import Triple
from knowledge_graph import normalise

HERE = Path(__file__).resolve().parent
DEFAULT_DIR = HERE.parent / "PrivacyPolicyTuples"

NAIVE_FILE = "privacy_regulations_2025_naive_ollie_tuples.csv"
SEMANTIC_FILE = "privacy_regulations_2025_semantic_tuples.csv"

#: How much each extractor is trusted, used by the "source" weight mode.  The
#: semantic file is a cleaned-up reading of the same statements, so it earns
#: more credence than the raw Ollie output.
DEFAULT_TRUST = {"semantic": 0.9, "naive": 0.6}

#: Columns carried onto the edge as provenance.
SEMANTIC_CONTEXT = ("conditions", "purpose", "exceptions")

WEIGHT_MODES = ("constant", "source", "specificity")

#: Provenance that must survive being asserted more than once.  A regulation
#: fact can be prescribed in several sections and found by both extractors; as
#: scalar properties the last write would win and the trail back to the
#: regulation would be lost, so these accumulate into list properties.
ACCUMULATE = {
    "section": "sections",
    "source": "sources",
    "surface_relation": "surface_relations",
}


# --------------------------------------------------------------------------- #
# Weighting
# --------------------------------------------------------------------------- #

def tuple_weight(
    mode: str,
    source: str,
    row: dict[str, str],
    trust: dict[str, float] = DEFAULT_TRUST,
) -> float:
    """Decide the incoming weight for one CSV row.

    ``constant``
        Every tuple arrives at 1.0.  The weight then only carries information if
        the augmentation rule is count-sensitive (``sum``, ``mean``) - note that
        ``ema`` is a no-op on constant input, since 0.9w + 0.1w == w.
    ``source``
        Weight is the trust in the extractor that produced the row.  Ingesting
        both files then makes edge weight a measure of *extractor agreement*.
    ``specificity``
        Source trust plus a small bonus per populated context column, on the
        argument that a statement extracted with its conditions and purpose was
        read more carefully than a bare triple.
    """
    if mode == "constant":
        return 1.0
    base = trust[source]
    if mode == "source":
        return base
    if mode == "specificity":
        filled = sum(1 for column in SEMANTIC_CONTEXT if (row.get(column) or "").strip())
        return min(1.0, base + 0.05 * filled)
    raise ValueError(f"unknown weight_mode {mode!r}; expected one of {WEIGHT_MODES}")


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #

def read_rows(path: Path) -> list[dict[str, str]]:
    # utf-8-sig: the files carry a BOM, which would otherwise end up glued to
    # the first column name.
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _entity(value: str, normalise_entities: bool) -> str:
    value = (value or "").strip()
    return normalise(value) if normalise_entities else value


def _meta(row: dict[str, str], source: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Provenance stored on the edge.  Empty values are dropped, not written as ''."""
    meta: dict[str, Any] = {"source": source, "section": (row.get("section") or "").strip()}
    for column in SEMANTIC_CONTEXT:
        value = (row.get(column) or "").strip()
        if value:
            meta[column] = value
    if extra:
        meta.update(extra)
    return {key: value for key, value in meta.items() if value != ""}


def semantic_triples(
    path: Path,
    *,
    weight_mode: str = "source",
    trust: dict[str, float] = DEFAULT_TRUST,
    normalise_entities: bool = True,
) -> list[Triple]:
    return [
        Triple(
            from_entity=_entity(row["subject"], normalise_entities),
            relationship=row["relation"].strip(),
            to_entity=_entity(row["object"], normalise_entities),
            weight=tuple_weight(weight_mode, "semantic", row, trust),
            meta=_meta(row, "semantic"),
        )
        for row in read_rows(path)
    ]


def naive_triples(
    path: Path,
    *,
    weight_mode: str = "source",
    trust: dict[str, float] = DEFAULT_TRUST,
    normalise_entities: bool = True,
    relation_overrides: dict[int, str] | None = None,
) -> list[Triple]:
    """Load the naive file.

    ``relation_overrides`` maps row index to the semantic relation, so a naive
    row can be cast as a second observation of the same edge rather than a
    parallel edge with a different relation name.
    """
    overrides = relation_overrides or {}
    triples = []
    for index, row in enumerate(read_rows(path)):
        aligned = index in overrides
        triples.append(
            Triple(
                from_entity=_entity(row["arg1"], normalise_entities),
                relationship=overrides.get(index, row["relation"].strip()),
                to_entity=_entity(row["arg2"], normalise_entities),
                weight=tuple_weight(weight_mode, "naive", row, trust),
                meta=_meta(
                    row, "naive",
                    {"surface_relation": row["relation"].strip(), "aligned": aligned},
                ),
            )
        )
    return triples


# --------------------------------------------------------------------------- #
# Aligning the two extractions
# --------------------------------------------------------------------------- #

def align_relations(
    naive_path: Path,
    semantic_path: Path,
    *,
    normalise_entities: bool = True,
) -> tuple[dict[int, str], list[int]]:
    """Match naive rows onto their semantic counterpart.

    The files are row-aligned, so this is a positional zip guarded by a check
    that the endpoints really are the same claim.  Returns the relation override
    map and the indices that could not be matched.

    Without this, ``(x) -[is prescribed]-> (y)`` and ``(x) -[PRESCRIBED_AS]-> (y)``
    are two unrelated edges and the second extractor reinforces nothing.
    """
    naive_rows = read_rows(naive_path)
    semantic_rows = read_rows(semantic_path)
    if len(naive_rows) != len(semantic_rows):
        raise ValueError(
            f"files are not row-aligned: {len(naive_rows)} naive rows vs "
            f"{len(semantic_rows)} semantic rows"
        )

    overrides: dict[int, str] = {}
    unmatched: list[int] = []
    for index, (naive, semantic) in enumerate(zip(naive_rows, semantic_rows)):
        endpoints_match = (
            _entity(naive["arg1"], normalise_entities) == _entity(semantic["subject"], normalise_entities)
            and _entity(naive["arg2"], normalise_entities) == _entity(semantic["object"], normalise_entities)
        )
        if endpoints_match and naive["section"].strip() == semantic["section"].strip():
            overrides[index] = semantic["relation"].strip()
        else:
            unmatched.append(index)
    return overrides, unmatched


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def load(
    directory: str | Path = DEFAULT_DIR,
    *,
    sources: Sequence[str] = ("semantic",),
    weight_mode: str = "source",
    trust: dict[str, float] = DEFAULT_TRUST,
    normalise_entities: bool = True,
    align: bool = True,
) -> list[Triple]:
    """Build the tuple list to feed into ``KnowledgeGraph.add_many``.

    ``sources`` may name ``"semantic"``, ``"naive"``, or both.  With both and
    ``align=True`` the naive rows adopt the semantic relation wherever the two
    extractors describe the same claim, so agreement shows up as a second
    observation on one edge instead of a duplicate edge.

    Ordering matters for order-sensitive rules: semantic tuples are emitted
    first, so under ``ema`` the more-trusted reading sets the edge and the naive
    one nudges it.
    """
    directory = Path(directory)
    unknown = set(sources) - {"semantic", "naive"}
    if unknown:
        raise ValueError(f"unknown source(s): {', '.join(sorted(unknown))}")

    overrides: dict[int, str] = {}
    if align and "naive" in sources and "semantic" in sources:
        overrides, _ = align_relations(
            directory / NAIVE_FILE, directory / SEMANTIC_FILE,
            normalise_entities=normalise_entities,
        )

    triples: list[Triple] = []
    if "semantic" in sources:
        triples += semantic_triples(
            directory / SEMANTIC_FILE, weight_mode=weight_mode, trust=trust,
            normalise_entities=normalise_entities,
        )
    if "naive" in sources:
        triples += naive_triples(
            directory / NAIVE_FILE, weight_mode=weight_mode, trust=trust,
            normalise_entities=normalise_entities, relation_overrides=overrides,
        )
    return triples


def describe(triples: Iterable[Triple]) -> dict[str, int]:
    """Counts worth printing before a build."""
    triples = list(triples)
    keys = [t.key for t in triples]
    entities = {t.from_entity for t in triples} | {t.to_entity for t in triples}
    return {
        "tuples": len(triples),
        "distinct_edges": len(set(keys)),
        "repeated_edges": len(keys) - len(set(keys)),
        "entities": len(entities),
        "relations": len({t.relationship for t in triples}),
    }
