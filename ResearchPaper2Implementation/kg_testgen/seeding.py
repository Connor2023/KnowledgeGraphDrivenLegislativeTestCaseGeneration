"""Seeding: map the input section's terms onto graph entry points.

Terms come from the vendored EDC ``EntityExtractor``, so the query vocabulary is
produced by the same extractor that built the graph. Matching then runs in three tiers --
exact, normalised, fuzzy -- against the ``key`` property, which ``build_graph.normalise``
produced during construction.

When ``provision_anchor`` is on, the input's own subclause node is added as a seed. Note
that :Provision nodes are near-leaves in this graph (59 of 77 have degree 1), which is
why they are given a deeper hop budget than entity seeds; see Config.
"""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import edc_bridge
from .config import Config
from .neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)

ENTITY_SEED = "entity"
PROVISION_SEED = "provision"


class SeedingError(RuntimeError):
    """No usable entry point into the graph. Fatal unless --allow-unaugmented."""


@dataclass
class Seed:
    key: str
    name: str
    node_type: str
    source_term: str
    match_tier: str            # exact | normalised | fuzzy | provision
    seed_kind: str             # entity | provision
    score: float = 1.0

    def as_dict(self) -> dict:
        return {
            "key": self.key, "name": self.name, "node_type": self.node_type,
            "source_term": self.source_term, "match_tier": self.match_tier,
            "seed_kind": self.seed_kind, "score": round(self.score, 4),
        }


@dataclass
class SeedingResult:
    extracted_terms: List[str] = field(default_factory=list)
    seeds: List[Seed] = field(default_factory=list)
    unmatched_terms: List[str] = field(default_factory=list)
    provision_id: Optional[str] = None
    provision_matched: bool = False

    def as_dict(self) -> dict:
        return {
            "extracted_terms": self.extracted_terms,
            "seeds": [s.as_dict() for s in self.seeds],
            "unmatched_terms": self.unmatched_terms,
            "provision_id": self.provision_id,
            "provision_matched": self.provision_matched,
        }


def seed_by_vector_similarity(*_args, **_kwargs):
    """EXTENSION POINT -- not implemented.

    Embedding-based seeding for terms that match no node lexically. Requires node
    embeddings, which the graph does not have; generating them is out of POC scope.
    The instance does support vector indexes (probed at startup and recorded in the run
    metadata), so the remaining work is embedding generation plus an index build.
    """
    raise NotImplementedError(
        "Vector seeding is an unimplemented extension point: no node embeddings exist.")


def _load_node_index(client: Neo4jClient, config: Config) -> List[Dict[str, str]]:
    """Pull every candidate node once, so the three matching tiers run in memory.

    The graph is small (hundreds of nodes); a single scan beats one round trip per term.
    """
    rows = client.run(
        "MATCH (n:`%s`) RETURN n.key AS key, n.name AS name, n.type AS type"
        % config.node_label)
    return [r for r in rows if r.get("key")]


def _match_terms(terms: List[str], nodes: List[Dict[str, str]], config: Config):
    by_key = {n["key"]: n for n in nodes}
    by_name_lower = {}
    for n in nodes:
        if n.get("name"):
            by_name_lower.setdefault(n["name"].lower(), n)

    seeds: List[Seed] = []
    unmatched: List[str] = []
    claimed = set()

    for term in terms:
        node, tier, score = None, None, 1.0

        # Tier 1: exact match on the stored display name.
        candidate = by_name_lower.get(term.strip().lower())
        if candidate:
            node, tier = candidate, "exact"

        # Tier 2: normalised match, using the very function that produced `key`.
        if node is None:
            norm_key, _ = edc_bridge.normalise_mention(term)
            candidate = by_key.get(norm_key)
            if candidate:
                node, tier = candidate, "normalised"

        # Tier 3: fuzzy, above the configured threshold.
        if node is None:
            norm_key, _ = edc_bridge.normalise_mention(term)
            best, best_ratio = None, 0.0
            for key in by_key:
                ratio = difflib.SequenceMatcher(None, norm_key, key).ratio()
                if ratio > best_ratio:
                    best, best_ratio = key, ratio
            if best is not None and best_ratio >= config.fuzzy_threshold:
                node, tier, score = by_key[best], "fuzzy", best_ratio

        if node is None:
            unmatched.append(term)
            logger.info("  term %-42s -> NO MATCH", term[:42])
            continue
        if node["key"] in claimed:
            logger.info("  term %-42s -> %s (already seeded)", term[:42], node["key"])
            continue

        claimed.add(node["key"])
        seeds.append(Seed(key=node["key"], name=node.get("name") or node["key"],
                          node_type=node.get("type") or "", source_term=term,
                          match_tier=tier, seed_kind=ENTITY_SEED, score=score))
        logger.info("  term %-42s -> %-38s [%s%s]", term[:42], node["key"][:38], tier,
                    "" if tier != "fuzzy" else " %.2f" % score)

    return seeds, unmatched


def seed(text: str, client: Neo4jClient, config: Config) -> SeedingResult:
    result = SeedingResult()

    logger.info("Extracting candidate terms with the EDC entity extractor (1 LLM call)...")
    result.extracted_terms = edc_bridge.extract_entities(text, config.llm_model)
    logger.info("Extracted %d candidate term(s): %s",
                len(result.extracted_terms), result.extracted_terms)

    nodes = _load_node_index(client, config)
    logger.info("Matching against %d :%s nodes", len(nodes), config.node_label)

    result.seeds, result.unmatched_terms = _match_terms(result.extracted_terms, nodes, config)

    if config.provision_anchor:
        provision_id = config.provision_id or edc_bridge.detect_provision_id(text)
        result.provision_id = provision_id
        if provision_id:
            key = edc_bridge.provision_key(provision_id)
            match = next((n for n in nodes if n["key"] == key), None)
            if match:
                already = any(s.key == key for s in result.seeds)
                if not already:
                    result.seeds.append(Seed(
                        key=key, name=match.get("name") or key,
                        node_type=match.get("type") or "", source_term=provision_id,
                        match_tier="provision", seed_kind=PROVISION_SEED))
                else:
                    for s in result.seeds:
                        if s.key == key:
                            s.seed_kind = PROVISION_SEED
                result.provision_matched = True
                logger.info("  provision anchor %-33s -> %s", provision_id, key)
            else:
                logger.warning("  provision anchor %s -> NO MATCHING NODE (key %r)",
                               provision_id, key)
        else:
            logger.warning("  provision anchor enabled but no subclause id found in the "
                           "input; pass --provision-id to set it explicitly")

    logger.info("Seeding: %d seed(s) matched, %d term(s) unmatched",
                len(result.seeds), len(result.unmatched_terms))

    if not result.seeds:
        raise SeedingError(
            "Zero seed matches: none of the %d extracted term(s) matched a node in the "
            "graph.\nExtracted: %s\nThe pipeline will not silently fall through to an "
            "unaugmented LLM call. Re-run with --allow-unaugmented to proceed anyway, "
            "or lower --fuzzy-threshold (currently %.2f)."
            % (len(result.extracted_terms), result.extracted_terms, config.fuzzy_threshold))

    return result
