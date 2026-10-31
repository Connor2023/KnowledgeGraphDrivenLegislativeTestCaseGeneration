"""
In-memory implementation of :class:`DatabaseAPI`.

Same semantics as the Neo4j backend for everything the ingestion path uses, so
augmentation strategies can be prototyped and tested without an Aura instance.
It cannot evaluate a strategy's Cypher expression, which it advertises via
``supports_cypher_augment = False``; :class:`KnowledgeGraph` then routes every
strategy down the Python path automatically.
"""

from __future__ import annotations

from typing import Any, Sequence

from graph_database import DatabaseAPI


class MemoryGDB(DatabaseAPI):
    supports_cypher_augment = False

    def __init__(self):
        self.nodes: dict[str, set[str]] = {}
        self.edges: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.running = False

    def start(self):
        self.running = True
        return True

    def shutdown(self):
        self.running = False
        return True

    def clear(self):
        self.nodes.clear()
        self.edges.clear()

    def ensure_schema(self, base_label: str = "Entity") -> None:
        pass

    def _touch(self, entity: str, *labels: str | None) -> None:
        current = self.nodes.setdefault(entity, {"Entity"})
        current.update(label for label in labels if label)

    def fetch_edges(self, keys: Sequence[tuple[str, str, str]], **_kwargs):
        return {
            tuple(key): dict(self.edges[tuple(key)])
            for key in keys
            if tuple(key) in self.edges
        }

    def upsert_edges(self, rows: Sequence[dict[str, Any]], *, from_label=None, to_label=None,
                     **_kwargs) -> dict[str, int]:
        created = 0
        for row in rows:
            key = (row["from_entity"], row["relationship"], row["to_entity"])
            self._touch(row["from_entity"], from_label)
            self._touch(row["to_entity"], to_label)
            edge = self.edges.get(key)
            if edge is None:
                created += 1
                edge = {"observations": 0, "first_seen": row["now"], "props": {}}
                self.edges[key] = edge
            edge["props"] = {**edge["props"], **row["props"]}
            edge["weight"] = row["props"]["weight"]
            edge["observations"] += row["observations"]
            edge["last_seen"] = row["now"]
            edge["props"].update(
                relationship=row["relationship"],
                observations=edge["observations"],
                first_seen=edge["first_seen"],
                last_seen=edge["last_seen"],
            )
        return {"written": len(rows), "created": created}

    def augment_edges(self, rows, *, first_expression, update_expression, **_kwargs):
        raise NotImplementedError(
            "MemoryGDB cannot evaluate Cypher expressions; construct the "
            "KnowledgeGraph with prefer_cypher=False (this happens automatically)."
        )

    def list_relationships(self, entity_type: str, entity: str):
        found = [
            {
                "connected_node": to_entity if from_entity == entity else from_entity,
                "connected_labels": sorted(
                    self.nodes.get(to_entity if from_entity == entity else from_entity, set())
                ),
                "relationship": relationship,
                "strength": edge["weight"],
                "observations": edge["observations"],
            }
            for (from_entity, relationship, to_entity), edge in self.edges.items()
            if entity in (from_entity, to_entity)
        ]
        return sorted(found, key=lambda item: item["strength"], reverse=True)

    def top_edges(self, limit: int = 20, **_kwargs):
        ranked = sorted(
            self.edges.items(),
            key=lambda item: (item[1]["weight"], item[1]["observations"]),
            reverse=True,
        )
        return [
            {
                "from_entity": from_entity,
                "relationship": relationship,
                "to_entity": to_entity,
                "weight": edge["weight"],
                "observations": edge["observations"],
            }
            for (from_entity, relationship, to_entity), edge in ranked[:limit]
        ]

    def counts(self) -> dict[str, int]:
        return {"nodes": len(self.nodes), "relationships": len(self.edges)}
