"""Automatic metrics over the experiment grid: diversity, stability, efficiency.

Tiers 5, 6 and 7 of the metric plan -- everything computable from the run records that
already exist, with no new LLM call and no human judgement. The point of these three is
that they are the metrics which can *undermine* the headline numbers, so they should be
computed before the headline numbers are believed:

  diversity   a high scenario count is only coverage if the scenarios differ. Self-BLEU
              (Zhu et al., SIGIR 2018) says whether an 11-scenario run is eleven tests or
              five tests paraphrased.
  stability   temperature 0 is not deterministic (Ouyang et al., arXiv:2308.02828), so a
              single run's count is a sample, not a measurement.
  efficiency  tokens and cost per scenario -- the one axis where the comparison needs no
              interpretation at all.

Legal-element coverage (Tier 2) and gold-standard recall (Tier 1) need a hand-built
decomposition and a fixed matching protocol; they are deliberately not here.

    python -m evaluation.analyse_runs
    python -m evaluation.analyse_runs --repeats 3 --json
"""

from __future__ import annotations

import argparse
import collections
import io
import json
import math
import os
import random
import re
import sys

from .gherkin import parse_feature_text
from .run_experiment import ARMS, SECTIONS, cell_dir

# gpt-4o-mini list price, USD per 1M tokens. Every arm uses the same model, so the
# comparison holds under any price; only the absolute figures depend on these.
PRICE_IN, PRICE_OUT = 0.150, 0.600

OUT_DIR = "runs/experiment"
_WORD = re.compile(r"[a-z0-9]+")
_PROVISION_TAG = re.compile(r"@s\d+(-\d+)?$")


# --- tokenisation and BLEU ----------------------------------------------------------

def tokenise(text):
    return _WORD.findall(text.lower())


def ngrams(tokens, n):
    return collections.Counter(
        tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1))


def sentence_bleu(candidate, references, max_n=4):
    """Multi-reference BLEU (Papineni et al., ACL 2002) with add-1 smoothing for n > 1.

    Smoothing is not optional here. Scenarios run to a few dozen tokens, so a single
    unmatched 4-gram sends an unsmoothed score to zero and every cell then reads as
    maximally diverse regardless of content. Add-1 is Chen & Cherry's method 2.
    """
    if not candidate or not references:
        return 0.0
    log_precisions = []
    for n in range(1, max_n + 1):
        cand_grams = ngrams(candidate, n)
        if not cand_grams:
            continue
        # Clip each candidate n-gram at the highest count any single reference shows.
        best = collections.Counter()
        for ref in references:
            for gram, count in ngrams(ref, n).items():
                if count > best[gram]:
                    best[gram] = count
        matched = sum(min(c, best[g]) for g, c in cand_grams.items())
        total = sum(cand_grams.values())
        if n > 1:
            matched, total = matched + 1, total + 1
        if matched == 0:
            return 0.0
        log_precisions.append(math.log(matched / total))
    if not log_precisions:
        return 0.0

    closest = min((abs(len(r) - len(candidate)), len(r)) for r in references)[1]
    brevity = 1.0 if len(candidate) > closest else math.exp(
        1 - closest / max(1, len(candidate)))
    return brevity * math.exp(sum(log_precisions) / len(log_precisions))


def self_bleu(texts):
    """Mean BLEU of each text against all the others in its own set.

    Zhu et al.'s definition: lower means the set is more internally diverse. Undefined
    for a set of one, which is why single-scenario cells report as None rather than as
    perfectly diverse.
    """
    if len(texts) < 2:
        return None
    toks = [tokenise(t) for t in texts]
    scores = [sentence_bleu(toks[i], toks[:i] + toks[i + 1:]) for i in range(len(toks))]
    return sum(scores) / len(scores)


def self_bleu_at_k(texts, k, samples=200, seed=0):
    """Self-BLEU restricted to random subsets of exactly k scenarios.

    Raw self-BLEU is confounded by set size: a larger set gives each scenario more
    chances to overlap something, so an arm can look less diverse purely for producing
    more. Holding k fixed across arms removes that, which matters here because the
    per-arm scenario counts differ by more than a factor of two on APP 6.1.
    """
    if len(texts) < max(2, k):
        return None
    if len(texts) == k:
        return self_bleu(texts)
    rng = random.Random(seed)
    draws = [self_bleu(rng.sample(texts, k)) for _ in range(samples)]
    return sum(draws) / len(draws)


def distinct_n(texts, n):
    """Unique n-grams as a fraction of all n-grams across a set (Li et al., NAACL 2016)."""
    pooled = collections.Counter()
    for t in texts:
        pooled.update(ngrams(tokenise(t), n))
    total = sum(pooled.values())
    return (len(pooled) / total) if total else None


def jaccard(a, b):
    if not a and not b:
        return None
    return len(a & b) / len(a | b)


# --- loading ------------------------------------------------------------------------

def scenario_text(scenario):
    """Name plus steps.

    The `# Derives from:` comment is excluded on purpose: it is a verbatim statutory
    quote, and several scenarios legitimately share one. Counting it would report the
    statute's repetition as the generator's redundancy.
    """
    return " ".join([scenario.name] + scenario.steps)


def behaviour_tags(scenario):
    """The model's own semantic labels, minus the provision tag and any bare '@'."""
    return {t for t in scenario.tags if len(t) > 1 and not _PROVISION_TAG.match(t)}


def load_cell(section_key, arm, repeat, encoder):
    d = cell_dir(section_key, arm, repeat)
    feature_path = os.path.join(d, "generated.feature")
    record_path = os.path.join(d, "run_record.json")
    if not os.path.exists(feature_path):
        return None
    with io.open(feature_path, encoding="utf-8") as fh:
        feature = parse_feature_text(fh.read())
    record = {}
    if os.path.exists(record_path):
        with io.open(record_path, encoding="utf-8") as fh:
            record = json.load(fh)

    # The provider's own count when the run recorded one, and only otherwise a
    # reconstruction from the stored text. The two are not the same measurement: the
    # reconstruction cannot see the chat envelope's per-message overhead, and it counts a
    # retried call once when both attempts were billed. Cells recorded before usage was
    # captured have no such field and still fall back, so old and new stay comparable --
    # but which method was used is carried through, not averaged away.
    llm = record.get("llm") or {}
    if llm.get("usage_source") == "api":
        tin, tout, basis = llm.get("prompt_tokens", 0), llm.get("completion_tokens", 0), "api"
    else:
        prompt = record.get("prompt", "")
        completion = llm.get("text", "")
        tin, tout, basis = len(encoder(prompt)), len(encoder(completion)), "reconstructed"
    texts = [scenario_text(s) for s in feature.scenarios]
    tags = set()
    for s in feature.scenarios:
        tags |= behaviour_tags(s)

    return {
        "dir": d,
        "scenarios": len(feature.scenarios),
        "texts": texts,
        "tags": tags,
        "tokens_in": tin,
        "tokens_out": tout,
        "token_basis": basis,
        "cost": tin / 1e6 * PRICE_IN + tout / 1e6 * PRICE_OUT,
        "self_bleu": self_bleu(texts),
        "distinct_1": distinct_n(texts, 1),
        "distinct_2": distinct_n(texts, 2),
    }


def make_encoder(model="gpt-4o-mini"):
    try:
        import tiktoken
        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        return enc.encode, "tiktoken"
    except ImportError:
        return (lambda t: [None] * (len(t) // 4)), "heuristic(chars/4)"


# --- formatting ---------------------------------------------------------------------

def _token_basis_note(grid):
    """Say how the token counts in this table were arrived at.

    A table mixing provider-reported counts with counts reconstructed from stored text
    is presenting two different measurements in one column. Rather than hide that, the
    report states which cells are which, so a reader can weigh the comparison.
    """
    bases = [c.get("token_basis", "reconstructed")
             for cells in grid.values() for c in cells]
    api, recon = bases.count("api"), bases.count("reconstructed")
    if not bases:
        return ""
    if not recon:
        return "Token counts are the provider's own, summed across retries."
    if not api:
        return ("Token counts are **reconstructed** by re-tokenising the stored prompt "
                "and completion. They omit the chat envelope's per-message overhead, and "
                "count a retried call once where both attempts were billed, so they are "
                "a floor rather than a measurement.")
    return ("Token counts are the provider's own for %d cell(s) and **reconstructed** "
            "from stored text for %d. The reconstruction omits per-message overhead and "
            "counts a retried call once, so those cells read slightly low."
            % (api, recon))


def fmt(value, spec="%.3f", dash="--"):
    return dash if value is None else spec % value


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def main():
    global PRICE_IN, PRICE_OUT

    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--price-in", type=float, default=PRICE_IN)
    ap.add_argument("--price-out", type=float, default=PRICE_OUT)
    ap.add_argument("--json", action="store_true", help="Also write metrics.json.")
    args = ap.parse_args()

    PRICE_IN, PRICE_OUT = args.price_in, args.price_out

    encoder, method = make_encoder()
    grid = {}
    for skey, _path, _desc, _app in SECTIONS:
        for arm, _label, _cfg in ARMS:
            cells = [load_cell(skey, arm, r, encoder) for r in range(1, args.repeats + 1)]
            grid[(skey, arm)] = [c for c in cells if c]

    L = [
        "# Automatic metrics: diversity, stability, efficiency",
        "",
        "Computed from the existing run records -- no new LLM calls, no human judgement. "
        "Token counts via `%s`; prices $%.3f / $%.3f per 1M in/out tokens."
        % (method, PRICE_IN, PRICE_OUT),
        "",
        "These are the metrics that can *undermine* a scenario count, so read them before "
        "trusting one.",
        "",
        "---",
        "",
        "## Tier 7 -- Efficiency",
        "",
        "Mean over repeats. `cost/scenario` is the number that matters: it prices the "
        "context each arm carries against what that context actually produced.",
        "",
        _token_basis_note(grid),
        "",
        "| Section | Arm | Prompt tok | Completion tok | Cost (USD) | Tok/scenario | Cost/scenario |",
        "|---|---|---|---|---|---|---|",
    ]
    for skey, _p, desc, _a in SECTIONS:
        for arm, _label, _c in ARMS:
            cells = grid[(skey, arm)]
            if not cells:
                L.append("| %s | `%s` | -- | -- | -- | -- | -- |" % (desc, arm))
                continue
            tin = mean([c["tokens_in"] for c in cells])
            tout = mean([c["tokens_out"] for c in cells])
            cost = mean([c["cost"] for c in cells])
            per = [(c["tokens_in"] + c["tokens_out"]) / c["scenarios"]
                   for c in cells if c["scenarios"]]
            cps = [c["cost"] / c["scenarios"] for c in cells if c["scenarios"]]
            L.append("| %s | `%s` | %s | %s | $%s | %s | $%s |"
                     % (desc, arm, fmt(tin, "%.0f"), fmt(tout, "%.0f"),
                        fmt(cost, "%.5f"), fmt(mean(per), "%.0f"),
                        fmt(mean(cps), "%.5f")))

    L += ["", "### Arm totals (all sections, all repeats)", "",
          "| Arm | Total tok | Total cost | Scenarios | Cost/scenario |",
          "|---|---|---|---|---|"]
    for arm, _label, _c in ARMS:
        cells = [c for skey, _p, _d, _a in SECTIONS for c in grid[(skey, arm)]]
        if not cells:
            continue
        tot_tok = sum(c["tokens_in"] + c["tokens_out"] for c in cells)
        tot_cost = sum(c["cost"] for c in cells)
        scen = sum(c["scenarios"] for c in cells)
        L.append("| `%s` | %s | $%.4f | %d | $%s |"
                 % (arm, "{:,}".format(tot_tok), tot_cost, scen,
                    fmt(tot_cost / scen if scen else None, "%.5f")))

    L += ["",
          "> **Understated for the graph arms.** `kg`, `kg-text-only` and `rp1` each make "
          "an extra EDC entity-extraction call during seeding that the run record does "
          "not capture, so their true token cost is higher than shown. The two control "
          "arms make exactly one call.",
          "", "---", "",
          "## Tier 5 -- Diversity",
          "",
          "Self-BLEU scores each scenario against the others in its own run: **lower means "
          "more internally diverse**, so a high value beside a high scenario count means "
          "paraphrase, not coverage. `distinct-2` is unique bigrams over all bigrams.",
          "",
          "| Section | Arm | Scenarios | Self-BLEU | distinct-1 | distinct-2 |",
          "|---|---|---|---|---|---|"]
    for skey, _p, desc, _a in SECTIONS:
        for arm, _label, _c in ARMS:
            cells = grid[(skey, arm)]
            if not cells:
                continue
            L.append("| %s | `%s` | %s | %s | %s | %s |"
                     % (desc, arm, "/".join(str(c["scenarios"]) for c in cells),
                        fmt(mean([c["self_bleu"] for c in cells])),
                        fmt(mean([c["distinct_1"] for c in cells])),
                        fmt(mean([c["distinct_2"] for c in cells]))))

    L += ["", "### Diversity-adjusted scenario count", "",
          "`scenarios x (1 - self-BLEU)` -- a crude discount that charges a run for its "
          "own internal repetition. Not a published metric; a sanity check on whether an "
          "arm's lead survives its redundancy.",
          "", "| Arm | Raw scenarios | Mean self-BLEU | Adjusted |", "|---|---|---|---|"]
    for arm, _label, _c in ARMS:
        cells = [c for skey, _p, _d, _a in SECTIONS for c in grid[(skey, arm)]]
        if not cells:
            continue
        raw = sum(c["scenarios"] for c in cells)
        adj = sum(c["scenarios"] * (1 - (c["self_bleu"] or 0.0)) for c in cells)
        L.append("| `%s` | %d | %s | %.1f |"
                 % (arm, raw, fmt(mean([c["self_bleu"] for c in cells])), adj))

    L += ["", "### Size-controlled self-BLEU", "",
          "The check on the table above. Every cell is re-scored on random subsets of "
          "exactly `k` scenarios, `k` being the smallest count any arm produced for that "
          "section, averaged over 200 draws. If an arm's diversity lead survives here it "
          "is a real difference in content; if it collapses, the arm was only ever "
          "benefiting from having written fewer scenarios.",
          "",
          "| Section | k | " + " | ".join("`%s`" % a for a, _l, _c in ARMS) + " |",
          "|---|---|" + "---|" * len(ARMS)]
    for skey, _p, desc, _a in SECTIONS:
        counts = [c["scenarios"] for arm, _l, _c in ARMS for c in grid[(skey, arm)]]
        k = max(2, min(counts)) if counts else 2
        row = []
        for arm, _label, _c in ARMS:
            row.append(fmt(mean([self_bleu_at_k(c["texts"], k)
                                 for c in grid[(skey, arm)]])))
        L.append("| %s | %d | %s |" % (desc, k, " | ".join(row)))

    L += ["", "---", "",
          "## Tier 6 -- Stability across repeats",
          "",
          "Same prompt, same temperature, three runs. `Tag Jaccard` is the mean pairwise "
          "overlap of the behaviour tags a run emitted -- **a proxy for legal-element "
          "overlap until the Tier 2 decomposition exists**, since the tags are the "
          "model's own semantic labels rather than independent ground truth.",
          "",
          "| Section | Arm | Counts | Range | Tag Jaccard | Tags in all 3 | Tags in any |",
          "|---|---|---|---|---|---|---|"]
    for skey, _p, desc, _a in SECTIONS:
        for arm, _label, _c in ARMS:
            cells = grid[(skey, arm)]
            if not cells:
                continue
            counts = [c["scenarios"] for c in cells]
            tagsets = [c["tags"] for c in cells]
            pairs = [jaccard(tagsets[i], tagsets[j])
                     for i in range(len(tagsets)) for j in range(i + 1, len(tagsets))]
            L.append("| %s | `%s` | %s | %d | %s | %d | %d |"
                     % (desc, arm, "/".join(map(str, counts)),
                        max(counts) - min(counts), fmt(mean(pairs)),
                        len(set.intersection(*tagsets)), len(set.union(*tagsets))))

    L += ["", "### Arm stability summary", "",
          "| Arm | Mean count range | Mean tag Jaccard | Reliable / reachable tags |",
          "|---|---|---|---|"]
    for arm, _label, _c in ARMS:
        ranges, jac, reliable, reachable = [], [], 0, 0
        for skey, _p, _d, _a in SECTIONS:
            cells = grid[(skey, arm)]
            if not cells:
                continue
            counts = [c["scenarios"] for c in cells]
            ranges.append(max(counts) - min(counts))
            tagsets = [c["tags"] for c in cells]
            jac += [jaccard(tagsets[i], tagsets[j])
                    for i in range(len(tagsets)) for j in range(i + 1, len(tagsets))]
            reliable += len(set.intersection(*tagsets))
            reachable += len(set.union(*tagsets))
        share = (100.0 * reliable / reachable) if reachable else None
        L.append("| `%s` | %s | %s | %d / %d  (%s) |"
                 % (arm, fmt(mean(ranges), "%.1f"), fmt(mean(jac)),
                    reliable, reachable, fmt(share, "%.0f%%")))

    L += ["",
          "A low Jaccard beside a large tag union means the arm *can* reach many distinct "
          "behaviours but does not reach the same ones twice -- which makes any "
          "single-run comparison between arms unsafe.",
          "", "---", "",
          "## What these do not tell you",
          "",
          "* Nothing here judges whether a scenario is legally correct. Self-BLEU cannot "
          "tell two genuinely different wrong scenarios from two right ones.",
          "* Behaviour tags are the model's self-description, so tag stability bounds "
          "real semantic stability from neither side: a run can relabel the same "
          "behaviour and read as unstable, or reuse a label for different content and "
          "read as stable.",
          "* n = 3 subclauses. Descriptive only -- no significance testing at this size "
          "(Arcuri & Briand, STVR 2014).",
          ""]

    report = "\n".join(L) + "\n"
    out = os.path.join(OUT_DIR, "metrics.md")
    with io.open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(report)
    print("Wrote %s" % out)

    if args.json:
        blob = {"%s|%s" % k: [{kk: vv for kk, vv in c.items()
                               if kk not in ("texts", "tags")} for c in v]
                for k, v in grid.items()}
        jout = os.path.join(OUT_DIR, "metrics.json")
        with io.open(jout, "w", encoding="utf-8") as fh:
            json.dump(blob, fh, indent=2)
        print("Wrote %s" % jout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
