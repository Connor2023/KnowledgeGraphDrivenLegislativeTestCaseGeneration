"""
Pluggable weight-augmentation strategies for the knowledge graph.

Every fact pushed into the graph is a tuple ``(from_entity, relationship,
to_entity, weight)``.  When a tuple arrives, exactly one function decides what
the stored edge weight becomes:

    new_weight = strategy(current_edge_state_or_None, incoming_triple)

``current`` is ``None`` the first time an edge is seen, so a strategy has full
control over both initialisation and reinforcement.  Swapping the strategy is
the only change needed to change how the graph learns.

Two execution paths are supported:

1. **Python path** (always available).  The builder reads the current edge state
   out of Neo4j, calls the strategy in Python, then writes the result back.  Use
   this for anything that cannot be expressed in Cypher - e.g. a torch model.
2. **Cypher path** (opt-in).  A strategy that *can* express itself as a Cypher
   expression sets ``cypher_update``; the builder folds the update into the same
   query as the MERGE, halving the round trips and making the read-modify-write
   atomic.  Leave ``cypher_update`` as ``None`` to force the Python path.

Cypher expressions may reference these identifiers:

    old_weight, old_observations, old_first_seen, old_last_seen  - edge, pre-update
    row.weight, row.now                                          - incoming tuple

``old_weight`` is ``NULL`` on first observation, in which case ``cypher_first``
is evaluated instead.
"""

from __future__ import annotations

import inspect
import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

# exp(-LN2 * dt / half_life) == 0.5 ** (dt / half_life)
_LN2 = math.log(2.0)


# --------------------------------------------------------------------------- #
# Data carried in and out of a strategy
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class Triple:
    """One incoming fact: (from_entity, relationship, to_entity, weight)."""

    from_entity: str
    relationship: str
    to_entity: str
    weight: float = 1.0
    from_type: str | None = None      # optional role label, e.g. "User"
    to_type: str | None = None        # optional role label, e.g. "PostCondition"
    timestamp: float | None = None    # epoch seconds; defaults to ingestion time
    meta: Mapping[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.from_entity, self.relationship, self.to_entity)

    @classmethod
    def from_tuple(cls, t, **defaults) -> "Triple":
        """Build from a plain ``(from, relationship, to, weight)`` tuple."""
        from_entity, relationship, to_entity, *rest = t
        weight = float(rest[0]) if rest else 1.0
        return cls(from_entity, relationship, to_entity, weight, **defaults)


@dataclass(frozen=True, slots=True)
class EdgeState:
    """What the graph already knows about an edge, before this update."""

    weight: float
    observations: int = 0
    first_seen: float | None = None
    last_seen: float | None = None
    props: Mapping[str, Any] = field(default_factory=dict)

    def seconds_since_update(self, now: float | None = None) -> float:
        if self.last_seen is None:
            return 0.0
        return max(0.0, (now if now is not None else time.time()) - self.last_seen)


# --------------------------------------------------------------------------- #
# Strategy base class
# --------------------------------------------------------------------------- #

class AugmentStrategy(ABC):
    """Base class for every ``augment_relationship`` implementation.

    Subclasses must implement :meth:`augment`.  They may optionally set
    ``cypher_update`` / ``cypher_first`` to enable the single-round-trip path.
    """

    name: str = "augment"
    cypher_update: str | None = None
    cypher_first: str = "row.weight"

    @abstractmethod
    def augment(self, current: EdgeState | None, incoming: Triple) -> float | dict[str, Any]:
        """Return the new edge weight, or a dict of edge properties.

        A dict must contain a ``weight`` key; any other keys are written onto the
        relationship too (useful for storing model diagnostics alongside the edge).
        """

    # Strategies are callable so a bare function can be swapped in anywhere one
    # of these objects is expected.
    def __call__(self, current: EdgeState | None, incoming: Triple) -> float | dict[str, Any]:
        return self.augment(current, incoming)

    @property
    def supports_cypher(self) -> bool:
        return self.cypher_update is not None

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r}>"


def _clamp(value: float, bounds: tuple[float, float] | None) -> float:
    if bounds is None:
        return value
    low, high = bounds
    return min(max(value, low), high)


def _clamp_cypher(expr: str, bounds: tuple[float, float] | None) -> str:
    if bounds is None:
        return expr
    low, high = bounds
    return (
        f"CASE WHEN ({expr}) < {low!r} THEN {low!r} "
        f"WHEN ({expr}) > {high!r} THEN {high!r} ELSE ({expr}) END"
    )


# --------------------------------------------------------------------------- #
# Closed-form strategies (both execution paths available)
# --------------------------------------------------------------------------- #

class Replace(AugmentStrategy):
    """Last write wins - the behaviour of the original ``update_relationship``."""

    name = "replace"
    cypher_update = "row.weight"

    def augment(self, current, incoming):
        return incoming.weight


class Sum(AugmentStrategy):
    """Accumulate evidence: repeated observations keep pushing the weight up."""

    name = "sum"
    cypher_update = "old_weight + row.weight"

    def augment(self, current, incoming):
        return incoming.weight if current is None else current.weight + incoming.weight


class Max(AugmentStrategy):
    """Keep the strongest observation ever seen."""

    name = "max"
    cypher_update = "CASE WHEN old_weight > row.weight THEN old_weight ELSE row.weight END"

    def augment(self, current, incoming):
        return incoming.weight if current is None else max(current.weight, incoming.weight)


class RunningMean(AugmentStrategy):
    """Unweighted mean over every observation of the edge."""

    name = "mean"
    cypher_update = (
        "(old_weight * old_observations + row.weight) / (old_observations + 1.0)"
    )

    def augment(self, current, incoming):
        if current is None:
            return incoming.weight
        n = max(current.observations, 1)
        return (current.weight * n + incoming.weight) / (n + 1.0)


class ExponentialMovingAverage(AugmentStrategy):
    """``new = memory * old + learning * incoming``.

    This is the worked example from the brief: with ``memory=0.9`` and
    ``learning=0.1`` a duplicate relationship nudges the stored weight one tenth
    of the way towards the incoming weight, so an edge reinforced by consistent
    evidence converges on that evidence while a single outlier barely moves it.

    ``memory + learning == 1`` keeps the weight inside the range of the inputs;
    the two are independent parameters so asymmetric variants (the 0.8 / 0.95
    pair from the original ``KG`` class, say) are still expressible.
    """

    def __init__(
        self,
        memory: float = 0.9,
        learning: float = 0.1,
        *,
        clamp: tuple[float, float] | None = None,
    ):
        self.memory = float(memory)
        self.learning = float(learning)
        self.clamp = clamp
        self.name = f"ema({self.memory:g},{self.learning:g})"
        self.cypher_update = _clamp_cypher(
            f"{self.memory!r} * old_weight + {self.learning!r} * row.weight", clamp
        )

    def augment(self, current, incoming):
        if current is None:
            return _clamp(incoming.weight, self.clamp)
        return _clamp(self.memory * current.weight + self.learning * incoming.weight, self.clamp)


class TimeDecayedEMA(AugmentStrategy):
    """EMA whose memory term decays with wall-clock age.

    An edge that has not been reinforced for a long time forgets; one that is
    reinforced constantly holds its weight.  ``half_life`` is in seconds.
    """

    def __init__(
        self,
        memory: float = 0.9,
        learning: float = 0.1,
        half_life: float = 86_400.0,
        *,
        clamp: tuple[float, float] | None = None,
    ):
        self.memory = float(memory)
        self.learning = float(learning)
        self.half_life = float(half_life)
        self.clamp = clamp
        self.name = f"decay_ema({self.memory:g},{self.learning:g},{self.half_life:g})"
        decay = (
            f"exp(-{_LN2!r} * (row.now - coalesce(old_last_seen, row.now)) / {self.half_life!r})"
        )
        self.cypher_update = _clamp_cypher(
            f"{self.memory!r} * old_weight * {decay} + {self.learning!r} * row.weight", clamp
        )

    def augment(self, current, incoming):
        if current is None:
            return _clamp(incoming.weight, self.clamp)
        now = incoming.timestamp if incoming.timestamp is not None else time.time()
        decay = math.exp(-_LN2 * current.seconds_since_update(now) / self.half_life)
        return _clamp(
            self.memory * current.weight * decay + self.learning * incoming.weight, self.clamp
        )


class NoisyOr(AugmentStrategy):
    """Probabilistic fusion: ``1 - (1 - old)(1 - incoming)``.

    The right choice when weights are independent confidences in [0, 1] - which
    is what the Ollie extractor emits.  Repeated weak evidence accumulates
    towards 1 without ever exceeding it.
    """

    name = "noisy_or"
    cypher_update = "1.0 - (1.0 - old_weight) * (1.0 - row.weight)"

    def augment(self, current, incoming):
        if current is None:
            return incoming.weight
        return 1.0 - (1.0 - current.weight) * (1.0 - incoming.weight)


class BoundedHebbian(AugmentStrategy):
    """``old + lr * incoming * (1 - old)`` - saturating reinforcement in [0, 1]."""

    def __init__(self, learning_rate: float = 0.1):
        self.learning_rate = float(learning_rate)
        self.name = f"hebbian({self.learning_rate:g})"
        self.cypher_update = (
            f"old_weight + {self.learning_rate!r} * row.weight * (1.0 - old_weight)"
        )

    def augment(self, current, incoming):
        if current is None:
            return incoming.weight
        return current.weight + self.learning_rate * incoming.weight * (1.0 - current.weight)


# --------------------------------------------------------------------------- #
# Neurosymbolic strategy (Python path only)
# --------------------------------------------------------------------------- #

class GatedEMA(AugmentStrategy):
    """EMA whose memory/learning split is decided per update by a learned gate.

    The symbolic half is the EMA update rule; the neural half is a gate that
    reads features of the edge and the incoming tuple and decides how much to
    remember:

        gate = sigmoid(w . [old_weight, incoming_weight, log1p(observations), recency])
        new  = gate * old + (1 - gate) * incoming

    A well-supported edge (many observations, high weight) gets a gate near 1 and
    resists change; a thinly-supported one moves readily.  The hand-set weights
    below are a stand-in for a trained model - replace :meth:`gate` with a call
    into torch and everything else keeps working, because this strategy declares
    no ``cypher_update`` and therefore runs on the Python path.

    Returns a dict so the gate value is persisted on the edge, which makes the
    model's decisions auditable after the fact.
    """

    name = "gated"
    cypher_update = None  # explicit: this cannot be pushed down into Cypher

    def __init__(
        self,
        weights: tuple[float, float, float, float] = (1.2, -0.8, 0.9, -0.4),
        bias: float = 1.0,
        recency_scale: float = 3600.0,
    ):
        self.weights = tuple(float(w) for w in weights)
        self.bias = float(bias)
        self.recency_scale = float(recency_scale)

    def features(self, current: EdgeState, incoming: Triple, now: float) -> tuple[float, ...]:
        return (
            current.weight,
            incoming.weight,
            math.log1p(current.observations),
            math.tanh(current.seconds_since_update(now) / self.recency_scale),
        )

    def gate(self, current: EdgeState, incoming: Triple, now: float) -> float:
        z = self.bias + sum(w * f for w, f in zip(self.weights, self.features(current, incoming, now)))
        return 1.0 / (1.0 + math.exp(-z))

    def augment(self, current, incoming):
        if current is None:
            return {"weight": incoming.weight, "gate": 0.0}
        now = incoming.timestamp if incoming.timestamp is not None else time.time()
        g = self.gate(current, incoming, now)
        return {"weight": g * current.weight + (1.0 - g) * incoming.weight, "gate": g}


# --------------------------------------------------------------------------- #
# Adapting plain functions
# --------------------------------------------------------------------------- #

class CallableStrategy(AugmentStrategy):
    """Wrap a plain function so it can be used as a strategy.

    Two calling conventions are accepted:

    * **scalar** - ``f(old_weight: float | None, new_weight: float) -> float``.
      This matches the original ``KG.augment_relationship`` signature.
    * **rich** - ``f(current: EdgeState | None, incoming: Triple) -> float | dict``.

    ``style="auto"`` picks scalar for two-positional-argument functions whose
    first parameter is not named ``current``/``state``/``edge``.
    """

    def __init__(self, fn: Callable, *, style: str = "auto", name: str | None = None,
                 cypher_update: str | None = None):
        self.fn = fn
        self.name = name or getattr(fn, "__name__", "callable")
        self.cypher_update = cypher_update
        self.style = self._resolve_style(fn, style)

    @staticmethod
    def _resolve_style(fn: Callable, style: str) -> str:
        if style != "auto":
            if style not in ("scalar", "rich"):
                raise ValueError(f"unknown style {style!r}; expected 'scalar', 'rich' or 'auto'")
            return style
        try:
            params = [
                p for p in inspect.signature(fn).parameters.values()
                if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
            ]
        except (TypeError, ValueError):
            return "rich"
        if len(params) == 2 and params[0].name.lower() not in ("current", "state", "edge"):
            return "scalar"
        return "rich"

    def augment(self, current, incoming):
        if self.style == "scalar":
            return self.fn(None if current is None else current.weight, incoming.weight)
        return self.fn(current, incoming)


def as_strategy(obj: AugmentStrategy | Callable | str | None) -> AugmentStrategy:
    """Coerce a strategy object, plain function, or registry name into a strategy."""
    if obj is None:
        return ExponentialMovingAverage(0.9, 0.1)
    if isinstance(obj, AugmentStrategy):
        return obj
    if isinstance(obj, str):
        return get_strategy(obj)
    if callable(obj):
        return CallableStrategy(obj)
    raise TypeError(f"cannot use {obj!r} as an augmentation strategy")


# --------------------------------------------------------------------------- #
# Registry - lets a strategy be chosen from a CLI flag or config file
# --------------------------------------------------------------------------- #

STRATEGIES: dict[str, Callable[..., AugmentStrategy]] = {
    "replace": Replace,
    "sum": Sum,
    "max": Max,
    "mean": RunningMean,
    "ema": ExponentialMovingAverage,
    "decay_ema": TimeDecayedEMA,
    "noisy_or": NoisyOr,
    "hebbian": BoundedHebbian,
    "gated": GatedEMA,
}


def get_strategy(spec: str) -> AugmentStrategy:
    """Build a strategy from a spec string, e.g. ``"ema"``, ``"ema:0.9,0.1"``.

    Arguments after the colon are passed positionally and parsed as floats.
    """
    name, _, raw_args = spec.partition(":")
    name = name.strip()
    if name not in STRATEGIES:
        raise KeyError(f"unknown strategy {name!r}; available: {', '.join(sorted(STRATEGIES))}")
    args = [float(a) for a in raw_args.split(",") if a.strip()] if raw_args else []
    return STRATEGIES[name](*args)
