# Work since KG construction

Three things were built on top of the existing knowledge graph: a **query + test-case
generation pipeline**, a **two-stage evaluation harness** that checks generated test
cases against real privacy policies, and a **controlled four-arm experiment** measuring
whether the knowledge graph actually helps.

19 modules in `kg_testgen/`, plus `run_experiment.py` and `setup_env.ps1`.

**Headline finding:** across two separate controlled comparisons, the knowledge graph
shows no measurable benefit over prompting with the section text alone. The context that
does help is the *verbatim text of related provisions* — not extracted relationships,
from either graph.

---

## 1. Where the KG left off

The construction pipeline (EDC) produced a graph now live in Neo4j Aura `e6598edc`:

- **369 `:AppNode` nodes**, 440 relationships, 75 relationship types
- Node types: `Concept` (249), `Provision` (77), `Legislation` (16), `Principle` (14),
  `Party` (9), `InformationType` (4)
- Every relationship carries `relation` (original text), `weight` (how many clauses
  assert it), and `provisions` (which subclauses)

That graph is the input to everything below. Nothing here modifies it.

---

## 2. Query pipeline (`python -m kg_testgen`)

**In:** one subclause of legislation, as a file or stdin.
**Out:** a timestamped folder under `runs/` containing `generated.feature`,
`run_record.json`, `prompt.txt`.

```
subclause text
  → EDC EntityExtractor          [LLM call 1]   → candidate terms
  → match to node keys (exact → normalised → fuzzy)
  → Cypher expansion (depth 2 entity / 3 provision, hard caps)
  → rank: hop → weight → degree
  → drop restatements, fit token budget
  → 4-block prompt (task | verbatim section | KG context | output contract)
  → generate                     [LLM call 2]   → Gherkin
```

Two LLM calls per run, `gpt-4o-mini` at temperature 0.

### Four context modes — the experimental arms

`--context-mode` selects what Block 3 of the prompt carries. Only that block changes;
everything else is held constant.

| Mode | Block 3 | Prompt size (APP 6.1) | Touches Neo4j |
|---|---|---|---|
| `none` | nothing — section text alone | 8,315 chars | no |
| `full-corpus` | all 134 documents of `app_schedule1.txt`, verbatim | 66,716 chars | no |
| `kg` | subgraph from the 369-node APP graph, as triples | 19,295 chars | yes |
| `rp1` | the whole 21-node RP1 concept graph | 14,730 chars | yes |

Each arm has its **own Block 3 header**, which matters more than it sounds. The `kg`
header asserts its statements "come from OTHER provisions" — true of retrieval, but
false of the pasted corpus (which contains the target section) and of RP1 (which has no
provisions at all). Reusing one header would put a false claim in the prompt.

### Design decisions worth knowing

**Vocabulary reuse.** Seeding reuses EDC's `EntityExtractor` and, critically,
`build_graph.normalise` — the function that produced every node's `key`. Without it,
extracted terms would not match what was stored.

**Asymmetric hop depth.** `:Provision` nodes are near-leaves (59 of 77 have degree 1), so
they get depth 3 while entity seeds get depth 2. Measured reach at depth 2: a provision
seed touches 5–12 nodes, an entity seed 105–150.

**Exclusion happens at serialisation, not traversal.** Triples restating the input
subclause are dropped from the LLM's context, but the graph walk still passes *through*
them — filtering during traversal would sever a provision seed at hop 1 and it would
contribute nothing.

`--self-provision-policy sole` (default) drops a triple only when the input subclause is
its **only** asserting provision. A triple asserted by the input clause *and ten others*
is genuine cross-section context and is kept. (`any` = stricter, `none` = off.)

**Fails loudly.** Zero seed matches, empty retrieval, missing env vars, unreachable DB,
and unknown node labels are all fatal with distinct exit codes. `--allow-unaugmented`
deliberately overrides, recording `augmented: false`.

### Which knobs actually matter

All 21 tunables are CLI flags. Only two are currently **binding**:

- `--max-relationships-per-node` (25) — every run hits it
- `--context-token-budget` (3000) — binds on larger sections

`--max-nodes` (120) and `--max-relationships` (200) have slack; changing them does
nothing until the other two are raised.

---

## 3. A second graph, needing a different query method (`rp1_query.py`)

The Aura instance also holds a second, disjoint graph built from `ResearchPaper1/output.json`
— 21 entities, 31 triples, labelled `:RP1Entity` with `RP1_`-prefixed relationship types.
Verified against source: 0 missing, 0 extra, all labels match.

It is a different shape of graph, so hop-limited retrieval is the wrong tool:

| Property | APP graph | RP1 graph |
|---|---|---|
| Size | 369 nodes / 440 edges | 21 nodes / 31 edges |
| Whole graph serialised | far over budget | **2,208 tokens** |
| Predicate vocabulary | 75 types, canonicalised | 27 types, 85% used once |
| Payload | topology only | entity `description` + `pred_description` |
| Provenance | `provisions` on every edge | none |

The entire RP1 graph is smaller than the APP arm's *budget for a subgraph*. So the method
**selects and orders** rather than retrieves — nothing is excluded for size, and seed
matching drives emphasis instead of filtering.

Optimisations for a legal/privacy reading:

- **Deontic-first ordering.** Only 8 of 31 edges carry legal force (`must comply with`,
  `has right to`, `is subject to`, `allows`); the other 23 are associative (`about`,
  `related to`, `involves`). Compliance tests derive from modality, so obligations and
  rights are presented first, under their own heading.
- **Definitional closure.** Every entity's description is included, *including the two
  isolated nodes* — a term with no edges may still be the one a provision turns on, and
  topology-only retrieval would drop it.
- **Inverse-pair collapsing.** Four node pairs carry duplicate edges, two of them true
  inverses (`requires compliance from` / `must comply with`). Where a pair differs in
  force, the deontic side is kept.
- **Role typing** from the free-text `types` field: Regulated party / Information type /
  Legal instrument / Process — what a compliance test needs to know.
- **Deliberately not ranked by degree.** `personal information` holds 18 of 62 edge
  endpoints; degree ranking would let the hub's most generic edges dominate.

## 4. Evaluation harness (`python -m kg_testgen.evaluate`)

**In:** a generated `.feature` plus the two Microsoft policies in
`../MicrosoftPrivacyPolicy/` (2016: 23k tokens, 2026: 37k).
**Out:** `evaluation.json` and `evaluation.md` beside the feature.

Two stages, per the original requirements: every scenario judged against 2016, and
**only the failures** re-judged against 2026.

| Classification | Meaning |
|---|---|
| `green_tick` | Satisfied by the 2016 policy |
| `orange_cross` | Failed 2016, satisfied 2026 — a real gap later closed |
| `red_cross` | Failed both — **ambiguous**, flagged for manual review |

Both policies fit in context whole, so there is no retrieval layer over the policy.

**Anti-fabrication check.** Every verdict must cite a verbatim policy span, which is then
verified as a substring programmatically. Three states: `verified`, `no_quote` (correct
for a `not_satisfied` verdict), and `unverified` — a quote that is *not* in the policy,
i.e. a fabricated citation.

**Judge calibration.** Before trusting results, the judge was run against controls
(`sections/calibration.feature`): two obviously-satisfied requirements returned
`satisfied` with verified quotes; one absurd requirement (a named Australian statutory
deadline) returned `not_satisfied`. So the judge discriminates rather than refusing
everything.

---

## 5. Results A — policy evaluation, 6 sections, 31 scenarios

| Section | Scenarios | Satisfied 2016 | Gap closed by 2026 | Needs review |
|---|---|---|---|---|
| APP 1.4 (policy contents) | 9 | 5 | 0 | 4 |
| APP 5.2 (notification matters) | 11 | 7 | 0 | 4 |
| APP 6.1 (secondary use) | 2 | 0 | 0 | 2 |
| APP 8.1 (cross-border) | 1 | 0 | 0 | 1 |
| APP 11.1 (security) | 6 | 5 | 0 | 1 |
| APP 12.1 (access) | 2 | 1 | 0 | 1 |
| **Total** | **31** | **18 (58%)** | **0** | **13 (42%)** |

**0 fabricated evidence citations** across 51 judge calls.

### Key finding: zero orange crosses

Every 2016 failure also failed 2026, so the ground-truth mechanism produced no
discrimination on this sample. Not a bug — the calibration controls confirm the judge
works. Microsoft's policy simply is not written to the APP framework in **either** year.

Of the 13 review-flagged scenarios, 4 cite legislation and are unverifiable by
construction. The other 9 look like genuine gaps, several independently corroborated
across sections — e.g. the policy never names the countries overseas recipients are in
(found separately by APP 1.4 and APP 5.2), never states that access requests are free
(APP 12.1), never commits to consent before secondary use (APP 6.1).

## 6. Results B — does the knowledge graph help?

Two controlled comparisons were run. Neither found a benefit.

### B1. Ablation — 6 sections, KG vs no KG

Same sections, same prompt, same judge; the only difference is whether the KG context
block was present.

| Metric | No KG | With KG |
|---|---|---|
| Scenarios generated | 31 | 31 |
| Satisfied by 2016 policy | **19 (61%)** | 18 (58%) |
| Flagged for review | **9** | 13 |
| Gaps closed by 2026 | **3** | 0 |
| Scenarios citing legislation | **3 (10%)** | 4 (13%) |
| Fabricated citations | 1 | **0** |

The baseline is equal or better on every measure except fabrication. Two of the three
baseline "gap closed" verdicts rest on the judge accepting an *implication* rather than
an explicit statement, so even that difference is soft.

### B2. Four-arm comparison — 3 subclauses, 4 arms, 3 repeats

36 cells, driven by `run_experiment.py`. Subclauses chosen because each depends on
clauses **outside** its own text — where a KG should earn its place:

- **APP 2.2** — an exception disapplying 2.1, which is not in the input
- **APP 4.4** — almost pure cross-reference ("APPs 5 to 13 apply as if…")
- **APP 6.1** — prohibition whose exceptions point at 6.2 and 6.3

| Section | Manual ref. | `none` | `full-corpus` | `kg` | `rp1` |
|---|---|---|---|---|---|
| APP 2.2 | 16 | 8/8/8 | 5/5/6 | 6/6/6 | 8/8/9 |
| APP 4.4 | 6 | 2/2/2 | 2/1/2 | 2/2/2 | 2/2/2 |
| APP 6.1 | 8 | 5/5/5 | 13/6/14 | 5/5/5 | 5/5/5 |
| **Total, 9 runs** | | **45** | **54** | **39** | **46** |

Hand-written reference cases (30 across the three subclauses) come from
`testcasecomparison/Test cases FYP.docx` and are reproduced in the comparison document.

**Every arm falls far short of the manual set** — most starkly on APP 2.2, where 16
hand-written cases separate law from court order from tribunal order, requires from
authorises, and anonymity from pseudonymity.

### The baseline-case finding, and its correction

A single `rp1` run produced a *baseline* scenario on APP 2.2 — the case where no
exception applies and the primary rule stands — which no other arm had managed. That
looked like evidence that concept definitions supply what topology cannot.

Measured across all runs, it does not hold:

| Arm | Runs with a baseline case (of 9) |
|---|---|
| `none` | 5 |
| `full-corpus` | **7** |
| `kg` | 5 |
| `rp1` | 5 |

On APP 2.2 specifically `rp1` managed 1 of 3; the demo happened to be that run.
`full-corpus` got it 3 of 3. So the mechanism is real but the attribution was wrong:
what helps is having **the clause the exception disapplies actually in context**, not
having concept definitions.

### Caveats that bound all of the above

- 3 subclauses, 3 repeats. The spread between arms (39–54 scenarios) is comparable to
  the spread *within* `full-corpus` alone (6–14 on one clause).
- **Temperature 0 is not deterministic** — 7 of 9 cells produced 3 different outputs
  across 3 repeats.
- `full-corpus` drifts off-target: its higher count on APP 6.1 comes from generating
  scenarios for 6.2, 6.3, 6.5, 6.6 and 6.7, which the prompt explicitly forbids.
- Long context also degrades formatting: `full-corpus` emitted `@ s6-1` (with a space)
  on 30 of 30 APP 6.1 scenarios, which Gherkin reads as a bare `@` tag. The same bug
  later appeared in `none`, so it is not exclusive to long prompts.

### Generator prompt tightening

The first 6.1 run produced scenarios asserting the policy must "explain when subclause
6.2 applies" — untestable, since no company policy cites Australian subclauses. The
prompt now forbids legislative citations, mandates policy vocabulary, and requires each
`Then` to be one self-contained checkable claim, with worked bad/good examples.

| | Before | After |
|---|---|---|
| Then steps citing legislation | 33% (1 of 3) | 13% (4 of 31) |
| Vague "certain conditions" steps | 1 | 0 |

The 4 remaining citations are inherent to their provisions (APP 1.4(e) literally requires
telling individuals how to complain about an APP breach), not generator sloppiness.

### Second iteration — comprehensiveness

Comparison against the manual set exposed a different failure: the generator *collapsed*
compound conditions instead of decomposing them. One `Given` covered six of the manual
cases at once:

> `Given the APP entity is required or authorised by Australian law or a court/tribunal order`

Five changes went into the prompt:

1. **Decomposition axes named explicitly** — "an Australian law, or a court/tribunal
   order" is **three**; "required or authorised" is **two**.
2. **Mandatory baseline case** — for every exception, also write the scenario where it
   does not apply.
3. **Extended ban list** — "where an exception applies", "if permitted", "as applicable",
   and five more.
4. **Worked decomposition example** showing the collapsed `Given` expanded into six.
5. **Direction fix** — state what a condition *permits or requires*, rather than
   restating the condition as the outcome.

| APP 2.2, scenarios | Before | After |
|---|---|---|
| `none` | 2/2/2 | **8/8/8** |
| `full-corpus` | 3/3/3 | 5/5/6 |
| `kg` | 2/2/2 | 6/6/6 |

Decomposition worked exactly as specified — the instrument × modality cross-product now
appears in full, mapping one-to-one onto manual cases TC03–TC08. Banned phrasings: **0
occurrences across all 27 cells**. The direction bug is fixed: what previously read "the
entity may deal with individuals who have not identified themselves" now reads "the
entity may require individuals to identify themselves".

The mandatory baseline instruction, however, largely **failed** — see the baseline
finding above. It is in the prompt; the model does not follow it when the primary rule
lives in a clause it cannot see.

Still uncovered on APP 2.2: mixed practicability (TC11/TC12) and the boundary cases
(TC14 company-policy-is-not-an-exception, TC15 scope-limited-to-that-matter, TC16).
Best case is 8 of 16, up from 2 — the remaining gap is structural, not a prompting
failure.

---

## 7. Setup

```bash
python -m venv .venv-testgen
.venv-testgen\Scripts\python.exe -m pip install -e .
```

Heavy ML dependencies (`torch`, `transformers`, `sentence_transformers`) are stubbed at
import — only EDC's OpenAI path is used — so the venv has five real dependencies.

Credentials come from environment variables only. `. .\setup_env.ps1` loads them from the
Aura credentials file and your user environment without copying secrets to disk. Run
records contain **no** secrets (`Secrets` is a separate dataclass that never reaches the
record).

```bash
. .\setup_env.ps1
.\.venv-testgen\Scripts\python.exe -m kg_testgen sections\app_6_1.txt --context-mode kg
.\.venv-testgen\Scripts\python.exe -m kg_testgen.evaluate runs\<run>\generated.feature
.\.venv-testgen\Scripts\python.exe run_experiment.py --repeats 3
```

`run_experiment.py` runs the full 4-arm grid and writes `runs/experiment/comparison.md`.
It skips completed cells, so it is resumable and adding an arm re-runs only that arm.
`--report-only` rebuilds the document without regenerating.

**The Aura instance auto-pauses.** A paused Free instance has its DNS record withdrawn,
so the failure presents as `Non-existent domain` rather than a refused connection — it
looks like a deleted database. Resume it in the console before any run or demo.

---

## 8. Known issues and what's stubbed

**Issues**

- The generator under-produces on conditional obligations (APP 8.1 → 1 scenario, APP 12.1
  → 2) while scaling well on enumerated lists (APP 5.2 → 11). Uneven coverage.
- APP 1.4 and 8.1 tripped the structure checker with `no 'When' steps` — Given/Then only,
  so the triggering activity is unstated.
- **The structure checker accepts `@ s6-1`** (with a space) because the line starts with
  `@`, so malformed tags pass generation and are only caught by the comparison
  document's mechanical checks.
- Corpus and query pipeline are **not wired together**; section files were extracted by
  hand. Batch processing is a deliberate stub.
- Generated scenarios and the manual reference cases **test different things**. The
  manual cases test the entity's *conduct* ("the individual can proceed without
  identifying themselves"); the generated ones assert what a *policy states*, as
  specified. Compare on substance, not wording — or re-specify one side.

**Stubbed, raising `NotImplementedError`**

Vector/embedding seeding · embedding-similarity and centrality ranking · JSON
serialisation · asymmetric depth by *relationship type* · relationship prioritisation ·
temporal validity filtering · iterative multi-turn retrieval · batch processing.

Note: the Aura instance is **enterprise 5.27** — APOC, GDS, fulltext and vector indexes
are all available (probed at runtime and recorded in run metadata). The original "free
tier, no GDS" constraint does not apply. Vector seeding needs only embedding generation
plus an index build.

---

## 9. Where this points next

The one finding durable across both comparisons is that context containing the
**verbatim text of related provisions** outperforms context containing extracted
relationships — from either graph. The APP graph stores no source text; the RP1 graph
stores definitions but no provisions. `full-corpus` has the actual clauses, and it is
the only arm that reliably produces baseline cases.

That suggests the highest-value change is not a better retrieval method but a richer
graph:

1. **Store provision text on the node**, so retrieval returns law rather than
   abstractions — then re-run the same experiment unchanged.
2. **Model cross-references as edges** ("unless subclause 6.2 applies"), making the
   exception structure traversable. This is exactly what the failed baseline cases need:
   subclause 2.2 disapplies 2.1, and 2.1 is currently unreachable.
3. Scale past 3 subclauses and 3 repeats to get above the noise floor.
4. Add a second judge model and report inter-rater agreement.

A KG that carried provision text and cross-references would be testable against
`full-corpus` on equal terms — retrieving the same information, but selectively. That is
the comparison this work has set up but not yet run.
