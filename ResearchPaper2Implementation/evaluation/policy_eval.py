"""Two-stage evaluation of generated test cases against the Microsoft privacy policies.

Stage 1 judges every scenario against the 2016 policy. Stage 2 re-judges only the 2016
failures against the 2026 policy, which acts as ground truth for whether a failure was a
real gap that Microsoft later closed.

Classification:

    green_tick    satisfied by the 2016 policy
    orange_cross  not satisfied in 2016, satisfied in 2026 -- a real gap, later closed.
                  This also corroborates the test case: a policy eventually addressed it.
    red_cross     not satisfied by either. AMBIGUOUS by design: this is either a
                  persistent compliance gap or a spurious generated test case, and the
                  two cannot be told apart automatically. Flagged for manual review.

Every verdict carries a verbatim policy quote, checked programmatically against the
policy text, so fabricated citations surface instead of being trusted.
"""

from __future__ import annotations

import datetime as _dt
import io
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import policy_check
from kg_testgen.config import Config, Secrets
from .gherkin import Feature, Scenario, parse_feature
from .policy_check import NOT_SATISFIED, SATISFIED, PolicyVerdict

logger = logging.getLogger(__name__)

GREEN_TICK = "green_tick"
ORANGE_CROSS = "orange_cross"
RED_CROSS = "red_cross"

CLASSIFICATION_MEANING = {
    GREEN_TICK: "Satisfied by the 2016 policy.",
    ORANGE_CROSS: "Not satisfied in 2016 but satisfied in 2026 - a real gap that was "
                  "later closed, which also corroborates the test case.",
    RED_CROSS: "Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a "
               "spurious test case. Needs manual review.",
}
SYMBOL = {GREEN_TICK: "[PASS]", ORANGE_CROSS: "[GAP]", RED_CROSS: "[REVIEW]"}


@dataclass
class ScenarioEvaluation:
    scenario: Scenario
    verdict_2016: PolicyVerdict
    verdict_2026: Optional[PolicyVerdict] = None
    classification: str = ""
    needs_manual_review: bool = False

    def as_dict(self) -> dict:
        return {
            "scenario": self.scenario.as_dict(),
            "verdict_2016": self.verdict_2016.as_dict(),
            "verdict_2026": self.verdict_2026.as_dict() if self.verdict_2026 else None,
            "classification": self.classification,
            "classification_meaning": CLASSIFICATION_MEANING.get(self.classification, ""),
            "needs_manual_review": self.needs_manual_review,
        }


@dataclass
class EvaluationResult:
    feature_name: str = ""
    feature_path: Optional[str] = None
    evaluations: List[ScenarioEvaluation] = field(default_factory=list)
    timestamp: str = ""

    def counts(self) -> Dict[str, int]:
        out = {GREEN_TICK: 0, ORANGE_CROSS: 0, RED_CROSS: 0}
        for e in self.evaluations:
            out[e.classification] = out.get(e.classification, 0) + 1
        return out

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "feature_name": self.feature_name,
            "feature_path": self.feature_path,
            "counts": self.counts(),
            "classification_meaning": CLASSIFICATION_MEANING,
            "scenarios_evaluated": len(self.evaluations),
            "fabricated_evidence_count": sum(
                1 for e in self.evaluations
                for v in (e.verdict_2016, e.verdict_2026)
                if v is not None and v.evidence_status == "unverified"),
            "evaluations": [e.as_dict() for e in self.evaluations],
        }


def classify(evaluation: ScenarioEvaluation) -> str:
    """Map the one or two verdicts onto the tri-state classification."""
    if evaluation.verdict_2016.verdict == SATISFIED:
        return GREEN_TICK
    if evaluation.verdict_2026 is not None and evaluation.verdict_2026.verdict == SATISFIED:
        return ORANGE_CROSS
    return RED_CROSS


def read_policy(path: str) -> str:
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def evaluate_feature(feature_path: str, policy_2016_path: str, policy_2026_path: str,
                     config: Config, secrets: Secrets) -> EvaluationResult:
    feature: Feature = parse_feature(feature_path)
    if not feature.scenarios:
        raise ValueError("No scenarios found in %s" % feature_path)

    policy_2016 = read_policy(policy_2016_path)
    policy_2026 = read_policy(policy_2026_path)

    logger.info("Evaluating %d scenario(s) from %s", len(feature.scenarios), feature_path)
    logger.info("  2016 policy: %d words   2026 policy: %d words",
                len(policy_2016.split()), len(policy_2026.split()))

    result = EvaluationResult(
        feature_name=feature.name, feature_path=feature_path,
        timestamp=_dt.datetime.now().astimezone().isoformat())

    for index, scenario in enumerate(feature.scenarios, 1):
        logger.info("[%d/%d] %s", index, len(feature.scenarios), scenario.name[:70])

        verdict_2016 = policy_check.judge(scenario, policy_2016, "2016", config, secrets)
        logger.info("    2016 -> %-14s (%s confidence, evidence: %s)",
                    verdict_2016.verdict, verdict_2016.confidence,
                    verdict_2016.evidence_status)

        evaluation = ScenarioEvaluation(scenario=scenario, verdict_2016=verdict_2016)

        # Stage 2 runs only on 2016 failures, per the original requirements.
        if verdict_2016.verdict == NOT_SATISFIED:
            verdict_2026 = policy_check.judge(scenario, policy_2026, "2026", config, secrets)
            evaluation.verdict_2026 = verdict_2026
            logger.info("    2026 -> %-14s (%s confidence, evidence: %s)",
                        verdict_2026.verdict, verdict_2026.confidence,
                        verdict_2026.evidence_status)

        evaluation.classification = classify(evaluation)
        evaluation.needs_manual_review = evaluation.classification == RED_CROSS
        logger.info("    => %s %s", SYMBOL[evaluation.classification],
                    evaluation.classification)
        result.evaluations.append(evaluation)

    counts = result.counts()
    logger.info("Done: %d satisfied, %d gap-later-closed, %d needing review",
                counts[GREEN_TICK], counts[ORANGE_CROSS], counts[RED_CROSS])
    return result


def write_results(result: EvaluationResult, out_dir: str) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "evaluation.json")
    with io.open(json_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(result.as_dict(), fh, indent=2, ensure_ascii=False)

    md_path = os.path.join(out_dir, "evaluation.md")
    with io.open(md_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_markdown(result))

    logger.info("Wrote %s", json_path)
    logger.info("Wrote %s", md_path)
    return {"json": json_path, "markdown": md_path}


def render_markdown(result: EvaluationResult) -> str:
    counts = result.counts()
    lines = [
        "# Evaluation: %s" % (result.feature_name or "(unnamed feature)"),
        "",
        "Source: `%s`  " % result.feature_path,
        "Generated: %s" % result.timestamp,
        "",
        "| Classification | Count | Meaning |",
        "|---|---|---|",
        "| Satisfied (2016) | %d | %s |" % (counts[GREEN_TICK], CLASSIFICATION_MEANING[GREEN_TICK]),
        "| Gap later closed | %d | %s |" % (counts[ORANGE_CROSS], CLASSIFICATION_MEANING[ORANGE_CROSS]),
        "| Needs review | %d | %s |" % (counts[RED_CROSS], CLASSIFICATION_MEANING[RED_CROSS]),
        "",
    ]

    unverified = [e for e in result.evaluations
                  for v in (e.verdict_2016, e.verdict_2026)
                  if v is not None and v.evidence_status == "unverified"]
    if unverified:
        lines += ["> **%d verdict(s) cite evidence that could not be located in the policy "
                  "text.** Those citations may be fabricated; read them before relying on "
                  "the verdict." % len(unverified), ""]

    for index, e in enumerate(result.evaluations, 1):
        lines += [
            "## %d. %s %s" % (index, SYMBOL[e.classification], e.scenario.name),
            "",
            "Tags: %s" % (" ".join(e.scenario.tags) or "(none)"),
            "",
        ]
        if e.scenario.derives_from:
            lines += ["Derives from: *%s*" % e.scenario.derives_from, ""]
        lines += ["```gherkin", e.scenario.as_text(), "```", ""]

        for verdict in (e.verdict_2016, e.verdict_2026):
            if verdict is None:
                continue
            lines += ["**%s policy — %s** (%s confidence)"
                      % (verdict.policy_label, verdict.verdict, verdict.confidence), ""]
            if verdict.reasoning:
                lines += [verdict.reasoning, ""]
            if verdict.evidence_quote:
                mark = "verified in policy text" if verdict.evidence_verified \
                    else "**NOT FOUND in policy text — possibly fabricated**"
                lines += ["> %s" % verdict.evidence_quote.strip(), "", "(%s)" % mark, ""]
            else:
                lines += ["_No supporting passage cited._", ""]
            if verdict.parse_error:
                lines += ["_Parse error: %s_" % verdict.parse_error, ""]

        lines += ["**Classification: %s** — %s"
                  % (e.classification, CLASSIFICATION_MEANING[e.classification]), "", "---", ""]

    return "\n".join(lines)


def process_batch(_section_paths: List[str]) -> List[Dict]:
    """EXTENSION POINT -- not implemented.

    Batch processing of multiple legislation sections in one invocation. The CLI is
    deliberately one-section-per-run for the POC.
    """
    raise NotImplementedError("Batch processing is not implemented.")
