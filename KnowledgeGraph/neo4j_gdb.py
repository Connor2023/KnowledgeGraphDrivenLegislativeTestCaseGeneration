import re
from typing import Any, Mapping, Sequence

from neo4j import GraphDatabase, Driver

from graph_database import DatabaseAPI

#: Every entity node carries this label, and MERGE always keys on it, so one
#: uniqueness constraint covers the whole graph and a given entity string is one
#: node no matter which role it plays.
BASE_LABEL = "Entity"

#: Role labels (User, PostCondition, ...) are added *on top* of the base label.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    """Backtick-quote a label or relationship type after validating it.

    Labels cannot be parameterised in Cypher, so they are interpolated into the
    query string; this keeps that interpolation from being an injection point.
    """
    if not _IDENT_RE.match(name):
        raise ValueError(f"invalid Neo4j identifier: {name!r}")
    return f"`{name}`"


class Neo4JGDB(DatabaseAPI):
    #: This backend can evaluate a strategy's Cypher expression server-side.
    supports_cypher_augment = True

    def __init__(self, uri, auth, database: str = "neo4j"):
        self.__uri = uri
        self.__auth = auth
        self.__database = database
        self.__driver: Driver | None = None

    def start(self):
        """Start driver connection."""
        if self.__driver is None:
            self.__driver = GraphDatabase.driver(self.__uri, auth=self.__auth)
            self.__driver.verify_connectivity()
            self.__driver.verify_authentication()
        return self.__driver is not None

    def shutdown(self):
        """Close driver connection."""
        if self.__driver is not None:
            self.__driver.close()
            self.__driver = None
        return self.__driver is None

    def _session(self):
        """Open a session pinned to the target database.

        Naming the database skips a routing round trip per session, which is
        worth having against Aura.
        """
        if not self.__driver:
            raise RuntimeError("Driver not started.")
        return self.__driver.session(database=self.__database)

    # ------------------------------------------------------------------ #
    # Schema
    # ------------------------------------------------------------------ #

    def ensure_schema(self, base_label: str = BASE_LABEL) -> None:
        """Create the uniqueness constraint the ingestion path relies on.

        Without an index behind it, every ``MERGE (a:Entity {entity: ...})`` is a
        full label scan, so this is the difference between a linear-time and a
        quadratic-time build. Idempotent.
        """
        label = _safe_ident(base_label)
        constraint = _safe_ident(f"{base_label}_entity_unique")
        query = (
            f"CREATE CONSTRAINT {constraint} IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.entity IS UNIQUE"
        )
        with self._session() as session:
            session.run(query).consume()

    # ------------------------------------------------------------------ #
    # Batched tuple ingestion
    # ------------------------------------------------------------------ #

    def _edge_prelude(
        self,
        from_label: str | None,
        to_label: str | None,
        base_label: str,
        rel_type: str,
    ) -> str:
        """MERGE the two endpoints, their role labels, and the relationship."""
        base = _safe_ident(base_label)
        label_sets = []
        if from_label and from_label != base_label:
            label_sets.append(f"a:{_safe_ident(from_label)}")
        if to_label and to_label != base_label:
            label_sets.append(f"b:{_safe_ident(to_label)}")
        set_labels = f"SET {', '.join(label_sets)}\n" if label_sets else ""
        return (
            "UNWIND $rows AS row\n"
            f"MERGE (a:{base} {{entity: row.from_entity}})\n"
            f"MERGE (b:{base} {{entity: row.to_entity}})\n"
            f"{set_labels}"
            f"MERGE (a)-[r:{_safe_ident(rel_type)} {{relationship: row.relationship}}]->(b)\n"
        )

    @staticmethod
    def _accumulator_pairs(accumulate: Mapping[str, str] | None) -> list[tuple[int, str, str]]:
        """``(index, meta key, list property)`` for each accumulator, in a stable order."""
        return [
            (index, key, prop)
            for index, (key, prop) in enumerate(sorted((accumulate or {}).items()))
        ]

    def _accumulator_bindings(self, accumulate: Mapping[str, str] | None) -> str:
        """Capture each list property in the WITH, before anything writes to it."""
        return "".join(
            f",\n             coalesce(r.{_safe_ident(prop)}, []) AS acc_{index}"
            for index, _key, prop in self._accumulator_pairs(accumulate)
        )

    def _accumulator_updates(self, accumulate: Mapping[str, str] | None) -> str:
        """Append this row's value to each list property, skipping nulls and repeats."""
        clauses = []
        for index, key, prop in self._accumulator_pairs(accumulate):
            value = f"row.acc.{_safe_ident(key)}"
            clauses.append(
                f",\n            r.{_safe_ident(prop)} = "
                f"CASE WHEN {value} IS NULL THEN acc_{index} "
                f"WHEN {value} IN acc_{index} THEN acc_{index} "
                f"ELSE acc_{index} + {value} END"
            )
        return "".join(clauses)

    def fetch_edges(
        self,
        keys: Sequence[tuple[str, str, str]],
        *,
        base_label: str = BASE_LABEL,
        rel_type: str = "RELATED_TO",
    ) -> dict[tuple[str, str, str], dict[str, Any]]:
        """Read the current state of many edges in one round trip.

        ``keys`` are ``(from_entity, relationship, to_entity)`` tuples; missing
        edges are simply absent from the result.
        """
        if not keys:
            return {}
        base = _safe_ident(base_label)
        query = f"""
        UNWIND $keys AS k
        MATCH (a:{base} {{entity: k[0]}})-[r:{_safe_ident(rel_type)} {{relationship: k[1]}}]->
              (b:{base} {{entity: k[2]}})
        RETURN k AS key,
               r.weight AS weight,
               coalesce(r.observations, 0) AS observations,
               r.first_seen AS first_seen,
               r.last_seen AS last_seen,
               properties(r) AS props
        """
        with self._session() as session:
            records = session.execute_read(
                lambda tx: list(tx.run(query, keys=[list(k) for k in keys]))
            )
        return {
            tuple(record["key"]): {
                "weight": record["weight"],
                "observations": record["observations"],
                "first_seen": record["first_seen"],
                "last_seen": record["last_seen"],
                "props": record["props"],
            }
            for record in records
        }

    def upsert_edges(
        self,
        rows: Sequence[dict[str, Any]],
        *,
        from_label: str | None = None,
        to_label: str | None = None,
        base_label: str = BASE_LABEL,
        rel_type: str = "RELATED_TO",
    ) -> dict[str, int]:
        """Write pre-computed edge properties for a batch of tuples.

        Each row needs ``from_entity``, ``relationship``, ``to_entity``,
        ``props`` (a map that must include ``weight``), ``observations`` (how
        many times this edge was seen in the batch) and ``now``.

        The caller is responsible for having already folded duplicate keys, since
        the weights here are final values rather than increments.

        Returns ``{"written": n, "created": n}``.
        """
        if not rows:
            return {"written": 0, "created": 0}
        query = self._edge_prelude(from_label, to_label, base_label, rel_type) + """
        WITH row, r, r.first_seen AS old_first_seen
        SET r += row.props,
            r.observations = coalesce(r.observations, 0) + row.observations,
            r.first_seen = coalesce(old_first_seen, row.now),
            r.last_seen = row.now
        RETURN count(r) AS written,
               sum(CASE WHEN old_first_seen IS NULL THEN 1 ELSE 0 END) AS created
        """
        with self._session() as session:
            record = session.execute_write(lambda tx: tx.run(query, rows=list(rows)).single())
        return record.data() if record else {"written": 0, "created": 0}

    def augment_edges(
        self,
        rows: Sequence[dict[str, Any]],
        *,
        first_expression: str,
        update_expression: str,
        from_label: str | None = None,
        to_label: str | None = None,
        base_label: str = BASE_LABEL,
        rel_type: str = "RELATED_TO",
        accumulate: Mapping[str, str] | None = None,
    ) -> dict[str, int]:
        """Apply an augmentation rule server-side, in the same query as the MERGE.

        ``update_expression`` is evaluated for an edge that already exists and
        ``first_expression`` for one being created; both may reference
        ``old_weight``, ``old_observations``, ``old_first_seen``,
        ``old_last_seen``, ``row.weight`` and ``row.now``.

        Each row needs ``from_entity``, ``relationship``, ``to_entity``,
        ``weight``, ``props`` (provenance to store on the edge; may be empty),
        ``acc`` (values to append to list properties) and ``now``.  A key must
        not appear twice in one call - see ``KnowledgeGraph._unique_waves``.

        ``accumulate`` maps a key of ``row.acc`` to the list property it feeds.
        Those properties gather the distinct values seen across every
        observation, instead of the last one overwriting the rest.

        Returns ``{{"written": n, "created": n}}``.
        """
        if not rows:
            return {"written": 0, "created": 0}
        query = self._edge_prelude(from_label, to_label, base_label, rel_type) + f"""
        WITH row, r,
             r.weight AS old_weight,
             coalesce(r.observations, 0) AS old_observations,
             r.first_seen AS old_first_seen,
             r.last_seen AS old_last_seen{self._accumulator_bindings(accumulate)}
        SET r += row.props,
            r.weight = CASE WHEN old_weight IS NULL
                            THEN ({first_expression})
                            ELSE ({update_expression}) END,
            r.observations = old_observations + 1,
            r.first_seen = coalesce(old_first_seen, row.now),
            r.last_seen = row.now{self._accumulator_updates(accumulate)}
        RETURN count(r) AS written,
               sum(CASE WHEN old_weight IS NULL THEN 1 ELSE 0 END) AS created
        """
        with self._session() as session:
            record = session.execute_write(lambda tx: tx.run(query, rows=list(rows)).single())
        return record.data() if record else {"written": 0, "created": 0}

    # ------------------------------------------------------------------ #
    # Single-entity / single-edge operations
    # ------------------------------------------------------------------ #

    def create_new_entity(self, type: str, entity: str):
        """Create a node if it doesn't exist."""
        cypher_query = f"""
        MERGE (n:{_safe_ident(BASE_LABEL)} {{entity: $entity}})
        SET n:{_safe_ident(type)}
        RETURN n
        """
        with self._session() as session:
            record = session.execute_write(lambda tx: tx.run(cypher_query, entity=entity).single())
            return record["n"] if record else None

    def check_entity_exists(self, type: str, entity: str) -> bool:
        """Check if a node exists."""
        cypher_query = f"""
        MATCH (n:{_safe_ident(type)} {{entity: $entity}})
        RETURN n LIMIT 1
        """
        with self._session() as session:
            return session.execute_read(
                lambda tx: tx.run(cypher_query, entity=entity).single() is not None
            )

    def list_nodes(self, type: str | None = None):
        """
        Return all node entities, optionally filtered by label type.

        Args:
            type (str | None): Optional label type (e.g., 'Person', 'Company').
                            If None, returns all nodes.
        Returns:
            list[dict]: A list of {'entity': str, 'labels': list[str]} for each node.
        """
        match = f"MATCH (n:{_safe_ident(type)})" if type else "MATCH (n)"
        cypher_query = f"""
        {match}
        RETURN labels(n) AS labels, n.entity AS entity
        """
        with self._session() as session:
            records = session.execute_read(lambda tx: list(tx.run(cypher_query)))
            return [
                {"entity": record["entity"], "labels": record["labels"]}
                for record in records
                if record["entity"] is not None
            ]

    def update_relationship(
        self,
        entity1_type: str,
        entity1: str,
        entity2_type: str,
        entity2: str,
        relationship: str,
        strength: float,
    ):
        """
        Create or update a directional relationship between two nodes.

        The ``relationship`` property is part of the MERGE pattern, so two
        different relations between the same pair of entities are two distinct
        edges.  (Merging on the pattern alone and then setting the property
        afterwards silently overwrites whichever relation was stored first.)
        """
        cypher_query = f"""
        MERGE (a:{_safe_ident(BASE_LABEL)} {{entity: $entity1}})
        MERGE (b:{_safe_ident(BASE_LABEL)} {{entity: $entity2}})
        SET a:{_safe_ident(entity1_type)}, b:{_safe_ident(entity2_type)}
        MERGE (a)-[r:RELATED_TO {{relationship: $relationship}}]->(b)
        SET r.weight = $strength,
            r.strength = $strength
        RETURN a.entity AS from_node,
            b.entity AS to_node,
            r.relationship AS relationship,
            r.weight AS strength
        """
        with self._session() as session:
            record = session.execute_write(
                lambda tx: tx.run(
                    cypher_query,
                    entity1=entity1,
                    entity2=entity2,
                    relationship=relationship,
                    strength=strength,
                ).single()
            )
            return record.data() if record else None

    def get_relationship(
        self,
        entity1_type: str,
        entity1: str,
        entity2_type: str,
        entity2: str,
        relationship: str,
    ):
        """
        Get details for a specific relationship (with given 'relationship' property)
        between two nodes of specified types.
        """
        cypher_query = f"""
        MATCH (a:{_safe_ident(entity1_type)} {{entity: $entity1}})
              -[r:RELATED_TO {{relationship: $relationship}}]->
              (b:{_safe_ident(entity2_type)} {{entity: $entity2}})
        RETURN r.weight AS weight,
               r.weight AS strength,
               coalesce(r.observations, 0) AS observations,
               r.first_seen AS first_seen,
               r.last_seen AS last_seen
        """
        with self._session() as session:
            record = session.execute_read(
                lambda tx: tx.run(
                    cypher_query,
                    entity1=entity1,
                    entity2=entity2,
                    relationship=relationship,
                ).single()
            )
            return record.data() if record else None

    def relationship_exists(
        self,
        entity1_type: str,
        entity1: str,
        entity2_type: str,
        entity2: str,
        relationship: str,
    ) -> bool:
        """
        Check if a specific relationship (with given 'relationship' property)
        exists between two nodes of specified types.
        """
        cypher_query = f"""
        MATCH (a:{_safe_ident(entity1_type)} {{entity: $entity1}})
              -[r:RELATED_TO {{relationship: $relationship}}]->
              (b:{_safe_ident(entity2_type)} {{entity: $entity2}})
        RETURN COUNT(r) > 0 AS exists
        """
        with self._session() as session:
            record = session.execute_read(
                lambda tx: tx.run(
                    cypher_query,
                    entity1=entity1,
                    entity2=entity2,
                    relationship=relationship,
                ).single()
            )
            return record["exists"] if record else False

    def list_relationships(self, entity_type: str, entity: str):
        """
        List all outgoing and incoming relationships for a given node type and entity.
        Returns both connected node labels and relationship details.
        """
        cypher_query = f"""
        MATCH (n:{_safe_ident(entity_type)} {{entity: $entity}})-[r:RELATED_TO]-(m)
        RETURN
            labels(m) AS connected_labels,
            m.entity AS connected_node,
            r.relationship AS relationship,
            r.weight AS strength,
            coalesce(r.observations, 0) AS observations
        ORDER BY r.weight DESC
        """
        with self._session() as session:
            records = session.execute_read(lambda tx: list(tx.run(cypher_query, entity=entity)))
            return [
                {
                    "connected_node": record["connected_node"],
                    "connected_labels": record["connected_labels"],
                    "relationship": record["relationship"],
                    "strength": record["strength"],
                    "observations": record["observations"],
                }
                for record in records
                if record["connected_node"] is not None
            ]

    def top_edges(self, limit: int = 20, *, rel_type: str = "RELATED_TO"):
        """Heaviest edges in the graph - a quick sanity check after a build."""
        cypher_query = f"""
        MATCH (a)-[r:{_safe_ident(rel_type)}]->(b)
        RETURN a.entity AS from_entity,
               r.relationship AS relationship,
               b.entity AS to_entity,
               r.weight AS weight,
               coalesce(r.observations, 0) AS observations
        ORDER BY r.weight DESC, observations DESC
        LIMIT $limit
        """
        with self._session() as session:
            records = session.execute_read(lambda tx: list(tx.run(cypher_query, limit=limit)))
            return [record.data() for record in records]

    def counts(self) -> dict[str, int]:
        """Node and relationship totals."""
        with self._session() as session:
            record = session.execute_read(
                lambda tx: tx.run(
                    "MATCH (n) WITH count(n) AS nodes "
                    "OPTIONAL MATCH ()-[r]->() "
                    "RETURN nodes, count(r) AS relationships"
                ).single()
            )
            return record.data() if record else {"nodes": 0, "relationships": 0}

    def clear(self):
        """Remove all nodes and relationships."""
        with self._session() as session:
            session.execute_write(lambda tx: tx.run("MATCH (n) DETACH DELETE n").consume())
