"""
When given a phrase to generate for:
- It extracts nouns/entities from the phrase
- Searches for these in the graph structure
- Uses associated entities (which are semantically connected) when generating the relevant test case
"""

from collections import Counter
import math
import json
from neo4j_gdb import Neo4JGDB

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
    
    def construct(self):
        for from_entity, to_entity in self.entity_pairs:
            pass

    def augment_relationship(past_strength, new_strength):
        return KG.MEMORY_RATE * past_strength + KG.LEARNING_RATE * new_strength


def normalise(phrase: str):
    phrase = phrase.strip().lower()
    first_word = phrase.split()[0]
    if len(first_word) + 1 < len(phrase) and first_word in ["a", "an", "the"]:
        return phrase[len(first_word) + 1:]
    return phrase

# Extraction
with open("requirements_pronouns_normalised.json", "r", encoding="utf-8") as f:
    data = json.load(f)

triples = []            # (subject, object, relation, confidence)
def extract_triple(t):
    s, r, o = [normalise(v) for v in t["triple"]]
    c = t["confidence"]
    triples.append((s, o, r, c))

for story in data:
    for key in story:
        if key == "acceptanceCriteria":
            for criteria in story[key]:
                for lst in criteria["ollie"].values():
                    for triple in lst:
                        extract_triple(triple)
        elif key != "ID":
            for parts in story[key]:
                for part in parts["parts"]:
                    for triple in part["ollie"]:
                        extract_triple(triple)

print(len(triples))


USER = "User"
POST_CONDITION = "PostCondition"

with Neo4JGDB("neo4j+s://18c2042c.databases.neo4j.io", ("neo4j", "***REMOVED***")) as db:
    db.clear()
    print(f"Adding triples, expected time = {round(0.5 * len(triples) / 60, 2)} minutes")
    for i in range(len(triples)):
        if i % 100 == 0:
            print(i)
        t = triples[i]
        for et, entity in [(USER, 0), (POST_CONDITION, 1)]:
            db.create_new_entity(et, t[entity])

        rel = db.get_relationship(USER, t[0], POST_CONDITION, t[1], t[2])
        if rel is not None:
            db.update_relationship(USER, t[0], POST_CONDITION, t[1], t[2], KG.augment_relationship(rel['strength'], t[3]))
        else:
            db.update_relationship(USER, t[0], POST_CONDITION, t[1], t[2], t[3])

