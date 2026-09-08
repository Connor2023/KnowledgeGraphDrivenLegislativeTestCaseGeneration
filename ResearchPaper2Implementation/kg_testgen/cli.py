"""Thin CLI entry point. All real work lives in the modules it calls."""

from __future__ import annotations

import argparse
import logging
import sys

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import corpus_config  # noqa: E402

from .config import ConfigError, add_cli_arguments, config_from_args, secrets_from_env
from .neo4j_client import GraphUnavailable
from .llm import LLMError
from .pipeline import run as run_pipeline
from .errors import ContextError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kg-testgen",
        description="Generate Gherkin compliance test cases for a section of privacy "
                    "legislation, using a Neo4j knowledge graph for supplementary context.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", nargs="?", default=None,
                        help="Path to a file containing the legislation section, or '-' for "
                             "stdin. Omit it and use --provision instead.")
    parser.add_argument("--provision", metavar="ID",
                        help="Generate for this provision of the configured corpus, e.g. "
                             "'6.1' or '26WE(1)'. The text comes from the segmentation, so "
                             "no file has to be made by hand.")
    parser.add_argument("--list-provisions", action="store_true",
                        help="Print every provision identifier, in document order, and exit.")
    add_cli_arguments(parser)
    return parser


def _provision_text(identifier: str) -> str:
    """One provision's text, straight from the segmentation.

    Without this, generating for a clause meant hand-making a file under sections/ --
    which is why that directory holds eleven of them. It is also the difference between
    "a graph exists" and "test cases are ready to generate": the corpus already knows what
    every provision says, and asking the user to copy it into a file is asking them to
    reproduce work the pipeline has already done.

    The identifier is prefixed onto the text. Part IIIC's subsections do not carry their
    section number -- 26WE(1) reads "(1) This section applies if:" -- so without this the
    generator could not tell which provision it had been given.
    """
    import prep_corpus

    provisions = prep_corpus.provisions()
    text = provisions.get(identifier)
    if text is None:
        near = [p for p in provisions if p.startswith(identifier.split("(")[0])][:6]
        raise ConfigError(
            "No provision %r in corpus %r.%s\nRun --list-provisions to see them all."
            % (identifier, corpus_config.NAME,
               (" Did you mean: %s?" % ", ".join(near)) if near else ""))
    return text if text.startswith(identifier) else "%s %s" % (identifier, text)


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

    if args.list_provisions:
        import prep_corpus
        for identifier in prep_corpus.order():
            print(identifier)
        return 0

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

        # Resolve the input BEFORE asking for credentials: a mistyped provision id
        # should not require a working Neo4j connection to discover.
        if args.provision:
            section_text = _provision_text(args.provision)
            input_path = "%s:%s" % (corpus_config.NAME, args.provision)
            config.provision_id = config.provision_id or args.provision
        else:
            section_text = _read_input(args.input or "-")
            input_path = None if (args.input or "-") == "-" else args.input

        secrets = secrets_from_env()
        result = run_pipeline(section_text, config, secrets, input_path=input_path)
    except ConfigError as exc:
        print("Configuration error: %s" % exc, file=sys.stderr)
        return 2
    except GraphUnavailable as exc:
        print("Database error: %s" % exc, file=sys.stderr)
        return 3
    except ContextError as exc:
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
