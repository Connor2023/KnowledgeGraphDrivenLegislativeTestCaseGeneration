"""Evaluation harness -- entirely unimplemented, by design.

Evaluation is manual for now: read `generated.feature` alongside `run_record.json` and
check each scenario against the privacy policy by hand. The interfaces below mark where
automation would attach so that later work does not have to restructure the pipeline.

Every function here raises NotImplementedError. None is called by the pipeline.
"""

from __future__ import annotations

from typing import Dict, List, Literal

# Intended classification vocabulary for automated checking, recorded here so the
# pipeline's data model can accommodate it later.
Verdict = Literal["satisfied", "not_satisfied", "partially_satisfied"]
VERDICT_SYMBOLS = {
    "satisfied": "green tick",
    "not_satisfied": "red cross",
    "partially_satisfied": "orange cross",
}


def check_against_policy_2016(_feature_path: str, _policy_path: str) -> List[Dict]:
    """EXTENSION POINT -- not implemented.

    Automatically check each generated scenario against the 2016 Microsoft privacy
    policy and return a verdict per scenario.
    """
    raise NotImplementedError("Automated checking against the 2016 policy is not implemented.")


def recheck_failures_against_policy_2026(_results: List[Dict], _policy_path: str) -> List[Dict]:
    """EXTENSION POINT -- not implemented.

    Re-check scenarios that failed against the 2016 policy using the 2026 policy, to
    distinguish requirements the newer policy satisfies from those it still does not.
    """
    raise NotImplementedError("Automated re-checking against the 2026 policy is not implemented.")


def classify(_scenario_result: Dict) -> Verdict:
    """EXTENSION POINT -- not implemented.

    Map a check result onto the green tick / red cross / orange cross classification.
    """
    raise NotImplementedError("Verdict classification is not implemented.")


def score_run(_run_record: Dict) -> Dict:
    """EXTENSION POINT -- not implemented.

    Aggregate per-scenario verdicts into run-level metrics for comparing retrieval
    configurations against each other.
    """
    raise NotImplementedError("Automated scoring is not implemented.")


def process_batch(_section_paths: List[str]) -> List[Dict]:
    """EXTENSION POINT -- not implemented.

    Batch processing of multiple legislation sections in one invocation. The CLI is
    deliberately one-section-per-run for the POC.
    """
    raise NotImplementedError("Batch processing is not implemented.")
