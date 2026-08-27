# Research Paper 2 — KG construction and query pipelines

Two pipelines over the Australian Privacy Principles (Schedule 1 of the *Privacy Act 1988*):

1. **KG construction** — EDC (Extract–Define–Canonicalize) builds a knowledge graph from
   the legislation text. See `KG_Construction_Report.docx` for the full write-up.
2. **KG query + test-case generation** (`kg_testgen/`) — takes one subclause, queries the
   graph for supplementary context, and generates Gherkin compliance test cases.

---

## kg_testgen — query and test-case generation

Takes a section of privacy legislation, extracts its entities, matches them onto the
knowledge graph, retrieves related material from **elsewhere** in the legislation, and
asks an LLM to produce Gherkin scenarios.

The generated scenarios are **not executable software tests**. Each is written to be
checked, by a person reading a company's privacy policy, against what that policy states
or commits to.

### Setup

```bash
python -m venv .venv-testgen
.venv-testgen\Scripts\python.exe -m pip install -e .
```

Requires Python 3.10+. The heavy ML dependencies EDC pulls in (`torch`, `transformers`,
`sentence_transformers`) are stubbed at import time — only the OpenAI code path is used,
so they are not installed.

### Environment variables

All secrets are read from the environment. Copy `.env.example` to `.env` and fill it in,
or export them in your shell. Nothing is ever hardcoded or committed.

| Variable | Purpose |
|---|---|
| `NEO4J_URI` | Aura connection URI, e.g. `neo4j+s://xxxx.databases.neo4j.io` |
| `NEO4J_USERNAME` | Usually `neo4j` |
| `NEO4J_PASSWORD` | From the Aura credentials file |
| `NEO4J_DATABASE` | Optional; defaults to `neo4j` |
| `OPENAI_API_KEY` | Preferred name. `OPENAI_KEY` is accepted as a fallback because the vendored EDC code reads that name directly |

The first four come from the `Neo4j-<id>-Created-<date>.txt` file Aura produces when you
create an instance.

### Example invocation

```bash
.venv-testgen\Scripts\python.exe -m kg_testgen sections/app_6_1.txt
```

Reads the subclause from the file (or `-` for stdin) and writes a timestamped run folder
under `runs/`:

| File | Contents |
|---|---|
| `generated.feature` | The Gherkin test cases |
| `run_record.json` | Input text, extracted terms, matched seeds, unmatched terms, retrieved triples, prompt, raw LLM response, config, timestamp |
| `prompt.txt` | The assembled prompt, for inspection |

`run_record.json` is what makes manual evaluation possible — it records every
intermediate stage, not just the output.

### How it works

1. **Seeding** — the vendored EDC `EntityExtractor` pulls candidate terms from the input
   (one LLM call), so the query vocabulary matches the vocabulary the graph was built
   with. Terms are matched to nodes in three tiers: exact, then normalised via
   `build_graph.normalise` (the function that produced every node's `key`), then fuzzy
   above `--fuzzy-threshold`. With `--provision-anchor` on (the default), the input's own
   subclause node is added as a seed.
2. **Retrieval** — parameterised Cypher expands outward from each seed under hard caps.
   Hop depth is asymmetric by seed kind: provision seeds get `--provision-hop-depth`
   (default 3), entity seeds `--entity-hop-depth` (default 2). `:Provision` nodes are
   near-leaves — 59 of 77 have degree 1 — so they need the extra hop to reach anything,
   while an entity seed already touches 28–40% of the graph at depth 2.
3. **Ranking** — hop distance, then relationship `weight` (how many clauses assert the
   relation), then node degree. Degree is computed in Cypher; GDS is not used.
4. **Serialisation** — triples grouped by seed entity, fitted to
   `--context-token-budget`. Triples that merely restate the input subclause are dropped
   here; see below.
5. **Prompt** — four labelled blocks: task, verbatim target section, supplementary KG
   context, output contract. The separation matters — the graph holds no source text, so
   retrieved triples come from other provisions and must not be read as part of the
   target section.
6. **Generation** — a single LLM call at temperature 0. No agent loop.

### Why exclusion happens at serialisation, not traversal

Triples asserted by the input subclause are filtered out of the context block, but the
graph walk still passes *through* them. This is deliberate. A `:Provision` node's only
edge is usually its own `BELONGS_TO_PRINCIPLE`, so filtering during traversal would sever
the anchor at hop 1 and the provision seed would contribute nothing at all.

`--self-provision-policy` controls what counts as a restatement:

- `sole` (default) — drop a triple only when the input subclause is its **only** asserting
  provision. A triple asserted by the input clause *and ten others* is genuine
  cross-section context and is kept.
- `any` — drop any triple whose provision list mentions the input subclause. Stricter, but
  it discards widely-asserted facts, which are the strongest context available.
- `none` — keep everything.

### Failure behaviour

The pipeline fails loudly rather than silently degrading to an unaugmented LLM call.
Missing environment variables, an unreachable database, a node label absent from the
graph, zero seed matches, and empty retrieval are all fatal, with a distinct exit code
and a message naming the fix. Pass `--allow-unaugmented` to deliberately proceed without
KG context — the run record then records `augmented: false`.

| Exit code | Meaning |
|---|---|
| 2 | Configuration or input error |
| 3 | Database unreachable or misconfigured |
| 4 | Zero seed matches or empty retrieval |
| 5 | LLM error |

### Configuration

Every tunable is a CLI flag so retrieval variations can be compared without editing code.
`python -m kg_testgen --help` lists them all. The defaults live in `kg_testgen/config.py`.

### Not implemented

Deliberately left as documented stubs, each raising `NotImplementedError`:

- Vector/embedding seeding and node embedding generation (`seeding.seed_by_vector_similarity`)
- Embedding-similarity and centrality ranking (`ranking.rank_by_*`)
- JSON serialisation (`serialisation.serialise_as_json`)
- Asymmetric depth by *relationship type*, relationship prioritisation, temporal validity
  filtering (`retrieval.*`)
- Iterative/multi-turn retrieval (`llm.request_additional_context`)
- Automated checking against the Microsoft privacy policies, verdict classification,
  scoring, and batch processing (`evaluation.py`)

Vector index support **is** available on this instance (probed at startup and recorded in
the run metadata), so vector seeding needs only embedding generation plus an index build.
