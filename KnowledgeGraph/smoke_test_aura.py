"""
Verify the Cypher augmentation path against the live Aura instance.

Every closed-form strategy declares a Cypher expression as well as a Python
implementation; this checks the two agree by running the same tuples through
both and comparing the resulting weights.  It also exercises schema creation,
duplicate folding across waves, and distinct relations between one pair.

Non-destructive: all test entities are namespaced with a random prefix and are
deleted at the end, so nothing already in the graph is read, modified or removed.

    python smoke_test_aura.py
"""

from __future__ import annotations

import sys
import uuid

from augmentation import get_strategy
from config import load_credentials
from kg import KnowledgeGraph
from memory_gdb import MemoryGDB
from neo4j_gdb import Neo4JGDB

PREFIX = f"__smoke_{uuid.uuid4().hex[:8]}"
LABEL = "SmokeTest"
NOW = 1_700_000_000.0
WEIGHTS = [0.40, 0.90, 0.20, 0.70]
CLOSED_FORM = ["ema:0.9,0.1", "sum", "max", "mean", "noisy_or", "hebbian", "decay_ema:0.9,0.1,3600"]


def expected_weight(spec: str, tuples) -> float:
    """Ground truth: the same tuples through the Python implementation."""
    db = MemoryGDB()
    db.start()
    with KnowledgeGraph(db, get_strategy(spec), batch_size=100) as kg:
        for from_entity, relationship, to_entity, weight, when in tuples:
            kg.add(from_entity, relationship, to_entity, weight, timestamp=when)
    return kg.weight(tuples[0][0], tuples[0][1], tuples[0][2])


def cleanup(db: Neo4JGDB) -> int:
    with db._session() as session:
        record = session.execute_write(
            lambda tx: tx.run(
                "MATCH (n) WHERE n.entity STARTS WITH $prefix "
                "DETACH DELETE n RETURN count(n) AS removed",
                prefix=PREFIX,
            ).single()
        )
    return record["removed"] if record else 0


def main() -> int:
    creds = load_credentials()
    print(f"Connecting to {creds.uri} (credentials from {creds.source})")
    print(f"Test namespace: {PREFIX}*\n")

    failures = 0
    with Neo4JGDB(creds.uri, creds.auth, database=creds.database) as db:
        try:
            db.ensure_schema()
            print("ok    ensure_schema")

            before = db.counts()
            print(f"      graph currently holds {before}")

            for spec in CLOSED_FORM:
                for batch_size in (1, 100):
                    node = f"{PREFIX}_{spec.split(':')[0]}_{batch_size}"
                    tuples = [
                        (f"{node}_a", "rel", f"{node}_b", w, NOW + i * 1800.0)
                        for i, w in enumerate(WEIGHTS)
                    ]
                    strategy = get_strategy(spec)
                    with KnowledgeGraph(
                        db, strategy, batch_size=batch_size,
                        default_from_type=LABEL, default_to_type=LABEL,
                    ) as kg:
                        assert kg.uses_cypher_path, f"{spec} should use the Cypher path"
                        for from_entity, relationship, to_entity, weight, when in tuples:
                            kg.add(from_entity, relationship, to_entity, weight, timestamp=when)

                    got = kg.weight(f"{node}_a", "rel", f"{node}_b")
                    want = expected_weight(spec, tuples)
                    edge = kg.edge(f"{node}_a", "rel", f"{node}_b")
                    agree = got is not None and abs(got - want) < 1e-9
                    counted = edge is not None and edge["observations"] == len(WEIGHTS)
                    if agree and counted:
                        print(f"ok    {spec:<26} batch={batch_size:<3} cypher={got:.6f}")
                    else:
                        failures += 1
                        print(
                            f"FAIL  {spec:<26} batch={batch_size:<3} "
                            f"cypher={got} python={want} "
                            f"observations={edge and edge['observations']}"
                        )

            # Two relations between one pair must be two edges.
            with KnowledgeGraph(db, get_strategy("ema"), default_from_type=LABEL,
                                default_to_type=LABEL) as kg:
                kg.add(f"{PREFIX}_x", "can view", f"{PREFIX}_y", 0.9, timestamp=NOW)
                kg.add(f"{PREFIX}_x", "can edit", f"{PREFIX}_y", 0.4, timestamp=NOW)
            pair = [
                kg.weight(f"{PREFIX}_x", "can view", f"{PREFIX}_y"),
                kg.weight(f"{PREFIX}_x", "can edit", f"{PREFIX}_y"),
            ]
            if pair == [0.9, 0.4]:
                print("ok    distinct relations stay distinct edges")
            else:
                failures += 1
                print(f"FAIL  distinct relations stay distinct edges: {pair}")

            # An entity used on both sides must remain a single node.
            with KnowledgeGraph(db, get_strategy("ema"), default_from_type=LABEL,
                                default_to_type=LABEL) as kg:
                kg.add(f"{PREFIX}_p", "expires", f"{PREFIX}_q", 0.5, timestamp=NOW)
                kg.add(f"{PREFIX}_q", "belongs to", f"{PREFIX}_p", 0.5, timestamp=NOW)
            with db._session() as session:
                nodes = session.execute_read(
                    lambda tx: tx.run(
                        "MATCH (n) WHERE n.entity IN [$p, $q] RETURN count(n) AS n",
                        p=f"{PREFIX}_p", q=f"{PREFIX}_q",
                    ).single()
                )["n"]
            if nodes == 2:
                print("ok    shared entity is one node")
            else:
                failures += 1
                print(f"FAIL  shared entity is one node: found {nodes} nodes, expected 2")

            # Accumulated provenance: the Cypher list update must match Python's.
            observations = [
                (0.9, {"section": "16(a)", "source": "semantic"}),
                (0.6, {"section": "19(b)", "source": "naive"}),
                (0.6, {"section": "16(a)", "source": "naive"}),
            ]
            for batch_size in (1, 100):
                node = f"{PREFIX}_acc_{batch_size}"
                with KnowledgeGraph(
                    db, get_strategy("noisy_or"), batch_size=batch_size,
                    accumulate=("section", "source"),
                    default_from_type=LABEL, default_to_type=LABEL,
                ) as kg:
                    assert kg.uses_cypher_path
                    for weight, meta in observations:
                        kg.add(f"{node}_a", "rel", f"{node}_b", weight, timestamp=NOW, **meta)
                props = kg.edge(f"{node}_a", "rel", f"{node}_b")["props"]

                memory = MemoryGDB()
                memory.start()
                with KnowledgeGraph(memory, get_strategy("noisy_or"), batch_size=batch_size,
                                    accumulate=("section", "source")) as reference:
                    for weight, meta in observations:
                        reference.add(f"{node}_a", "rel", f"{node}_b", weight, timestamp=NOW, **meta)
                want = reference.edge(f"{node}_a", "rel", f"{node}_b")["props"]

                got_lists = (list(props.get("sections", [])), list(props.get("sources", [])))
                want_lists = (list(want["sections"]), list(want["sources"]))
                scalar_gone = "section" not in props and "source" not in props
                if got_lists == want_lists == (["16(a)", "19(b)"], ["semantic", "naive"]) and scalar_gone:
                    print(f"ok    accumulated provenance    batch={batch_size:<3} {got_lists[0]} {got_lists[1]}")
                else:
                    failures += 1
                    print(
                        f"FAIL  accumulated provenance    batch={batch_size:<3} "
                        f"cypher={got_lists} python={want_lists} scalars_removed={scalar_gone}"
                    )

            # The Python path writes through the same schema.
            with KnowledgeGraph(db, get_strategy("gated"), default_from_type=LABEL,
                                default_to_type=LABEL) as kg:
                assert not kg.uses_cypher_path
                kg.add(f"{PREFIX}_g", "rel", f"{PREFIX}_h", 1.0, timestamp=NOW)
                kg.add(f"{PREFIX}_g", "rel", f"{PREFIX}_h", 0.2, timestamp=NOW)
            edge = kg.edge(f"{PREFIX}_g", "rel", f"{PREFIX}_h")
            if edge and "gate" in edge["props"] and edge["observations"] == 2:
                print(f"ok    python path stores extra props (gate={edge['props']['gate']:.4f})")
            else:
                failures += 1
                print(f"FAIL  python path stores extra props: {edge}")
        finally:
            removed = cleanup(db)
            print(f"\nCleaned up {removed} test nodes")
            print(f"Graph holds {db.counts()}")

    print(f"\n{'FAILED' if failures else 'All checks passed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
