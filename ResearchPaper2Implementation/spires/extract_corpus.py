"""Run SPIRES extraction over every clause of Schedule 1, resumably.

Sixty-two extractions at roughly half a minute each is long enough that a bash loop is
the wrong tool: a network blip a third of the way through should not cost the whole run.
Each clause is written as it completes and skipped if already present, so re-running
after a failure resumes rather than restarts.

Clause blocks, not the 134 corpus documents: a clause maps 1:1 onto the :Provision nodes
the query method already uses, whereas prep_app.py's documents split some clauses across
several self-contained sentences and would produce several disconnected extractions for
one provision.

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

from enrich_graph import raw_clause_text  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(HERE, "app_norm.yaml")
INPUT_DIR = os.path.join(HERE, "input")
OUTPUT_DIR = os.path.join(HERE, "output")
PYTHON = os.path.join(".venv-ontogpt", "Scripts", "ontogpt.exe")


def slug(provision_id):
    return provision_id.replace(".", "_")


def write_inputs(clauses):
    """One file per clause, so ontogpt's -i has something to point at."""
    os.makedirs(INPUT_DIR, exist_ok=True)
    written = {}
    for key, text in sorted(clauses.items()):
        pid = key.replace("subclause ", "")
        path = os.path.join(INPUT_DIR, "app_%s.txt" % slug(pid))
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("%s %s\n" % (pid, text) if not text.startswith(pid) else text + "\n")
        written[pid] = path
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-4o")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--only", nargs="*", default=None, help="Specific provision ids.")
    args = ap.parse_args()

    clauses = raw_clause_text()
    inputs = write_inputs(clauses)
    if args.only:
        inputs = {k: v for k, v in inputs.items() if k in set(args.only)}

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    todo = []
    for pid, path in sorted(inputs.items(), key=lambda kv: [int(x) for x in kv[0].split(".")]):
        out = os.path.join(OUTPUT_DIR, "app_%s.yaml" % slug(pid))
        if os.path.exists(out) and not args.overwrite:
            continue
        todo.append((pid, path, out))

    print("%d clause(s) total, %d already extracted, %d to do"
          % (len(inputs), len(inputs) - len(todo), len(todo)))
    if args.dry_run:
        # The pilot cost $1 for ~24 extractions of comparable clauses.
        print("estimated cost: $%.2f on %s" % (len(todo) * 0.042, args.model))
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
