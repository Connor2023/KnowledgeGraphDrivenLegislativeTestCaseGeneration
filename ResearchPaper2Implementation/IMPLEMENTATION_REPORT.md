# Work since KG construction

Two things were built on top of the existing knowledge graph: a **query + test-case
generation pipeline**, and a **two-stage evaluation harness** that checks the generated
test cases against real privacy policies.

18 modules, ~2,400 lines, in `kg_testgen/`.

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

## 3. Evaluation harness (`python -m kg_testgen.evaluate`)

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

## 4. Current results — 6 sections, 31 scenarios

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

---

## 5. Setup

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
.\.venv-testgen\Scripts\python.exe -m kg_testgen sections\app_6_1.txt
.\.venv-testgen\Scripts\python.exe -m kg_testgen.evaluate runs\<run>\generated.feature
```

---

## 6. Known issues and what's stubbed

**Issues**

- The generator under-produces on conditional obligations (APP 8.1 → 1 scenario, APP 12.1
  → 2) while scaling well on enumerated lists (APP 5.2 → 11). Uneven coverage.
- APP 1.4 and 8.1 tripped the structure checker with `no 'When' steps` — Given/Then only,
  so the triggering activity is unstated.
- Corpus and query pipeline are **not wired together**; section files were extracted by
  hand. Batch processing is a deliberate stub.
- `runs/` is not gitignored (no secrets in it, but it is noise).

**Stubbed, raising `NotImplementedError`**

Vector/embedding seeding · embedding-similarity and centrality ranking · JSON
serialisation · asymmetric depth by *relationship type* · relationship prioritisation ·
temporal validity filtering · iterative multi-turn retrieval · batch processing.

Note: the Aura instance is **enterprise 5.27** — APOC, GDS, fulltext and vector indexes
are all available (probed at runtime and recorded in run metadata). The original "free
tier, no GDS" constraint does not apply. Vector seeding needs only embedding generation
plus an index build.
