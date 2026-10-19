"""
Build the knowledge graph in Neo4j Aura from the extracted Ollie triples.

    python build_kg.py --clear --strategy ema:0.9,0.1
    python build_kg.py --strategy noisy_or --batch-size 1000
    python build_kg.py --strategy gated --dry-run          # no database needed

``--strategy`` selects the ``augment_relationship`` rule applied to every tuple;
see ``augmentation.STRATEGIES``.  ``--dry-run`` runs the same rule against an
in-memory graph, which is the quick way to compare rules before committing to a
full build.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable

from augmentation import STRATEGIES, Triple, get_strategy
from config import load_credentials
from kg import KnowledgeGraph
from knowledge_graph import normalise
from neo4j_gdb import Neo4JGDB

HERE = Path(__file__).resolve().parent
DEFAULT_JSON = HERE / "requirements_pronouns_normalised.json"

USER = "User"
POST_CONDITION = "PostCondition"


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #

def extract_triples(data: Iterable[dict[str, Any]]) -> list[tuple[str, str, str, float]]:
    """Flatten the requirements JSON into ``(from, relationship, to, weight)``.

    Ollie emits ``triple = [subject, relation, object]`` with a confidence; that
    maps directly onto the tuple the graph ingests.  Triples with an empty
    component are dropped rather than normalised into nonsense.
    """
    triples: list[tuple[str, str, str, float]] = []

    def take(raw: dict[str, Any]) -> None:
        subject, relation, obj = (normalise(part) for part in raw["triple"])
        if not (subject and relation and obj):
            return
        triples.append((subject, relation, obj, float(raw["confidence"])))

    for story in data:
        for key in story:
            if key == "acceptanceCriteria":
                for criteria in story[key]:
                    for group in criteria["ollie"].values():
                        for raw in group:
                            take(raw)
            elif key != "ID":
                for parts in story[key]:
                    for part in parts["parts"]:
                        for raw in part["ollie"]:
                            take(raw)
    return triples


def load_triples(path: Path = DEFAULT_JSON) -> list[tuple[str, str, str, float]]:
    with open(path, "r", encoding="utf-8") as handle:
        return extract_triples(json.load(handle))


# --------------------------------------------------------------------------- #
# Dry run - same strategy, in-memory graph
# --------------------------------------------------------------------------- #

def dry_run(triples, strategy, top: int = 15) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Apply the strategy without touching the database, and report the result."""
    from augmentation import EdgeState

    edges: dict[tuple[str, str, str], EdgeState] = {}
    now = time.time()
    for from_entity, relationship, to_entity, weight in triples:
        incoming = Triple(from_entity, relationship, to_entity, weight, timestamp=now)
        current = edges.get(incoming.key)
        result = strategy(current, incoming)
        new_weight = float(result["weight"] if isinstance(result, dict) else result)
        edges[incoming.key] = EdgeState(
            weight=new_weight,
            observations=(current.observations if current else 0) + 1,
            first_seen=current.first_seen if current else now,
            last_seen=now,
        )

    duplicates = sum(1 for state in edges.values() if state.observations > 1)
    print(f"  tuples          : {len(triples)}")
    print(f"  distinct edges  : {len(edges)}")
    print(f"  edges augmented : {duplicates}")
    print(f"\n  heaviest edges under {strategy.name}:")
    ranked = sorted(edges.items(), key=lambda item: item[1].weight, reverse=True)[:top]
    for (from_entity, relationship, to_entity), state in ranked:
        print(
            f"    {state.weight:7.4f}  x{state.observations:<3} "
            f"({from_entity}) -[{relationship}]-> ({to_entity})"
        )
    return {key: {"weight": s.weight, "observations": s.observations} for key, s in edges.items()}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--strategy", default="ema:0.9,0.1",
        help=f"augmentation rule; one of {', '.join(sorted(STRATEGIES))}, "
             f"optionally with ':'-separated parameters (default: %(default)s)",
    )
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON, help="input triples file")
    parser.add_argument("--batch-size", type=int, default=500, help="tuples per write (default: %(default)s)")
    parser.add_argument("--limit", type=int, default=None, help="only ingest the first N tuples")
    parser.add_argument("--clear", action="store_true", help="wipe the graph before building")
    parser.add_argument("--dry-run", action="store_true", help="apply the strategy in memory only")
    parser.add_argument(
        "--no-cypher", action="store_true",
        help="force the Python augmentation path even when the strategy could run in Cypher",
    )
    parser.add_argument("--top", type=int, default=15, help="how many heaviest edges to print")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    strategy = get_strategy(args.strategy)

    triples = load_triples(args.json)
    if args.limit:
        triples = triples[: args.limit]
    print(f"Loaded {len(triples)} triples from {args.json.name}")
    print(f"Strategy: {strategy.name}")

    if args.dry_run:
        print("\nDry run (no database writes)")
        dry_run(triples, strategy, top=args.top)
        return 0

    creds = load_credentials()
    print(f"Connecting to {creds.uri} (credentials from {creds.source})")

    started = time.perf_counter()
    with Neo4JGDB(creds.uri, creds.auth, database=creds.database) as db:
        if args.clear:
            db.clear()
            print("Cleared existing graph")
        db.ensure_schema()

        with KnowledgeGraph(
            db,
            strategy,
            batch_size=args.batch_size,
            default_from_type=USER,
            default_to_type=POST_CONDITION,
            prefer_cypher=not args.no_cypher,
        ) as kg:
            path = "cypher" if kg.uses_cypher_path else "python"
            print(f"Ingesting via the {path} augmentation path...")
            for index, tuple_ in enumerate(triples, start=1):
                kg.add(*tuple_)
                if index % 2000 == 0:
                    print(f"  {index}/{len(triples)}")

        elapsed = time.perf_counter() - started
        stats = kg.stats
        print(
            f"\nDone in {elapsed:.1f}s - {stats['tuples']} tuples, "
            f"{stats['created']} edges created, {stats['queries']} queries, "
            f"{stats['tuples'] / max(elapsed, 1e-9):.0f} tuples/s"
        )
        print(f"Graph now holds {db.counts()}")

        print(f"\nHeaviest edges:")
        for edge in db.top_edges(args.top):
            print(
                f"  {edge['weight']:7.4f}  x{edge['observations']:<3} "
                f"({edge['from_entity']}) -[{edge['relationship']}]-> ({edge['to_entity']})"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
