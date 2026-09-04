"""Query strategy for the RP1 graph — a different shape of KG, needing a different method.

The RP1 graph (21 entities, 31 triples, 27 predicates) differs from the APP graph in
every way that matters to retrieval:

  * It is tiny. Entities with descriptions plus triples with predicate definitions come
    to ~2,200 tokens — less than the APP arm's *budget for a subgraph*. Hop-limited
    expansion is therefore the wrong frame: nothing needs to be left out for size.
  * Its predicate vocabulary is open. 23 of 27 predicates are used exactly once, so
    filtering or prioritising by relationship type is meaningless.
  * It carries natural-language payload the APP graph does not: every entity has a
    `description`, every edge a `pred_description`. That prose, not the topology, is the
    informative content.
  * It has no provenance. Nothing can be cited to a provision, so its statements are
    background understanding only.
  * It is hub-and-spoke: `personal information` alone holds 18 of 62 edge endpoints, so
    proximity-based ranking returns almost everything, undifferentiated.

So this strategy SELECTS AND ORDERS rather than retrieves. Everything is eligible; what
varies is emphasis, and the ordering is built for a legal/privacy reading (see
`order_for_legal_context`).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .config import Config
from .neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)

NODE_LABEL = "RP1Entity"

# Predicates carrying legal force. Compliance test cases are derived from modality --
# who must, must not, or may do what -- so these are surfaced ahead of mere association.
DEONTIC_RE = re.compile(
    r"\b(must|shall|require[sd]?|oblig|prohibit|forbid|permit|allow|entitl|right|"
    r"subject to|compl(y|ies|iance)|govern|protect|restrict|limit|authoris|authoriz)\b",
    re.I)

# Entity roles, read off the free-text `types` field. A compliance test needs to know
# who the actor is, what data is acted on, and which instrument imposes the duty.
ROLE_PATTERNS = [
    ("Regulated party", re.compile(r"organi[sz]ation|entity|business|company|agency|actor|person", re.I)),
    ("Information type", re.compile(r"\bdata\b|information|identifier|record|content", re.I)),
    ("Legal instrument", re.compile(r"law|legal|regulation|framework|principle|act\b|statute", re.I)),
    ("Process or activity", re.compile(r"process|activity|practice|action|procedure|communication|method", re.I)),
]


@dataclass
class RP1Node:
    key: str
    rp1_id: int
    name: str
    description: str = ""
    types: List[str] = field(default_factory=list)

    def role(self) -> str:
        blob = " ".join(self.types)
        for role, pattern in ROLE_PATTERNS:
            if pattern.search(blob):
                return role
        return "Other concept"


@dataclass
class RP1Edge:
    subject_key: str
    subject_name: str
    predicate: str
    predicate_description: str
    object_key: str
    object_name: str

    def is_deontic(self) -> bool:
        return bool(DEONTIC_RE.search(self.predicate))

    def pair(self) -> frozenset:
        return frozenset((self.subject_key, self.object_key))


@dataclass
class RP1Context:
    text: str = ""
    edges_included: int = 0
    edges_collapsed: int = 0
    entities_included: int = 0
    seeds_matched: List[str] = field(default_factory=list)
    token_estimate: int = 0

    def as_dict(self) -> dict:
        return {
            "edges_included": self.edges_included,
            "edges_collapsed_as_inverse": self.edges_collapsed,
            "entities_included": self.entities_included,
            "seeds_matched": self.seeds_matched,
            "token_estimate": self.token_estimate,
        }


def load_graph(client: Neo4jClient) -> Tuple[Dict[str, RP1Node], List[RP1Edge]]:
    """Two queries pull the whole graph. At this size there is nothing to paginate."""
    nodes = {}
    for row in client.run(
            "MATCH (n:`%s`) RETURN n.key AS key, n.rp1_id AS rp1_id, n.name AS name, "
            "n.description AS description, n.types AS types" % NODE_LABEL):
        nodes[row["key"]] = RP1Node(
            key=row["key"], rp1_id=row["rp1_id"], name=row["name"] or row["key"],
            description=row["description"] or "", types=list(row["types"] or []))

    edges = [
        RP1Edge(subject_key=r["sk"], subject_name=r["sn"], predicate=r["p"] or "",
                predicate_description=r["pd"] or "", object_key=r["ok"], object_name=r["on"])
        for r in client.run(
            "MATCH (a:`{lab}`)-[r]->(b:`{lab}`) "
            "RETURN a.key AS sk, a.name AS sn, r.pred_label AS p, "
            "r.pred_description AS pd, b.key AS ok, b.name AS on".format(lab=NODE_LABEL))
    ]
    logger.info("RP1 graph loaded: %d entities, %d edges", len(nodes), len(edges))
    return nodes, edges


def collapse_inverse_pairs(edges: List[RP1Edge]) -> Tuple[List[RP1Edge], int]:
    """Drop the weaker of two edges that restate one fact in both directions.

    The extraction was not deduplicated, so pairs like 'requires compliance from' /
    'must comply with' and 'includes' / 'is a subset of' both appear. Presenting both
    spends context on one fact and invites the reader to treat them as two.

    Where a pair differs in force, the deontic edge is kept: 'must comply with' states
    an obligation, 'requires compliance from' merely restates it from the other side.
    """
    by_pair: Dict[frozenset, List[RP1Edge]] = {}
    for edge in edges:
        by_pair.setdefault(edge.pair(), []).append(edge)

    kept, collapsed = [], 0
    for group in by_pair.values():
        if len(group) == 1:
            kept.append(group[0])
            continue
        deontic = [e for e in group if e.is_deontic()]
        chosen = deontic[0] if deontic else group[0]
        kept.append(chosen)
        collapsed += len(group) - 1
    return kept, collapsed


def match_seeds(nodes: Dict[str, RP1Node], section_text: str) -> Set[str]:
    """Which entities the target section actually mentions.

    With 21 nodes this is used for EMPHASIS, not filtering -- everything is included
    regardless. Matching on name and on each free-text type gives a cheap relevance
    signal without an LLM call.
    """
    lowered = section_text.lower()
    matched = set()
    for key, node in nodes.items():
        candidates = [node.name] + node.types
        if any(c and c.lower() in lowered for c in candidates):
            matched.add(key)
    return matched


def order_for_legal_context(edges: List[RP1Edge], seeds: Set[str]) -> List[RP1Edge]:
    """Order edges the way a compliance reader needs them.

    1. Deontic before associative. A test case is derived from an obligation, a
       prohibition or a permission; 'personal information -- related to -- privacy' is
       background at best.
    2. Edges touching an entity named in the target section before those that do not.
    3. Stable alphabetical thereafter, so runs are reproducible.

    Deliberately NOT ordered by degree: the hub (`personal information`, 18 of 62
    endpoints) would dominate, and its edges are the most generic in the graph.
    """
    def key(edge: RP1Edge):
        touches_seed = edge.subject_key in seeds or edge.object_key in seeds
        return (0 if edge.is_deontic() else 1,
                0 if touches_seed else 1,
                edge.subject_name.lower(), edge.predicate.lower())
    return sorted(edges, key=key)


def serialise(nodes: Dict[str, RP1Node], edges: List[RP1Edge], seeds: Set[str],
              include_predicate_definitions: bool = True) -> str:
    """Render the graph as prose for the prompt.

    Entities come first with their definitions, grouped by role. Legal terms of art are
    unusable without them, and definitional closure is why isolated entities are kept:
    an entity with no edges may still be the term the provision turns on.
    """
    lines = [
        "This background knowledge graph was built from a separate analysis of the "
        "Australian Privacy Principles. It records concepts and how they relate.",
        "",
        "IMPORTANT: it carries NO provision references and NO source text. Nothing in it "
        "can be cited, and no test case should be derived from it directly. Use it only "
        "to understand what the terms in the target section mean and how they connect.",
        "",
        "CONCEPTS AND THEIR MEANINGS",
        "",
    ]

    by_role: Dict[str, List[RP1Node]] = {}
    for node in nodes.values():
        by_role.setdefault(node.role(), []).append(node)

    for role in ("Regulated party", "Information type", "Legal instrument",
                 "Process or activity", "Other concept"):
        group = sorted(by_role.get(role, []), key=lambda n: n.name.lower())
        if not group:
            continue
        lines.append("%s:" % role)
        for node in group:
            mark = " *" if node.key in seeds else ""
            lines.append("  - %s%s: %s" % (node.name, mark, node.description))
        lines.append("")

    lines += ["(* marks a concept named in the target section.)", "",
              "RELATIONSHIPS EXPRESSING OBLIGATION, RIGHT OR PERMISSION", ""]
    deontic = [e for e in edges if e.is_deontic()]
    associative = [e for e in edges if not e.is_deontic()]

    for edge in deontic:
        lines.append("  - %s — %s — %s" % (edge.subject_name, edge.predicate, edge.object_name))
        if include_predicate_definitions and edge.predicate_description:
            lines.append("      (%s: %s)" % (edge.predicate, edge.predicate_description.strip()))
    if not deontic:
        lines.append("  (none)")

    lines += ["", "OTHER RELATIONSHIPS (association only, no legal force)", ""]
    for edge in associative:
        lines.append("  - %s — %s — %s" % (edge.subject_name, edge.predicate, edge.object_name))

    return "\n".join(lines).rstrip() + "\n"


def build_context(client: Neo4jClient, section_text: str, config: Config) -> RP1Context:
    """Entry point: whole graph, deduplicated, ordered for a legal reading."""
    from .serialisation import estimate_tokens

    nodes, edges = load_graph(client)
    if not nodes:
        from .retrieval import RetrievalError
        raise RetrievalError(
            "The RP1 graph is empty: no :%s nodes found. Load it with "
            "ResearchPaper1/load_rp1_kg.py before using --context-mode rp1." % NODE_LABEL)

    edges, collapsed = collapse_inverse_pairs(edges)
    seeds = match_seeds(nodes, section_text)
    edges = order_for_legal_context(edges, seeds)

    text = serialise(nodes, edges, seeds)
    tokens, _method = estimate_tokens(text, config.llm_model)

    logger.info("RP1 context: %d entities, %d edges (%d collapsed as inverse), "
                "%d concept(s) named in the section, %d tokens",
                len(nodes), len(edges), collapsed, len(seeds), tokens)

    return RP1Context(
        text=text, edges_included=len(edges), edges_collapsed=collapsed,
        entities_included=len(nodes),
        seeds_matched=sorted(nodes[k].name for k in seeds),
        token_estimate=tokens)
