"""Ranking and pruning.

POC ordering: hop distance from a seed, then relationship weight, then node degree.
`weight` records how many source clauses assert a relation, so it is a relevance signal
already computed during construction and stored on the edge. Degree is computed in
Cypher (see retrieval._DEGREES); GDS is not available on the free tier and is not used.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

from kg_testgen.config import Config
from .retrieval import RetrievalResult, RetrievedTriple

logger = logging.getLogger(__name__)


@dataclass
class RankingResult:
    kept: List[RetrievedTriple] = field(default_factory=list)
    pruned_count: int = 0
    pruned_by: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"kept": len(self.kept), "pruned": self.pruned_count,
                "pruned_by": self.pruned_by}


def rank_by_embedding_similarity(*_args, **_kwargs):
    """EXTENSION POINT -- not implemented.

    Rank retrieved elements by embedding similarity to the input section. Needs node or
    edge embeddings, which do not exist; see seeding.seed_by_vector_similarity.
    """
    raise NotImplementedError("Embedding-similarity ranking is not implemented.")


def rank_by_centrality(*_args, **_kwargs):
    """EXTENSION POINT -- not implemented.

    Centrality-based ranking (PageRank, betweenness). These are GDS algorithms and GDS
    is unavailable on AuraDB free tier; a Cypher reimplementation is out of POC scope.
    """
    raise NotImplementedError("Centrality-based ranking is not implemented.")


def _sort_key(triple: RetrievedTriple, degrees, ranking_key: str):
    degree = max(degrees.get(triple.subject_key, 0), degrees.get(triple.object_key, 0))
    if ranking_key == "hop_degree":
        return (triple.hop, -degree)
    return (triple.hop, -triple.weight, -degree)


def rank_and_prune(retrieval: RetrievalResult, config: Config) -> RankingResult:
    result = RankingResult()
    triples = sorted(
        retrieval.all_triples(),
        key=lambda t: _sort_key(t, retrieval.node_degrees, config.ranking_key))

    kept: List[RetrievedTriple] = []
    nodes_seen = set()

    for triple in triples:
        if len(kept) >= config.max_relationships:
            result.pruned_by.append("max_relationships")
            break
        prospective = nodes_seen | {triple.subject_key, triple.object_key}
        if len(prospective) > config.max_nodes:
            result.pruned_by.append("max_nodes")
            continue
        nodes_seen = prospective
        kept.append(triple)

    result.kept = kept
    result.pruned_count = len(triples) - len(kept)
    result.pruned_by = sorted(set(result.pruned_by))

    logger.info("Ranking (%s): kept %d of %d relationship(s) over %d node(s)%s",
                config.ranking_key, len(kept), len(triples), len(nodes_seen),
                "" if not result.pruned_by else "; capped by " + ", ".join(result.pruned_by))
    return result
