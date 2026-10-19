"""Serialise the retrieved subgraph into an LLM-readable context block.

This is where self-asserted triples are dropped. Retrieval deliberately traverses
through them -- a provision seed's only edge is usually its own BELONGS_TO_PRINCIPLE, so
filtering during the walk would sever the anchor at hop 1 and the seed would contribute
nothing. Filtering here keeps the walk intact while ensuring the LLM never reads a triple
that merely restates the target section.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from kg_testgen.config import Config
from .retrieval import RetrievedTriple
from .seeding import SeedingResult

logger = logging.getLogger(__name__)


@dataclass
class SerialisationResult:
    text: str = ""
    included: List[RetrievedTriple] = field(default_factory=list)
    excluded_self: List[RetrievedTriple] = field(default_factory=list)
    excluded_budget: List[RetrievedTriple] = field(default_factory=list)
    token_estimate: int = 0
    token_method: str = "heuristic"

    def as_dict(self) -> dict:
        return {
            "included_count": len(self.included),
            "excluded_self_provision_count": len(self.excluded_self),
            "excluded_budget_count": len(self.excluded_budget),
            "token_estimate": self.token_estimate,
            "token_method": self.token_method,
            "included": [t.as_dict() for t in self.included],
            "excluded_self_provision": [t.as_dict() for t in self.excluded_self],
        }


def serialise_as_json(*_args, **_kwargs):
    """EXTENSION POINT -- stubbed alternative serialisation format.

    Selected with --serialisation-format json. A structured rendering would let the LLM
    consume node types and edge properties directly rather than as flat prose.
    """
    raise NotImplementedError(
        "JSON serialisation is a stubbed extension point; use --serialisation-format triples.")


# Moved to kg_testgen.tokens when the spires arm needed it and this module became
# an evaluation arm. Re-exported so the callers here read unchanged.
from kg_testgen.tokens import estimate_tokens  # noqa: E402,F401


def _asserting_provisions(triple: RetrievedTriple) -> set:
    """The set of provisions that assert this triple, from the stored `provisions` string."""
    raw = (triple.provisions or "").strip()
    if not raw:
        return set()
    return {part.strip().lower() for part in raw.split(";") if part.strip()}


def _is_self_triple(triple: RetrievedTriple, provision_id: Optional[str], policy: str) -> bool:
    """Whether this triple merely restates the target section.

    Under 'sole', a triple counts as a restatement only when the input subclause is the
    single provision asserting it. A triple asserted by the input subclause AND several
    others is real cross-section context -- it shows the concept recurring elsewhere in
    the legislation -- so dropping it would discard exactly what the KG is here to add.
    """
    if policy == "none" or not provision_id:
        return False
    bare = provision_id.strip().lower().replace("subclause", "").strip()
    target = "subclause %s" % bare
    provisions = _asserting_provisions(triple)
    if target not in provisions:
        return False
    return True if policy == "any" else provisions == {target}


def _render(groups: Dict[str, List[RetrievedTriple]], total: int) -> str:
    lines = [
        "The following %d related statements were retrieved from the knowledge graph, "
        "grouped by the entity in the target section that led to them." % total,
        "",
    ]
    for seed_name in sorted(groups):
        triples = groups[seed_name]
        lines.append("Related to \"%s\" (%d statement%s):"
                     % (seed_name, len(triples), "" if len(triples) == 1 else "s"))
        for t in triples:
            provenance = (" [asserted by %s]" % t.provisions) if t.provisions else ""
            lines.append("  - %s — %s — %s%s"
                         % (t.subject_name, t.relation or t.rel_type, t.object_name, provenance))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def serialise(triples: List[RetrievedTriple], seeding: SeedingResult,
              config: Config) -> SerialisationResult:
    if config.serialisation_format == "json":
        serialise_as_json()

    result = SerialisationResult()

    working: List[RetrievedTriple] = []
    for triple in triples:
        if _is_self_triple(triple, seeding.provision_id, config.self_provision_policy):
            result.excluded_self.append(triple)
        else:
            working.append(triple)

    if result.excluded_self:
        logger.info("Excluded %d triple(s) restating the input subclause (%s, policy=%s) "
                    "so the context stays supplementary to the verbatim text",
                    len(result.excluded_self), seeding.provision_id,
                    config.self_provision_policy)

    seed_names = {s.key: s.name for s in seeding.seeds}

    # Fit to the token budget by dropping from the tail, which ranking has already
    # ordered least-relevant-last.
    included = list(working)
    while True:
        groups: Dict[str, List[RetrievedTriple]] = {}
        for t in included:
            groups.setdefault(seed_names.get(t.seed_key, t.seed_key), []).append(t)
        text = _render(groups, len(included))
        tokens, method = estimate_tokens(text, config.llm_model)
        if tokens <= config.context_token_budget or not included:
            result.text, result.token_estimate, result.token_method = text, tokens, method
            break
        result.excluded_budget.append(included.pop())

    result.included = included
    if result.excluded_budget:
        logger.info("Dropped %d triple(s) to fit the %d-token context budget",
                    len(result.excluded_budget), config.context_token_budget)
    logger.info("Serialised %d triple(s) into %d tokens (%s)",
                len(included), result.token_estimate, result.token_method)
    return result
