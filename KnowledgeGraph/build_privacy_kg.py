"""
Build the Privacy Regulations knowledge graph in Neo4j Aura from the
PrivacyPolicyTuples CSVs.

    python build_privacy_kg.py --dry-run                       # nothing written
    python build_privacy_kg.py --source semantic --strategy sum
    python build_privacy_kg.py --source both --strategy noisy_or --weight-mode source

Neither CSV carries a confidence, so ``--weight-mode`` decides what a weight
means and ``--strategy`` decides how repeated assertions combine; the two
choices only make sense together.  See ``privacy_tuples.tuple_weight``.

Entities are labelled ``:PrivacyConcept`` on top of the shared ``:Entity`` key,
so this graph can be queried on its own even if the requirements graph from
``build_kg.py`` lives in the same instance.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import privacy_tuples
from augmentation import STRATEGIES, get_strategy
from build_kg import dry_run
from config import load_credentials
from kg import KnowledgeGraph
from neo4j_gdb import Neo4JGDB

DEFAULT_LABEL = "PrivacyConcept"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--source", choices=("semantic", "naive", "both"), default="semantic",
        help="which extraction to ingest (default: %(default)s)",
    )
    parser.add_argument(
        "--weight-mode", choices=privacy_tuples.WEIGHT_MODES, default="source",
        help="where the incoming weight comes from (default: %(default)s)",
    )
    parser.add_argument(
        "--strategy", default="noisy_or",
        help=f"augmentation rule; one of {', '.join(sorted(STRATEGIES))}, optionally "
             f"with ':'-separated parameters (default: %(default)s)",
    )
    parser.add_argument(
        "--directory", type=Path, default=privacy_tuples.DEFAULT_DIR,
        help="folder holding the CSVs (default: %(default)s)",
    )
    parser.add_argument("--label", default=DEFAULT_LABEL, help="role label for entity nodes")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--clear", action="store_true", help="wipe the whole graph first")
    parser.add_argument("--dry-run", action="store_true", help="apply the rule in memory only")
    parser.add_argument(
        "--no-align", action="store_true",
        help="with --source both, keep the naive surface relations instead of "
             "casting them onto the semantic vocabulary",
    )
    parser.add_argument(
        "--raw-entities", action="store_true",
        help="keep original casing and articles instead of normalising entity names",
    )
    parser.add_argument(
        "--scalar-provenance", action="store_true",
        help="store section/source as single values that later observations "
             "overwrite, instead of accumulating every distinct value into a list",
    )
    parser.add_argument("--top", type=int, default=15, help="how many heaviest edges to print")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    strategy = get_strategy(args.strategy)
    sources = ("semantic", "naive") if args.source == "both" else (args.source,)

    triples = privacy_tuples.load(
        args.directory,
        sources=sources,
        weight_mode=args.weight_mode,
        normalise_entities=not args.raw_entities,
        align=not args.no_align,
    )
    summary = privacy_tuples.describe(triples)
    print(f"Source     : {args.source}")
    print(f"Weight mode: {args.weight_mode}")
    print(f"Strategy   : {strategy.name}")
    print(
        f"Loaded     : {summary['tuples']} tuples, {summary['distinct_edges']} distinct edges, "
        f"{summary['repeated_edges']} repeats, {summary['entities']} entities, "
        f"{summary['relations']} relations"
    )

    if args.weight_mode == "constant" and strategy.name.startswith("ema"):
        print(
            "\nWarning: ema on constant weights is a no-op (0.9w + 0.1w == w). "
            "Use --strategy sum for a frequency count, or a weight mode that varies."
        )

    if args.dry_run:
        print("\nDry run (no database writes)")
        plain = [(t.from_entity, t.relationship, t.to_entity, t.weight) for t in triples]
        dry_run(plain, strategy, top=args.top)
        return 0

    creds = load_credentials()
    print(f"\nConnecting to {creds.uri} (credentials from {creds.source})")

    started = time.perf_counter()
    with Neo4JGDB(creds.uri, creds.auth, database=creds.database) as db:
        if args.clear:
            db.clear()
            print("Cleared existing graph")
        db.ensure_schema()

        with KnowledgeGraph(
            db, strategy,
            batch_size=args.batch_size,
            default_from_type=args.label,
            default_to_type=args.label,
            accumulate=None if args.scalar_provenance else privacy_tuples.ACCUMULATE,
        ) as kg:
            print(f"Ingesting via the {'cypher' if kg.uses_cypher_path else 'python'} path...")
            kg.add_many(triples)

        elapsed = time.perf_counter() - started
        print(
            f"\nDone in {elapsed:.1f}s - {kg.stats['tuples']} tuples, "
            f"{kg.stats['created']} edges created, {kg.stats['queries']} queries"
        )
        print(f"Graph now holds {db.counts()}")

        print("\nHeaviest edges:")
        for edge in db.top_edges(args.top):
            print(
                f"  {edge['weight']:7.4f}  x{edge['observations']:<3} "
                f"({edge['from_entity']}) -[{edge['relationship']}]-> ({edge['to_entity']})"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
