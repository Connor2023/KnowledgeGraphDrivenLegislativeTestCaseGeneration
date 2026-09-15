# Gherkin compliance test cases from privacy legislation

A plain-text statute goes in. A knowledge graph of its deontic norms comes out, and from
that graph, Gherkin compliance test cases for any provision.

The generated scenarios are **not executable software tests**. Each is written to be
checked by a person reading a company's published privacy policy, against what that
policy states or commits to.

```bash
python pipeline/build_corpus.py pipeline/corpora/APPartIIIC.txt
python -m kg_testgen --corpus part_iiic --provision "26WE(1)" "26WK(2)" --context-mode spires
```

---

## Layout

The repository is split by one question: **is this needed to run the pipeline?**

| | |
|---|---|
| **`pipeline/`** | The proposed artefact. Runs with everything else deleted. |
| **`evaluation/`** | Everything that measures it, or that it superseded. |
| **`pipeline_ui/`** | A browser front end over the same commands. Optional. |
| **`docs/`** | Reports, the deck, the EDC paper. Describe the work; don't perform it. |

That split is not a convention — it is checked. The pipeline suite runs with `evaluation/`
renamed away, and four equivalence proofs inside it skip rather than fail when the
superseded code they compare against is absent.

### `pipeline/`

```
build_corpus.py       one command, .txt to graph, with a gate between each stage
induce_structure.py   induces the structural profile from the text (1 LLM call)
prep_corpus.py        applies the profile: segmentation
references.py         profile-driven citation parsing
corpus_config.py      which instrument this checkout is pointed at
graph_registry.py     node-prefix ownership, so two corpora cannot merge silently
credentials.py        Neo4j credentials from an Aura dump, .env, or the environment
check_environment.py  preflight; --live also verifies the LLM key
kg_testgen/           retrieval and generation
spires/               the LinkML schema and the extraction, cleaning and build stages
corpora/              the statutes, their configs, and the prefix registry
profiles/             induced structural profiles
tests/                53 checks, no API calls, no database
```

### `evaluation/`

```
arms/                 twelve comparison arms, reaching the pipeline through one seam
score_elements.py     element coverage — did any scenario address this proposition?
score_soundness.py    correctness — is the scenario RIGHT? Coverage alone is half a result
analyse_runs.py       diversity, stability and efficiency
run_experiment.py     the grid
edc/                  the vendored EDC framework, its loader and graph builder
ground_truth/         element decomposition, section texts, the manual test cases
reports/              decks and arm snapshots
tests/                the 117-prompt replay and the isolation check
```

Evaluation may import the pipeline. The pipeline must never import evaluation.

---

## Setup

```powershell
.\bootstrap.ps1          # the pipeline only -- enough to build a graph
.\bootstrap.ps1 -All     # plus the evaluation and EDC environments
.\bootstrap.ps1 -Check   # report what exists, change nothing
```

Three virtualenvs, deliberately separate because their dependencies conflict:
`.venv-testgen` (the pipeline and the code that measures it), `.venv-ontogpt` (SPIRES
extraction; ontogpt pins linkml and pydantic versions the pipeline cannot use), and
`.venv-edc` (the EDC arm; drags in torch).

Credentials go in `.env` — copy `.env.example`. On Windows, `. .\setup_env.ps1` reads an
Aura credentials file into the shell instead. Everything resolves through
`pipeline/credentials.py`, so either works.

```bash
python pipeline/check_environment.py --live    # verifies the key, free
python pipeline/tests/run_all.py -q            # 53 checks, no API calls
```

---

## Cost

Only two stages spend anything, and `--dry-run` stops before either.

| | |
|---|---|
| Structure induction | ~$0.02, once per new instrument |
| SPIRES extraction | tracks **provision count**, not corpus size |
| Exception recovery | one call per norm carrying an exception |
| Generation | ~$0.001 per provision on gpt-4o-mini |

Part IIIC — 106 provisions — cost about $1.55 and took 32 minutes.

---

## Where to read next

- `pipeline/PIPELINE_RUNBOOK.md` — how to run each stage, and what each gate means
- `evaluation/EVALUATION.md` — the arms, the judges and the metrics
- `REFERENCES.md` — every work this stands on, and where in the code it does its work
