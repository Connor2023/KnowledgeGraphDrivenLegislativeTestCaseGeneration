"""Turn the SPIRES extractions into a reified norm graph in the existing Aura instance.

The analogue of build_graph.py, but the shape is the whole point. EDC's graph is flat
binary triples -- `APP entity - holds - personal information` -- and the controlled
experiment measured those as net-negative: withholding them beat including them. A Norm
is not a triple, so it is reified as a node with typed edges to its bearer, action,
object, conditions and exceptions. Flattening here would re-create exactly the failure
the extraction was bought to avoid.

    :SP_Provision {key:'6.1'} -[:SP_HAS_NORM]-> :SP_Norm {modality:'PROHIBITION'}
        -[:SP_BEARER]->    :SP_Actor      {name:'APP entity'}
        -[:SP_ACTION]->    :SP_Action     {name:'use or disclose'}
        -[:SP_OBJECT]->    :SP_InfoType   {name:'personal information'}
        -[:SP_CONDITION]-> :SP_Condition  {statement:'for a secondary purpose'}
        -[:SP_EXCEPTION]-> :SP_Exemption  {statement:'unless the individual has consented'}
    :SP_Provision {key:'2.2'} -[:SP_DISAPPLIES]-> :SP_Provision {key:'2.1'}
    :SP_Provision {key:'6.1'} -[:SP_REFERS_TO]->  :SP_Provision {key:'6.2'}

Two sources, each doing what it measured best at:

    norms, modality, conditions, exceptions   SPIRES
    cross-reference edges                     enrich_graph.parse_references

That split is not a preference. Over all 62 clauses the regex found cross-references in
28 provisions against SPIRES' 10, recovering 19 that SPIRES missed entirely -- so taking
edges from SPIRES would discard two thirds of the graph's connectivity.

Actors, actions and information types are shared across provisions; conditions and
exceptions are not. A condition is a sentence about one norm, so pooling identical
statements would assert a connection between provisions that the statute does not make.
Shared vocabulary nodes are what give the graph cross-provision structure at all.

    python spires/build_spires_graph.py --dry-run
    python spires/build_spires_graph.py
    python spires/build_spires_graph.py --wipe        # drop SP_* first
"""

from __future__ import annotations

import argparse
import collections
import csv
import glob
import io
import os
import re
import sys
import urllib.parse

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from enrich_graph import parse_references, raw_clause_text  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
GRAPH_DIR = os.path.join(HERE, "graph")
PREFIX = "SP_"

# Reuse the verified extractions when present -- they carry the recovered exceptions --
# and fall back to the merely cleaned ones for any provision the verifier had to skip.
VERIFIED = os.path.join(HERE, "output", "app_*.verified.yaml")
CLEANED = os.path.join(HERE, "output", "app_*.clean.yaml")

_WS = re.compile(r"\s+")


def decode(value):
    """SPIRES writes NamedEntity slots as `AUTO:use%20or%20disclose`."""
    if not isinstance(value, str):
        return None
    text = value.split(":", 1)[-1] if value.startswith("AUTO:") else value
    return _WS.sub(" ", urllib.parse.unquote(text)).strip() or None


def vocab_key(kind, name):
    """Stable id for a shared vocabulary node, case-folded so spellings converge."""
    return "%s:%s" % (kind, _WS.sub(" ", name.lower()).strip())


def load_provisions():
    """One cleaned provision per id, preferring the verified file."""
    out = {}
    for pattern in (CLEANED, VERIFIED):          # verified second so it wins
        for path in sorted(glob.glob(pattern)):
            with io.open(path, encoding="utf-8") as fh:
                document = yaml.safe_load(fh)
            if not document or not document.get("provision_id"):
                continue
            out[str(document["provision_id"])] = document
    return out


def build(provisions):
    nodes, edges = {}, []
    counts = collections.Counter()

    def node(key, label, **props):
        if key not in nodes:
            nodes[key] = {"key": key, "label": label, **props}
            counts[label] += 1
        return key

    def edge(src, rel, dst, **props):
        edges.append({"from_key": src, "rel": rel, "to_key": dst, **props})
        counts[rel] += 1

    for pid, document in sorted(provisions.items()):
        prov_key = "provision:%s" % pid
        node(prov_key, "SP_Provision", name="subclause %s" % pid, provision=pid)

        for index, norm in enumerate(document.get("norms") or [], 1):
            modality = (norm.get("deontic_modality") or "UNSPECIFIED").strip()
            norm_key = "norm:%s:%d" % (pid, index)
            node(norm_key, "SP_Norm", name="%s %s#%d" % (modality, pid, index),
                 modality=modality, provision=pid,
                 scope_qualifier=norm.get("scope_qualifier") or "")
            edge(prov_key, "SP_HAS_NORM", norm_key)

            for slot, label, rel in (("bearer", "SP_Actor", "SP_BEARER"),
                                     ("action", "SP_Action", "SP_ACTION"),
                                     ("object", "SP_InfoType", "SP_OBJECT")):
                name = decode(norm.get(slot))
                if not name:
                    continue
                key = vocab_key(label, name)
                node(key, label, name=name)
                edge(norm_key, rel, key)

            for slot, label, rel in (("conditions", "SP_Condition", "SP_CONDITION"),
                                     ("exceptions", "SP_Exemption", "SP_EXCEPTION")):
                for item_index, item in enumerate(norm.get(slot) or [], 1):
                    statement = (item.get("statement") or "").strip()
                    if not statement:
                        continue
                    key = "%s:%s:%d:%d" % (label.lower(), pid, index, item_index)
                    node(key, label, name=statement[:70], statement=statement,
                         source_provision=str(item.get("source_provision") or ""),
                         verified=bool(item.get("verified")))
                    edge(norm_key, rel, key)

    return nodes, edges, counts


def add_reference_edges(nodes, edges, counts, provisions):
    """Cross-reference edges from the regex, which measured far better than SPIRES."""
    raw = raw_clause_text()
    known = {pid for pid in provisions}
    added = skipped = 0
    for key, text in sorted(raw.items()):
        pid = key.replace("subclause ", "")
        if pid not in known:
            continue
        targets, _principles = parse_references(text, key)
        for target in targets:
            target_pid = target.replace("subclause ", "")
            if target_pid not in known or target_pid == pid:
                skipped += 1
                continue
            edges.append({"from_key": "provision:%s" % pid, "rel": "SP_REFERS_TO",
                          "to_key": "provision:%s" % target_pid})
            counts["SP_REFERS_TO"] += 1
            added += 1

    # `disapplies` is the one edge SPIRES produces that the regex cannot: it distinguishes
    # "this switches that off" from a bare mention, which is a semantic call, not a
    # pattern. Kept alongside SP_REFERS_TO rather than instead of it.
    for pid, document in sorted(provisions.items()):
        for target in (document.get("disapplies") or []):
            target_pid = str(target).replace("subclause ", "").strip()
            if target_pid in known and target_pid != pid:
                edges.append({"from_key": "provision:%s" % pid,
                              "rel": "SP_DISAPPLIES",
                              "to_key": "provision:%s" % target_pid})
                counts["SP_DISAPPLIES"] += 1
    return added, skipped


def write_csvs(nodes, edges):
    os.makedirs(GRAPH_DIR, exist_ok=True)
    node_fields = ["key", "label", "name", "modality", "provision", "scope_qualifier",
                   "statement", "source_provision", "verified"]
    with io.open(os.path.join(GRAPH_DIR, "nodes.csv"), "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, node_fields, extrasaction="ignore")
        writer.writeheader()
        for value in nodes.values():
            writer.writerow(value)
    with io.open(os.path.join(GRAPH_DIR, "edges.csv"), "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, ["from_key", "rel", "to_key"], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(edges)


def load(nodes, edges, wipe, creds_path=None):
    from load_neo4j import load_credentials
    from neo4j import GraphDatabase

    creds = load_credentials(creds_path)
    if not creds.get("NEO4J_URI"):
        raise SystemExit(
            "No Neo4j credentials. Dot-source setup_env.ps1, or pass --creds with the "
            "path to the Aura credentials file.")
    driver = GraphDatabase.driver(creds["NEO4J_URI"],
                                  auth=(creds["NEO4J_USERNAME"], creds["NEO4J_PASSWORD"]))
    try:
        with driver.session(database=creds.get("NEO4J_DATABASE") or "neo4j") as session:
            if wipe:
                # Only SP_*; :AppNode and :RP1Entity share this instance and must survive.
                removed = session.run(
                    "MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH $p) "
                    "DETACH DELETE n RETURN count(n) AS c", p=PREFIX).single()["c"]
                print("wiped %d existing %s node(s)" % (removed, PREFIX))

            by_label = collections.defaultdict(list)
            for value in nodes.values():
                by_label[value["label"]].append(value)
            for label, rows in sorted(by_label.items()):
                session.run(
                    "UNWIND $rows AS row MERGE (n:`%s` {key: row.key}) SET n += row" % label,
                    rows=rows)
                print("  %-14s %4d nodes" % (label, len(rows)))

            by_rel = collections.defaultdict(list)
            for e in edges:
                by_rel[e["rel"]].append(e)
            for rel, rows in sorted(by_rel.items()):
                # The relationship type cannot be parameterised, and the query contains
                # literal braces, so it is concatenated rather than .format()-ed.
                session.run(
                    "UNWIND $rows AS row MATCH (a {key: row.from_key}) "
                    "MATCH (b {key: row.to_key}) MERGE (a)-[:`" + rel + "`]->(b)",
                    rows=rows)
                print("  %-14s %4d edges" % (rel, len(rows)))

            total = session.run(
                "MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH $p) "
                "RETURN count(n) AS c", p=PREFIX).single()["c"]
            print("\nin Aura: %d %s nodes" % (total, PREFIX))
    finally:
        driver.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Write CSVs, do not load.")
    ap.add_argument("--wipe", action="store_true", help="Delete existing SP_* first.")
    ap.add_argument("--creds", default=None,
                    help="Aura credentials file; the environment wins over it.")
    args = ap.parse_args()

    provisions = load_provisions()
    nodes, edges, counts = build(provisions)
    added, skipped = add_reference_edges(nodes, edges, counts, provisions)
    write_csvs(nodes, edges)

    print("provisions        : %d" % len(provisions))
    for label in sorted(k for k in counts if k.startswith("SP_") and "_" not in k[3:]):
        pass
    print("\nnodes")
    for label in ("SP_Provision", "SP_Norm", "SP_Actor", "SP_Action", "SP_InfoType",
                  "SP_Condition", "SP_Exemption"):
        print("  %-14s %4d" % (label, counts.get(label, 0)))
    print("\nedges")
    for rel in ("SP_HAS_NORM", "SP_BEARER", "SP_ACTION", "SP_OBJECT", "SP_CONDITION",
                "SP_EXCEPTION", "SP_REFERS_TO", "SP_DISAPPLIES"):
        print("  %-14s %4d" % (rel, counts.get(rel, 0)))
    print("\ntotals            : %d nodes, %d edges" % (len(nodes), len(edges)))
    print("cross-refs skipped: %d (target not a known provision)" % skipped)
    print("csvs              : %s" % GRAPH_DIR)

    if args.dry_run:
        print("\nDry run -- nothing loaded.")
        return 0
    load(nodes, edges, args.wipe, args.creds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
