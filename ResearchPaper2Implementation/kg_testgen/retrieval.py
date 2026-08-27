"""Subgraph retrieval: expand outward from seeds under hard, config-driven caps.

All Cypher is parameterised. The only value interpolated into a query string is the node
label, which is validated against live schema introspection before any query runs
(Neo4jClient._validate_label) because Cypher cannot parameterise a label.

Hop depth is asymmetric by seed kind: provision seeds get a deeper budget than entity
seeds. Measured on this graph, a provision seed reaches 5-12 nodes at depth 2 while an
entity seed reaches 105-150, so a single global depth serves neither well.

Self-asserted triples -- those whose `provisions` names the input subclause -- are
deliberately NOT filtered here. The traversal must be free to pass through them or a
provision seed is severed at hop 1 and contributes nothing. They are dropped later, at
serialisation, so the LLM never sees them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .config import Config
from .neo4j_client import Neo4jClient
from .seeding import PROVISION_SEED, Seed, SeedingResult

logger = logging.getLogger(__name__)


class RetrievalError(RuntimeError):
    """Retrieval produced nothing usable. Fatal unless --allow-unaugmented."""


@dataclass
class RetrievedTriple:
    subject_key: str
    subject_name: str
    rel_type: str
    relation: str
    object_key: str
    object_name: str
    weight: int
    provisions: str
    hop: int
    seed_key: str

    def identity(self) -> Tuple[str, str, str]:
        return (self.subject_key, self.rel_type, self.object_key)

    def as_dict(self) -> dict:
        return {
            "subject_key": self.subject_key, "subject_name": self.subject_name,
            "rel_type": self.rel_type, "relation": self.relation,
            "object_key": self.object_key, "object_name": self.object_name,
            "weight": self.weight, "provisions": self.provisions,
            "hop": self.hop, "seed_key": self.seed_key,
        }


@dataclass
class RetrievalResult:
    triples: List[RetrievedTriple] = field(default_factory=list)
    seed_to_seed: List[RetrievedTriple] = field(default_factory=list)
    node_degrees: Dict[str, int] = field(default_factory=dict)
    truncated_at_cap: bool = False

    def all_triples(self) -> List[RetrievedTriple]:
        return self.triples + self.seed_to_seed


# --- Extension points (deliberately unimplemented) ---------------------------------

def expand_with_asymmetric_depth_by_relationship_type(*_args, **_kwargs):
    """EXTENSION POINT -- not implemented.

    Different hop budgets per relationship type (e.g. follow HAS_EXCEPTION further than
    RELATES_TO). Depth is currently asymmetric by *seed kind*, not relationship type.
    Meaningful prioritisation needs deontic typing the schema does not yet carry.
    """
    raise NotImplementedError("Asymmetric depth by relationship type is not implemented.")


def filter_by_relationship_priority(*_args, **_kwargs):
    """EXTENSION POINT -- not implemented.

    Prioritise or exclude relationship types during expansion. Requires a defensible
    ordering over the 75 relationship types, which needs schema work not yet done.
    """
    raise NotImplementedError("Relationship-type prioritisation is not implemented.")


def filter_by_temporal_validity(*_args, **_kwargs):
    """EXTENSION POINT -- not implemented.

    Restrict retrieval to provisions in force at a given date. The graph stores no
    commencement or repeal dates.
    """
    raise NotImplementedError("Temporal validity filtering is not implemented.")


# --- Retrieval ---------------------------------------------------------------------

_NEIGHBOURHOOD = """
MATCH path = (seed:`{label}` {{key: $seed_key}})-[*1..{depth}]-(other:`{label}`)
WITH relationships(path) AS rels, length(path) AS hop
UNWIND range(0, size(rels) - 1) AS idx
WITH rels[idx] AS rel, idx + 1 AS rel_hop
WITH DISTINCT rel, min(rel_hop) AS hop
WITH startNode(rel) AS a, endNode(rel) AS b, rel, hop
RETURN a.key AS subject_key, a.name AS subject_name,
       type(rel) AS rel_type, rel.relation AS relation,
       b.key AS object_key, b.name AS object_name,
       coalesce(rel.weight, 1) AS weight,
       coalesce(rel.provisions, '') AS provisions,
       hop AS hop
ORDER BY hop ASC, weight DESC
LIMIT $limit
"""

_SEED_TO_SEED = """
MATCH (a:`{label}`)-[rel]-(b:`{label}`)
WHERE a.key IN $seed_keys AND b.key IN $seed_keys AND a.key <> b.key
RETURN DISTINCT startNode(rel).key AS subject_key, startNode(rel).name AS subject_name,
       type(rel) AS rel_type, rel.relation AS relation,
       endNode(rel).key AS object_key, endNode(rel).name AS object_name,
       coalesce(rel.weight, 1) AS weight,
       coalesce(rel.provisions, '') AS provisions
"""

_DEGREES = """
MATCH (n:`{label}`)
WHERE n.key IN $keys
RETURN n.key AS key, COUNT {{ (n)--() }} AS degree
"""


def _depth_for(seed: Seed, config: Config) -> int:
    return (config.provision_hop_depth if seed.seed_kind == PROVISION_SEED
            else config.entity_hop_depth)


def retrieve(seeding: SeedingResult, client: Neo4jClient, config: Config) -> RetrievalResult:
    result = RetrievalResult()
    seen: Set[Tuple[str, str, str]] = set()

    for seed in seeding.seeds:
        depth = _depth_for(seed, config)
        rows = client.run(
            _NEIGHBOURHOOD.format(label=config.node_label, depth=depth),
            seed_key=seed.key, limit=config.max_relationships_per_node)
        kept = 0
        for row in rows:
            triple = RetrievedTriple(seed_key=seed.key, **row)
            if triple.identity() in seen:
                continue
            seen.add(triple.identity())
            result.triples.append(triple)
            kept += 1
        logger.info("  seed %-38s depth %d -> %3d relationship(s), %d new",
                    seed.key[:38], depth, len(rows), kept)

    # Relationships directly between seeds, in addition to the neighbourhood expansion.
    seed_keys = [s.key for s in seeding.seeds]
    if len(seed_keys) > 1:
        for row in client.run(_SEED_TO_SEED.format(label=config.node_label),
                              seed_keys=seed_keys):
            triple = RetrievedTriple(hop=0, seed_key="<seed-to-seed>", **row)
            if triple.identity() in seen:
                continue
            seen.add(triple.identity())
            result.seed_to_seed.append(triple)
        logger.info("  seed-to-seed -> %d additional relationship(s)",
                    len(result.seed_to_seed))

    # Degrees for the ranking tiebreaker, computed in Cypher rather than GDS.
    keys = {t.subject_key for t in result.all_triples()} | {t.object_key for t in result.all_triples()}
    if keys:
        for row in client.run(_DEGREES.format(label=config.node_label), keys=sorted(keys)):
            result.node_degrees[row["key"]] = row["degree"]

    total = len(result.all_triples())
    logger.info("Retrieval: %d relationship(s) across %d distinct node(s)", total, len(keys))

    if total == 0:
        raise RetrievalError(
            "Retrieval returned zero relationships from %d seed(s): %s\n"
            "The pipeline will not silently fall through to an unaugmented LLM call. "
            "Re-run with --allow-unaugmented to proceed anyway, or raise "
            "--entity-hop-depth / --provision-hop-depth."
            % (len(seeding.seeds), ", ".join(seed_keys)))

    return result
