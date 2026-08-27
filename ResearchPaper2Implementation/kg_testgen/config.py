"""Configuration for the KG query + test-case generation pipeline.

Every tunable named in the requirements lives here so retrieval variations can be
compared without editing code. Secrets are never stored on the dataclass: they are read
from the environment at point of use (see `secrets_from_env`).
"""

from __future__ import annotations

import argparse
import dataclasses
import os
from dataclasses import dataclass, field
from typing import Optional

# Secrets are read from these environment variables only, never hardcoded.
ENV_NEO4J_URI = "NEO4J_URI"
ENV_NEO4J_USER = "NEO4J_USERNAME"
ENV_NEO4J_PASSWORD = "NEO4J_PASSWORD"
ENV_NEO4J_DATABASE = "NEO4J_DATABASE"
# The vendored EDC code hardcodes OPENAI_KEY; the conventional name is OPENAI_API_KEY.
# Both are accepted, and OPENAI_KEY is populated internally so EDC's client works.
ENV_LLM_KEY_PRIMARY = "OPENAI_API_KEY"
ENV_LLM_KEY_FALLBACK = "OPENAI_KEY"


class ConfigError(RuntimeError):
    """Raised for missing or contradictory configuration. Always fatal, never swallowed."""


@dataclass
class Config:
    # --- Seeding -----------------------------------------------------------------
    seeding_method: str = "llm"
    """'llm' uses the vendored EDC EntityExtractor. 'vector' is an unimplemented stub."""

    fuzzy_threshold: float = 0.85
    """Minimum similarity ratio for the fuzzy matching tier. 0-1."""

    provision_anchor: bool = True
    """Seed on the input's own :Provision node in addition to extracted entities."""

    provision_id: Optional[str] = None
    """Explicit subclause id, e.g. '6.1'. Auto-detected from the input text if omitted."""

    # --- Retrieval ---------------------------------------------------------------
    entity_hop_depth: int = 2
    provision_hop_depth: int = 3
    """Asymmetric by seed type. Provision nodes are near-leaves -- 59 of 77 have degree
    1 -- so they need an extra hop to reach anything, while entity seeds already touch
    28-40% of the graph at depth 2."""

    max_nodes: int = 120
    max_relationships: int = 200
    max_relationships_per_node: int = 25

    node_label: str = "AppNode"
    """Validated against live schema introspection rather than trusted blindly."""

    # --- Ranking -----------------------------------------------------------------
    ranking_key: str = "hop_weight_degree"
    """'hop_weight_degree' (POC) or 'hop_degree'. Embedding and centrality are stubs."""

    # --- Serialisation -----------------------------------------------------------
    serialisation_format: str = "triples"
    """'triples' (default) or 'json' (stubbed)."""

    self_provision_policy: str = "sole"
    """How to drop triples asserted by the input subclause. Applied at serialisation,
    NOT at traversal: the walk must be free to pass through those edges or a provision
    seed is severed at hop 1 and contributes nothing.

    'sole' (default) drops a triple only when the input subclause is its ONLY asserting
    provision, i.e. it genuinely just restates the verbatim text. 'any' drops a triple if
    the input subclause appears anywhere in its provision list -- stricter, but it also
    discards facts asserted by many provisions, which are the strongest cross-section
    context available. 'none' disables the filter."""

    context_token_budget: int = 3000

    # --- LLM ---------------------------------------------------------------------
    llm_model: str = "gpt-4o-mini"
    temperature: float = 0.0
    max_output_tokens: int = 4000

    # --- Behaviour ---------------------------------------------------------------
    allow_unaugmented: bool = False
    """When false (default), zero seed matches or empty retrieval is fatal. The
    requirements forbid silently falling through to an unaugmented LLM call; this flag
    makes the fallthrough explicit and deliberate, and is recorded in the run record."""

    output_dir: Optional[str] = None
    """Defaults to a timestamped run folder under ./runs."""

    log_level: str = "INFO"

    def validate(self) -> None:
        if self.seeding_method not in ("llm", "vector"):
            raise ConfigError("seeding_method must be 'llm' or 'vector' (got %r)" % self.seeding_method)
        if self.seeding_method == "vector":
            raise ConfigError(
                "Vector seeding is an unimplemented extension point: node embeddings do "
                "not exist in the graph. See seeding.seed_by_vector_similarity.")
        if self.serialisation_format not in ("triples", "json"):
            raise ConfigError("serialisation_format must be 'triples' or 'json'")
        if self.self_provision_policy not in ("sole", "any", "none"):
            raise ConfigError("self_provision_policy must be 'sole', 'any' or 'none'")
        if self.ranking_key not in ("hop_weight_degree", "hop_degree"):
            raise ConfigError("ranking_key must be 'hop_weight_degree' or 'hop_degree'")
        if not 0.0 <= self.fuzzy_threshold <= 1.0:
            raise ConfigError("fuzzy_threshold must be between 0 and 1")
        for name in ("entity_hop_depth", "provision_hop_depth"):
            if getattr(self, name) < 1:
                raise ConfigError("%s must be >= 1" % name)
        for name in ("max_nodes", "max_relationships", "max_relationships_per_node",
                     "context_token_budget"):
            if getattr(self, name) < 1:
                raise ConfigError("%s must be >= 1" % name)

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass
class Secrets:
    """Held apart from Config so the run record can serialise Config safely."""
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_database: str
    llm_api_key: str


def secrets_from_env() -> Secrets:
    """Read every secret from the environment. Fails loudly and names what is missing."""
    missing = []
    uri = os.environ.get(ENV_NEO4J_URI)
    user = os.environ.get(ENV_NEO4J_USER)
    password = os.environ.get(ENV_NEO4J_PASSWORD)
    for name, value in ((ENV_NEO4J_URI, uri), (ENV_NEO4J_USER, user), (ENV_NEO4J_PASSWORD, password)):
        if not value:
            missing.append(name)

    llm_key = os.environ.get(ENV_LLM_KEY_PRIMARY) or os.environ.get(ENV_LLM_KEY_FALLBACK)
    if not llm_key:
        missing.append("%s (or %s)" % (ENV_LLM_KEY_PRIMARY, ENV_LLM_KEY_FALLBACK))

    if missing:
        raise ConfigError(
            "Missing required environment variables: %s\n"
            "Copy .env.example to .env and fill it in, or export them in your shell."
            % ", ".join(missing))

    # The vendored EDC client reads OPENAI_KEY directly; populate it so that code path
    # works regardless of which name the user set.
    os.environ[ENV_LLM_KEY_FALLBACK] = llm_key

    return Secrets(
        neo4j_uri=uri,
        neo4j_user=user,
        neo4j_password=password,
        neo4j_database=os.environ.get(ENV_NEO4J_DATABASE) or "neo4j",
        llm_api_key=llm_key,
    )


def add_cli_arguments(parser: argparse.ArgumentParser) -> None:
    """Expose every tunable as a CLI override. Defaults are None so unset flags do not
    clobber the dataclass defaults."""
    g = parser.add_argument_group("retrieval")
    g.add_argument("--entity-hop-depth", type=int)
    g.add_argument("--provision-hop-depth", type=int)
    g.add_argument("--max-nodes", type=int)
    g.add_argument("--max-relationships", type=int)
    g.add_argument("--max-relationships-per-node", type=int)
    g.add_argument("--node-label")
    g.add_argument("--provision-anchor", dest="provision_anchor", action="store_true", default=None)
    g.add_argument("--no-provision-anchor", dest="provision_anchor", action="store_false", default=None)
    g.add_argument("--provision-id", help="Subclause id, e.g. 6.1. Auto-detected if omitted.")

    g = parser.add_argument_group("seeding")
    g.add_argument("--seeding-method", choices=["llm", "vector"])
    g.add_argument("--fuzzy-threshold", type=float)

    g = parser.add_argument_group("ranking and serialisation")
    g.add_argument("--ranking-key", choices=["hop_weight_degree", "hop_degree"])
    g.add_argument("--serialisation-format", choices=["triples", "json"])
    g.add_argument("--context-token-budget", type=int)
    g.add_argument("--self-provision-policy", choices=["sole", "any", "none"],
                   help="Which triples asserted by the input subclause to drop from the "
                        "context. 'sole' (default) drops only those the input subclause "
                        "alone asserts; 'any' drops any that mention it; 'none' keeps all.")

    g = parser.add_argument_group("llm")
    g.add_argument("--llm-model")
    g.add_argument("--temperature", type=float)
    g.add_argument("--max-output-tokens", type=int)

    g = parser.add_argument_group("behaviour")
    g.add_argument("--allow-unaugmented", action="store_true", default=None,
                   help="Proceed with an unaugmented LLM call when retrieval yields "
                        "nothing. Off by default: the pipeline fails loudly instead.")
    g.add_argument("--output-dir")
    g.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"])


def config_from_args(args: argparse.Namespace) -> Config:
    """Build a Config from defaults, overridden by any flag the user actually passed."""
    overrides = {
        f.name: getattr(args, f.name)
        for f in dataclasses.fields(Config)
        if getattr(args, f.name, None) is not None
    }
    cfg = Config(**overrides)
    cfg.validate()
    return cfg
