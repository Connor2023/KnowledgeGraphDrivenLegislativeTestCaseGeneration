"""
Co-occurrence statistics over extracted entities.

When given a phrase to generate for:
- It extracts nouns/entities from the phrase
- Searches for these in the graph structure
- Uses associated entities (which are semantically connected) when generating
  the relevant test case

This module is import-safe: it computes statistics and yields tuples, and does
not touch the database.  Ingestion lives in ``build_kg.py``; the rule that
decides how a repeated relationship changes an edge weight lives in
``augmentation.py``.
"""

from collections import Counter
import math

from augmentation import ExponentialMovingAverage

#: The default ``augment_relationship`` rule: a duplicate relationship moves the
#: stored weight one tenth of the way towards the incoming weight.
DEFAULT_STRATEGY = ExponentialMovingAverage(memory=0.9, learning=0.1)

CO_OCCURS_WITH = "co_occurs_with"


class KG:
    LEARNING_RATE = 0.95
    MEMORY_RATE = 0.8

    def __init__(self):
        self.pair_counter = Counter()
        self.entity_counter = Counter()
        self.u_all = 0
        self.u_all_entities = 0
        self.entity_pairs = None

    # Count co-occurrence pairs and single nouns
    def set_up(self, entity_counts, entity_pairs):
        self.entity_pairs = entity_pairs
        for from_entity, to_entity in entity_pairs:
            self.pair_counter[tuple(sorted([from_entity, to_entity]))] += 1
        for entity, count in entity_counts:
            self.entity_counter[entity] = count

        self.u_all = sum(self.pair_counter.values())
        self.u_all_entities = sum(self.entity_counter.values())

    # Probabilities
    def p_ab(self, a, b):
        key = tuple(sorted([a, b]))
        u_ab = self.pair_counter.get(key, 0)
        return u_ab / self.u_all if self.u_all > 0 else 0.0

    def p(self, a):
        u_a = self.entity_counter.get(a, 0)
        return u_a / self.u_all_entities if self.u_all_entities > 0 else 0.0

    # Associative strength R_ab
    def R_ab(self, a, b):
        pab = self.p_ab(a, b)
        pa, pb = self.p(a), self.p(b)
        if pab == 0 or pa == 0 or pb == 0:
            return 0.0
        numerator = math.log(pab / (pa * pb))
        denominator = math.log(2) * (pa + pb)
        return numerator / denominator

    def construct(self, relationship=CO_OCCURS_WITH):
        """Yield ``(from_entity, relationship, to_entity, weight)`` tuples.

        Weights are the associative strength R_ab, so the output can be fed
        straight into ``KnowledgeGraph.add_many`` alongside the extracted
        triples.  Each unordered pair is emitted once.
        """
        for a, b in self.pair_counter:
            strength = self.R_ab(a, b)
            if strength:
                yield (a, relationship, b, strength)

    @staticmethod
    def augment_relationship(past_strength, new_strength):
        """Weight for an edge that already exists, given a new observation.

        Kept as a module-level entry point for backwards compatibility; the rule
        itself is :data:`DEFAULT_STRATEGY`, and every ingestion path takes the
        strategy as a parameter so it can be swapped without editing this file.
        """
        return DEFAULT_STRATEGY.augment(
            None if past_strength is None else _state(past_strength),
            _incoming(new_strength),
        )


def _state(weight):
    from augmentation import EdgeState

    return EdgeState(weight=float(weight))


def _incoming(weight):
    from augmentation import Triple

    return Triple("", "", "", float(weight))


def normalise(phrase: str) -> str:
    """Lower-case, strip, and drop a leading article."""
    phrase = phrase.strip().lower()
    if not phrase:
        return ""
    first_word = phrase.split()[0]
    if len(first_word) + 1 < len(phrase) and first_word in ["a", "an", "the"]:
        return phrase[len(first_word) + 1:].strip()
    return phrase
