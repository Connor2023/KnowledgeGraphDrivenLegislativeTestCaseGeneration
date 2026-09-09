# Pipeline runbook

How to take a new piece of legislation from a plain-text file to a knowledge graph, and
how to generate compliance test cases from any clause using any of the arms.

This document covers the pipeline and stops where a `.feature` file exists. Measuring
that output — the multi-arm comparison, the coverage and soundness judges, the policy
check — is a separate concern and lives in `EVALUATION.md`. The code is separated the
same way: `kg_testgen` is the installable pipeline, `evaluation/` is not installed, and
`tests/test_pipeline_isolation.py` fails if the pipeline ever imports it.

**The pipeline builds one context mode: `spires`.** The six comparison arms — `none`,
`full-corpus`, `kg`, `kg-text-only`, `rp1` and the format probes — are kept and runnable
in `evaluation/arms/`, and reach the pipeline through an `ExternalContext` it is handed
rather than one it builds. That is why `--context-mode` offers only `spires` here.

Everything below was run on Windows with Git Bash and PowerShell side by side. Commands
are given for PowerShell; the Bash equivalents differ only in how environment variables
are set.

---

## 0. A new statute is a .txt file

```powershell
python build_corpus.py MyStatute.txt --dry-run    # every free stage and gate, no spending
python build_corpus.py MyStatute.txt              # induce, segment, extract, clean, build
python -m kg_testgen --list-provisions
python -m kg_testgen --provision "26WE(1)" --context-mode spires
```

Naming a statute this checkout has no config for is enough: `build_corpus.py` induces the
profile, generates `corpus.<name>.yaml`, and re-runs itself under it. If a config already
points at that file it is found and used -- matched on what it points at, not what it is
called, so `corpus.part_iiic.yaml` and `APPartIIIC.txt` pair up.

That is the whole of it. The pipeline used to be coupled to Schedule 1 in seven places,
each needing hand-written code for a new instrument. Six of them are now driven by a
**structural profile** that `induce_structure.py` derives from the text and validates
against the whole file before anything is spent:

| Was | Now |
|---|---|
| `prep_app.py`'s regexes for APP headings and `N.M` clauses | `profiles/<name>.yaml` line classifiers, applied by `prep_corpus.py` |
| `enrich_graph.parse_references`' three citation patterns | `references.py`, built from the profile's citation nouns, identifier pattern and `id_template` |
| `edc_bridge._PROVISION_RE` | `corpus_config.PROVISION_RE`, from the profile |
| `pipeline.DEFAULT_CORPUS_PATH` | the full-corpus arm's concern, in `evaluation/arms/` |
| `app_*.txt` / `app_*.yaml` filename prefixes | `file_prefix` in `corpus.yaml`, generated |
| `spires/app_norm.yaml`'s APP worked examples | `spires/norm.yaml`, instrument-neutral |

**What still needs a human.** The profile is induced but should be read: correcting one
pattern by hand is cheaper than re-inducing, and `profiles/<name>.yaml` is a normal file.
`node_prefix` in the generated `corpus.yaml` is worth checking against
`python graph_registry.py`, since several corpora share one Aura instance. And a statute
with genuinely new normative shapes — deadlines, offences — may need the modality enum
extended; no induction fixes that.

**The gates are the safety net.** Each build stage reports a number that is checked before
the next runs, because every one of these has happened here and none of them raises:

| Gate | Catches |
|---|---|
| **input hygiene** | **a .txt whose structure is intact and whose text is mangled** |
| provision count | a profile that segments the file into almost nothing |
| interior orphan rate | a structural form unrecognised mid-instrument, its text dropped |
| reference resolution | an identifier pattern that recovers nothing |
| provisions citing anything | the same, disguised as a 100% rate over an empty denominator |
| modality spread | every norm labelled NONE — the schema's distinctions did not land |
| node prefix | a second corpus about to merge into the first |

A failed gate stops the run before extraction, which is the first stage that costs money.

**The hygiene gate is the one that catches what the others cannot.** Every other gate
looks at structure. Measured by damaging Schedule 1 three ways and checking whether the
provision *text* survived:

| Damage | Provisions found | Texts corrupted | Old gates catch it |
|---|---|---|---|
| Hard wrap, no hyphenation | 62 (correct) | 0 / 62 | — nothing to catch |
| Hard wrap **with hyphenation** | 62 (correct) | **45 / 62** | no |
| Running headers + page numbers | 62 (correct) | **13 / 62** | no |

Both corrupting variants segment to exactly the right count with an orphan rate under the
ceiling, so provision count, orphan rate and reference resolution all pass — on a file
whose text is three-quarters mangled.

The three signals are each unambiguous, and each measured at zero on both real corpora: a
word ending in a hyphen before a space (a rejoined line break), a line that is nothing but
a number (a page number), and a line repeating five or more times **at a regular pitch**
(a running header). That last qualifier matters — wrapping leaves fragments like "personal
information" repeating just as often, and their gaps vary by 0.73–0.93 against 0.02 for a
real header. A plain wrap is deliberately allowed through, because its provision texts
come out byte-identical.

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
```

`check_setup.py` also exists, but it preflights the EDC construction path -- its
dataset, its few-shot files, its dependencies -- and that path is now an evaluation arm.
For the pipeline, `build_corpus.py --dry-run` is the preflight: it runs every free stage
and every gate and stops before spending.

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

### 2.0 Learn the statute's structure (stage 0)

Before anything is parsed, work out how the instrument lays itself out. One LLM call over
a sample of the document returns a **structural profile** — an ordered list of line
classifiers, which level is the provision, and how an identifier is composed — and that
profile is then validated against the whole file before it is allowed anywhere near the
extraction.

```powershell
python induce_structure.py APPartIIIC.txt --dry-run    # prompt size and cost, no call
python induce_structure.py APPartIIIC.txt              # ~$0.013, writes profiles/<name>.yaml
```

Validation is the point, not the call. A profile is rejected if too many lines belong to
no provision, if the provision count is implausible, if identifiers collide, if one
provision holds a quarter of the text, or if a pattern fails to compile, is unanchored,
can backtrack catastrophically, or claims nothing once the levels above it have taken
theirs. A rejected profile is re-asked once with the failure report attached; a second
rejection stops the run and names the pattern, because an empty graph found three stages
later is the expensive outcome.

Warnings are printed but are not fatal. The one that matters is a recurring
heading-shaped line no level claims — that text is not lost, but it is being glued onto
the end of the provision above it.

**Check the profile before going further**, and correct it by hand if a pattern is
slightly wrong. `profiles/<name>.yaml` is a normal file, editing it is cheaper than
re-inducing, and the header records what the numbers were when it was accepted.

To check a hand-written profile without spending anything:

```powershell
python induce_structure.py APPschedule1.txt --profile profiles/app_schedule1.yaml
```

Measured so far:

| Corpus | Provisions | Interior orphans | Agreement |
|---|---|---|---|
| Schedule 1, hand-written profile | 62 | 1.8% | identical ids to `prep_app.py` |
| Part IIIC, hand-written profile | 106 | 0.0% | — |
| Part IIIC, induced profile | 106 | 0.4% | identical ids to the hand-written one |

The controls cost nothing to run. None of them makes an API call, and the one check
that wants Neo4j skips cleanly without it:

```powershell
python tests/test_induce_structure.py      # profile format, segmentation, 10 mutations
python tests/test_references.py            # citation parsing, Schedule 1 equivalence
python tests/test_build_gates.py           # the gates catch three broken profiles
python tests/test_graph_registry.py        # prefix collisions are refused
python tests/test_modality_vocabulary.py   # APPLICABILITY across two corpora
python tests/test_pipeline_isolation.py    # the pipeline does not import evaluation
python tests/test_arm_prompts_unchanged.py # 117 recorded prompts, byte for byte
python tests/test_hygiene.py               # damaged .txt files the other gates miss
```

### 2.1 Segment it into provisions

`prep_corpus.py` applies the profile. It is what `prep_app.py` used to be, minus the
statute-specific regexes:

```powershell
python prep_corpus.py                  # how many provisions, first and last
python prep_corpus.py --list           # every identifier, in document order
python prep_corpus.py --show 6.1       # one provision's verbatim text
```

**Check this before going further.** A provision count of zero or three means the
profile's patterns did not match, and everything downstream would be built on nothing.
`build_corpus.py` checks it for you and stops.

Keys are bare identifiers — `6.1`, `26WE(1)` — and the order is the order the instrument
states them in, which is also the sort key. Nothing derives an ordering from the
identifier grammar; two places used to, with `[int(x) for x in pid.split(".")]`, and both
raised on anything not numbered `N.M`.

`prep_app.py` still exists and still produces the flattened one-document-per-line file
under `edc-main/edc-main/datasets/`. Nothing in the pipeline reads it any more: it feeds
the `full-corpus` and EDC arms, which are in `evaluation/arms/`.

### 2.2 Build the SPIRES norm graph

This is the graph the pipeline queries. Four stages, and `build_corpus.py` runs all of
them — the commands below are for running one at a time.

```powershell
# 1. Extract — one call per provision against the LinkML schema, resumable
python spires\extract_corpus.py --dry-run     # how many provisions, what it costs
python spires\extract_corpus.py               # ~20 min, ~$0.90 on gpt-4o for 62 clauses

# 2. Clean — strip the prompt's own fill-in markers, which the model echoes back
python spires\clean_extraction.py

# 3. Verify — recover exception clauses the recursive extraction drops
python spires\verify_exceptions.py

# 4. Build and load
python spires\build_spires_graph.py --dry-run  # writes CSVs, reports node/edge counts
python spires\build_spires_graph.py            # claims the node prefix, then loads
```

**Cost scales with the number of provisions, not with the size of the corpus.** The
schema is resent with every call and is 2,107 tokens against a mean provision of about
100, so it dominates. Part IIIC has 1.44x Schedule 1's words but 1.71x its provisions,
and costs about 1.7x: ~$1.51 on gpt-4o against Schedule 1's measured ~$0.90. On
gpt-4o-mini the same run is ~$0.09.

Always run `--dry-run` first. It prices the actual prompt rather than applying a flat
per-provision rate -- the previous estimate did the latter, calibrated on an early
24-provision pilot, and over-stated Schedule 1 by 2.9x.

`--wipe` on the last command deletes existing nodes under this corpus's prefix first. It
is scoped to that prefix, so other graphs in the same instance survive.

Four things worth knowing:

- **The loader claims the node prefix before writing anything.** Neo4j has no namespaces,
  so a second corpus loading under a prefix the first one owns would merge both graphs
  with nothing reported. `python graph_registry.py` shows what is claimed and what is
  live.
- **Cleaning discards roughly 46% of condition and exception field values.** That is not
  a bug. SPIRES marks fill-in slots with angle brackets and the model returns them
  filled in but still bracketed, or echoes the field description itself. Run
  `python spires\review_discards.py` to audit what was dropped, ranked by how much it
  could cost rather than by frequency.
- **Cross-reference edges come from `references.py`, not from SPIRES.** Over 62 clauses
  the parser finds cross-references in 26 provisions against SPIRES' 10, with exactly one
  provision that only SPIRES found. Two extractors, each doing what it measured best at.
- **Citations that leave the corpus become `:*_ExternalRef` stubs.** Part IIIC makes 25 of
  them. They used to be dropped with a count printed, which left the graph understating
  its own incompleteness.

### 2.3 Optional: build the EDC graph

Not part of the pipeline. It exists for the `kg` and `kg-text-only` comparison arms, which
live in `evaluation/arms/`, and it pulls in the vendored `edc-main` tree along with
transformers and torch.

```powershell
# EDC three-stage construction (extract, define, canonicalize)
.\.venv-edc\Scripts\python.exe edc-main\edc-main\run.py --oie_llm gpt-4o-mini ...

# Load, then add provision text and REFERS_TO edges
python load_neo4j.py
python -m evaluation.arms.enrich_graph --dry-run
python -m evaluation.arms.enrich_graph
```

The SPIRES graph no longer depends on any of this. It used to: the `spires-hybrid` arm
read provision text out of `:AppNode`, so on a corpus with only a norm graph it silently
returned nothing and degraded to plain `spires`. `:SP_Provision` nodes now carry
`text_raw` themselves.

`prep_app.py` and `enrich_graph.py` moved into `evaluation/arms/` with the arms they
serve. `build_graph.py` and `check_setup.py` are the same category and could follow;
`load_neo4j.py` cannot, because `spires/build_spires_graph.py` reads its credential
helper.

---

## 3. Generating test cases

Name a provision and the text comes from the segmentation:

```powershell
python -m kg_testgen --list-provisions
python -m kg_testgen --provision 6.1 --context-mode spires
python -m kg_testgen --provision "26WE(1)" --context-mode spires --spires-provision-text
```

A file or stdin still works, for text that is not in the configured corpus:

```powershell
python -m kg_testgen path\to\clause.txt --context-mode spires
```

The provision identifier is detected from the text automatically; `--provision` sets it
directly, which matters for instruments whose subsections do not carry their section
number — `26WE(1)` reads "(1) This section applies if:" and nothing in it says 26WE.

### The pipeline builds one context mode

`--context-mode spires` walks the norm graph. That is the only mode the pipeline builds,
which is why it is the only choice the CLI offers.

| Arm | How to run it | Where it lives |
|---|---|---|
| `spires` | `--context-mode spires` | the pipeline |
| `spires-hybrid` | `--context-mode spires --spires-provision-text` | the pipeline |
| `none`, `full-corpus`, `kg`, `kg-text-only`, `rp1`, six `fmt-*` probes | `python -m evaluation.run_experiment` | `evaluation/arms/` |

The comparison arms are kept and runnable — they are what the spires results are quoted
against — but they reach the pipeline through an `ExternalContext` they build themselves,
so the pipeline never imports them. Asking it for one of their modes fails with a message
naming where the arm went. See `EVALUATION.md`.

### Tuning the SPIRES arm

```powershell
python -m kg_testgen --provision 6.1 --context-mode spires `
    --spires-hop-depth 2 `             # follow references two hops instead of one
    --spires-modality-filter deontic ` # keep only MUST / MUST NOT / MAY norms
    --no-spires-inbound `              # forwards only (see the warning below)
    --no-spires-exceptions-first       # conditions above exceptions
```

**`--no-spires-inbound` will quietly weaken the retrieval.** Inbound edges are what find
the provision that *defeats* the target: APP 2.1 read alone states an unqualified right
to anonymity and is misleading until 2.2 — which points at it — is in view. Outbound-only
retrieval can never reach 2.2 from 2.1.

**There is no node cap on this arm.** `max_nodes` belongs to the EDC arm. A whole-section
citation reaches every subsection of that section, so a provision citing an eleven-
subsection section pulls all eleven. Measured worst case in Part IIIC is 14 provisions at
roughly 1,250 tokens, against 4 and 537 for Schedule 1 — comfortable, but measured rather
than enforced, and worth re-checking on a new corpus.

### Other useful flags

```
--model gpt-4o                 the generator model (default gpt-4o-mini)
--temperature 0.0              not strictly deterministic even at 0
--provision-id 6.1             override the identifier detected from the text
--block3-format terse|neutral  alternative header phrasings, for sensitivity testing only
--output-dir <dir>             where to write (default: a timestamped folder under runs/)
--allow-unaugmented            proceed when retrieval finds nothing, instead of failing
```

`--block3-format` exists to measure how much of a score is the context and how much is
the wording around it. It is not a configuration you would ship.


## 4. Where the output goes

By default each run writes a timestamped directory under `runs/`. With `--output-dir`
it writes exactly where you say.

| File | Contents |
|---|---|
| `generated.feature` | **The test cases.** Gherkin: one `Feature`, one `Scenario` per obligation, condition or exception, each tagged with its provision and carrying a `# Derives from:` quote |
| `prompt.txt` | The full four-block prompt as sent, so a result can be reproduced or audited |
| `run_record.json` | Everything else: config, the graph context that was retrieved, the raw model response, and any structural problems found in the Gherkin |

`runs/` is in `.gitignore` — these are regenerable and there are thousands of them.

### Reading a run record

```powershell
python -c "import json; d=json.load(open('runs/<dir>/run_record.json')); print(d['spires_context'])"
```

Useful keys: `augmented` (did context reach the prompt), `spires_context` (what the
norm graph returned, including which provisions were reached inbound and outbound, and
the token estimate), `gherkin_structure_problems` (malformed output). A record written by
an evaluation arm carries that arm's own keys instead -- `seeding`, `retrieval`,
`ranking`, `serialisation`, `provision_text` for the EDC arm, `rp1_context` for RP1.

---

## 5. What happens next

The pipeline ends here: a `.feature` file and a run record. Everything about judging,
scoring, comparing arms and reproducing the experiment is in **`EVALUATION.md`**, and
none of it is needed to run the pipeline or to point it at a new statute.
