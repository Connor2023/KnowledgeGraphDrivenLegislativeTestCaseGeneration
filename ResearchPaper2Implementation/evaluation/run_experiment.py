"""Run the 3-section x 3-arm x N-repeat comparison and build a side-by-side document.

Arms
    none         section text alone, no supplementary context
    full-corpus  the whole app_schedule1.txt pasted in verbatim (includes the target)
    kg           subgraph retrieved from Neo4j and serialised as triples

Repeats exist because temperature 0 is not strictly deterministic. With only three
sections, run-to-run variance has to be visible or a difference between arms cannot be
distinguished from noise.

    python -m evaluation.run_experiment                 # run everything, write the comparison
    python -m evaluation.run_experiment --repeats 1     # quick pass
    python -m evaluation.run_experiment --report-only   # rebuild the document from existing runs
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
import traceback

from kg_testgen.config import Config, secrets_from_env
from .gherkin import parse_feature_text
from kg_testgen.pipeline import run as run_pipeline

SECTIONS = [
    ("line34", "sections/line34_app_2_2.txt", "APP 2.2 — exception to anonymity", "2.2"),
    ("line49", "sections/line49_app_4_4.txt", "APP 4.4 — cross-reference to APPs 5-13", "4.4"),
    ("line60", "sections/line60_app_6_1.txt", "APP 6.1 — secondary use prohibition", "6.1"),
]

MANUAL_DOCX = os.path.join("testcasecomparison", "Test cases FYP.docx")
_MANUAL_ID = None  # compiled lazily; see load_manual_cases
# (key, label, config overrides). Carrying overrides rather than a bare mode string lets
# an arm vary any tunable, not just which graph it reads.
ARMS = [
    ("none", "No KG — section text only", {"context_mode": "none"}),
    ("full-corpus", "Full corpus pasted in", {"context_mode": "full-corpus"}),
    ("kg", "APP KG + provision text", {"context_mode": "kg"}),
    ("rp1", "RP1 concept graph", {"context_mode": "rp1"}),
    ("kg-text-only", "Provision text, no triples",
     {"context_mode": "kg", "include_triples": False}),
    ("spires", "SPIRES norm graph", {"context_mode": "spires"}),
    ("spires-hybrid", "SPIRES norms + provision text",
     {"context_mode": "spires", "spires_include_provision_text": True}),
    # Format-sensitivity probes. Same context, same retrieval; only the block 3 header
    # is rephrased. Three arms x three formats measures whether the gaps BETWEEN arms
    # survive the variation WITHIN an arm -- the reporting practice Sclar et al. (ICLR
    # 2024) argue for. These are not proposed configurations; they are the control.
    ("fmt-none-terse", "[fmt] none, terse header",
     {"context_mode": "none", "block3_format": "terse"}),
    ("fmt-none-neutral", "[fmt] none, neutral header",
     {"context_mode": "none", "block3_format": "neutral"}),
    ("fmt-ktext-terse", "[fmt] kg-text-only, terse header",
     {"context_mode": "kg", "include_triples": False, "block3_format": "terse"}),
    ("fmt-ktext-neutral", "[fmt] kg-text-only, neutral header",
     {"context_mode": "kg", "include_triples": False, "block3_format": "neutral"}),
    ("fmt-spires-terse", "[fmt] spires, terse header",
     {"context_mode": "spires", "block3_format": "terse"}),
    ("fmt-spires-neutral", "[fmt] spires, neutral header",
     {"context_mode": "spires", "block3_format": "neutral"}),
]
ARM_CONFIG = {key: cfg for key, _label, cfg in ARMS}

EXPERIMENT_DIR = "runs/experiment"

logger = logging.getLogger("experiment")


def cell_dir(section_key: str, arm: str, repeat: int) -> str:
    return os.path.join(EXPERIMENT_DIR, "%s__%s__r%d" % (section_key, arm, repeat))


def run_cell(section_key, path, arm, repeat, secrets, overwrite=False):
    out = cell_dir(section_key, arm, repeat)
    if os.path.exists(os.path.join(out, "generated.feature")) and not overwrite:
        logger.info("  exists, skipping: %s", out)
        return True
    overrides = dict(ARM_CONFIG[arm])
    overrides.update(output_dir=out,
                     run_label="%s|%s|r%d" % (section_key, arm, repeat))
    config = Config(**overrides)
    config.validate()
    with io.open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        run_pipeline(text, config, secrets, input_path=path)
        return True
    except Exception as exc:  # noqa: BLE001 - one failed cell must not stop the grid
        logger.error("  FAILED %s / %s / r%d: %s", section_key, arm, repeat, exc)
        with io.open(os.path.join(EXPERIMENT_DIR, "errors.log"), "a", encoding="utf-8") as fh:
            fh.write("%s %s r%d\n%s\n\n" % (section_key, arm, repeat, traceback.format_exc()))
        return False


def load_manual_cases(path=MANUAL_DOCX):
    """Read the hand-written reference cases out of the .docx.

    They live in 3-column tables (Test ID | Test case | Expected result), spread across
    several tables — some with a header row, some without — so rows are selected by the
    shape of the ID rather than by table position.
    """
    import re
    try:
        import docx
    except ImportError:
        logger.warning("python-docx not installed; manual cases will be omitted")
        return {}
    if not os.path.exists(path):
        logger.warning("manual cases not found at %s; omitting", path)
        return {}

    ident = re.compile(r"^APP\s*(\d+\.\d+)\s*-\s*TC\s*(\d+)", re.I)
    out = {}
    document = docx.Document(path)
    for tbl in document.tables:
        for row in tbl.rows:
            cells = [c.text.strip().replace("\n", " ") for c in row.cells]
            if len(cells) < 3:
                continue
            m = ident.match(cells[0])
            if not m:
                continue
            out.setdefault(m.group(1), []).append(
                {"id": cells[0], "case": cells[1], "expected": cells[2]})
    for sec, items in out.items():
        logger.info("manual cases: APP %s -> %d", sec, len(items))
    return out


def load_cell(section_key, arm, repeat):
    d = cell_dir(section_key, arm, repeat)
    feature = os.path.join(d, "generated.feature")
    record = os.path.join(d, "run_record.json")
    if not os.path.exists(feature):
        return None
    with io.open(feature, encoding="utf-8") as fh:
        text = fh.read()
    rec = {}
    if os.path.exists(record):
        with io.open(record, encoding="utf-8") as fh:
            rec = json.load(fh)
    return {"dir": d, "gherkin": text, "record": rec,
            "feature": parse_feature_text(text)}


def build_report(repeats: int) -> str:
    manual = load_manual_cases()
    lines = [
        "# KG augmentation comparison",
        "",
        "Three subclauses, three prompting arms, %d run%s each. Temperature 0, "
        "`gpt-4o-mini` throughout. The only variable is what Block 3 of the prompt "
        "contains." % (repeats, "" if repeats == 1 else "s"),
        "",
        "| Arm | Block 3 contents |",
        "|---|---|",
        "| `none` | nothing — the section text alone |",
        "| `full-corpus` | all 134 documents of `app_schedule1.txt`, verbatim, including the target |",
        "| `kg` | subgraph triples PLUS the text of cross-referenced provisions |",
        "| `kg-text-only` | the same provision text, with the triples withheld |",
        "| `rp1` | the whole 21-node RP1 concept graph, with entity definitions, ordered deontic-first |",
        "",
        "Hand-written reference cases are reproduced under each section below, taken "
        "from `testcasecomparison/Test cases FYP.docx`.",
        "",
        "> **Note on form.** The manual cases are written as tests of the *entity's "
        "conduct* (\"the individual can proceed without identifying themselves\"). The "
        "generated scenarios are written as assertions about *what a privacy policy "
        "states*, which is what the generator was specified to produce. Compare them on "
        "substance — which obligations, conditions and exceptions each covers — rather "
        "than on wording.",
        "",
        "---",
        "",
        "## Scenario counts",
        "",
        "| Section | " + " | ".join(label for _k, label, _c in ARMS) + " |",
        "|---|" + "---|" * len(ARMS),
    ]

    for key, _path, desc, _app in SECTIONS:
        cells = []
        for arm, _lbl, _c in ARMS:
            counts = []
            for r in range(1, repeats + 1):
                c = load_cell(key, arm, r)
                counts.append(str(len(c["feature"].scenarios)) if c else "—")
            cells.append(", ".join(counts))
        lines.append("| %s | %s |" % (desc, " | ".join(cells)))

    lines += ["", "Comma-separated values are the repeated runs, in order.", "",
              "## Prompt size", "",
              "| Section | " + " | ".join(label for _k, label, _c in ARMS) + " |",
              "|---|" + "---|" * len(ARMS)]
    for key, _path, desc, _app in SECTIONS:
        cells = []
        for arm, _lbl, _c in ARMS:
            c = load_cell(key, arm, 1)
            n = len(c["record"].get("prompt", "")) if c else 0
            cells.append(("{:,} chars".format(n)) if n else "—")
        lines.append("| %s | %s |" % (desc, " | ".join(cells)))

    # Objective mechanical checks. These characterise the output; they do not judge
    # whether a scenario is a *good* test case -- that is the manual comparison.
    lines += ["", "## Mechanical checks", "",
              "Objective properties only — nothing here judges test-case quality.", "",
              "| Section | Arm | Scenarios | Repeats identical | Valid provision tag |",
              "|---|---|---|---|---|"]
    for key, _path, desc, _app in SECTIONS:
        for arm, label, _c in ARMS:
            counts, tagged, total, texts = [], 0, 0, []
            for r in range(1, repeats + 1):
                c = load_cell(key, arm, r)
                if not c:
                    continue
                texts.append(c["gherkin"].strip())
                counts.append(len(c["feature"].scenarios))
                for s in c["feature"].scenarios:
                    total += 1
                    if s.provision_tag:
                        tagged += 1
            ident = "yes" if len(set(texts)) == 1 else "no (%d variants)" % len(set(texts))
            tag = "%d / %d" % (tagged, total)
            if total and tagged == 0:
                tag += "  **malformed**"
            lines.append("| %s | `%s` | %s | %s | %s |"
                         % (desc, arm, "/".join(map(str, counts)) or "—", ident, tag))

    lines += ["",
              "A missing provision tag usually means the model wrote `@ s6-1` with a space, "
              "which Gherkin reads as a bare `@` tag. Worth checking before trusting a "
              "cell's scenario count.",
              "", "---", ""]

    for key, path, desc, app_no in SECTIONS:
        lines += ["## %s" % desc, "", "**Input** (`%s`):" % path, ""]
        with io.open(path, encoding="utf-8") as fh:
            lines += ["> " + fh.read().strip(), ""]
        cases = manual.get(app_no, [])
        lines += ["### Manual reference test cases (%d)" % len(cases), ""]
        if cases:
            lines += ["| ID | Test case | Expected result |", "|---|---|---|"]
            for c in cases:
                # Escape any pipe in the prose so it does not break the markdown table.
                lines.append("| `%s` | %s | %s |"
                             % (c["id"], c["case"].replace("|", r"\|"),
                                c["expected"].replace("|", r"\|")))
            lines.append("")
        else:
            lines += ["_None found for this subclause._", ""]
        for arm, label, _c in ARMS:
            lines += ["### %s" % label, ""]
            for r in range(1, repeats + 1):
                c = load_cell(key, arm, r)
                lines.append("**Run %d** — `%s`" % (r, cell_dir(key, arm, r)))
                lines.append("")
                if c is None:
                    lines += ["_no output — the cell failed; see errors.log_", ""]
                    continue
                lines += ["```gherkin", c["gherkin"].strip(), "```", ""]
        lines += ["---", ""]

    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)-8s %(name)-22s %(message)s", stream=sys.stderr)
    logger.setLevel(logging.INFO)
    os.makedirs(EXPERIMENT_DIR, exist_ok=True)

    if not args.report_only:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        secrets = secrets_from_env()
        total = len(SECTIONS) * len(ARMS) * args.repeats
        done = ok = 0
        for key, path, _desc, _app in SECTIONS:
            for arm, _label, _cfg in ARMS:
                for r in range(1, args.repeats + 1):
                    done += 1
                    logger.info("[%d/%d] %s / %s / run %d", done, total, key, arm, r)
                    ok += run_cell(key, path, arm, r, secrets, args.overwrite)
        logger.info("Completed %d of %d cells", ok, total)

    report = build_report(args.repeats)
    out = os.path.join(EXPERIMENT_DIR, "comparison.md")
    with io.open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(report)
    print("\nComparison document: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
