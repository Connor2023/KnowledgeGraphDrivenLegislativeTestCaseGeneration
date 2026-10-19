"""Build each comparison arm's block 3, and say what header it should carry.

This is the code that used to sit inline in `kg_testgen.pipeline.run`. Lifting it out is
what lets the pipeline ship one context mode; the behaviour is unchanged, and it is meant
to stay unchanged, because these arms are the baseline the spires results are quoted
against and a silent improvement to a control invalidates the comparison.

Each builder returns a `kg_testgen.pipeline.ExternalContext`: the block 3 text, the
header to put above it, and whatever belongs in the run record so a run stays
diagnosable. `text=None` means genuinely no context, which is the `none` arm and is not
the same as an empty string.
"""

from __future__ import annotations

import logging
from typing import Optional

from kg_testgen.config import Config
from kg_testgen.errors import RetrievalError
from kg_testgen.neo4j_client import Neo4jClient
from kg_testgen.pipeline import ExternalContext

from . import headers

logger = logging.getLogger(__name__)

# Context modes this package owns. `spires` is deliberately absent: it is the pipeline's.
ARM_MODES = ("none", "full-corpus", "kg", "rp1")


def block3_header(context_mode: str, block3_format: str = "default") -> str:
    """The header for an arm's block 3, including the two perturbation formats."""
    return headers.for_mode(context_mode, block3_format)


def _corpus_path(config: Config) -> str:
    if config.corpus_path:
        return config.corpus_path
    # evaluation's own config, not the pipeline's: the flattened corpus is this arm's
    # input and the pipeline never reads it.
    from evaluation import eval_config
    return eval_config.EDC_CORPUS_PATH


def build_none(config: Config) -> ExternalContext:
    logger.warning("ARM 'none': no supplementary context; the knowledge graph is not "
                   "consulted.")
    return ExternalContext(text=None,
                           header=block3_header("none", config.block3_format))


def build_full_corpus(config: Config) -> ExternalContext:
    path = _corpus_path(config)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read().strip()
    except OSError as exc:
        raise RetrievalError(
            "context_mode='full-corpus' could not read the corpus at %r: %s\n"
            "Pass --corpus-path." % (path, exc)) from exc
    logger.warning("ARM 'full-corpus': pasting %d words of legislation verbatim; the "
                   "knowledge graph is not consulted.", len(text.split()))
    return ExternalContext(text=text,
                           header=block3_header("full-corpus", config.block3_format),
                           record={"corpus_path": path})


def build_rp1(client: Neo4jClient, section_text: str, config: Config) -> ExternalContext:
    from . import rp1_query
    rp1 = rp1_query.build_context(client, section_text, config)
    return ExternalContext(text=rp1.text,
                           header=block3_header("rp1", config.block3_format),
                           record={"rp1_context": rp1.as_dict()})


def build_kg(client: Neo4jClient, section_text: str, config: Config) -> ExternalContext:
    """The EDC triple arm: seed, expand, rank, prune, serialise, plus provision text.

    `include_triples=False` is the kg-text-only arm. Retrieval still runs in full and the
    triples are still recorded -- they are withheld from the prompt only. That is
    deliberate: the arm measures whether the triples help, so it has to be the same
    retrieval with one thing removed, not a different retrieval.
    """
    from . import provision_text as ptext
    from . import ranking, retrieval, seeding

    seed_result = seeding.seed(section_text, client, config)
    record = {"seeding": seed_result.as_dict()}

    retrieved = retrieval.retrieve(seed_result, client, config)
    record["retrieval"] = {
        "relationship_count": len(retrieved.all_triples()),
        "seed_to_seed_count": len(retrieved.seed_to_seed),
        "triples": [t.as_dict() for t in retrieved.all_triples()],
    }

    ranked = ranking.rank_and_prune(retrieved, config)
    record["ranking"] = ranked.as_dict()

    serialised = serialisation_of(ranked, seed_result, config)
    record["serialisation"] = serialised.as_dict()

    # The graph stores relationships; the cross-referenced provisions supply the law
    # those relationships are about.
    retrieved_provisions = sorted({
        part.strip().lower()
        for t in retrieved.all_triples()
        for part in (t.provisions or "").split(";") if part.strip()})
    ptext_result = ptext.fetch(
        client, config,
        provision_key=getattr(seed_result, "provision_key", None),
        retrieved_provisions=retrieved_provisions)
    record["provision_text"] = ptext_result.as_dict()
    ptext_block = ptext.render(ptext_result)

    if not config.include_triples:
        logger.info("include_triples=False: retrieval ran as normal, but the %d "
                    "serialised triple(s) are withheld from the prompt",
                    len(serialised.included))

    triple_block = serialised.text if config.include_triples else ""
    parts = [x for x in (ptext_block, triple_block) if x]
    if not parts:
        raise RetrievalError(
            "Every retrieved triple was excluded (all were asserted by the input "
            "subclause), leaving no supplementary context.\nRe-run with "
            "--allow-unaugmented to proceed, or --self-provision-policy none to keep "
            "them.")

    return ExternalContext(text="\n\n".join(parts),
                           header=block3_header("kg", config.block3_format),
                           record=record,
                           provision_id=seed_result.provision_id)


def serialisation_of(ranked, seed_result, config):
    from . import serialisation
    return serialisation.serialise(ranked.kept, seed_result, config)


def build_context(client: Optional[Neo4jClient], section_text: str,
                  config: Config) -> ExternalContext:
    """Dispatch on context_mode. `client` may be None for the two offline arms."""
    mode = config.context_mode
    if mode == "none":
        return build_none(config)
    if mode == "full-corpus":
        return build_full_corpus(config)
    if client is None:
        raise RetrievalError("context_mode=%r needs a graph connection." % mode)
    if mode == "rp1":
        return build_rp1(client, section_text, config)
    if mode == "kg":
        return build_kg(client, section_text, config)
    raise RetrievalError(
        "context_mode=%r is not an evaluation arm. 'spires' is the pipeline's own mode "
        "and is built by kg_testgen; the arms here are %s."
        % (mode, ", ".join(ARM_MODES)))


def needs_graph(config: Config) -> bool:
    return config.context_mode in ("kg", "rp1")
