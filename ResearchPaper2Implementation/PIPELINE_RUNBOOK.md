# Pipeline runbook

How to take a new piece of legislation from a plain-text file to a knowledge graph, and
how to generate compliance test cases from any clause using any of the arms.

This document covers the pipeline and stops where a `.feature` file exists. Measuring
that output — the multi-arm comparison, the coverage and soundness judges, the policy
check — is a separate concern and lives in `EVALUATION.md`. The code is separated the
same way: `kg_testgen` is the installable pipeline, `evaluation/` is not installed, and
`tests/test_pipeline_isolation.py` fails if the pipeline ever imports it.

Everything below was run on Windows with Git Bash and PowerShell side by side. Commands
are given for PowerShell; the Bash equivalents differ only in how environment variables
are set.

---

## 0. Read this first: what is corpus-specific

The pipeline was built against Schedule 1 of the Privacy Act 1988 (Cth) and is coupled
to that corpus in seven specific places. A new statute will not work end to end until
these are adapted. They are listed here rather than buried because discovering them one
crash at a time is the slow way.

| File | What is APP-specific | What a new statute needs |
|---|---|---|
| `prep_app.py` | `RE_APP` matches `N Australian Privacy Principle N—title`; `RE_CLAUSE` assumes `N.M` numbering | A new prep script, or new regexes for that instrument's heading and clause forms |
| `enrich_graph.py` | `RAW_PATH = "APPschedule1.txt"`; `parse_references` matches "subclause N.M" and "Australian Privacy Principles N to M" | Point `RAW_PATH` at the new file and rewrite the three cross-reference patterns for that statute's citation style |
| `kg_testgen/edc_bridge.py` | `_PROVISION_RE` detects `N.M` subclause identifiers | A pattern for the new numbering scheme |
| `kg_testgen/pipeline.py` | `DEFAULT_CORPUS_PATH` points at `app_schedule1.txt` | Pass `--corpus-path`, or change the constant |
| `spires/extract_corpus.py` | Writes and reads `app_*.txt` / `app_*.yaml` | Change the filename prefix, or accept `app_` as a meaningless prefix |
| `spires/build_spires_graph.py` | Globs `app_*.clean.yaml` and `app_*.verified.yaml` | Same prefix decision as above |
| `spires/app_norm.yaml` | Descriptions cite APP 2.2, 4.4 and 6.2 as worked examples | Substitute clauses from the new instrument — the examples are load-bearing, not decoration |

**The clause numbering scheme is the thing that matters most.** Everything downstream
keys on a stable per-provision identifier. If the new instrument numbers clauses
differently (`s 12(3)(a)`, `Art. 6(1)(b)`), that is the first thing to change.

---

## 1. Credentials and environment

Three secrets are needed. **None of them belong in a file that git tracks** — `.env`,
`apikey.txt`, and `Neo4j-*.txt` are all in `.gitignore`.

| Variable | What it is | Where it comes from |
|---|---|---|
| `OPENAI_API_KEY` | LLM key for extraction, generation and scoring | Your OpenAI account. `OPENAI_KEY` is also accepted, because the vendored EDC code hardcodes that name |
| `NEO4J_URI` | Aura connection string, `neo4j+s://<id>.databases.neo4j.io` | The credentials file Aura downloads when the instance is created |
| `NEO4J_USERNAME` | Usually `neo4j` | Same file |
| `NEO4J_PASSWORD` | Instance password | Same file |
| `NEO4J_DATABASE` | The database name — **on Aura this is the instance id, not `neo4j`** | Same file |

That last row costs people an hour. Aura names the database after the instance
(`e6598edc`, say), and connecting to `neo4j` fails with
`DatabaseNotFound: Unable to get a routing table for database 'neo4j'`.

### Loading them

```powershell
# Dot-sourced, so the variables land in YOUR shell and not a child process that exits
. .\setup_env.ps1
```

`setup_env.ps1` reads the Neo4j values straight out of the Aura credentials file so the
password is never duplicated, takes `OPENAI_API_KEY` from your user environment, and
prints nothing. Point it elsewhere with `-CredsFile`:

```powershell
. .\setup_env.ps1 -CredsFile 'C:\path\to\Neo4j-xxxx-Created-2026-01-01.txt'
```

To check without printing any secret:

```powershell
python check_key.py      # length, prefix family, stray characters — never the value
python check_setup.py    # 11 dependency and connectivity preflight checks
```

### Virtual environments

Three, deliberately separate, because their dependencies conflict:

| venv | Used by | Install |
|---|---|---|
| `.venv-testgen` | The query pipeline | `pip install neo4j openai python-dotenv truststore tiktoken pyyaml` |
| `.venv-edc` | EDC knowledge-graph construction | `pip install -r edc-main/edc-main/requirements.txt` |
| `.venv-ontogpt` | SPIRES extraction | `pip install ontogpt truststore` |

**If you are behind a TLS-inspecting proxy**, Python will fail every HTTPS call with
`CERTIFICATE_VERIFY_FAILED` while `curl` works fine. The fix is `truststore`, which
routes verification through the Windows certificate store. It is called at the top of
`run.py` and `llm.py`; for OntoGPT, whose console script has no such hook, there is a
`sitecustomize.py` in `.venv-ontogpt/Lib/site-packages/` that injects it at interpreter
startup.

---

## 2. Input text to knowledge graph

### 2.1 Prepare the corpus

Put the raw statute at the repository root as a plain `.txt` file, one line per
structural element, then flatten it into self-contained documents:

```powershell
python prep_app.py
```

This reads `APPschedule1.txt` and writes `edc-main/edc-main/datasets/app_schedule1.txt`:
134 documents from 62 clause blocks. Each document is self-contained — a clause's
lettered paragraphs and any trailing text that closes them are joined into one line — so
that a document can be read without its neighbours.

**Check the output before going further.** If the clause-block count is zero or wildly
wrong, the regexes did not match your statute and everything downstream will be built on
nothing.

### 2.2 Build the SPIRES norm graph

This is the graph the `spires` arms use. Four stages.

```powershell
# 1. Extract — one call per clause against the LinkML schema, resumable
python spires\extract_corpus.py --dry-run     # how many clauses, what it costs
python spires\extract_corpus.py               # ~20 min, ~$0.90 on gpt-4o for 62 clauses

# 2. Clean — strip the prompt's own fill-in markers, which the model echoes back
python spires\clean_extraction.py --glob "spires/output/app_*.yaml"

# 3. Verify — recover exception clauses the recursive extraction drops
python spires\verify_exceptions.py --glob "spires/output/app_*.yaml"

# 4. Build and load
python spires\build_spires_graph.py --dry-run  # writes CSVs, reports node/edge counts
python spires\build_spires_graph.py            # loads to Aura with an SP_ prefix
```

`--wipe` on the last command deletes existing `SP_*` nodes first. It is scoped to that
prefix, so `:AppNode` and `:RP1Entity` in the same instance survive.

Two things worth knowing:

- **Cleaning discards roughly 46% of condition and exception field values.** That is not
  a bug. SPIRES marks fill-in slots with angle brackets and the model returns them
  filled in but still bracketed, or echoes the field description itself. Run
  `python spires\review_discards.py` to audit what was dropped, ranked by how much it
  could cost rather than by frequency.
- **Cross-reference edges come from the regex in `enrich_graph.py`, not from SPIRES.**
  Over 62 clauses the regex found cross-references in 28 provisions against SPIRES' 10.
  Two extractors, each doing what it measured best at.

### 2.3 Optional: build the EDC graph and enrich it

Only needed for the `kg` and `kg-text-only` arms.

```powershell
# EDC three-stage construction (extract, define, canonicalize)
.\.venv-edc\Scripts\python.exe edc-main\edc-main\run.py --oie_llm gpt-4o-mini ...

# Load, then add provision text and REFERS_TO edges
python load_neo4j.py
python enrich_graph.py --dry-run
python enrich_graph.py
```

`enrich_graph.py` is what makes `kg-text-only` possible: it puts each clause's verbatim
text on its `:Provision` node and links provisions that cite one another. Without it the
graph holds relationships but no law.

---

## 3. Running a single arm on any clause

The entry point takes a file or stdin:

```powershell
python -m kg_testgen path\to\clause.txt --context-mode spires
```

```powershell
"6.1 If an APP entity holds personal information..." | python -m kg_testgen - --context-mode none
```

The input is one clause of text. The provision identifier is detected from it
automatically; pass `--provision-id 6.1` when detection fails or the text does not
contain its own number.

### The seven arms

| Arm | Command | Reads Neo4j |
|---|---|---|
| `none` | `--context-mode none` | no |
| `full-corpus` | `--context-mode full-corpus` | no |
| `kg` | `--context-mode kg` | yes |
| `kg-text-only` | `--context-mode kg --no-triples` | yes |
| `rp1` | `--context-mode rp1` | yes |
| `spires` | `--context-mode spires` | yes |
| `spires-hybrid` | `--context-mode spires --spires-provision-text` | yes |

### Tuning the SPIRES arm

```powershell
python -m kg_testgen sections\line60_app_6_1.txt --context-mode spires `
    --spires-hop-depth 2 `            # follow references two hops instead of one
    --spires-modality-filter deontic ` # keep only MUST / MUST NOT / MAY norms
    --no-spires-inbound `              # forwards only (see the warning below)
    --no-spires-exceptions-first       # conditions above exceptions
```

**`--no-spires-inbound` will quietly weaken the retrieval.** Inbound edges are what find
the provision that *defeats* the target: APP 2.1 read alone states an unqualified right
to anonymity and is misleading until 2.2 — which points at it — is in view. Outbound-only
retrieval can never reach 2.2 from 2.1.

### Other useful flags

```
--model gpt-4o                 the generator model (default gpt-4o-mini)
--temperature 0.0              not strictly deterministic even at 0
--provision-text-scope none    for kg arms: withhold cross-referenced statutory text
--block3-format terse|neutral  alternative header phrasings, for sensitivity testing only
--corpus-path <file>           the corpus for --context-mode full-corpus
--output-dir <dir>             where to write (default: a timestamped folder under runs/)
--allow-unaugmented            proceed when retrieval finds nothing, instead of failing
```

`--block3-format` exists to measure how much of a score is the context and how much is
the wording around it. It is not a configuration you would ship.

---

## 4. Where the output goes

By default each run writes a timestamped directory under `runs/`. With `--output-dir`
it writes exactly where you say.

| File | Contents |
|---|---|
| `generated.feature` | **The test cases.** Gherkin: one `Feature`, one `Scenario` per obligation, condition or exception, each tagged with its provision and carrying a `# Derives from:` quote |
| `prompt.txt` | The full four-block prompt as sent, so a result can be reproduced or audited |
| `run_record.json` | Everything else: config, seeding, retrieval, ranking, serialisation, the raw model response, and any structural problems found in the Gherkin |

`runs/` is in `.gitignore` — these are regenerable and there are thousands of them.

### Reading a run record

```powershell
python -c "import json; d=json.load(open('runs/<dir>/run_record.json')); print(d['spires_context'])"
```

Useful keys: `augmented` (did context reach the prompt), `spires_context` /
`rp1_context` / `retrieval` (what the graph returned), `provision_text` (which clauses
contributed statutory text), `gherkin_structure_problems` (malformed output).

---

## 5. What happens next

The pipeline ends here: a `.feature` file and a run record. Everything about judging,
scoring, comparing arms and reproducing the experiment is in **`EVALUATION.md`**, and
none of it is needed to run the pipeline or to point it at a new statute.
