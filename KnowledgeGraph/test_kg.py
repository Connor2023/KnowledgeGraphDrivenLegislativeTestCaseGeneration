"""
Offline checks for the tuple ingestion path and the augmentation strategies.

Runs against :class:`MemoryGDB`, so no Aura instance is required:

    python test_kg.py
"""

from __future__ import annotations

from augmentation import (
    BoundedHebbian,
    CallableStrategy,
    EdgeState,
    ExponentialMovingAverage,
    GatedEMA,
    Max,
    NoisyOr,
    RunningMean,
    Sum,
    Triple,
    get_strategy,
)
from kg import KnowledgeGraph
from memory_gdb import MemoryGDB


def close(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


#: Pinning the ingestion time keeps time-dependent strategies (decay, gated)
#: deterministic, so batched and unbatched runs are comparable exactly.
FIXED_NOW = 1_700_000_000.0


def build(strategy, tuples, **kwargs) -> tuple[KnowledgeGraph, MemoryGDB]:
    db = MemoryGDB()
    db.start()
    kg = KnowledgeGraph(db, strategy, **kwargs)
    kg.add_many(tuples, timestamp=FIXED_NOW)
    kg.flush()
    return kg, db


def test_ema_matches_the_worked_example():
    """0.9 * old + 0.1 * incoming, applied once per duplicate tuple."""
    tuples = [
        ("user", "can view", "dashboard", 1.0),
        ("user", "can view", "dashboard", 0.0),
        ("user", "can view", "dashboard", 0.0),
    ]
    kg, _ = build(ExponentialMovingAverage(0.9, 0.1), tuples)
    # 1.0 -> 0.9*1.0 + 0.1*0.0 = 0.9 -> 0.9*0.9 = 0.81
    assert close(kg.weight("user", "can view", "dashboard"), 0.81), kg.weight("user", "can view", "dashboard")

    edge = kg.edge("user", "can view", "dashboard")
    assert edge["observations"] == 3, edge


def test_batching_does_not_change_the_result():
    """Folding duplicates inside a batch must match strict write-through."""
    tuples = [("a", "r", "b", w) for w in (0.4, 0.9, 0.2, 0.7, 0.55)]
    tuples += [("a", "other", "b", 0.3), ("c", "r", "b", 0.8)]

    for strategy_factory in (
        lambda: ExponentialMovingAverage(0.9, 0.1),
        lambda: NoisyOr(),
        lambda: RunningMean(),
        lambda: Sum(),
        lambda: Max(),
        lambda: BoundedHebbian(0.25),
        lambda: GatedEMA(),
    ):
        one, _ = build(strategy_factory(), tuples, batch_size=1)
        many, _ = build(strategy_factory(), tuples, batch_size=100)
        for key in [("a", "r", "b"), ("a", "other", "b"), ("c", "r", "b")]:
            w1, w2 = one.weight(*key), many.weight(*key)
            assert close(w1, w2, 1e-12), (strategy_factory().name, key, w1, w2)


def test_distinct_relationships_are_distinct_edges():
    """The bug the original MERGE had: two relations collapsing into one edge."""
    tuples = [
        ("user", "can view", "dashboard", 0.9),
        ("user", "can edit", "dashboard", 0.4),
    ]
    kg, db = build(ExponentialMovingAverage(), tuples)
    assert db.counts()["relationships"] == 2, db.counts()
    assert close(kg.weight("user", "can view", "dashboard"), 0.9)
    assert close(kg.weight("user", "can edit", "dashboard"), 0.4)


def test_shared_entity_is_one_node():
    """An entity appearing as both subject and object must not be duplicated."""
    tuples = [("session", "expires", "token", 0.5), ("token", "belongs to", "session", 0.5)]
    _, db = build(ExponentialMovingAverage(), tuples, default_from_type="User",
                  default_to_type="PostCondition")
    assert db.counts()["nodes"] == 2, db.nodes
    assert db.nodes["session"] == {"Entity", "User", "PostCondition"}, db.nodes["session"]


def test_a_plain_function_can_be_swapped_in():
    """The scalar (old, new) signature of the original KG.augment_relationship."""

    def augment_relationship(past_strength, new_strength):
        if past_strength is None:
            return new_strength
        return 0.5 * past_strength + 0.5 * new_strength

    kg, _ = build(augment_relationship, [("a", "r", "b", 1.0), ("a", "r", "b", 0.0)])
    assert close(kg.weight("a", "r", "b"), 0.5), kg.weight("a", "r", "b")

    # ...and the rich signature, which also sees the observation count.
    def confidence_weighted(current: EdgeState | None, incoming: Triple) -> float:
        if current is None:
            return incoming.weight
        n = current.observations
        return (current.weight * n + incoming.weight) / (n + 1)

    kg, _ = build(confidence_weighted, [("a", "r", "b", 1.0), ("a", "r", "b", 0.0)])
    assert close(kg.weight("a", "r", "b"), 0.5), kg.weight("a", "r", "b")
    assert CallableStrategy(augment_relationship).style == "scalar"
    assert CallableStrategy(confidence_weighted).style == "rich"


def test_strategy_can_persist_extra_properties():
    """A dict return writes model diagnostics onto the edge alongside the weight."""
    kg, _ = build(GatedEMA(), [("a", "r", "b", 1.0), ("a", "r", "b", 0.2)])
    edge = kg.edge("a", "r", "b")
    assert "gate" in edge["props"], edge["props"]
    gate = edge["props"]["gate"]
    assert 0.0 < gate < 1.0, gate
    assert close(edge["weight"], gate * 1.0 + (1 - gate) * 0.2), edge


def test_strategy_can_be_swapped_mid_stream():
    db = MemoryGDB()
    db.start()
    kg = KnowledgeGraph(db, ExponentialMovingAverage(0.9, 0.1), batch_size=100)
    kg.add("a", "r", "b", 1.0)
    kg.set_strategy(Sum())
    kg.add("a", "r", "b", 0.5)
    kg.flush()
    assert close(kg.weight("a", "r", "b"), 1.5), kg.weight("a", "r", "b")


def test_accumulated_provenance_keeps_every_value():
    """A fact asserted in several sections must remember all of them."""
    db = MemoryGDB()
    db.start()
    with KnowledgeGraph(db, NoisyOr(), batch_size=100,
                        accumulate=("section", "source")) as kg:
        kg.add("crn", "PRESCRIBED_AS", "identifier", 0.9, section="16(a)", source="semantic")
        kg.add("crn", "PRESCRIBED_AS", "identifier", 0.6, section="19(b)", source="naive")
        kg.add("crn", "PRESCRIBED_AS", "identifier", 0.6, section="16(a)", source="naive")

    props = kg.edge("crn", "PRESCRIBED_AS", "identifier")["props"]
    assert props["sections"] == ["16(a)", "19(b)"], props          # order kept, no repeat
    assert props["sources"] == ["semantic", "naive"], props
    assert "section" not in props and "source" not in props, props  # not also stored scalar


def test_accumulators_survive_across_batches():
    """The list must extend an edge already in the database, not restart."""
    db = MemoryGDB()
    db.start()
    for section in ("16(a)", "19(b)", "16(a)"):
        with KnowledgeGraph(db, NoisyOr(), batch_size=1, accumulate=("section",)) as kg:
            kg.add("a", "R", "b", 0.5, section=section)
    assert kg.edge("a", "R", "b")["props"]["sections"] == ["16(a)", "19(b)"]


def test_scalar_provenance_still_overwrites_when_not_accumulated():
    """Without `accumulate`, the previous behaviour is unchanged."""
    db = MemoryGDB()
    db.start()
    with KnowledgeGraph(db, NoisyOr(), batch_size=100) as kg:
        kg.add("a", "R", "b", 0.9, section="16(a)")
        kg.add("a", "R", "b", 0.6, section="19(b)")
    assert kg.edge("a", "R", "b")["props"]["section"] == "19(b)"


def test_accumulate_accepts_a_mapping():
    db = MemoryGDB()
    db.start()
    with KnowledgeGraph(db, NoisyOr(), accumulate={"section": "cited_in"}) as kg:
        kg.add("a", "R", "b", 0.9, section="16(a)")
    assert kg.edge("a", "R", "b")["props"]["cited_in"] == ["16(a)"]


def test_unique_waves_preserve_order():
    triples = [Triple("a", "r", "b", w) for w in (1, 2, 3)] + [Triple("c", "r", "d", 4.0)]
    waves = KnowledgeGraph._unique_waves(triples)
    assert [len(w) for w in waves] == [2, 1, 1], waves
    assert [t.weight for wave in waves for t in wave] == [1, 4, 2, 3]


def test_registry_parses_parameters():
    strategy = get_strategy("ema:0.8,0.2")
    assert (strategy.memory, strategy.learning) == (0.8, 0.2)
    assert get_strategy("noisy_or").supports_cypher
    assert not get_strategy("gated").supports_cypher


def test_closed_form_strategies_agree_with_their_cypher():
    """Sanity-check each Cypher expression against its Python twin by hand."""
    old, new = 0.6, 0.25
    current = EdgeState(weight=old, observations=3, first_seen=0.0, last_seen=0.0)
    incoming = Triple("a", "r", "b", new, timestamp=0.0)
    expected = {
        "ema": 0.9 * old + 0.1 * new,
        "sum": old + new,
        "max": max(old, new),
        "mean": (old * 3 + new) / 4,
        "noisy_or": 1 - (1 - old) * (1 - new),
        "hebbian": old + 0.1 * new * (1 - old),
    }
    for name, want in expected.items():
        got = get_strategy(name).augment(current, incoming)
        assert close(float(got), want), (name, got, want)


def test_decay_forgets_over_time():
    strategy = get_strategy("decay_ema")  # half life of one day
    stale = EdgeState(weight=1.0, observations=1, first_seen=0.0, last_seen=0.0)
    fresh = EdgeState(weight=1.0, observations=1, first_seen=0.0, last_seen=86_400.0)
    incoming = Triple("a", "r", "b", 0.0, timestamp=86_400.0)
    assert close(strategy.augment(stale, incoming), 0.9 * 0.5)
    assert close(strategy.augment(fresh, incoming), 0.9)


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    failures = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {test.__name__}: {exc}")
        else:
            print(f"ok    {test.__name__}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
