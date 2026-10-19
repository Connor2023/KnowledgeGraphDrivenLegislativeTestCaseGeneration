"""Collect everything clean_extraction.py throws away, so the discard rate can be audited.

Cleaning drops 47% of condition and exception field values. Most of that is genuinely
SPIRES' angle-bracket placeholders, but "most" is an assumption until someone looks, and
anything wrongly dropped is content that was paid for and extracted correctly.

Discards are ranked by how much they could cost, not by how many there are:

  compound_dropped  a whole condition or exception was removed because its `statement`
                    did not survive -- yet its other fields held content. This is the
                    only category that can lose a real legal proposition, so it goes
                    first however few there are.
  description_echo  matched a phrase from the schema's own field description. Usually a
                    genuine echo, but a real statement could contain the same words --
                    "as stated in the text" is a plausible thing for a clause to say.
  nullish           "None", "Blank", "N/A". Safe unless a clause is genuinely about none.
  bracket_only      "<>", "<Empty>". Unambiguously an artefact; listed last and capped.

The classification calls clean_extraction's own predicates rather than reimplementing
them, so this file cannot drift from what the cleaner actually does.

    python spires/review_discards.py
    python spires/review_discards.py --glob "spires/pilot/output/app_*.yaml"
"""

from __future__ import annotations

import argparse
import glob
import io
import os
import sys

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)                       # sibling modules
sys.path.insert(0, os.path.dirname(_HERE))      # repo root, for corpus_config

import corpus_config  # noqa: E402
from clean_extraction import _DESCRIPTION_TELLS, _NULLISH, denull, unwrap  # noqa: E402

DEFAULT_GLOB = corpus_config.provision_glob(".yaml")
OUT_PATH = os.path.join(corpus_config.SPIRES_DIR, "discard_review.md")

RANK = {"compound_dropped": 0, "description_echo": 1, "nullish": 2, "bracket_only": 3}


def classify(raw_value):
    """Why this value did not survive, or None if it did."""
    if not isinstance(raw_value, str):
        return None
    unwrapped = unwrap(raw_value)
    if denull(unwrapped) is not None:
        return None
    lowered = unwrapped.strip().lower()
    if any(tell in lowered for tell in _DESCRIPTION_TELLS):
        return "description_echo"
    if lowered in _NULLISH:
        # A bare "<>" or "<Empty>" is the prompt's own marker; a bare "None" is the model
        # answering in words. Worth separating: only the latter could ever be meant.
        return "bracket_only" if raw_value.strip().startswith("<") and not lowered else "nullish"
    return "nullish"


def collect(paths):
    rows = []
    kept = dropped = 0
    for path in paths:
        with io.open(path, encoding="utf-8") as fh:
            document = yaml.safe_load(fh)
        extracted = document.get("extracted_object") or {}
        pid = str(extracted.get("provision_id"))
        for norm_index, norm in enumerate(extracted.get("norms") or [], 1):
            if not isinstance(norm, dict):
                continue
            for field in ("conditions", "exceptions"):
                for item_index, item in enumerate(norm.get(field) or [], 1):
                    if not isinstance(item, dict):
                        continue
                    statement_survives = denull(unwrap(item.get("statement"))) is not None
                    survivors = {k: denull(unwrap(v)) for k, v in item.items()}
                    has_other = any(v for k, v in survivors.items() if k != "statement")

                    for key, value in item.items():
                        reason = classify(value)
                        if reason is None:
                            kept += 1
                            continue
                        dropped += 1
                        # A dropped statement that took real sibling content with it is
                        # the expensive case, not just another placeholder.
                        if key == "statement" and not statement_survives and has_other:
                            reason = "compound_dropped"
                        rows.append({
                            "provision": pid, "norm": norm_index,
                            "path": "%s[%d].%s" % (field, item_index, key),
                            "raw": value,
                            "siblings": {k: v for k, v in item.items() if k != key},
                            "reason": reason,
                        })
    rows.sort(key=lambda r: (RANK[r["reason"]], r["provision"]))
    return rows, kept, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default=DEFAULT_GLOB)
    ap.add_argument("--out", default=OUT_PATH)
    ap.add_argument("--bracket-cap", type=int, default=15,
                    help="How many bracket_only rows to show; they are all identical.")
    args = ap.parse_args()

    paths = sorted(p for p in glob.glob(args.glob)
                   if not p.endswith((".clean.yaml", ".verified.yaml")))
    rows, kept, dropped = collect(paths)
    total = kept + dropped

    counts = {}
    for row in rows:
        counts[row["reason"]] = counts.get(row["reason"], 0) + 1

    L = [
        "# Discard review",
        "",
        "Every condition/exception field value that `clean_extraction.py` removed, from "
        "%d provisions. Ranked by how much the discard could cost, not by frequency."
        % len(paths),
        "",
        "| | Count | Share of all values | Risk |",
        "|---|---|---|---|",
    ]
    RISK = {
        "compound_dropped": "**HIGH** - a whole condition/exception was lost while its other fields held content",
        "description_echo": "MEDIUM - usually a genuine echo, but a real clause could contain the same words",
        "nullish": "LOW - the model wrote a word for absence",
        "bracket_only": "NONE - the prompt's own fill-in marker",
    }
    for reason in sorted(counts, key=lambda r: RANK[r]):
        L.append("| `%s` | %d | %.0f%% | %s |"
                 % (reason, counts[reason], 100.0 * counts[reason] / total, RISK[reason]))
    L += ["",
          "%d of %d values kept, %d discarded (%.0f%%)."
          % (kept, total, dropped, 100.0 * dropped / total),
          "",
          "**How to review:** read the HIGH and MEDIUM sections. For each row ask whether "
          "the raw value carried legal content. If it did, the cleaner is deleting "
          "extracted data and its rules need narrowing before the graph is built on it.",
          "", "---", ""]

    for reason in sorted(counts, key=lambda r: RANK[r]):
        subset = [r for r in rows if r["reason"] == reason]
        shown = subset[:args.bracket_cap] if reason == "bracket_only" else subset
        L += ["## %s  (%d)" % (reason, len(subset)), "", RISK[reason], ""]
        if reason in ("compound_dropped", "description_echo"):
            L += ["| Provision | Field | Discarded value | Sibling fields |",
                  "|---|---|---|---|"]
            for r in shown:
                siblings = "; ".join("%s=%s" % (k, str(v)[:40])
                                     for k, v in r["siblings"].items()) or "-"
                L.append("| %s | `%s` | %s | %s |"
                         % (r["provision"], r["path"],
                            str(r["raw"]).replace("|", r"\|")[:110],
                            siblings.replace("|", r"\|")))
        else:
            L += ["| Provision | Field | Discarded value |", "|---|---|---|"]
            for r in shown:
                L.append("| %s | `%s` | %s |"
                         % (r["provision"], r["path"],
                            str(r["raw"]).replace("|", r"\|")[:110]))
        if len(shown) < len(subset):
            L.append("")
            L.append("_%d further rows omitted; they are the same marker._"
                     % (len(subset) - len(shown)))
        L += [""]

    with io.open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L) + "\n")

    print("%d values total, %d kept, %d discarded (%.0f%%)"
          % (total, kept, dropped, 100.0 * dropped / total))
    for reason in sorted(counts, key=lambda r: RANK[r]):
        print("  %-18s %3d" % (reason, counts[reason]))
    print("wrote %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
