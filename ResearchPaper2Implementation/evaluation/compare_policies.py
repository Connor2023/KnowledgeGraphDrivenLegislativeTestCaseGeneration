"""Evaluate every Gherkin scenario against two named policy snapshots.

Unlike ``evaluation.evaluate``, this comparator always judges both policies.  That
preserves regressions (satisfied -> not satisfied) as well as improvements.

Example, from the repository root::

    python -m evaluation.compare_policies evaluation/gdpr_github/gdpr_article13_sample.feature \
      --policy historical=evaluation/gdpr_github/policies/github_2017.md \
      --policy gdpr_release=evaluation/gdpr_github/policies/github_2018.md \
      --out-dir runs/gdpr_github/github_2017_vs_2018
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# The production package lives under pipeline/ after the repository reorganisation.
# Keep this top-level evaluation command runnable from a normal repository checkout.
PIPELINE_ROOT = Path(__file__).resolve().parents[1] / "pipeline"
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

from kg_testgen.config import Config, ConfigError, Secrets
from kg_testgen.llm import LLMError

from .gherkin import parse_feature
from .policy_check import NOT_SATISFIED, SATISFIED, judge


TRANSITIONS = {
    (SATISFIED, SATISFIED): "stable_satisfied",
    (NOT_SATISFIED, SATISFIED): "gap_closed",
    (NOT_SATISFIED, NOT_SATISFIED): "persistent_gap",
    (SATISFIED, NOT_SATISFIED): "regression",
}


def classify_transition(first: str, second: str) -> str:
    try:
        return TRANSITIONS[(first, second)]
    except KeyError as exc:
        raise ValueError("Unsupported verdict transition: %r -> %r" % (first, second)) from exc


def _policy_arg(value: str) -> Tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("policy must be LABEL=PATH")
    label, path = value.split("=", 1)
    if not label.strip() or not path.strip():
        raise argparse.ArgumentTypeError("policy must have a non-empty LABEL and PATH")
    return label.strip(), path.strip()


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _read(path: str) -> str:
    with io.open(path, encoding="utf-8") as stream:
        return stream.read()


def _secrets_for_policy_judge() -> Secrets:
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_KEY")
    if not key:
        raise ConfigError("Missing OPENAI_API_KEY (or OPENAI_KEY)")
    return Secrets(neo4j_uri="", neo4j_user="", neo4j_password="",
                   neo4j_database="", llm_api_key=key)


def _markdown(result: dict) -> str:
    first, second = [item["label"] for item in result["policies"]]
    lines = [
        "# Policy comparison",
        "",
        "- Feature: `%s`" % result["feature"]["path"],
        "- Baseline: `%s`" % first,
        "- Comparison: `%s`" % second,
        "- Generated: `%s`" % result["generated_at"],
        "",
        "| Requirement | %s | %s | Transition | Evidence verified |" % (first, second),
        "|---|---|---|---|---|",
    ]
    for item in result["evaluations"]:
        v1 = item["verdicts"][first]
        v2 = item["verdicts"][second]
        verified = "%s: %s; %s: %s" % (
            first, v1["evidence_status"], second, v2["evidence_status"])
        lines.append("| %s | %s | %s | %s | %s |" % (
            item["scenario"]["name"].replace("|", "\\|"),
            v1["verdict"], v2["verdict"], item["transition"], verified))
    lines += [
        "",
        "> A `not_satisfied` verdict normally has no supporting quote because absence is the",
        "> finding. Check it manually against `manual_oracle.yaml` before treating it as ground truth.",
        "",
    ]
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Judge every scenario against two policy snapshots and retain all four transitions.")
    parser.add_argument("feature")
    parser.add_argument("--policy", action="append", type=_policy_arg, required=True,
                        metavar="LABEL=PATH", help="Specify exactly twice, in chronological order.")
    parser.add_argument("--out-dir", default="runs/policy-comparison")
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate inputs and print the number of LLM calls without calling the API.")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def main(argv: List[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level),
                        format="%(levelname)-8s %(name)-25s %(message)s")
    if len(args.policy) != 2:
        print("Exactly two --policy arguments are required.", file=sys.stderr)
        return 2

    paths = [args.feature] + [path for _, path in args.policy]
    missing = [path for path in paths if not os.path.isfile(path)]
    if missing:
        print("Missing input file(s): %s" % ", ".join(missing), file=sys.stderr)
        return 2

    feature = parse_feature(args.feature)
    if not feature.scenarios:
        print("The feature contains no scenarios: %s" % args.feature, file=sys.stderr)
        return 2
    if args.dry_run:
        print("Scenarios: %d" % len(feature.scenarios))
        print("Policies : 2")
        print("LLM calls: %d" % (len(feature.scenarios) * 2))
        return 0

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    overrides = {}
    if args.llm_model:
        overrides["llm_model"] = args.llm_model
    if args.temperature is not None:
        overrides["temperature"] = args.temperature
    config = Config(**overrides)
    try:
        secrets = _secrets_for_policy_judge()
        policies: Dict[str, str] = {label: _read(path) for label, path in args.policy}
        evaluations = []
        first, second = [label for label, _ in args.policy]
        for scenario in feature.scenarios:
            verdicts = {
                label: judge(scenario, text, label, config, secrets).as_dict()
                for label, text in policies.items()
            }
            evaluations.append({
                "scenario": scenario.as_dict(),
                "verdicts": verdicts,
                "transition": classify_transition(
                    verdicts[first]["verdict"], verdicts[second]["verdict"]),
            })
    except (ConfigError, LLMError, ValueError) as exc:
        print("Comparison failed: %s" % exc, file=sys.stderr)
        return 2

    result = {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "model": config.llm_model,
        "temperature": config.temperature,
        "feature": {"path": args.feature, "sha256": _sha256(args.feature)},
        "policies": [
            {"label": label, "path": path, "sha256": _sha256(path)}
            for label, path in args.policy
        ],
        "evaluations": evaluations,
    }
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with io.open(out / "comparison.json", "w", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    with io.open(out / "comparison.md", "w", encoding="utf-8") as stream:
        stream.write(_markdown(result))
    print("Wrote %s" % (out / "comparison.json"))
    print("Wrote %s" % (out / "comparison.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
