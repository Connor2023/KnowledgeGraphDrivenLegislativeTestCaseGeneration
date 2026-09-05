"""End-to-end orchestration: section text in, Gherkin out.

Failure policy: seeding and retrieval failures are fatal unless --allow-unaugmented is
set, and the run record is written either way so a failed run is still diagnosable.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

from . import llm as llm_module
from . import output, prompting, ranking, retrieval, serialisation, seeding
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import corpus_config as _corpus_config  # noqa: E402

from .config import Config, Secrets
from .neo4j_client import Neo4jClient
from .retrieval import RetrievalError
from .seeding import SeedingError

logger = logging.getLogger(__name__)

# The corpus pasted in by --context-mode full-corpus. From corpus.yaml so the
# control arm follows the configured instrument rather than a second hard-coded path.
DEFAULT_CORPUS_PATH = _corpus_config.CORPUS_PATH


@dataclass
class PipelineResult:
    run_dir: str
    feature_path: Optional[str]
    record_path: str
    gherkin: Optional[str]
    augmented: bool
    structure_problems: list


def _generate_and_write(record, section_text, context_block, config, secrets,
                        provision_id=None):
    """Prompt, generate, and write outputs. Shared by the normal and ablation paths."""
    from . import edc_bridge

    if provision_id is None:
        provision_id = config.provision_id or edc_bridge.detect_provision_id(section_text)

    augmented = context_block is not None
    record["augmented"] = augmented
    prompt = prompting.build_prompt(section_text, context_block, provision_id,
                                    context_mode=config.context_mode,
                                    block3_format=config.block3_format)
    record["prompt"] = prompt

    logger.info("Calling %s (temperature %.1f)%s", config.llm_model, config.temperature,
                "" if augmented else " WITHOUT KG context")
    response = llm_module.generate(prompt, config, secrets)
    record["llm"] = response.as_dict()

    gherkin = llm_module.clean_gherkin(response.text)
    problems = llm_module.check_gherkin_structure(gherkin)
    record["gherkin"] = gherkin
    record["gherkin_structure_problems"] = problems
    record["status"] = "ok"
    if problems:
        logger.warning("Generated Gherkin has structural problems: %s", "; ".join(problems))

    run_dir = output.make_run_dir(config.output_dir, provision_id)
    feature_path = output.write_feature(run_dir, gherkin)
    output.write_prompt(run_dir, prompt)
    record_path = output.write_run_record(run_dir, record)
    return PipelineResult(run_dir=run_dir, feature_path=feature_path,
                          record_path=record_path, gherkin=gherkin,
                          augmented=augmented, structure_problems=problems)


def run(section_text: str, config: Config, secrets: Secrets,
        input_path: Optional[str] = None) -> PipelineResult:
    record = output.new_record(config, input_path, section_text)
    run_dir = None

    if config.context_mode in ("none", "full-corpus"):
        # Control arms: no seeding, no retrieval, no database connection at all.
        context_block = None
        if config.context_mode == "full-corpus":
            corpus_path = config.corpus_path or DEFAULT_CORPUS_PATH
            try:
                with open(corpus_path, "r", encoding="utf-8") as fh:
                    context_block = fh.read().strip()
            except OSError as exc:
                raise RetrievalError(
                    "context_mode='full-corpus' could not read the corpus at %r: %s\n"
                    "Pass --corpus-path." % (corpus_path, exc)) from exc
            record["corpus_path"] = corpus_path
            logger.warning("ARM 'full-corpus': pasting %d words of legislation verbatim; "
                           "the knowledge graph is not consulted.",
                           len(context_block.split()))
        else:
            logger.warning("ARM 'none': no supplementary context; the knowledge graph is "
                           "not consulted.")
        return _generate_and_write(record, section_text, context_block, config, secrets)

    try:
        with Neo4jClient(secrets, config) as client:
            record["schema"] = client.schema.as_dict()

            context_block = None
            augmented = False
            provision_id = None

            if config.context_mode == "spires":
                # A reified norm graph: retrieval walks provisions and renders norms,
                # so it shares nothing with the triple pipeline below.
                from . import spires_query
                spires = spires_query.build_context(client, section_text, config)
                record["spires_context"] = spires.as_dict()
                return _generate_and_write(record, section_text, spires.text, config,
                                           secrets, provision_id=spires.target_provision)

            if config.context_mode == "rp1":
                # A different graph shape needs a different method: whole-graph
                # selection and legal-context ordering, not hop-limited retrieval.
                from . import rp1_query
                rp1 = rp1_query.build_context(client, section_text, config)
                record["rp1_context"] = rp1.as_dict()
                return _generate_and_write(record, section_text, rp1.text, config, secrets)

            try:
                seed_result = seeding.seed(section_text, client, config)
                record["seeding"] = seed_result.as_dict()
                provision_id = seed_result.provision_id

                retrieved = retrieval.retrieve(seed_result, client, config)
                record["retrieval"] = {
                    "relationship_count": len(retrieved.all_triples()),
                    "seed_to_seed_count": len(retrieved.seed_to_seed),
                    "triples": [t.as_dict() for t in retrieved.all_triples()],
                }

                ranked = ranking.rank_and_prune(retrieved, config)
                record["ranking"] = ranked.as_dict()

                serialised = serialisation.serialise(ranked.kept, seed_result, config)
                record["serialisation"] = serialised.as_dict()

                # Statutory text for the clauses this section points at. The graph
                # stores relationships; the cross-referenced provisions supply the law
                # those relationships are about.
                from . import provision_text as ptext
                retrieved_provisions = sorted({
                    part.strip().lower()
                    for t in retrieved.all_triples()
                    for part in (t.provisions or "").split(";") if part.strip()})
                ptext_result = ptext.fetch(
                    client, config,
                    provision_key=(seed_result.provision_key
                                   if hasattr(seed_result, "provision_key") else None),
                    retrieved_provisions=retrieved_provisions)
                record["provision_text"] = ptext_result.as_dict()
                ptext_block = ptext.render(ptext_result)

                if not config.include_triples:
                    logger.info("include_triples=False: retrieval ran as normal, but the "
                                "%d serialised triple(s) are withheld from the prompt",
                                len(serialised.included))

                triple_block = serialised.text if config.include_triples else ""
                if triple_block or ptext_block:
                    parts = [x for x in (ptext_block, triple_block) if x]
                    context_block = "\n\n".join(parts)
                    augmented = True
                else:
                    message = ("Every retrieved triple was excluded (all were asserted by "
                               "the input subclause), leaving no supplementary context.")
                    if not config.allow_unaugmented:
                        raise RetrievalError(
                            message + "\nRe-run with --allow-unaugmented to proceed, or "
                            "--self-provision-policy none to keep them.")
                    logger.warning("%s Proceeding unaugmented (--allow-unaugmented).", message)

            except (SeedingError, RetrievalError) as exc:
                if not config.allow_unaugmented:
                    record["error"] = str(exc)
                    record["status"] = "failed"
                    run_dir = output.make_run_dir(config.output_dir, provision_id)
                    output.write_run_record(run_dir, record)
                    raise
                logger.warning("Proceeding without KG augmentation (--allow-unaugmented): %s", exc)
                record["seeding"] = record.get("seeding")
                record["error"] = "non-fatal (allow_unaugmented): %s" % exc

            if provision_id is None:
                from . import edc_bridge
                provision_id = config.provision_id or edc_bridge.detect_provision_id(section_text)

            record["augmented"] = augmented
            prompt = prompting.build_prompt(section_text, context_block, provision_id,
                                    context_mode=config.context_mode,
                                    block3_format=config.block3_format)
            record["prompt"] = prompt

            logger.info("Calling %s (temperature %.1f)%s", config.llm_model,
                        config.temperature, "" if augmented else " WITHOUT KG context")
            response = llm_module.generate(prompt, config, secrets)
            record["llm"] = response.as_dict()

            gherkin = llm_module.clean_gherkin(response.text)
            problems = llm_module.check_gherkin_structure(gherkin)
            record["gherkin"] = gherkin
            record["gherkin_structure_problems"] = problems
            record["status"] = "ok"

            if problems:
                logger.warning("Generated Gherkin has structural problems: %s",
                               "; ".join(problems))

            run_dir = output.make_run_dir(config.output_dir, provision_id)
            feature_path = output.write_feature(run_dir, gherkin)
            output.write_prompt(run_dir, prompt)
            record_path = output.write_run_record(run_dir, record)

            return PipelineResult(run_dir=run_dir, feature_path=feature_path,
                                  record_path=record_path, gherkin=gherkin,
                                  augmented=augmented, structure_problems=problems)

    except (SeedingError, RetrievalError):
        raise
    except Exception as exc:  # noqa: BLE001 - always leave a diagnosable record
        record["error"] = "%s: %s" % (type(exc).__name__, exc)
        record["status"] = "failed"
        if run_dir is None:
            run_dir = output.make_run_dir(config.output_dir, None)
        output.write_run_record(run_dir, record)
        raise
