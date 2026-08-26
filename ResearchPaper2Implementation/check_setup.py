"""Dependency-free preflight for the APP run.

Renders the real prompt templates against the real few-shot files and dataset, loads the
seed schema exactly the way EDC.__init__ does, and runs EDC's own output parsers over the
few-shot answers. Catches format_map KeyErrors, CSV shape problems and encoding faults
before any paid API call.
"""

import csv
import io
import os
import sys
import types

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "edc-main", "edc-main")

# Stub the heavy third-party imports so edc.utils.llm_utils can be imported for its
# pure-python parsers without torch/transformers/openai being installed.
for name in ("openai", "torch", "transformers", "sentence_transformers"):
    if name not in sys.modules:
        mod = types.ModuleType(name)
        mod.__getattr__ = lambda attr: type(attr, (), {})
        sys.modules[name] = mod

sys.path.insert(0, ROOT)
import edc.utils.llm_utils as llm_utils  # noqa: E402


def read(path):
    with io.open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return fh.read()


failures = []


def check(label, condition, detail=""):
    print("{:<4} {}{}".format("ok" if condition else "FAIL", label,
                              "" if condition else "  -> " + detail))
    if not condition:
        failures.append(label)


# 1. Dataset
dataset = read("datasets/app_schedule1.txt").splitlines()
dataset = [line for line in dataset if line.strip()]
check("dataset loads, no blank documents", len(dataset) > 100, "got %d" % len(dataset))
check("every document is self-contained (mentions an APP or the Schedule)",
      all(("Australian Privacy Principle" in d or "Schedule" in d) for d in dataset))
check("no mojibake from cp1252 decoding", not any("â" in d for d in dataset))

# 2. Seed schema, loaded exactly as EDC.__init__ does
schema = {}
with io.open(os.path.join(ROOT, "schemas/app_seed.csv"), encoding="utf-8", newline="") as fh:
    for row in csv.reader(fh):
        relation, relation_definition = row      # EDC unpacks blind; a bad row raises here
        schema[relation] = relation_definition
check("seed schema unpacks to (relation, definition)", len(schema) > 0, "got %d" % len(schema))

# 3. OIE prompt renders
oie_prompt = read("prompt_templates/oie_template.txt").format_map({
    "few_shot_examples": read("few_shot_examples/app/oie_few_shot_examples.txt"),
    "input_text": dataset[0],
    "entities_hint": None,
    "relations_hint": None,
})
check("OIE prompt renders", "{" not in oie_prompt.replace("{'", "").replace("'}", ""))

# 4. SD prompt renders
sd_prompt = read("prompt_templates/sd_template.txt").format_map({
    "text": dataset[0],
    "few_shot_examples": read("few_shot_examples/app/sd_few_shot_examples.txt"),
    "relations": {"must protect"},
    "triples": [["APP entity", "must protect", "personal information"]],
})
check("SD prompt renders", "{few_shot_examples}" not in sd_prompt)

# 5. EDC's triple parser round-trips the OIE few-shot answers
few_shot_oie = read("few_shot_examples/app/oie_few_shot_examples.txt")
parsed_examples = [llm_utils.parse_raw_triplets(block.split("Triplets:", 1)[1])
                   for block in few_shot_oie.split("Example ")[1:]]
check("all OIE few-shot answers parse", all(len(p) > 0 for p in parsed_examples),
      str([len(p) for p in parsed_examples]))
check("all OIE few-shot triples are 3-tuples of str",
      all(len(t) == 3 and all(isinstance(x, str) for x in t)
          for p in parsed_examples for t in p))

# 6. EDC's definition parser round-trips the SD few-shot answers
few_shot_sd = read("few_shot_examples/app/sd_few_shot_examples.txt")
defined = {}
for block in few_shot_sd.split("Example ")[1:]:
    defined.update(llm_utils.parse_relation_definition(block.split("Answer:", 1)[1]))
check("all SD few-shot answers parse", len(defined) >= 18, "got %d" % len(defined))

# 7. Every relation the few-shots teach exists in the seed schema, so canonicalization
#    has a target to retrieve rather than immediately enriching.
taught = {t[1] for p in parsed_examples for t in p}
missing = sorted(taught - set(schema))
check("few-shot relations are all seeded in the schema", not missing, str(missing))

# 8. Relations that get defined must match the ones taught, or SD/SC disagree.
undefined = sorted(taught - set(defined))
check("few-shot relations that SD examples never define", not undefined, str(undefined))

print("\ndocuments: {}   seed relations: {}   defined in SD few-shots: {}".format(
    len(dataset), len(schema), len(defined)))
print("\n--- rendered OIE prompt, last 600 chars ---")
print(oie_prompt[-600:])

sys.exit(1 if failures else 0)
