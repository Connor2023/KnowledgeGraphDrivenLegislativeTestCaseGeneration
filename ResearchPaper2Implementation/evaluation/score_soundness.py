"""Legal soundness of individual scenarios. The correctness half of the evaluation.

`evaluation/score_elements.py` measures recall: did any scenario address this proposition? It never
asks whether the scenario is RIGHT. A scenario asserting the reverse of the law scores as
covering the element it reverses -- and that error class is not hypothetical here, it is
the direction bug the generator prompt had to be patched for.

Amaral et al. (IEEE TSE 2022) score completeness and correctness of privacy policies as
separate measures, and Hassani et al. (IST 2026) rate Relevance apart from Completeness.
Coverage alone is half a result.

Design, mirroring the element judge because those choices were validated there:

  one scenario per call    independent judgements, no anchoring down a list
  reasoning before verdict the JSON asks what the scenario asserts and what the statute
                          says BEFORE the label. Ordering this the other way measurably
                          produced rationalised verdicts in the element judge.
  verbatim evidence       the supporting or contradicting words must be quoted from the
                          Schedule and are checked against it
  blinded                 the judge never learns which arm wrote the scenario
  whole Schedule supplied a scenario may legitimately test a cross-referenced provision
                          (the SPIRES arms do this constantly), so judging it against the
                          target clause alone would mark correct law as unsound

    python -m evaluation.score_soundness --dry-run
    python -m evaluation.score_soundness --per-arm 14
    python -m evaluation.score_soundness --report-only
    python -m evaluation.score_soundness --sample-for-human 20
    python -m evaluation.score_soundness --kappa runs/soundness/human_sample_answers.csv
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import json
import logging
import os
import random
import sys
import time

import yaml

from kg_testgen.config import (ENV_LLM_KEY_FALLBACK, ENV_LLM_KEY_PRIMARY, ConfigError)
from .gherkin import parse_feature_text
from .run_experiment import ARMS, SECTIONS, cell_dir
from .score_elements import cohens_kappa, llm_key_from_env, normalise_ws

OUT_DIR = "runs/soundness"
SCHEDULE = "APPschedule1.txt"
ELEMENTS_PATH = os.path.join("elements", "legal_elements.yaml")

PRICES = {"gpt-4o-mini": (0.150, 0.600), "gpt-4o": (2.50, 10.00)}

LABELS = ("SOUND", "UNSOUND", "UNVERIFIABLE", "TRIVIAL")
ERROR_CLASSES = ("direction-reversal", "over-generalisation", "provision-conflation",
                 "fabricated-obligation", "scope-error", "other")

logger = logging.getLogger("soundness")


PROMPT = """\
You are checking whether one generated compliance test scenario states Australian privacy
law correctly.

THE LEGISLATION (Schedule 1 of the Privacy Act 1988, complete)
--------------------------------------------------------------
{schedule}

THE PROVISION THIS SCENARIO WAS WRITTEN FOR
-------------------------------------------
subclause {provision}: {section_text}

THE SCENARIO
------------
{scenario}

HOW TO LABEL IT
---------------
Judge the Then step(s). They are the assertion a person would check against a company's
published privacy policy; the Given and When steps only set the circumstance.

READ THIS FIRST -- it decides most of these cases. Every scenario here is a COMPLIANCE
TEST, written on purpose in the form "the privacy policy states that ...". The statute
never requires a policy to contain any particular sentence, so asking whether it mandates
the wording would make every scenario unsound and measure nothing.

Judge the LEGAL PROPOSITION UNDERNEATH the policy-statement wrapper. Strip "the privacy
policy states that" and ask only: is what follows an accurate statement of the law?

  "Then the privacy policy states that identification may be required where dealing
   anonymously is not practicable"
  -> the proposition is "identification may be required where anonymity is impracticable"
  -> APP 2.2(b) says exactly that -> SOUND.
  It is NOT unsound merely because no provision orders a policy to say it.

SOUND         the assertion states the law accurately. A compliance analyst would accept
              it. It may test a provision OTHER than the one above -- scenarios often
              test a cross-referenced clause -- and that is still SOUND if the law
              supports it.
UNSOUND       the assertion states something the legislation does not support, or
              supports in the opposite direction.
UNVERIFIABLE  the assertion cannot be checked against a privacy policy alone: it cites a
              provision number, names the Privacy Act, or defers to unnamed conditions
              ("where an exception applies", "unless certain conditions are met").
TRIVIAL       accurate but vacuous -- it restates the clause without asserting anything a
              policy could fail.

LABEL PRECEDENCE. Check in this order and stop at the first that applies:

  1. UNVERIFIABLE -- does the assertion name a subclause, an Australian Privacy
     Principle, the Privacy Act, or defer to unnamed conditions? If so it is
     UNVERIFIABLE, whatever else is wrong with it. A policy reader cannot check it at
     all, so its legal accuracy never arises.
  2. TRIVIAL      -- is it accurate but vacuous?
  3. UNSOUND      -- is the legal proposition wrong?
  4. SOUND        -- otherwise.

Without this order a scenario that both cites a subclause AND misstates the law gets
labelled by whichever defect is noticed first, and the two counts stop meaning anything.

Judge SOUND versus UNSOUND on the law. Do not mark a scenario unsound for being about a
different provision, for being narrow, or for wording you would have chosen differently.

CONDITIONAL REASONING -- read this before deciding, legislation is built from conditionals
and two invalid inferences look convincing here:

  "If NOT X, then Y" does NOT entail "If X, then NOT Y".
  APP 4.4 says that if subclause 4.3 does not apply, APPs 5 to 13 apply. It says NOTHING
  about what happens when 4.3 DOES apply. A scenario asserting "when 4.3 applies, APPs 5
  to 13 do not apply" is UNSOUND (direction-reversal), however natural it sounds.

  "If X, then Y" does NOT entail "If Y, then X".
  A scenario asserting that satisfying an exception's conditions proves the exception was
  relied on is UNSOUND.

If the legislation is silent on the LEGAL PROPOSITION the scenario asserts -- not on the
policy wording, on the proposition -- then the scenario is UNSOUND. Silence about a legal
consequence is neither permission nor prohibition. This does not apply to the
policy-statement wrapper, which the legislation is always silent about.

If UNSOUND, give the error class:
  direction-reversal      a condition restated as the outcome, or a permission stated as
                          a prohibition (or the reverse)
  over-generalisation     an exception stated as an unconditional rule, or a qualified
                          duty stated without its qualification
  provision-conflation    limits belonging to one provision applied to another
  fabricated-obligation   a requirement the legislation does not impose
  scope-error             a matter-specific or actor-specific rule stated more broadly
  other                   none of the above

Answer the JSON fields IN ORDER. State what the scenario claims and what the statute says
before deciding; a label chosen first only gets explained afterwards.

Reply with JSON only:
{{"what_it_asserts": "one sentence: what the Then step(s) require a policy to state",
  "statute_says": "verbatim words from the legislation above that support or contradict \
that assertion, or null if none bear on it",
  "analysis": "one or two sentences: does the legislation support the assertion, \
contradict it, or neither?",
  "label": "SOUND" or "UNSOUND" or "UNVERIFIABLE" or "TRIVIAL",
  "error_class": "one of the classes above, or null unless the label is UNSOUND"}}
"""


# Controls with known answers, for checking the judge before spending a full run on it.
# Two SOUND cases guard against the failure this judge has already had once -- marking
# correct law unsound because the statute does not order a policy to say it -- and the
# rest exercise one label or error class each, in the manner of Sai et al.'s perturbation
# checklists (EMNLP 2021): perturb along one axis and confirm the metric responds.
SELF_TEST = [
    ("2.2", "SOUND", None, """\
@s2-2 @law-requires-identification
Scenario: Australian law requires identification
  Given an Australian law requires the entity to deal with individuals who have identified themselves
  Then the privacy policy states that individuals may be required to identify themselves for that matter"""),

    ("6.1", "SOUND", None, """\
@s6-1 @consent-permits-secondary-use
Scenario: Consent permits secondary use
  Given the individual has consented to the use of their personal data for a further purpose
  Then the privacy policy states that personal data collected for one purpose is used for a further purpose only with the individual's consent"""),

    ("2.2", "UNSOUND", "direction-reversal", """\
@s2-2 @impracticable-reversed
Scenario: Impracticability read backwards
  Given it is impracticable for the entity to deal with individuals who have not identified themselves
  Then the privacy policy states that individuals may deal with the entity without identifying themselves"""),

    ("4.4", "UNSOUND", "direction-reversal", """\
@s4-4 @denying-the-antecedent
Scenario: Denying the antecedent
  Given the entity holds unsolicited personal information
  When subclause 4.3 applies to the information
  Then the privacy policy states that the handling principles do not apply to that information"""),

    ("6.1", "UNSOUND", "over-generalisation", """\
@s6-1 @exception-as-rule
Scenario: Exception stated as an unconditional rule
  Given the entity holds personal data collected for a primary purpose
  Then the privacy policy states that personal data may be used for any further purpose the entity considers related"""),

    ("6.1", "UNVERIFIABLE", None, """\
@s6-1 @cites-subclause
Scenario: Cites a subclause
  Given the entity wishes to use personal information for a secondary purpose
  Then the privacy policy states that the use is permitted where subclause 6.2 applies"""),

    ("2.2", "UNVERIFIABLE", None, """\
@s2-2 @unnamed-conditions
Scenario: Defers to unnamed conditions
  Given an individual wishes to deal with the entity anonymously
  Then the privacy policy states that anonymity is available unless certain conditions are met"""),
]


def self_test(args):
    """Run the controls and report per-label accuracy. Roughly $0.20."""
    from openai import OpenAI
    client = OpenAI(api_key=llm_key_from_env())
    schedule = load_schedule()
    section_texts = load_section_texts()

    correct = 0
    print("%-14s %-14s %-22s %s" % ("expected", "got", "error_class", "control"))
    print("-" * 88)
    for provision, expected, expected_class, scenario in SELF_TEST:
        unit = {"section": provision, "text": scenario}
        try:
            verdict, _a, _b = judge(client, args.judge_model, unit, schedule, section_texts)
        except Exception as exc:  # noqa: BLE001
            print("  FAILED: %s" % exc)
            continue
        got = (verdict.get("label") or "").strip().upper()
        got_class = verdict.get("error_class") or "-"
        ok = got == expected
        correct += ok
        name = scenario.splitlines()[1].replace("Scenario: ", "").strip()
        print("%-14s %-14s %-22s %s %s"
              % (expected, got, got_class, name[:32], "" if ok else "  <-- MISMATCH"))
        if not ok:
            print("      judge said: %s" % (verdict.get("analysis") or "")[:150])

    print("-" * 88)
    print("%d of %d controls correct" % (correct, len(SELF_TEST)))
    if correct < len(SELF_TEST):
        print("Fix the prompt before running the full scoring pass.")
    return 0 if correct == len(SELF_TEST) else 1


def quote_grounded(quote, schedule, window=6):
    """Whether the judge's statutory quote is really in the Schedule.

    Not an exact substring test. The judge reliably reproduces the statute's wording but
    stitches clauses together and trims connectives, so demanding a full verbatim match
    flagged 3 of the first 4 quotes as fabricated when all four were faithful. Requiring
    any `window`-word run to appear verbatim keeps the anti-fabrication property -- an
    invented sentence shares no six-word run with the source -- without punishing
    paraphrase at the joins.
    """
    words = normalise_ws(quote).lower().split()
    if len(words) < window:
        return normalise_ws(quote).lower() in normalise_ws(schedule).lower()
    haystack = normalise_ws(schedule).lower()
    return any(" ".join(words[i:i + window]) in haystack
               for i in range(len(words) - window + 1))


def load_schedule():
    with io.open(SCHEDULE, encoding="utf-8") as fh:
        return " ".join(fh.read().split())


def load_section_texts():
    with io.open(ELEMENTS_PATH, encoding="utf-8") as fh:
        elements = yaml.safe_load(fh)
    return {app: body["text"].strip()
            for app, body in elements["sections"].items()}


def scenario_units(include_format_arms=False, repeats=3):
    """Every generated scenario, with enough identity to cache a judgement against it."""
    units = []
    for skey, _path, _desc, app in SECTIONS:
        for arm, _label, _cfg in ARMS:
            if arm.startswith("fmt-") and not include_format_arms:
                continue
            for repeat in range(1, repeats + 1):
                path = os.path.join(cell_dir(skey, arm, repeat), "generated.feature")
                if not os.path.exists(path):
                    continue
                with io.open(path, encoding="utf-8") as fh:
                    feature = parse_feature_text(fh.read())
                for index, scenario in enumerate(feature.scenarios, 1):
                    units.append({
                        "section_key": skey, "section": app, "arm": arm,
                        "repeat": repeat, "index": index,
                        "name": scenario.name,
                        "text": scenario.as_text(),
                    })
    return units


def sample(units, per_arm, seed=0):
    """Stratify by ARM, not by section.

    The comparison is between arms, so each needs the same number of observations. A
    sample stratified by section would let a prolific arm dominate and make the
    per-arm rates incomparable.
    """
    rng = random.Random(seed)
    by_arm = collections.defaultdict(list)
    for unit in units:
        by_arm[unit["arm"]].append(unit)
    chosen = []
    for arm in sorted(by_arm):
        pool = by_arm[arm]
        chosen += rng.sample(pool, min(per_arm, len(pool)))
    return chosen


def judgement_path(unit):
    return os.path.join(OUT_DIR, "%s__%s__r%d" % (unit["section_key"], unit["arm"],
                                                  unit["repeat"]),
                        "s%02d.json" % unit["index"])


def judge(client, model, unit, schedule, section_texts, attempts=5):
    """One judgement, with a back-off that survives the token-per-minute limit.

    Each call carries the whole Schedule -- about 8,400 prompt tokens against a 30,000
    TPM ceiling, so roughly three calls a minute is the sustainable rate. Without this
    the first full run silently lost 14 of 98 judgements to 429s and left one arm with
    n = 4, which is not a sample anyone should read a percentage off.
    """
    prompt = PROMPT.format(schedule=schedule, provision=unit["section"],
                           section_text=section_texts.get(unit["section"], ""),
                           scenario=unit["text"])
    last = None
    for attempt in range(1, attempts + 1):
        try:
            completion = client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}],
                temperature=0.0, response_format={"type": "json_object"})
            usage = completion.usage
            return (json.loads(completion.choices[0].message.content),
                    usage.prompt_tokens, usage.completion_tokens)
        except Exception as exc:  # noqa: BLE001 - retry rate limits, surface the rest
            last = exc
            if "rate_limit" not in str(exc) and "429" not in str(exc):
                raise
            wait = 20 * attempt
            logger.warning("  rate limited, waiting %ds (attempt %d/%d)",
                           wait, attempt, attempts)
            time.sleep(wait)
    raise last


def run(chosen, args):
    from openai import OpenAI
    client = OpenAI(api_key=llm_key_from_env())
    schedule = load_schedule()
    section_texts = load_section_texts()

    tin = tout = calls = cached = 0
    for unit in chosen:
        out = judgement_path(unit)
        if os.path.exists(out) and not args.overwrite:
            cached += 1
            continue
        try:
            verdict, a, b = judge(client, args.judge_model, unit, schedule, section_texts)
        except Exception as exc:  # noqa: BLE001 - one bad scenario must not stop the run
            logger.error("  failed %s/%s/r%d s%d: %s", unit["section_key"], unit["arm"],
                         unit["repeat"], unit["index"], exc)
            continue
        tin, tout, calls = tin + a, tout + b, calls + 1

        label = (verdict.get("label") or "").strip().upper()
        if label not in LABELS:
            label = "UNVERIFIABLE"
        quote = verdict.get("statute_says")
        verified = quote_grounded(quote, schedule) if quote else None

        record = dict(unit)
        record.update({
            "label": label,
            "error_class": (verdict.get("error_class") or None) if label == "UNSOUND" else None,
            "what_it_asserts": verdict.get("what_it_asserts"),
            "statute_says": quote,
            "quote_verified": verified,
            "analysis": verdict.get("analysis"),
            "judge_model": args.judge_model,
        })
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with io.open(out, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2)
        if calls % 20 == 0:
            logger.info("  %d judged (%d cached)", calls, cached)

    pin, pout = PRICES.get(args.judge_model, PRICES["gpt-4o"])
    cost = tin / 1e6 * pin + tout / 1e6 * pout
    logger.info("Soundness: %d calls, %d cached, %s in / %s out, $%.4f",
                calls, cached, "{:,}".format(tin), "{:,}".format(tout), cost)


def load_judgements():
    out = []
    for root, _dirs, files in os.walk(OUT_DIR):
        for name in files:
            if not name.startswith("s") or not name.endswith(".json"):
                continue
            with io.open(os.path.join(root, name), encoding="utf-8") as fh:
                out.append(json.load(fh))
    return out


def element_coverage_by_arm():
    """Element coverage, so soundness can be folded into a precision-weighted figure."""
    path = os.path.join("runs", "elements", "coverage.json")
    if not os.path.exists(path):
        return {}
    with io.open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    tally = collections.defaultdict(lambda: [0, 0])
    for row in rows:
        tally[row["arm"]][1] += 1
        if row["covered"]:
            tally[row["arm"]][0] += 1
    return {arm: covered / total for arm, (covered, total) in tally.items() if total}


def build_report(judgements):
    by_arm = collections.defaultdict(collections.Counter)
    classes = collections.defaultdict(collections.Counter)
    for j in judgements:
        by_arm[j["arm"]][j["label"]] += 1
        if j["label"] == "UNSOUND" and j.get("error_class"):
            classes[j["arm"]][j["error_class"]] += 1

    coverage = element_coverage_by_arm()
    L = [
        "# Legal soundness of generated scenarios",
        "",
        "The correctness half of the evaluation. Element coverage measures recall only -- "
        "a scenario asserting the reverse of the law scores as covering the element it "
        "reverses. Judged one scenario per call, blinded to arm, with the complete "
        "Schedule supplied so a scenario testing a cross-referenced provision is not "
        "marked wrong for being off-target.",
        "",
        "`soundness` excludes UNVERIFIABLE from the denominator -- that is a prompt-"
        "compliance failure, not a legal error, and is reported beside it.",
        "",
        "| Arm | n | SOUND | UNSOUND | TRIVIAL | Soundness | UNVERIFIABLE | Coverage | Weighted |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for arm in sorted(by_arm):
        counts = by_arm[arm]
        sound, unsound = counts["SOUND"], counts["UNSOUND"]
        trivial, unver = counts["TRIVIAL"], counts["UNVERIFIABLE"]
        denominator = sound + unsound + trivial
        rate = (sound / denominator) if denominator else None
        cov = coverage.get(arm)
        weighted = (cov * rate) if (cov is not None and rate is not None) else None
        L.append("| `%s` | %d | %d | %d | %d | %s | %s | %s | %s |"
                 % (arm, sum(counts.values()), sound, unsound, trivial,
                    "--" if rate is None else "%.0f%%" % (100 * rate),
                    "%d (%.0f%%)" % (unver, 100 * unver / max(1, sum(counts.values()))),
                    "--" if cov is None else "%.0f%%" % (100 * cov),
                    "--" if weighted is None else "%.0f%%" % (100 * weighted)))

    L += ["",
          "**Weighted** is element coverage x soundness. An arm covering 80% of elements "
          "at 60% soundness is worse than one covering 70% at 90%, and the coverage "
          "table alone cannot tell them apart.",
          "", "---", "", "## Error classes among UNSOUND scenarios", "",
          "Basili & Selby (IEEE TSE 1987) found testing techniques differ by fault CLASS, "
          "not only fault count. With the arms near-identical on coverage, class is where "
          "a real difference would show.",
          ""]
    all_classes = sorted({c for counter in classes.values() for c in counter})
    if all_classes:
        L += ["| Arm | " + " | ".join(all_classes) + " |",
              "|---|" + "---|" * len(all_classes)]
        for arm in sorted(by_arm):
            L.append("| `%s` | %s |"
                     % (arm, " | ".join(str(classes[arm].get(c, 0)) for c in all_classes)))
    else:
        L.append("_No unsound scenarios recorded._")

    claimed = [j for j in judgements if j.get("statute_says")]
    bad = [j for j in claimed if j.get("quote_verified") is False]
    L += ["", "---", "", "## Judge reliability", "",
          "| Check | Result |", "|---|---|",
          "| Judgements | %d |" % len(judgements),
          "| With a statutory quote | %d |" % len(claimed),
          "| Quote NOT found in the Schedule | %d |" % len(bad),
          "",
          "> Validate before reporting: `--sample-for-human 20`, then `--kappa`. An "
          "unvalidated soundness rate is an opinion, and this judge has not been "
          "checked against a person the way the element judge was.",
          ""]
    return "\n".join(L) + "\n"


def sample_for_human(judgements, n, seed=0):
    """Blinded worksheet: scenario text and the four labels, no arm, no judge verdict."""
    rng = random.Random(seed)
    chosen = rng.sample(judgements, min(n, len(judgements)))
    rng.shuffle(chosen)
    section_texts = load_section_texts()

    lines = ["# Scenario soundness — human annotation worksheet", "",
             "For each scenario, label the **Then** step(s): SOUND, UNSOUND, "
             "UNVERIFIABLE or TRIVIAL. Definitions are in `evaluation/score_soundness.py`.",
             "",
             "A scenario testing a provision OTHER than the one named is still SOUND if "
             "the law supports it. Judge correctness, not relevance.",
             "",
             "> Do not open `human_sample_key.csv` until you have finished.",
             "", "---", ""]
    for i, j in enumerate(chosen, 1):
        lines += ["## %d — written for subclause %s" % (i, j["section"]), "",
                  "> %s" % section_texts.get(j["section"], ""), "",
                  "```gherkin", j["text"], "```", "",
                  "Label: ______________", "", "---", ""]

    os.makedirs(OUT_DIR, exist_ok=True)
    worksheet = os.path.join(OUT_DIR, "human_sample.md")
    with io.open(worksheet, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    answers = os.path.join(OUT_DIR, "human_sample_answers.csv")
    with io.open(answers, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["row_id", "human_label"])
        for i, _j in enumerate(chosen, 1):
            writer.writerow([i, ""])
    key = os.path.join(OUT_DIR, "human_sample_key.csv")
    with io.open(key, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["row_id", "judge_label", "arm"])
        for i, j in enumerate(chosen, 1):
            writer.writerow([i, j["label"], j["arm"]])
    print("Worksheet : %s (%d scenarios)" % (worksheet, len(chosen)))
    print("Answers   : %s" % answers)
    print("Key       : %s   <- do not open until finished" % key)


def report_kappa(annotated_path):
    key_path = os.path.join(OUT_DIR, "human_sample_key.csv")
    key = {r["row_id"]: r["judge_label"] for r in
           csv.DictReader(io.open(key_path, encoding="utf-8", newline=""))}
    human, judge_labels = [], []
    for row in csv.DictReader(io.open(annotated_path, encoding="utf-8", newline="")):
        label = (row.get("human_label") or "").strip().upper()
        if label not in LABELS:
            continue
        human.append(label)
        judge_labels.append(key.get(row["row_id"], "UNVERIFIABLE"))
    if not human:
        print("No labelled rows found.")
        return
    agree = sum(1 for a, b in zip(human, judge_labels) if a == b) / len(human)
    # Binary kappa on the decision that matters: is this scenario sound or not?
    hb = [x == "SOUND" for x in human]
    jb = [x == "SOUND" for x in judge_labels]
    k = cohens_kappa(hb, jb)
    print("Annotated rows      : %d" % len(human))
    print("Exact-label agreement: %.1f%%" % (100 * agree))
    print("Cohen's kappa (SOUND vs not): %s" % ("--" if k is None else "%.3f" % k))
    if k is not None:
        band = ("poor" if k < 0 else "slight" if k < 0.21 else "fair" if k < 0.41 else
                "moderate" if k < 0.61 else "substantial" if k < 0.81 else "almost perfect")
        print("Landis & Koch       : %s agreement" % band)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-arm", type=int, default=14)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--judge-model", default="gpt-4o")
    ap.add_argument("--include-format-arms", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true",
                    help="Run the known-answer controls and stop.")
    ap.add_argument("--sample-for-human", type=int, default=0)
    ap.add_argument("--kappa", default=None)
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)-8s %(name)-10s %(message)s", stream=sys.stderr)
    logger.setLevel(logging.INFO)
    os.makedirs(OUT_DIR, exist_ok=True)

    if args.kappa:
        report_kappa(args.kappa)
        return 0

    if args.self_test:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        return self_test(args)

    if not args.report_only and not args.sample_for_human:
        units = scenario_units(args.include_format_arms, args.repeats)
        chosen = sample(units, args.per_arm)
        if args.dry_run:
            schedule_tokens = len(load_schedule()) // 4
            pin, pout = PRICES.get(args.judge_model, PRICES["gpt-4o"])
            est = len(chosen) * ((schedule_tokens + 400) / 1e6 * pin + 200 / 1e6 * pout)
            arms = collections.Counter(u["arm"] for u in chosen)
            for arm in sorted(arms):
                print("  %-16s %d scenarios" % (arm, arms[arm]))
            print("\n%d of %d scenarios, %d calls on %s, roughly $%.2f"
                  % (len(chosen), len(units), len(chosen), args.judge_model, est))
            return 0
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        run(chosen, args)

    judgements = load_judgements()
    if args.sample_for_human:
        sample_for_human(judgements, args.sample_for_human)
        return 0

    report = build_report(judgements)
    out = os.path.join(OUT_DIR, "soundness.md")
    with io.open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(report)
    print("\nWrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
