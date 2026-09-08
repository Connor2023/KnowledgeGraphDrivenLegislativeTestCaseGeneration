"""Add provision text and cross-reference edges to the EDC knowledge graph.

NOT part of the pipeline. Its citation patterns were generalised into references.py,
and :SP_Provision nodes now carry their own text, so the SPIRES construction path
imports nothing from here. What remains serves the `kg` and `kg-text-only` arms,
which is why it sits beside them.

references.py reproduces parse_references exactly on Schedule 1 -- the same 33
REFERS_TO edges -- which is the equivalence that let the pipeline stop calling this;
see tests/test_references.py.

Two enrichments, both idempotent and both additive — nothing existing is removed:

1. `text_raw` and `text_normalised` properties on :Provision nodes.
   Raw is verbatim from APPschedule1.txt, so it can be cited. Normalised is the
   corpus document EDC actually saw, which is self-contained but paraphrases structure.

2. :REFERS_TO edges between provisions, and to :Principle nodes.
   This is the structural gap behind the failed baseline cases: subclause 2.2 disapplies
   2.1, but nothing in the graph connects them, so 2.1 is unreachable from 2.2.

    python enrich_graph.py --dry-run
    python enrich_graph.py
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import os
import re
import sys

# Three levels up: this module used to sit at the repository root and now sits in
# evaluation/arms/. corpus_config, prep_corpus and load_neo4j all live at the root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from . import prep_app  # noqa: E402  - reused for its line classification
import corpus_config  # noqa: E402
from corpus_config import detect_provision_id, provision_key  # noqa: E402

RAW_PATH = corpus_config.RAW_PATH
CORPUS_PATH = corpus_config.CORPUS_PATH
OUT_DIR = corpus_config.EDC_GRAPH_DIR

# --- cross-reference parsing -------------------------------------------------------
# "subclause 6.2 or 6.3 applies" -- the bare 6.3 carries the prefix across the
# conjunction, so a naive `subclause \d+\.\d+` silently drops it.
_SUBCLAUSE_RUN = re.compile(
    r"\b(?:sub)?clauses?\s+((?:\d+\.\d+)(?:\s*(?:,|or|and|to)\s*\d+(?:\.\d+)?)*)", re.I)
_PARAGRAPH = re.compile(r"\bparagraphs?\s+(\d+\.\d+)\([a-z]+\)", re.I)
# "Australian Privacy Principles 5 to 13" is a range; APP 4.4 is almost nothing else.
_APP_RUN = re.compile(
    r"\bAustralian Privacy Principles?\s+((?:\d+)(?:\s*(?:,|or|and|to)\s*\d+)*)", re.I)
_NUM = re.compile(r"\d+(?:\.\d+)?")


def _expand(run: str, dotted: bool):
    """Expand '6.2 or 6.3' and '5 to 13' into the individual identifiers."""
    tokens = _NUM.findall(run)
    out, has_range = [], re.search(r"\bto\b", run, re.I)
    for t in tokens:
        out.append(t)
    if has_range and len(tokens) >= 2 and not dotted:
        try:
            lo, hi = int(tokens[0]), int(tokens[-1])
            if 0 < lo < hi <= 13:
                out = [str(n) for n in range(lo, hi + 1)]
        except ValueError:
            pass
    return out


def parse_references(text: str, self_key: str):
    """Return (provision_keys, principle_names) referenced by this clause text."""
    provisions, principles = set(), set()

    for run in _SUBCLAUSE_RUN.findall(text):
        for ident in _expand(run, dotted=True):
            if "." in ident:
                provisions.add(provision_key(ident))
    for ident in _PARAGRAPH.findall(text):
        provisions.add(provision_key(ident))          # paragraph 6.2(e) -> subclause 6.2
    for run in _APP_RUN.findall(text):
        for ident in _expand(run, dotted=False):
            if "." not in ident:
                principles.add("Australian Privacy Principle %s" % ident)

    provisions.discard(self_key)                       # a clause referring to itself is noise
    return sorted(provisions), sorted(principles)


# --- text extraction ---------------------------------------------------------------

def raw_clause_text():
    """Verbatim text per subclause, straight from the Schedule.

    A clause runs from its own `N.M` line until the next clause, Part or Principle
    heading, so subparagraphs and closing tails stay attached.
    """
    lines = io.open(RAW_PATH, encoding="utf-8").read().splitlines()
    out, current, buffer = {}, None, []

    def flush():
        if current and buffer:
            out[provision_key(current)] = " ".join(
                prep_app.normalise(x) for x in buffer if x.strip())

    for raw in lines:
        line = prep_app.normalise(raw)
        if not line:
            continue
        if prep_app.RE_PART.match(line) or prep_app.RE_APP.match(line):
            flush()
            current, buffer = None, []
            continue
        m = prep_app.RE_CLAUSE.match(line)
        if m:
            flush()
            current, buffer = m.group(1), [line]
            continue
        if current:
            buffer.append(line)
    flush()
    return out


def normalised_clause_text():
    """The corpus documents EDC saw, grouped by the clause they belong to."""
    grouped = collections.defaultdict(list)
    for line in io.open(CORPUS_PATH, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        pid = detect_provision_id(line)
        if pid:
            grouped[provision_key(pid)].append(line)
    return {k: " ".join(v) for k, v in grouped.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Write CSVs but do not load.")
    ap.add_argument("--creds", default=None)
    args = ap.parse_args()

    raw = raw_clause_text()
    norm = normalised_clause_text()
    nodes = list(csv.DictReader(
        io.open(os.path.join(OUT_DIR, "nodes.csv"), encoding="utf-8", newline="")))
    provisions = {n["key"] for n in nodes if n["label"] == "Provision"}
    known = {n["key"] for n in nodes}
    by_name = {n["name"]: n["key"] for n in nodes}

    text_rows, missing = [], []
    for key in sorted(provisions):
        if key in raw or key in norm:
            text_rows.append({"key": key,
                              "text_raw": raw.get(key, ""),
                              "text_normalised": norm.get(key, "")})
        else:
            missing.append(key)

    ref_rows = []
    for key in sorted(provisions):
        source = raw.get(key) or norm.get(key)
        if not source:
            continue
        prov_refs, princ_refs = parse_references(source, key)
        for target in prov_refs:
            if target in known:
                ref_rows.append({"from_key": key, "to_key": target, "kind": "provision"})
        for name in princ_refs:
            target = by_name.get(name)
            if target and target != key:
                ref_rows.append({"from_key": key, "to_key": target, "kind": "principle"})

    os.makedirs(OUT_DIR, exist_ok=True)
    with io.open(os.path.join(OUT_DIR, "provision_text.csv"), "w",
                 encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["key", "text_raw", "text_normalised"])
        w.writeheader()
        w.writerows(text_rows)
    with io.open(os.path.join(OUT_DIR, "refers_to.csv"), "w",
                 encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["from_key", "to_key", "kind"])
        w.writeheader()
        w.writerows(ref_rows)

    print("provision nodes        : %d" % len(provisions))
    print("  with text            : %d" % len(text_rows))
    print("  without (structural) : %d  %s" % (len(missing), missing[:6]))
    print("cross-references found : %d over %d source clauses"
          % (len(ref_rows), len({r["from_key"] for r in ref_rows})))
    print("  to provisions        : %d" % sum(1 for r in ref_rows if r["kind"] == "provision"))
    print("  to principles        : %d" % sum(1 for r in ref_rows if r["kind"] == "principle"))
    print("written to             : %s" % OUT_DIR)

    if args.dry_run:
        print("\nDry run -- nothing loaded.")
        return 0

    from load_neo4j import load_credentials
    creds = load_credentials(args.creds)
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(creds["NEO4J_URI"],
                                  auth=(creds["NEO4J_USERNAME"], creds["NEO4J_PASSWORD"]))
    try:
        with driver.session(database=creds.get("NEO4J_DATABASE") or "neo4j") as session:
            session.run(
                "UNWIND $rows AS row MATCH (n:AppNode {key: row.key}) "
                "SET n.text_raw = row.text_raw, n.text_normalised = row.text_normalised",
                rows=text_rows)
            session.run(
                "UNWIND $rows AS row "
                "MATCH (a:AppNode {key: row.from_key}) MATCH (b:AppNode {key: row.to_key}) "
                "MERGE (a)-[r:REFERS_TO]->(b) SET r.kind = row.kind",
                rows=ref_rows)
            n = session.run("MATCH (n:AppNode) WHERE n.text_raw IS NOT NULL "
                            "RETURN count(n) AS c").single()["c"]
            e = session.run("MATCH (:AppNode)-[r:REFERS_TO]->(:AppNode) "
                            "RETURN count(r) AS c").single()["c"]
            print("\nloaded: %d nodes carry text, %d REFERS_TO edges" % (n, e))
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
