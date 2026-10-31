"""Load output.json (entities + triples) into the Neo4j Aura instance as a namespaced graph.

The instance already holds the APP graph (:AppNode / :Concept / :Provision / ...). This
loader keeps its output completely disjoint from it:

  * every node carries the label :RP1Entity, which nothing else in the database uses;
  * every relationship type is prefixed RP1_, so no type is shared with the APP graph;
  * every node and relationship carries graph = "rp1" as a property;
  * nodes are keyed on rp1_<id>, so re-running the loader updates in place instead of
    duplicating, and never touches a node outside the namespace.

Nothing existing is read, modified or deleted. Credentials come from an Aura credentials
dump or the environment; the password is never printed.

  python load_rp1_kg.py --dry-run
  python load_rp1_kg.py
  python load_rp1_kg.py --reset-namespace   # drop only the :RP1Entity subgraph, then load
"""

import argparse
import io
import json
import os
import re
import sys

NODE_LABEL = "RP1Entity"
GRAPH_TAG = "rp1"
REL_PREFIX = "RP1_"
DEFAULT_CREDS = r"C:\Users\conno\FYP\KnowledgeGraph\Neo4j-e6598edc-Created-2026-08-11.txt"


def load_credentials(path):
    """Parse an Aura credentials dump into a dict. Values are never echoed."""
    creds = {}
    if path and os.path.exists(path):
        with io.open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                creds[key.strip()] = value.strip()
    for key in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE"):
        if os.environ.get(key):          # environment wins over the file
            creds[key] = os.environ[key]
    return creds


def rel_type(pred_label):
    """Turn a predicate into a relationship type: 'is a type of' -> 'RP1_IS_A_TYPE_OF'.

    The prefix is what guarantees no collision with the 76 relationship types the APP
    graph already defines (it has its own IS_A_TYPE_OF, RELATES_TO, INVOLVES, ...).
    """
    slug = re.sub(r"[^A-Z0-9]+", "_", pred_label.upper()).strip("_")
    return REL_PREFIX + slug


def build_rows(data):
    entities, triples = data["entities"], data["triples"]

    nodes = [{"key": "rp1_{}".format(i),
              "rp1_id": i,
              "name": e["label"],
              "description": e.get("description", ""),
              "types": e.get("types", [])}
             for i, e in enumerate(entities)]

    # The *_id fields are authoritative: a couple of triples carry a label whose hyphens
    # were stripped ("crossborder disclosure"), while the id still points at the real entity.
    edges = []
    for t in triples:
        s, o = t["subj_id"], t["obj_id"]
        if not (0 <= s < len(entities) and 0 <= o < len(entities)):
            raise ValueError("triple references an unknown entity id: {}".format(t))
        edges.append({"subject_key": "rp1_{}".format(s),
                      "object_key": "rp1_{}".format(o),
                      "type": rel_type(t["pred_label"]),
                      "pred_label": t["pred_label"],
                      "pred_description": t.get("pred_description", "")})
    return nodes, edges


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=os.path.join(here, "output.json"))
    ap.add_argument("--creds", default=DEFAULT_CREDS, help="Path to the Aura credentials file.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Connect and report, but write nothing.")
    ap.add_argument("--reset-namespace", action="store_true",
                    help="Delete the existing :RP1Entity subgraph before loading. Only "
                         "touches nodes carrying that label -- the APP graph is untouched.")
    args = ap.parse_args()

    creds = load_credentials(args.creds)
    missing = [k for k in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD") if not creds.get(k)]
    if missing:
        print("Missing credentials: {}".format(", ".join(missing)))
        sys.exit(1)
    database = creds.get("NEO4J_DATABASE") or "neo4j"

    with io.open(args.input, encoding="utf-8") as fh:
        data = json.load(fh)
    nodes, edges = build_rows(data)

    by_type = {}
    for e in edges:
        by_type.setdefault(e["type"], []).append(e)

    print("source          : {}".format(args.input))
    print("target instance : {} (database: {})".format(creds.get("AURA_INSTANCEID", "?"), database))
    print("to load         : {} nodes, {} edges, {} relationship types"
          .format(len(nodes), len(edges), len(by_type)))
    print("namespace       : :{} nodes, {}* relationships, graph={}"
          .format(NODE_LABEL, REL_PREFIX, GRAPH_TAG))

    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(creds["NEO4J_URI"],
                                  auth=(creds["NEO4J_USERNAME"], creds["NEO4J_PASSWORD"]))
    try:
        driver.verify_connectivity()
        print("connection      : OK")

        with driver.session(database=database) as session:
            total_n = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            total_r = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            mine_n = session.run(
                "MATCH (n:%s) RETURN count(n) AS c" % NODE_LABEL).single()["c"]
            print("already present : {} nodes / {} relationships total, of which {} are :{}"
                  .format(total_n, total_r, mine_n, NODE_LABEL))

            # Guard: refuse to run if the namespace somehow overlaps the existing graph.
            clash = session.run(
                "MATCH (n:%s) WHERE n:AppNode RETURN count(n) AS c" % NODE_LABEL).single()["c"]
            if clash:
                print("ABORT: {} nodes carry both :{} and :AppNode -- namespaces are not "
                      "disjoint.".format(clash, NODE_LABEL))
                sys.exit(1)
            existing_types = {r["t"] for r in session.run(
                "CALL db.relationshipTypes() YIELD relationshipType AS t RETURN t")}
            overlap = {t for t in existing_types & set(by_type) if not t.startswith(REL_PREFIX)}
            if overlap:
                print("ABORT: relationship types would collide: {}".format(sorted(overlap)))
                sys.exit(1)

            if args.dry_run:
                print("\nDry run -- nothing written.")
                return

            if args.reset_namespace:
                deleted = session.run(
                    "MATCH (n:%s) DETACH DELETE n RETURN count(n) AS c" % NODE_LABEL
                ).single()["c"]
                print("namespace reset : {} :{} nodes removed".format(deleted, NODE_LABEL))

            session.run("CREATE CONSTRAINT rp1_entity_key IF NOT EXISTS "
                        "FOR (n:%s) REQUIRE n.key IS UNIQUE" % NODE_LABEL)

            session.run(
                "UNWIND $rows AS row "
                "MERGE (n:%s {key: row.key}) "
                "SET n.rp1_id = row.rp1_id, n.name = row.name, "
                "    n.description = row.description, n.types = row.types, "
                "    n.graph = $tag" % NODE_LABEL,
                rows=nodes, tag=GRAPH_TAG)
            print("nodes written   : {}".format(len(nodes)))

            written = 0
            for rtype, rows in sorted(by_type.items()):
                # The relationship type cannot be parameterised, so it is concatenated in --
                # rel_type() has already reduced it to [A-Z0-9_]. Everything else is bound.
                session.run(
                    "UNWIND $rows AS row "
                    "MATCH (a:" + NODE_LABEL + " {key: row.subject_key}) "
                    "MATCH (b:" + NODE_LABEL + " {key: row.object_key}) "
                    "MERGE (a)-[r:" + rtype + "]->(b) "
                    "SET r.pred_label = row.pred_label, "
                    "    r.pred_description = row.pred_description, "
                    "    r.graph = $tag",
                    rows=rows, tag=GRAPH_TAG)
                written += len(rows)
            print("edges written   : {}".format(written))

            final_n = session.run(
                "MATCH (n:%s) RETURN count(n) AS c" % NODE_LABEL).single()["c"]
            final_r = session.run(
                "MATCH (:%s)-[r]->(:%s) RETURN count(r) AS c" % (NODE_LABEL, NODE_LABEL)
            ).single()["c"]
            leak = session.run(
                "MATCH (a:%s)-[r]-(b) WHERE NOT b:%s RETURN count(r) AS c"
                % (NODE_LABEL, NODE_LABEL)).single()["c"]
            after_total_n = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            print("\nverified in db  : {} :{} nodes, {} relationships between them"
                  .format(final_n, NODE_LABEL, final_r))
            print("cross-graph edges to anything outside the namespace: {}".format(leak))
            print("database totals : {} nodes ({} before this run)".format(after_total_n, total_n))
    finally:
        driver.close()


if __name__ == "__main__":
    main()
