"""Thin CLI entry point. All real work lives in the modules it calls."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import ConfigError, add_cli_arguments, config_from_args, secrets_from_env
from .neo4j_client import GraphUnavailable
from .llm import LLMError
from .pipeline import run as run_pipeline
from .retrieval import RetrievalError
from .seeding import SeedingError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kg-testgen",
        description="Generate Gherkin compliance test cases for a section of privacy "
                    "legislation, using a Neo4j knowledge graph for supplementary context.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", nargs="?", default="-",
                        help="Path to a file containing the legislation section, or '-' for stdin.")
    add_cli_arguments(parser)
    return parser


def _read_input(path: str) -> str:
    if path == "-":
        text = sys.stdin.read()
        if not text.strip():
            raise ConfigError("No input received on stdin. Pass a file path or pipe text in.")
        return text
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise ConfigError("Could not read input file %r: %s" % (path, exc)) from exc
    if not text.strip():
        raise ConfigError("Input file %r is empty." % path)
    return text


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        config = config_from_args(args)
    except ConfigError as exc:
        print("Configuration error: %s" % exc, file=sys.stderr)
        return 2

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(levelname)-8s %(name)-28s %(message)s",
        stream=sys.stderr,
    )

    try:
        # Loading a .env is a convenience; the environment still wins.
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        secrets = secrets_from_env()
        section_text = _read_input(args.input)
        result = run_pipeline(section_text, config, secrets,
                              input_path=None if args.input == "-" else args.input)
    except ConfigError as exc:
        print("Configuration error: %s" % exc, file=sys.stderr)
        return 2
    except GraphUnavailable as exc:
        print("Database error: %s" % exc, file=sys.stderr)
        return 3
    except (SeedingError, RetrievalError) as exc:
        print("Retrieval failed: %s" % exc, file=sys.stderr)
        return 4
    except LLMError as exc:
        print("LLM error: %s" % exc, file=sys.stderr)
        return 5

    print()
    print("Run directory : %s" % result.run_dir)
    print("Feature file  : %s" % result.feature_path)
    print("Run record    : %s" % result.record_path)
    print("KG augmented  : %s" % ("yes" if result.augmented else "NO (unaugmented)"))
    if result.structure_problems:
        print("Gherkin warnings: %s" % "; ".join(result.structure_problems))
    return 0


if __name__ == "__main__":
    sys.exit(main())
