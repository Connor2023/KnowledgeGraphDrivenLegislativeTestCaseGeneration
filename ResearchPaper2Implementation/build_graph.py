"""Turn EDC's canonicalised triples into a loadable Neo4j graph.

EDC canonicalises relations but does no entity-mention canonicalisation, so the same
party arrives under several surface forms ("the entity", "an APP entity") and otherwise
identical phrases differ only by article ("how an individual may access..." vs "how the
individual may access..."). This pass folds those together, types the nodes, and emits
both CSVs and a self-contained .cypher script.

Merging is deliberately conservative. Most of the long tail -- notification matters,
exception conditions -- is genuinely distinct legal content that must stay distinct;
similarity-based clustering would collapse real content, so only article/plural variants
and an explicit synonym map are merged.
"""

import argparse
import collections
import csv
import io
import json
import os
import re

# Surface forms that denote the same actor. Everything is matched lower-cased.
SYNONYMS = {
    "entity": "APP entity",
    "the entity": "APP entity",
    "an app entity": "APP entity",
    "the app entity": "APP entity",
    "app entities": "APP entity",
    "entities": "APP entity",
    "individuals": "individual",
    "an individual": "individual",
    "the individual": "individual",
    "organisations": "organisation",
    "an organisation": "organisation",
    "the organisation": "organisation",
    "agencies": "agency",
    "an agency": "agency",
    "the agency": "agency",
    "australian privacy principles": "Australian Privacy Principles",
    "the australian privacy principles": "Australian Privacy Principles",
    "overseas recipients": "overseas recipient",
    "the overseas recipient": "overseas recipient",
    "personal information": "personal information",
    "the information": "personal information",
    "the personal information": "personal information",
}

# Node typing, applied in order; first match wins.
TYPE_RULES = [
    ("Principle", re.compile(r"^australian privacy principles?( \d+)?$", re.I)),
    ("Principle", re.compile(r"^australian privacy principle \d+", re.I)),
    ("Provision", re.compile(r"^(sub)?clause \d+\.\d+", re.I)),
    ("Provision", re.compile(r"^(schedule|part|division|paragraph)\b", re.I)),
    ("Legislation", re.compile(r"\b(act \d{4}|act of the commonwealth|australian law|regulations)\b", re.I)),
    ("Party", re.compile(r"^(app entity|organisation|agency|individual|overseas recipient|"
                         r"first organisation|enforcement body|commissioner|body corporate|"
                         r"related body corporate|contracted service provider)$", re.I)),
    ("InformationType", re.compile(r"^(personal information|sensitive information|health information|"
                                   r"government related identifier|biometric information|"
                                   r"credit information|unsolicited personal information)$", re.I)),
]

ARTICLE_RE = re.compile(r"^(a|an|the)\s+", re.I)
INNER_ARTICLE_RE = re.compile(r"\b(an|the)\s+(individual|entity|organisation|agency|information)\b", re.I)


def normalise(mention):
    """Fold a raw entity mention onto a canonical key.

    Returns (key, display). The key drives merging; the display form is chosen later as
    the most frequent original spelling in the cluster.
    """
    text = " ".join(mention.strip().split())
    text = text.strip("\"'.,;: ")

    low = text.lower()
    if low in SYNONYMS:
        canon = SYNONYMS[low]
        return canon.lower(), canon

    # Drop a leading article, then neutralise articles in front of the recurring actors so
    # "how an individual may access X" and "how the individual may access X" agree.
    stripped = ARTICLE_RE.sub("", text)
    key = INNER_ARTICLE_RE.sub(lambda m: m.group(2), stripped).lower()
    key = " ".join(key.split()).strip("\"'.,;: ")

    if key in SYNONYMS:
        canon = SYNONYMS[key]
        return canon.lower(), canon
    return key, stripped


def node_type(display):
    for label, pattern in TYPE_RULES:
        if pattern.search(display):
            return label
    return "Concept"


def rel_type(relation):
    """Cypher relationship types must be bare identifiers."""
    t = re.sub(r"[^0-9a-zA-Z]+", "_", relation).strip("_").upper()
    return t or "RELATED_TO"


def cypher_str(value):
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default="edc-main/edc-main/output/app_full/iter0")
    ap.add_argument("--seed-schema", default="edc-main/edc-main/schemas/app_seed.csv")
    ap.add_argument("--out-dir", default="edc-main/edc-main/output/app_full/graph")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    with io.open(os.path.join(args.run_dir, "result_at_each_stage.json"), encoding="utf-8") as fh:
        records = json.load(fh)

    # Pass 1: collect surface forms so the display name can be the commonest spelling.
    surface = collections.defaultdict(collections.Counter)
    for rec in records:
        for triple in rec["schema_canonicalizaiton"]:
            if not triple:
                continue
            for mention in (triple[0], triple[2]):
                key, display = normalise(mention)
                surface[key][display] += 1

    display_of = {key: counter.most_common(1)[0][0] for key, counter in surface.items()}

    # Pass 2: build edges, carrying provenance back to the source clause.
    edges = {}
    for rec in records:
        provision = next((t[0] for t in rec["schema_canonicalizaiton"]
                          if t and t[1] == "belongs to principle"), "")
        for triple in rec["schema_canonicalizaiton"]:
            if not triple:
                continue
            subject, relation, obj = triple
            skey, _ = normalise(subject)
            okey, _ = normalise(obj)
            if not skey or not okey or skey == okey:
                continue           # self-loops carry no information here
            edge = (skey, rel_type(relation), okey)
            # The same rule often restates across the documents a long clause was split
            # into, so collapse duplicates but keep the count as edge weight and retain
            # every provision that supports it.
            if edge not in edges:
                edges[edge] = {"relation": relation, "provisions": [], "docs": [], "weight": 0}
            data = edges[edge]
            data["weight"] += 1
            data["docs"].append(rec["index"])
            if provision and provision not in data["provisions"]:
                data["provisions"].append(provision)

    nodes = {key: {"name": display_of[key], "label": node_type(display_of[key])}
             for key in display_of}

    # Learned schema: EDC keeps the enriched schema in memory only, so rebuild it from the
    # per-document definitions plus the seed file.
    schema = {}
    with io.open(args.seed_schema, encoding="utf-8", newline="") as fh:
        for relation, definition in csv.reader(fh):
            schema[relation] = definition
    seeded = set(schema)
    for rec in records:
        for relation, definition in (rec.get("schema_definition") or {}).items():
            schema.setdefault(relation, definition)

    used = {data["relation"] for data in edges.values()}

    # --- write nodes.csv / edges.csv ---
    with io.open(os.path.join(args.out_dir, "nodes.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["key", "name", "label"])
        for key, data in sorted(nodes.items()):
            w.writerow([key, data["name"], data["label"]])

    with io.open(os.path.join(args.out_dir, "edges.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["subject_key", "type", "object_key", "relation", "weight", "provisions", "docs"])
        for (s, t, o), data in sorted(edges.items()):
            w.writerow([s, t, o, data["relation"], data["weight"],
                        "; ".join(data["provisions"]),
                        " ".join(str(i) for i in data["docs"])])

    with io.open(os.path.join(args.out_dir, "app_learned_schema.csv"), "w",
                 encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        for relation in sorted(schema):
            if relation in used:
                w.writerow([relation, schema[relation]])

    # --- write graph.cypher ---
    with io.open(os.path.join(args.out_dir, "graph.cypher"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("// Australian Privacy Principles knowledge graph\n")
        fh.write("// Generated by build_graph.py from EDC output.\n")
        fh.write("// Run with:  cypher-shell -u neo4j -p <password> -f graph.cypher\n\n")
        fh.write("CREATE CONSTRAINT app_node_key IF NOT EXISTS\n")
        fh.write("FOR (n:AppNode) REQUIRE n.key IS UNIQUE;\n\n")
        for key, data in sorted(nodes.items()):
            fh.write("MERGE (n:AppNode {{key: {}}}) SET n.name = {}, n:{};\n".format(
                cypher_str(key), cypher_str(data["name"]), data["label"]))
        fh.write("\n")
        for (s, t, o), data in sorted(edges.items()):
            fh.write(
                "MATCH (a:AppNode {{key: {}}}), (b:AppNode {{key: {}}}) "
                "MERGE (a)-[r:{}]->(b) SET r.relation = {}, r.weight = {}, r.provisions = {};\n".format(
                    cypher_str(s), cypher_str(o), t, cypher_str(data["relation"]),
                    data["weight"], cypher_str("; ".join(data["provisions"]))))

    by_label = collections.Counter(d["label"] for d in nodes.values())
    print("nodes            : {}".format(len(nodes)))
    for label, count in by_label.most_common():
        print("   {:<16} {}".format(label, count))
    print("edges            : {}".format(len(edges)))
    print("relation types   : {} ({} seeded, {} learned)".format(
        len(used), len(used & seeded), len(used - seeded)))
    print("written to       : {}".format(args.out_dir))


if __name__ == "__main__":
    main()
