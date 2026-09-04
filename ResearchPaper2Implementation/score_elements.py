"""Legal element coverage with an LLM judge. Tier 2 of the metric plan.

Replaces scenario counting, which cannot tell four scenarios covering four exception
limbs from four scenarios restating one. For each generated feature set and each element
of the target subclause, a judge decides whether the set addresses that proposition.

Four design decisions that the numbers depend on:

  one element per call   Elements are judged independently rather than as a checklist.
                         A single call listing 18 elements invites the model to anchor on
                         its earlier answers and to pattern-match down the list; separate
                         calls cost more and buy independence.

  verbatim evidence      The judge must quote the scenario text it relied on, and the
                         quote is checked against the feature file. An unverifiable quote
                         marks the judgement `quote_unverified` -- the same anti-
                         fabrication check the generator's citations already get, applied
                         to the evaluator.

  blinded                The judge never learns which arm produced a set, so it cannot
                         favour the graph arms or the controls.

  core vs cross-referenced
                         Reported separately throughout. An arm that cannot see
                         cross-references should score on `core` and fail on
                         `cross-referenced`; a single blended number would hide the only
                         effect the experiment is testing.

The judge is an LLM scoring LLM output, which G-Eval (Liu et al., EMNLP 2023) shows
carries a self-preference bias. Two mitigations are built in: `--judge-model` so the
judge can differ from the generator, and `--sample-for-human` / `--kappa` so agreement
with a human annotator can be measured and reported rather than assumed.

    python score_elements.py --dry-run          # how many calls, what it costs
    python score_elements.py                    # score everything (resumable)
    python score_elements.py --report-only      # rebuild the document
    python score_elements.py --sample-for-human 60
    python score_elements.py --kappa runs/elements/human_sample_annotated.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
import random
import sys

import yaml

from kg_testgen.config import (ENV_LLM_KEY_FALLBACK, ENV_LLM_KEY_PRIMARY, ConfigError)
from run_experiment import ARMS, SECTIONS, cell_dir

ELEMENTS_PATH = os.path.join("elements", "legal_elements.yaml")
OUT_DIR = "runs/elements"

# gpt-4o-mini list price, USD per 1M tokens; overridden per judge model below.
PRICES = {
    "gpt-4o-mini": (0.150, 0.600),
    "gpt-4o": (2.50, 10.00),
}

logger = logging.getLogger("score")


JUDGE_PROMPT = """\
You are evaluating whether a set of generated compliance test scenarios addresses one \
specific legal proposition drawn from Australian privacy legislation.

LEGAL PROPOSITION TO CHECK
--------------------------
{proposition}

THE STATUTORY PROVISION THESE SCENARIOS WERE WRITTEN FOR
--------------------------------------------------------
{section_text}

THE GENERATED SCENARIOS
-----------------------
{feature}

YOUR TASK
---------
Decide whether ANY scenario in the set addresses the legal proposition above.

It counts as addressed whether the scenario asserts the rule holds, tests that it is \
correctly NOT applied, or tests a violation of it. What matters is that the proposition \
is engaged with substantively.

It does NOT count if the scenario merely mentions related vocabulary, restates the \
provision generally without reaching this specific proposition, or covers a neighbouring \
proposition. Be strict: a proposition that a reader could only infer is not covered.

Note on form: these scenarios are written as assertions about what a privacy policy \
states, while the proposition is written as a rule of law. Judge on substance, not on \
whether the wording matches.

If it is covered, quote the scenario text you relied on EXACTLY as it appears above -- \
character for character, no paraphrasing, no ellipsis. If nothing covers it, say so; \
"not covered" is a perfectly good answer and many propositions genuinely are not.

Answer the JSON fields IN ORDER. The order is deliberate: state what the candidate \
scenario is actually about before deciding, so the verdict follows the analysis rather \
than the analysis excusing the verdict.

Reply with JSON only:
{{"closest_scenario": "the Scenario: line of the nearest candidate, or null if none",
  "what_it_is_about": "in one sentence, the proposition THAT scenario actually tests",
  "same_proposition": "does that match the proposition to check, or is it a different \
rule from the same clause? Answer in one sentence.",
  "evidence_quote": "verbatim text from the scenarios above, or null",
  "covered": true or false}}
"""


def llm_key_from_env():
    """Just the OpenAI key.

    Deliberately not `config.secrets_from_env`, which also demands the Neo4j
    credentials: scoring reads generated feature files off disk and never opens the
    graph, so requiring database credentials to run it would be a false dependency.
    """
    key = os.environ.get(ENV_LLM_KEY_PRIMARY) or os.environ.get(ENV_LLM_KEY_FALLBACK)
    if not key:
        raise ConfigError(
            "Missing %s (or %s). Dot-source setup_env.ps1 or set it in .env."
            % (ENV_LLM_KEY_PRIMARY, ENV_LLM_KEY_FALLBACK))
    return key


def load_elements(path=ELEMENTS_PATH):
    with io.open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def judgement_path(section_key, arm, repeat, element_id):
    return os.path.join(OUT_DIR, "%s__%s__r%d" % (section_key, arm, repeat),
                        "%s.json" % element_id.replace(".", "_"))


def read_cell_feature(section_key, arm, repeat):
    path = os.path.join(cell_dir(section_key, arm, repeat), "generated.feature")
    if not os.path.exists(path):
        return None
    with io.open(path, encoding="utf-8") as fh:
        return fh.read().strip()


def normalise_ws(text):
    """Collapse whitespace for quote checking.

    The judge reliably reproduces wording but not indentation, and a quote that differs
    only in leading spaces is still genuine evidence. Anything beyond whitespace counts
    as unverified.
    """
    return " ".join((text or "").split())


def call_judge(client, model, prompt, temperature=0.0):
    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    choice = completion.choices[0]
    usage = completion.usage
    return (json.loads(choice.message.content),
            usage.prompt_tokens, usage.completion_tokens)


def score_all(elements, args):
    from openai import OpenAI
    client = OpenAI(api_key=llm_key_from_env())

    total_in = total_out = calls = skipped = 0
    for skey, _path, _desc, app_no in SECTIONS:
        body = elements["sections"].get(app_no)
        if not body:
            logger.warning("no elements defined for APP %s; skipping", app_no)
            continue
        section_text = body["text"].strip()
        for arm, _label, _cfg in ARMS:
            for repeat in range(1, args.repeats + 1):
                feature = read_cell_feature(skey, arm, repeat)
                if feature is None:
                    logger.warning("  no feature for %s/%s/r%d", skey, arm, repeat)
                    continue
                for element in body["elements"]:
                    out = judgement_path(skey, arm, repeat, element["id"])
                    if os.path.exists(out) and not args.overwrite:
                        skipped += 1
                        continue
                    prompt = JUDGE_PROMPT.format(
                        proposition=element["proposition"].strip(),
                        section_text=section_text,
                        feature=feature)
                    try:
                        verdict, tin, tout = call_judge(client, args.judge_model, prompt)
                    except Exception as exc:  # noqa: BLE001 - one bad cell must not stop the grid
                        logger.error("  judge failed %s/%s/r%d/%s: %s",
                                     skey, arm, repeat, element["id"], exc)
                        continue
                    total_in += tin
                    total_out += tout
                    calls += 1

                    quote = verdict.get("evidence_quote")
                    covered = bool(verdict.get("covered"))
                    if covered and quote:
                        verified = normalise_ws(quote).lower() in normalise_ws(feature).lower()
                    else:
                        verified = None       # nothing to verify when nothing was claimed

                    record = {
                        "section": app_no, "section_key": skey, "arm": arm,
                        "repeat": repeat, "element_id": element["id"],
                        "tier": element["tier"], "covered": covered,
                        "scenario_name": verdict.get("closest_scenario"),
                        "evidence_quote": quote,
                        "quote_verified": verified,
                        "what_it_is_about": verdict.get("what_it_is_about"),
                        "same_proposition": verdict.get("same_proposition"),
                        "judge_model": args.judge_model,
                    }
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    with io.open(out, "w", encoding="utf-8") as fh:
                        json.dump(record, fh, indent=2)
                    if calls % 25 == 0:
                        logger.info("  %d calls made (%d skipped as cached)", calls, skipped)

    pin, pout = PRICES.get(args.judge_model, PRICES["gpt-4o-mini"])
    cost = total_in / 1e6 * pin + total_out / 1e6 * pout
    logger.info("Judge complete: %d calls, %d cached, %s in / %s out tokens, $%.4f",
                calls, skipped, "{:,}".format(total_in), "{:,}".format(total_out), cost)
    return calls, cost


def load_judgements(elements, repeats):
    """All judgements on disk, keyed (section_key, arm, repeat, element_id)."""
    out = {}
    for skey, _p, _d, app_no in SECTIONS:
        body = elements["sections"].get(app_no)
        if not body:
            continue
        for arm, _l, _c in ARMS:
            for repeat in range(1, repeats + 1):
                for element in body["elements"]:
                    path = judgement_path(skey, arm, repeat, element["id"])
                    if not os.path.exists(path):
                        continue
                    with io.open(path, encoding="utf-8") as fh:
                        out[(skey, arm, repeat, element["id"])] = json.load(fh)
    return out


def pct(numerator, denominator):
    return "--" if not denominator else "%d/%d (%.0f%%)" % (
        numerator, denominator, 100.0 * numerator / denominator)


def build_report(elements, judgements, repeats, judge_model):
    by_tier = {}
    for (skey, arm, repeat, eid), j in judgements.items():
        by_tier.setdefault((arm, j["tier"]), []).append(j)

    L = [
        "# Legal element coverage",
        "",
        "Tier 2 of the metric plan. Each cell's scenarios were judged against every "
        "element of its subclause, one element per call, blinded to which arm produced "
        "the set. Judge: `%s`." % judge_model,
        "",
        "**Read the two tiers separately.** `core` elements are derivable from the "
        "target section's own text; `cross-referenced` elements need the text of a "
        "provision the section points at. The gap between an arm's core and "
        "cross-referenced score is the effect the experiment is actually testing.",
        "",
        "---",
        "",
        "## Headline: coverage by arm",
        "",
        "Averaged over sections and repeats -- an element counts as covered in a run if "
        "the judge found it addressed in that run's scenarios.",
        "",
        "| Arm | Core | Cross-referenced | All |",
        "|---|---|---|---|",
    ]
    for arm, _label, _c in ARMS:
        row = []
        for tier in ("core", "cross-referenced"):
            js = by_tier.get((arm, tier), [])
            row.append(pct(sum(1 for j in js if j["covered"]), len(js)))
        allj = by_tier.get((arm, "core"), []) + by_tier.get((arm, "cross-referenced"), [])
        row.append(pct(sum(1 for j in allj if j["covered"]), len(allj)))
        L.append("| `%s` | %s | %s | %s |" % (arm, row[0], row[1], row[2]))

    L += ["", "## Per section", "",
          "| Section | Arm | Core | Cross-referenced |", "|---|---|---|---|"]
    for skey, _p, desc, app_no in SECTIONS:
        for arm, _l, _c in ARMS:
            cells = []
            for tier in ("core", "cross-referenced"):
                js = [j for (sk, a, r, e), j in judgements.items()
                      if sk == skey and a == arm and j["tier"] == tier]
                cells.append(pct(sum(1 for j in js if j["covered"]), len(js)))
            L.append("| %s | `%s` | %s | %s |" % (desc, arm, cells[0], cells[1]))

    # Stability, but on real semantic units this time rather than the tag proxy.
    L += ["", "---", "", "## Reliable coverage",
          "",
          "An element is *reliable* for an arm when all %d repeats covered it, and "
          "*reachable* when at least one did. The gap is the run-to-run instability the "
          "Tier 6 proxy could only estimate." % repeats,
          "",
          "| Arm | Reliable (all %d) | Reachable (any) | Reliability |" % repeats,
          "|---|---|---|---|"]
    for arm, _label, _c in ARMS:
        reliable = reachable = 0
        for skey, _p, _d, app_no in SECTIONS:
            body = elements["sections"].get(app_no)
            if not body:
                continue
            for element in body["elements"]:
                flags = [judgements[(skey, arm, r, element["id"])]["covered"]
                         for r in range(1, repeats + 1)
                         if (skey, arm, r, element["id"]) in judgements]
                if not flags:
                    continue
                if all(flags) and len(flags) == repeats:
                    reliable += 1
                if any(flags):
                    reachable += 1
        L.append("| `%s` | %d | %d | %s |"
                 % (arm, reliable, reachable,
                    "--" if not reachable else "%.0f%%" % (100.0 * reliable / reachable)))

    # Element-level view: which propositions nobody reaches is the most actionable output.
    L += ["", "---", "", "## Element detail",
          "",
          "Runs covering each element, out of %d per arm. An element no arm reaches is "
          "either genuinely hard or a sign the granularity is wrong -- check both." % repeats,
          "",
          "| Element | Tier | " + " | ".join("`%s`" % a for a, _l, _c in ARMS) + " |",
          "|---|---|" + "---|" * len(ARMS)]
    for skey, _p, _d, app_no in SECTIONS:
        body = elements["sections"].get(app_no)
        if not body:
            continue
        for element in body["elements"]:
            cells = []
            for arm, _l, _c in ARMS:
                n = sum(1 for r in range(1, repeats + 1)
                        if judgements.get((skey, arm, r, element["id"]), {}).get("covered"))
                cells.append(str(n))
            L.append("| `%s` | %s | %s |"
                     % (element["id"], element["tier"], " | ".join(cells)))

    # Evidence integrity: a judge that cannot quote its own evidence is not measuring.
    claimed = [j for j in judgements.values() if j["covered"]]
    unverified = [j for j in claimed if j.get("quote_verified") is False]
    noquote = [j for j in claimed if not j.get("evidence_quote")]
    L += ["", "---", "", "## Judge reliability", "",
          "| Check | Result |", "|---|---|",
          "| Judgements made | %d |" % len(judgements),
          "| Coverage claims | %d |" % len(claimed),
          "| Claims with a verified verbatim quote | %s |"
          % pct(len(claimed) - len(unverified) - len(noquote), len(claimed)),
          "| Claims whose quote is NOT in the feature file | %d |" % len(unverified),
          "| Claims with no quote at all | %d |" % len(noquote),
          "",
          "An unverified quote means the judge asserted coverage on text that is not in "
          "the scenarios. Treat a non-trivial count here as a reason to distrust the "
          "whole table, not as a rounding error.",
          "",
          "> **Self-preference bias.** The judge is an LLM scoring LLM output, which "
          "G-Eval (Liu et al., EMNLP 2023) shows favours machine-generated text. Run "
          "`--sample-for-human` and report Cohen's kappa before treating any number "
          "above as measured rather than estimated.",
          ""]
    return "\n".join(L) + "\n"


def sample_for_human(judgements, n, elements, seed=0):
    """Write a self-contained annotation worksheet, an answer sheet, and a hidden key.

    Three properties the measurement depends on:

    BLINDING. The worksheet never names the arm, and cells are labelled A, B, C rather
    than by their directory -- a path like `line34__spires__r1` would tell the annotator
    which method produced the scenarios, and agreement measured under that knowledge is
    not agreement about the scenarios.

    NO PEEKING. The judge's verdicts go in a separate key file that the worksheet does
    not reference. Seeing them first makes the exercise a confirmation, not a measurement.

    GROUPED BY CELL. Items are grouped so one set of scenarios is read once and judged
    against several propositions. Ungrouped, an annotator re-reads the same feature file
    a dozen times, and 60 items becomes an afternoon instead of an hour.
    """
    rng = random.Random(seed)
    buckets = {}
    for key, j in judgements.items():
        buckets.setdefault((j["arm"], j["tier"]), []).append((key, j))
    per = max(1, n // max(1, len(buckets)))
    chosen = []
    for bucket in sorted(buckets):
        chosen += rng.sample(buckets[bucket], min(per, len(buckets[bucket])))
    rng.shuffle(chosen)

    proposition = {}
    for body in elements["sections"].values():
        for element in body["elements"]:
            proposition[element["id"]] = " ".join(element["proposition"].split())

    # Group by cell, then hand each cell an opaque label in shuffled order.
    by_cell = {}
    for (skey, arm, repeat, eid), j in chosen:
        by_cell.setdefault((skey, arm, repeat), []).append((eid, j))
    cells = list(by_cell)
    rng.shuffle(cells)
    labels = {cell: "Set %s" % chr(ord("A") + i) if i < 26 else "Set %d" % i
              for i, cell in enumerate(cells)}

    rows, lines = [], [
        "# Element coverage — human annotation worksheet",
        "",
        "For each proposition below, decide whether ANY scenario in that set addresses "
        "it. Record YES or NO against the row id in `human_sample_answers.csv`.",
        "",
        "It counts as addressed whether the scenario asserts the rule holds, tests that "
        "it is correctly NOT applied, or tests a violation of it. It does NOT count if "
        "the scenario only mentions related vocabulary or covers a neighbouring rule of "
        "the same clause. **NO is the right answer more often than not.**",
        "",
        "The scenarios are written as assertions about what a privacy policy states, "
        "while the propositions are rules of law. Judge on substance, not wording.",
        "",
        "> Do not open `human_sample_key.csv` until you have finished. It holds the "
        "automated verdicts, and seeing them first turns this into a confirmation "
        "rather than a measurement.",
        "", "---", "",
    ]

    row_id = 0
    for cell in cells:
        skey, arm, repeat = cell
        feature_path = os.path.join(cell_dir(skey, arm, repeat), "generated.feature")
        try:
            with io.open(feature_path, encoding="utf-8") as fh:
                feature = fh.read().strip()
        except OSError:
            feature = "(feature file missing)"
        lines += ["## %s" % labels[cell], "", "```gherkin", feature, "```", "",
                  "| Row | Proposition | YES / NO |", "|---|---|---|"]
        for eid, j in by_cell[cell]:
            row_id += 1
            lines.append("| **%d** | %s | |" % (row_id, proposition.get(eid, eid)))
            rows.append((row_id, j))
        lines += ["", "---", ""]

    worksheet = os.path.join(OUT_DIR, "human_sample.md")
    with io.open(worksheet, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

    answers = os.path.join(OUT_DIR, "human_sample_answers.csv")
    with io.open(answers, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["row_id", "human_covered_YES_or_NO"])
        for rid, _j in rows:
            writer.writerow([rid, ""])

    key_path = os.path.join(OUT_DIR, "human_sample_key.csv")
    with io.open(key_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["row_id", "judge_covered", "arm", "element_id"])
        for rid, j in rows:
            writer.writerow([rid, "YES" if j["covered"] else "NO",
                             j["arm"], j["element_id"]])

    print("Worksheet : %s   (%d items across %d scenario sets)"
          % (worksheet, len(rows), len(cells)))
    print("Answers   : %s   <- fill in the YES/NO column" % answers)
    print("Key       : %s   <- do not open until finished" % key_path)
    print("\nThen: python score_elements.py --kappa %s" % answers)


def cohens_kappa(a, b):
    """Cohen's kappa for two binary raters (Cohen, 1960)."""
    n = len(a)
    if not n:
        return None
    agree = sum(1 for x, y in zip(a, b) if x == y) / n
    pa1, pb1 = sum(a) / n, sum(b) / n
    chance = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    if chance == 1.0:
        return None
    return (agree - chance) / (1 - chance)


def report_kappa(annotated_path):
    key_path = os.path.join(OUT_DIR, "human_sample_key.csv")
    key = {r["row_id"]: r["judge_covered"] for r in
           csv.DictReader(io.open(key_path, encoding="utf-8", newline=""))}
    human, judge, skipped = [], [], 0
    for row in csv.DictReader(io.open(annotated_path, encoding="utf-8", newline="")):
        label = (row.get("human_covered_YES_or_NO") or "").strip().upper()
        if label not in ("YES", "NO", "Y", "N"):
            skipped += 1
            continue
        human.append(label.startswith("Y"))
        judge.append(key.get(row["row_id"], "NO") == "YES")
    if skipped:
        print("(%d row(s) left blank or unreadable, ignored)" % skipped)
    k = cohens_kappa(human, judge)
    agreement = sum(1 for x, y in zip(human, judge) if x == y) / len(human) if human else 0
    print("Annotated rows : %d" % len(human))
    print("Raw agreement  : %.1f%%" % (100 * agreement))
    print("Cohen's kappa  : %s" % ("--" if k is None else "%.3f" % k))
    # Landis & Koch (1977) bands, the conventional reading.
    if k is not None:
        band = ("poor" if k < 0 else "slight" if k < 0.21 else "fair" if k < 0.41 else
                "moderate" if k < 0.61 else "substantial" if k < 0.81 else "almost perfect")
        print("Landis & Koch  : %s agreement" % band)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--judge-model", default="gpt-4o-mini",
                    help="Ideally NOT the generator's model; see self-preference bias.")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sample-for-human", type=int, default=0)
    ap.add_argument("--kappa", default=None)
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)-8s %(name)-12s %(message)s", stream=sys.stderr)
    logger.setLevel(logging.INFO)
    os.makedirs(OUT_DIR, exist_ok=True)

    if args.kappa:
        report_kappa(args.kappa)
        return 0

    elements = load_elements()

    if args.dry_run:
        total = 0
        for skey, _p, desc, app_no in SECTIONS:
            body = elements["sections"].get(app_no)
            if not body:
                continue
            n = len(body["elements"]) * len(ARMS) * args.repeats
            print("%-42s %2d elements x %d arms x %d repeats = %3d calls"
                  % (desc, len(body["elements"]), len(ARMS), args.repeats, n))
            total += n
        pin, pout = PRICES.get(args.judge_model, PRICES["gpt-4o-mini"])
        # Prompt is the section text plus a whole feature file; ~1.6k in, ~90 out.
        est = total * (1600 / 1e6 * pin + 90 / 1e6 * pout)
        print("\n%d calls on %s, roughly $%.2f" % (total, args.judge_model, est))
        return 0

    if not args.report_only:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        score_all(elements, args)

    judgements = load_judgements(elements, args.repeats)
    if args.sample_for_human:
        sample_for_human(judgements, args.sample_for_human, elements)
        return 0

    report = build_report(elements, judgements, args.repeats, args.judge_model)
    out = os.path.join(OUT_DIR, "coverage.md")
    with io.open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(report)
    with io.open(os.path.join(OUT_DIR, "coverage.json"), "w", encoding="utf-8") as fh:
        json.dump([j for j in judgements.values()], fh, indent=2)
    print("\nWrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
