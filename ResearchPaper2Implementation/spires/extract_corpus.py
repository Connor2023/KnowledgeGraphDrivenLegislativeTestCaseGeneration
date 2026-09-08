"""Run SPIRES extraction over every provision of the configured corpus, resumably.

A hundred extractions at roughly half a minute each is long enough that a bash loop is
the wrong tool: a network blip a third of the way through should not cost the whole run.
Each clause is written as it completes and skipped if already present, so re-running
after a failure resumes rather than restarts.

Provisions, not the flattened corpus documents: a provision maps 1:1 onto the :Provision
nodes the query method uses, whereas the flattening in evaluation/arms/prep_app.py splits
some clauses across several self-contained sentences and would produce several
disconnected extractions for one provision.

    python spires/extract_corpus.py --dry-run
    python spires/extract_corpus.py
    python spires/extract_corpus.py --only 6.1 6.2
"""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import corpus_config  # noqa: E402
import prep_corpus  # noqa: E402

SCHEMA = corpus_config.SPIRES_SCHEMA
INPUT_DIR = corpus_config.SPIRES_INPUT_DIR
OUTPUT_DIR = corpus_config.SPIRES_OUTPUT_DIR
PYTHON = os.path.join(".venv-ontogpt", "Scripts", "ontogpt.exe")



def write_inputs(clauses):
    """One file per clause, so ontogpt's -i has something to point at."""
    os.makedirs(INPUT_DIR, exist_ok=True)
    written = {}
    for pid, text in clauses.items():
        path = os.path.join(INPUT_DIR, corpus_config.provision_filename(pid, ".txt"))
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("%s %s\n" % (pid, text) if not text.startswith(pid) else text + "\n")
        written[pid] = path
    return written


# gpt-4o and gpt-4o-mini list prices, USD per 1M tokens.
PRICES = {"gpt-4o": (2.50, 10.00), "gpt-4o-mini": (0.150, 0.600)}

# SPIRES is recursive: a root call, then one more for each CompoundExpression slot it has
# to fill. Measured on Schedule 1 the whole run came to ~$0.90 against a single-call floor
# of $0.59, so it makes about half as many calls again as there are provisions.
RECURSION_MULTIPLIER = 1.5

# Completion length, measured across the 62 Schedule 1 extractions.
COMPLETION_TOKENS = 400


def estimate_cost(texts, model):
    """What this run will cost, priced from the prompt rather than from a flat rate.

    The previous estimate was `count x $0.042`, calibrated on an early 24-provision pilot.
    It over-stated Schedule 1 by 2.9x -- $2.60 against a measured $0.90 -- and projected
    $4.45 for Part IIIC, which reads as though the second corpus were five times as
    expensive. It is not: 1.71x the provisions, at ~$1.53.

    The shape that matters is that the schema is resent with every call and is 2,107
    tokens against a mean provision of ~100, so cost tracks the number of PROVISIONS, not
    the size of the corpus. Part IIIC has 1.44x Schedule 1's words but 1.71x its
    provisions, and costs 1.7x.
    """
    try:
        import tiktoken
        encoder = tiktoken.get_encoding("cl100k_base")
        count = lambda t: len(encoder.encode(t))      # noqa: E731
        how = "tiktoken"
    except ImportError:
        count = lambda t: max(1, len(t) // 4)         # noqa: E731
        how = "chars/4"

    if not texts:
        return 0.0, "nothing to do"
    with io.open(SCHEMA, encoding="utf-8") as fh:
        schema_tokens = count(fh.read())
    price_in, price_out = PRICES.get(model, PRICES["gpt-4o"])
    prompt_tokens = sum(schema_tokens + count(t) for t in texts)
    completion_tokens = len(texts) * COMPLETION_TOKENS
    floor = (prompt_tokens * price_in + completion_tokens * price_out) / 1e6
    return floor * RECURSION_MULTIPLIER, (
        "%d provisions x (%d schema + ~%d text) tokens, x%.1f for recursion, via %s"
        % (len(texts), schema_tokens,
           (prompt_tokens / max(1, len(texts))) - schema_tokens,
           RECURSION_MULTIPLIER, how))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-4o")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--only", nargs="*", default=None, help="Specific provision ids.")
    args = ap.parse_args()

    # Segmented from the structural profile, not from a parser written for this one
    # statute. Keys are bare identifiers -- '6.1', '26WE(1)' -- and the order is the
    # order the instrument states them in.
    clauses = prep_corpus.provisions()
    inputs = write_inputs(clauses)
    if args.only:
        inputs = {k: v for k, v in inputs.items() if k in set(args.only)}

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    todo = []
    # Document order from the segmentation. The previous key, [int(x) for x in
    # pid.split(".")], assumed every statute numbers clauses N.M and raises on "26WE(1)".
    for pid in [p for p in prep_corpus.order() if p in inputs]:
        path = inputs[pid]
        out = os.path.join(OUTPUT_DIR, corpus_config.provision_filename(pid, ".yaml"))
        if os.path.exists(out) and not args.overwrite:
            continue
        todo.append((pid, path, out))

    print("%d clause(s) total, %d already extracted, %d to do"
          % (len(inputs), len(inputs) - len(todo), len(todo)))
    if args.dry_run:
        estimate, detail = estimate_cost([clauses[pid] for pid, _p, _o in todo], args.model)
        print("estimated cost: $%.2f on %s   (%s)" % (estimate, args.model, detail))
        return 0

    env = dict(os.environ)
    key = env.get("OPENAI_API_KEY") or env.get("OPENAI_KEY")
    if not key:
        print("No OPENAI_API_KEY or OPENAI_KEY in the environment.")
        return 1
    env["OPENAI_API_KEY"] = key

    started, failed = time.time(), []
    for index, (pid, path, out) in enumerate(todo, 1):
        result = subprocess.run(
            [PYTHON, "extract", "-t", SCHEMA, "-i", path, "-m", args.model, "-o", out],
            env=env, capture_output=True, text=True)
        ok = result.returncode == 0 and os.path.exists(out)
        if not ok:
            failed.append(pid)
            # Keep the stderr tail: a schema error looks nothing like a rate limit, and
            # the difference decides whether re-running will help.
            with io.open(os.path.join(OUTPUT_DIR, "errors.log"), "a", encoding="utf-8") as fh:
                fh.write("=== %s ===\n%s\n\n" % (pid, (result.stderr or "")[-1500:]))
        elapsed = time.time() - started
        print("[%2d/%2d] %-6s %-4s  %.0fs elapsed, ~%.0fs left"
              % (index, len(todo), pid, "ok" if ok else "FAIL", elapsed,
                 elapsed / index * (len(todo) - index)))

    print("\ndone: %d extracted, %d failed %s"
          % (len(todo) - len(failed), len(failed), failed or ""))
    if failed:
        print("see %s; re-run to retry only the failures"
              % os.path.join(OUTPUT_DIR, "errors.log"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
