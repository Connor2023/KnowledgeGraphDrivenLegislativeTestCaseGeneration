"""Fetch statutory text for provisions the target clause depends on.

The knowledge graph stores relationships, not law. That is the gap the controlled
comparisons kept exposing: the arm holding the actual text of related provisions
outperformed both graph arms, and the scenarios that were never generated were the ones
whose primary rule lived in a clause the model could not see (subclause 2.2 disapplies
2.1, and 2.1 was unreachable).

Scope is the whole design. Including text for every provision touched by retrieval comes
to ~9,800 tokens on APP 6.1 -- 86% of the entire corpus -- so the graph arm would simply
become a worse full-corpus. Following REFERS_TO from the target clause instead pulls only
what the clause actually points at.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from kg_testgen.config import Config
from kg_testgen.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


@dataclass
class ProvisionText:
    key: str
    name: str
    text: str
    relation: str          # how it reached us: "cross-referenced" or "asserts-retrieved"

    def as_dict(self) -> dict:
        return {"key": self.key, "name": self.name, "relation": self.relation,
                "chars": len(self.text)}


@dataclass
class ProvisionTextResult:
    provisions: List[ProvisionText] = field(default_factory=list)
    scope: str = "none"
    token_estimate: int = 0
    skipped_no_text: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"scope": self.scope, "count": len(self.provisions),
                "token_estimate": self.token_estimate,
                "skipped_no_text": self.skipped_no_text,
                "provisions": [p.as_dict() for p in self.provisions]}


_CROSS_REFERENCED = """
MATCH (src:`{label}` {{key: $key}})-[:REFERS_TO]->(t:`{label}`)
WHERE t.text_raw IS NOT NULL OR t.text_normalised IS NOT NULL
RETURN t.key AS key, t.name AS name,
       t.text_raw AS text_raw, t.text_normalised AS text_normalised
"""

_BY_KEYS = """
MATCH (t:`{label}`)
WHERE t.key IN $keys AND (t.text_raw IS NOT NULL OR t.text_normalised IS NOT NULL)
RETURN t.key AS key, t.name AS name,
       t.text_raw AS text_raw, t.text_normalised AS text_normalised
"""


def _pick(row: Dict[str, str], variant: str) -> str:
    primary = "text_raw" if variant == "raw" else "text_normalised"
    fallback = "text_normalised" if variant == "raw" else "text_raw"
    return (row.get(primary) or row.get(fallback) or "").strip()


def fetch(client: Neo4jClient, config: Config, provision_key: Optional[str],
          retrieved_provisions: Optional[List[str]] = None) -> ProvisionTextResult:
    """Return the statutory text this run should carry, under the configured scope."""
    from .serialisation import estimate_tokens

    result = ProvisionTextResult(scope=config.provision_text_scope)
    if config.provision_text_scope == "none":
        return result

    rows: List[Dict[str, str]] = []
    if config.provision_text_scope == "cross-referenced":
        if not provision_key:
            logger.warning("provision_text_scope='cross-referenced' but the input's own "
                           "provision could not be identified; no text included")
            return result
        rows = client.run(_CROSS_REFERENCED.format(label=config.node_label),
                          key=provision_key)
        relation = "cross-referenced"
    else:
        keys = sorted({k for k in (retrieved_provisions or []) if k and k != provision_key})
        if keys:
            rows = client.run(_BY_KEYS.format(label=config.node_label), keys=keys)
        relation = "asserts-retrieved"

    for row in rows:
        text = _pick(row, config.provision_text_variant)
        if not text:
            result.skipped_no_text.append(row["key"])
            continue
        result.provisions.append(ProvisionText(
            key=row["key"], name=row.get("name") or row["key"],
            text=text, relation=relation))

    result.provisions.sort(key=lambda p: p.key)
    if result.provisions:
        result.token_estimate, _ = estimate_tokens(render(result), config.llm_model)

    logger.info("Provision text (%s): %d provision(s), %d tokens%s",
                config.provision_text_scope, len(result.provisions),
                result.token_estimate,
                "" if not result.skipped_no_text else
                " (%d had no stored text)" % len(result.skipped_no_text))
    return result


def render(result: ProvisionTextResult) -> str:
    """Render as its own labelled part of the context block.

    Kept separate from the triples: this is statutory text the target clause depends on,
    not an extracted relationship, and the distinction matters to how the model treats it.
    """
    if not result.provisions:
        return ""
    lines = [
        "PROVISIONS THIS SECTION DEPENDS ON",
        "",
        "The target section refers to the clauses below. Their text is reproduced so the "
        "conditions and exceptions it points at are visible. They are still NOT the "
        "target section -- write scenarios for the target section only, but use these to "
        "know what its cross-references actually say.",
        "",
    ]
    for p in result.provisions:
        lines += ["%s:" % p.name, "  %s" % p.text, ""]
    return "\n".join(lines).rstrip() + "\n"
