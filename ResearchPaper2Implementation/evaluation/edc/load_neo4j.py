"""Load the APP knowledge graph into a Neo4j Aura instance.

Reads nodes.csv / edges.csv and writes them with parameterised, batched queries -- faster
than replaying graph.cypher statement by statement, and immune to string-escaping issues.

Credentials come from an Aura credentials file (the NEO4J_URI / NEO4J_USERNAME /
NEO4J_PASSWORD / NEO4J_DATABASE dump Aura gives you) or from the environment. The password
is never logged, printed, or written anywhere.

  python load_neo4j.py --creds "C:/path/Neo4j-xxxx-Created-....txt" --dry-run
  python load_neo4j.py --creds "C:/path/Neo4j-xxxx-Created-....txt"
"""

import argparse
import csv
import json
import io
import os
import sys

# Three levels up to the repository root, then into pipeline/, where credentials.py lives.
# This loader is the EDC arm's and belongs here in evaluation; the credential resolution it
# used to own is needed by the SPIRES graph builder and the workbench API, which do not.
# Re-exported so `from load_neo4j import load_credentials` keeps working.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "pipeline"))

from credentials import load_credentials  # noqa: E402,F401

NODE_BATCH = 500
EDGE_BATCH = 500


def read_csv(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph-dir", default="evaluation/edc/edc-main/output/app_full/graph")
    ap.add_argument("--creds", default=None, help="Path to the Aura credentials file.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Connect and report what is already there, but write nothing.")
    ap.add_argument("--wipe", action="store_true",
                    help="Delete every node and relationship first. Dumps a JSON backup "
                         "of the existing graph beside the CSVs before deleting.")
    args = ap.parse_args()

    creds = load_credentials(args.creds)
    missing = [k for k in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD") if not creds.get(k)]
    if missing:
        print("Missing credentials: {}".format(", ".join(missing)))
        sys.exit(1)

    database = creds.get("NEO4J_DATABASE") or "neo4j"
    nodes = read_csv(os.path.join(args.graph_dir, "nodes.csv"))
    edges = read_csv(os.path.join(args.graph_dir, "edges.csv"))

    # Group edges by relationship type: the type cannot be parameterised in Cypher, so one
    # query per type keeps everything else safely bound.
    by_type = {}
    for e in edges:
        by_type.setdefault(e["type"], []).append(e)

    print("target instance : {} (database: {})".format(creds.get("AURA_INSTANCEID", "?"), database))
    print("to load         : {} nodes, {} edges, {} relationship types".format(
        len(nodes), len(edges), len(by_type)))

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(creds["NEO4J_URI"],
                                  auth=(creds["NEO4J_USERNAME"], creds["NEO4J_PASSWORD"]))
    try:
        driver.verify_connectivity()
        print("connection      : OK")

        with driver.session(database=database) as session:
            existing = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            existing_app = session.run("MATCH (n:AppNode) RETURN count(n) AS c").single()["c"]
            existing_rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            print("already present : {} nodes ({} :AppNode), {} relationships".format(
                existing, existing_app, existing_rels))

            if args.dry_run:
                print("\nDry run -- nothing written.")
                return

            if args.wipe:
                # Dump whatever is there before destroying it. Aura Free has no
                # point-in-time restore, so this file is the only way back.
                backup = {
                    "nodes": [
                        {"id": r["id"], "labels": r["labels"], "properties": r["props"]}
                        for r in session.run(
                            "MATCH (n) RETURN elementId(n) AS id, labels(n) AS labels, "
                            "properties(n) AS props")],
                    "relationships": [
                        {"start": r["s"], "end": r["e"], "type": r["t"], "properties": r["props"]}
                        for r in session.run(
                            "MATCH (a)-[r]->(b) RETURN elementId(a) AS s, elementId(b) AS e, "
                            "type(r) AS t, properties(r) AS props")],
                }
                backup_path = os.path.join(args.graph_dir, "pre_wipe_backup.json")
                with io.open(backup_path, "w", encoding="utf-8") as fh:
                    json.dump(backup, fh, indent=2, ensure_ascii=False)
                print("backup written  : {} ({} nodes, {} relationships)".format(
                    backup_path, len(backup["nodes"]), len(backup["relationships"])))

                session.run("MATCH (n) DETACH DELETE n")
                for record in list(session.run("SHOW CONSTRAINTS")):
                    name = record["name"]
                    if name != "app_node_key":
                        session.run("DROP CONSTRAINT {} IF EXISTS".format(name))
                        print("dropped constraint: {}".format(name))
                remaining = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
                print("wiped           : {} nodes remain".format(remaining))

            session.run("CREATE CONSTRAINT app_node_key IF NOT EXISTS "
                        "FOR (n:AppNode) REQUIRE n.key IS UNIQUE")

            written = 0
            for batch in chunks(nodes, NODE_BATCH):
                session.run(
                    "UNWIND $rows AS row "
                    "MERGE (n:AppNode {key: row.key}) "
                    "SET n.name = row.name, n.type = row.label",
                    rows=batch)
                written += len(batch)
            print("nodes written   : {}".format(written))

            # Apply the type label separately; APOC is not guaranteed on Aura Free, so the
            # label is set with one static query per distinct type.
            for label in sorted({n["label"] for n in nodes}):
                session.run(
                    "MATCH (n:AppNode) WHERE n.type = $label SET n:{}".format(label),
                    label=label)

            written = 0
            for rel_type, rows in sorted(by_type.items()):
                for batch in chunks(rows, EDGE_BATCH):
                    # Concatenate the relationship type rather than using .format(): the
                    # query body contains literal {key: ...} braces that format() would
                    # try to interpret as placeholders.
                    session.run(
                        "UNWIND $rows AS row "
                        "MATCH (a:AppNode {key: row.subject_key}) "
                        "MATCH (b:AppNode {key: row.object_key}) "
                        "MERGE (a)-[r:" + rel_type + "]->(b) "
                        "SET r.relation = row.relation, "
                        "    r.weight = toInteger(row.weight), "
                        "    r.provisions = row.provisions",
                        rows=batch)
                    written += len(batch)
            print("edges written   : {}".format(written))

            final_nodes = session.run("MATCH (n:AppNode) RETURN count(n) AS c").single()["c"]
            final_rels = session.run(
                "MATCH (:AppNode)-[r]->(:AppNode) RETURN count(r) AS c").single()["c"]
            print("\nverified in db  : {} :AppNode nodes, {} relationships".format(
                final_nodes, final_rels))
    finally:
        driver.close()


if __name__ == "__main__":
    main()
