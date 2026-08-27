"""End-to-end orchestration: section text in, Gherkin out.

Failure policy: seeding and retrieval failures are fatal unless --allow-unaugmented is
set, and the run record is written either way so a failed run is still diagnosable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from . import llm as llm_module
from . import output, prompting, ranking, retrieval, serialisation, seeding
from .config import Config, Secrets
from .neo4j_client import Neo4jClient
from .retrieval import RetrievalError
from .seeding import SeedingError

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    run_dir: str
    feature_path: Optional[str]
    record_path: str
    gherkin: Optional[str]
    augmented: bool
    structure_problems: list


def run(section_text: str, config: Config, secrets: Secrets,
        input_path: Optional[str] = None) -> PipelineResult:
    record = output.new_record(config, input_path, section_text)
    run_dir = None
    try:
        with Neo4jClient(secrets, config) as client:
            record["schema"] = client.schema.as_dict()

            context_block = None
            augmented = False
            provision_id = None

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

                if serialised.included:
                    context_block = serialised.text
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
            prompt = prompting.build_prompt(section_text, context_block, provision_id)
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
