"""
How to vary the augmentation rule.

Every example below is the same ingestion code with a different rule plugged in;
nothing else changes.  Run it with no database:

    python example_usage.py
"""

from __future__ import annotations

from augmentation import (
    AugmentStrategy,
    EdgeState,
    ExponentialMovingAverage,
    GatedEMA,
    NoisyOr,
    Triple,
)
from kg import KnowledgeGraph
from memory_gdb import MemoryGDB

TUPLES = [
    ("user", "can view", "dashboard", 0.90),
    ("user", "can view", "dashboard", 0.40),
    ("user", "can view", "dashboard", 0.55),
    ("user", "can edit", "dashboard", 0.70),
    ("dashboard", "displays", "task progress", 0.65),
]


def run(strategy, label: str) -> None:
    db = MemoryGDB()
    db.start()
    with KnowledgeGraph(db, strategy, default_from_type="User",
                        default_to_type="PostCondition") as kg:
        kg.add_many(TUPLES)
    weight = kg.weight("user", "can view", "dashboard")
    print(f"  {label:<34} user -[can view]-> dashboard = {weight:.4f}")


# --------------------------------------------------------------------------- #
# 1. Built-in rules
# --------------------------------------------------------------------------- #

print("Built-in strategies (0.90, then 0.40, then 0.55 on the same edge):")
run(ExponentialMovingAverage(0.9, 0.1), "ema(0.9, 0.1)  <- the brief")
run(ExponentialMovingAverage(0.5, 0.5), "ema(0.5, 0.5)")
run(NoisyOr(), "noisy_or")
run("mean", "mean (by registry name)")


# --------------------------------------------------------------------------- #
# 2. A plain function
# --------------------------------------------------------------------------- #
# Two positional arguments are read as (old_weight, new_weight) - the signature
# the original KG.augment_relationship used.  old_weight is None on first sight.

def augment_relationship(past_strength, new_strength):
    if past_strength is None:
        return new_strength
    return 0.9 * past_strength + 0.1 * new_strength


print("\nA plain function:")
run(augment_relationship, "augment_relationship")
run(lambda old, new: new if old is None else max(old, new), "lambda: keep the strongest")


# --------------------------------------------------------------------------- #
# 3. A function that needs more than the two weights
# --------------------------------------------------------------------------- #
# Any other signature is passed (EdgeState | None, Triple), so the rule can see
# the observation count, the timestamps and the incoming tuple's metadata.

def diminishing(current: EdgeState | None, incoming: Triple) -> float:
    """Later observations of an edge move it less and less."""
    if current is None:
        return incoming.weight
    learning = 1.0 / (1.0 + current.observations)
    return (1 - learning) * current.weight + learning * incoming.weight


print("\nA function that uses the edge's history:")
run(diminishing, "diminishing")


# --------------------------------------------------------------------------- #
# 4. A neurosymbolic rule
# --------------------------------------------------------------------------- #
# The symbolic part is the EMA update; the neural part decides the memory/
# learning split per update.  Subclassing gets a Cypher-free strategy, which the
# builder detects and evaluates in Python.

class ModelGatedEMA(AugmentStrategy):
    name = "model_gated"
    cypher_update = None  # cannot be pushed into the database

    def __init__(self, model):
        self.model = model

    def augment(self, current, incoming):
        if current is None:
            return incoming.weight
        features = [
            current.weight,
            incoming.weight,
            float(current.observations),
            current.seconds_since_update(incoming.timestamp),
        ]
        gate = float(self.model(features))          # e.g. torch: model(tensor).item()
        return {
            "weight": gate * current.weight + (1 - gate) * incoming.weight,
            "gate": gate,                            # extra keys are stored on the edge
        }


print("\nNeurosymbolic:")
run(ModelGatedEMA(model=lambda f: 0.75), "ModelGatedEMA (stub model)")
run(GatedEMA(), "GatedEMA (built-in)")


# --------------------------------------------------------------------------- #
# 5. Against the real database
# --------------------------------------------------------------------------- #

print(
    """
Against Aura, the only difference is the backend:

    from config import load_credentials
    from neo4j_gdb import Neo4JGDB

    creds = load_credentials()
    with Neo4JGDB(creds.uri, creds.auth, database=creds.database) as db:
        db.ensure_schema()
        with KnowledgeGraph(db, ExponentialMovingAverage(0.9, 0.1),
                            default_from_type="User",
                            default_to_type="PostCondition") as kg:
            kg.add_many(triples)
        print(kg.top_edges(10))

A strategy that sets `cypher_update` is evaluated inside the database in the
same query as the MERGE; one that does not is evaluated in Python, which costs
one extra round trip per batch.  Either way the ingestion code is identical."""
)
