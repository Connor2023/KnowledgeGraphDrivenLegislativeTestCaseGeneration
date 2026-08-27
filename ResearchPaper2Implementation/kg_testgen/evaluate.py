"""CLI for evaluating a generated .feature against the two Microsoft privacy policies.

    python -m kg_testgen.evaluate runs/final_6_1/generated.feature
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from .config import ConfigError, Config, secrets_from_env
from .evaluation import evaluate_feature, write_results, GREEN_TICK, ORANGE_CROSS, RED_CROSS
from .llm import LLMError

DEFAULT_POLICY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "MicrosoftPrivacyPolicy")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kg-testgen-evaluate",
        description="Check generated Gherkin scenarios against the 2016 Microsoft privacy "
                    "policy, using the 2026 policy as ground truth for any failures.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("feature", help="Path to a generated .feature file.")
    parser.add_argument("--policy-2016", default=os.path.join(DEFAULT_POLICY_DIR, "2016.txt"))
    parser.add_argument("--policy-2026", default=os.path.join(DEFAULT_POLICY_DIR, "2026.txt"))
    parser.add_argument("--out-dir", default=None,
                        help="Where to write evaluation.json and evaluation.md. "
                             "Defaults to the feature file's own directory.")
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level),
                        format="%(levelname)-8s %(name)-26s %(message)s", stream=sys.stderr)

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

    for label, path in (("--policy-2016", args.policy_2016), ("--policy-2026", args.policy_2026)):
        if not os.path.exists(path):
            print("Policy file not found (%s): %s" % (label, path), file=sys.stderr)
            return 2
    if not os.path.exists(args.feature):
        print("Feature file not found: %s" % args.feature, file=sys.stderr)
        return 2

    try:
        secrets = secrets_from_env()
        result = evaluate_feature(args.feature, args.policy_2016, args.policy_2026,
                                  config, secrets)
    except ConfigError as exc:
        print("Configuration error: %s" % exc, file=sys.stderr)
        return 2
    except LLMError as exc:
        print("LLM error: %s" % exc, file=sys.stderr)
        return 5
    except ValueError as exc:
        print("Input error: %s" % exc, file=sys.stderr)
        return 2

    out_dir = args.out_dir or os.path.dirname(os.path.abspath(args.feature))
    paths = write_results(result, out_dir)

    counts = result.counts()
    print()
    print("Scenarios evaluated : %d" % len(result.evaluations))
    print("  satisfied in 2016 : %d" % counts[GREEN_TICK])
    print("  gap, closed by 2026: %d" % counts[ORANGE_CROSS])
    print("  needs manual review: %d" % counts[RED_CROSS])
    print()
    print("Report : %s" % paths["markdown"])
    print("Data   : %s" % paths["json"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
