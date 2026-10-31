# Exact GDPR/GitHub experiment

## 1. Pre-register the comparison

Primary question:

> Can Gherkin tests generated from GDPR Article 13 distinguish GitHub's pre-GDPR
> privacy statement from the statement GitHub released to align with GDPR?

Use these policy snapshots for the primary comparison:

- Negative-control policy: Git tag `2017-10-11`, commit
  `f5b19e2a9caff2a9889f6a94e86ab70d283e340c`.
- Positive policy: Git tag `2018-05-25`, commit
  `abb0b833124f4a560a2bdd574f8f879c5f301225`.

Use the statement effective 27 April 2026, pinned at commit
`b9578b546d2506febda1da2cd7431644d58e512c`, only as a secondary persistence check.
The 2017-versus-2018 pair is the primary pair because GitHub itself says the 2018 release
focused on GDPR alignment. Comparing only 2017 with 2026 leaves eight years of unrelated
product and legal changes as a confounder.

Primary legislation: Regulation (EU) 2016/679, Article 13. Generate tests for paragraphs
13(1) and 13(2), including each lettered item. Treat 13(3) as a separate change-of-purpose
test. Do not generate a substantive test from 13(4), which is an exception where the data
subject already has the information and is difficult to establish from policy text alone.

Primary outcome: proportion of legally sound, policy-testable generated scenarios that
are `not_satisfied` in 2017 and `satisfied` in 2018 (`gap_closed`). Report all four
transitions; never discard regressions or persistent gaps.

## 2. Freeze the sources

Use the official EUR-Lex text for CELEX `32016R0679`:

`https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679`

Create `evaluation/gdpr_github/legislation/gdpr_articles_1_99.txt` containing the operative
text from Article 1 through Article 99. Exclude recitals, footnotes, page headers and the
final signatures. Keep each `Article N` heading on its own line. This gives the graph the
whole operative Regulation while keeping recitals from being misclassified as provisions.

Record the source URL, retrieval date and SHA-256 in a manifest. Manually compare Article
13 in the text file with EUR-Lex before any paid step. The EDPB transparency guidelines
may be used to create the human element list, but are guidance, not target legislation.

Verify the mechanical boundary before continuing:

```powershell
$articles = Select-String -Path evaluation/gdpr_github/legislation/gdpr_articles_1_99.txt -Pattern '^Article\s+\d+$'
$articles.Count                         # must print 99
$articles[0].Line                       # Article 1
$articles[-1].Line                      # Article 99
Get-FileHash evaluation/gdpr_github/legislation/gdpr_articles_1_99.txt -Algorithm SHA256
```

Freeze the policies from GitHub's official repository:

```powershell
git clone https://github.com/github/site-policy.git tmp/github-site-policy
git -C tmp/github-site-policy show 2017-10-11:Policies/github-privacy-statement.md |
  Set-Content -Encoding utf8 evaluation/gdpr_github/policies/github_2017.md
git -C tmp/github-site-policy show 2018-05-25:Policies/github-privacy-statement.md |
  Set-Content -Encoding utf8 evaluation/gdpr_github/policies/github_2018.md
git -C tmp/github-site-policy show b9578b546d2506febda1da2cd7431644d58e512c:Policies/privacy-policies/github-general-privacy-statement.md |
  Set-Content -Encoding utf8 evaluation/gdpr_github/policies/github_2026.md
Get-FileHash evaluation/gdpr_github/policies/* -Algorithm SHA256
```

Store those hashes in the run manifest. Do not use the live policy URL as an experimental
input because its contents can change without its URL changing.

## 3. Required code/configuration work before generating results

The following changes are required for a defensible full experiment:

1. Add `corpus.gdpr.yaml` and `profiles/gdpr.yaml`. Use `GDPR_` as a unique Neo4j prefix,
   `article` as the key prefix, and an identifier pattern matching Articles 1–99.
2. Replace the Australian worked examples still embedded in
   `kg_testgen/prompting.py` with instrument-neutral examples or corpus-configured
   examples. The opening citation examples are configurable, but later examples still
   mention Australian law, court/tribunal orders and APP clauses.
3. Review `spires/norm.yaml` and replace its remaining Australian example with
   neutral examples. Its data model—bearer, action, object, condition, exception and
   modality—is otherwise suitable for GDPR.
4. Use `evaluation.compare_policies`, not `evaluation.evaluate`. The latter is hardcoded
   to Microsoft 2016/2026 and only evaluates the second policy after an initial failure,
   so it cannot record regressions. The generic comparator judges both policies for every
   scenario and retains all four transitions.
5. Do not use `evaluation.run_experiment`, `score_elements`, `score_soundness` or
   `analyse_runs` unchanged. Their sections, paths, labels, manual-case parser and judge
   instructions are APP-specific. Either parameterise them from a GDPR evaluation config
   or make a small `evaluation/gdpr_experiment.py` runner.
6. Exclude the `kg`, `kg-text-only` and `rp1` arms unless their APP-specific graphs are
   rebuilt for GDPR. For the first GDPR experiment use only `none`, `full-corpus` and
   `spires`; those answer the relevant context-augmentation question without mixing laws.

The existing `evaluation.gherkin`, `evaluation.policy_check` and
`evaluation.compare_policies` modules can be reused unchanged.

## 4. Build and verify the GDPR corpus

Prepare the environments and credentials:

```powershell
.\bootstrap.ps1
. .\setup_env.ps1
.\.venv-testgen\Scripts\python.exe check_key.py
```

Induce the initial structure and write a separate corpus config:

```powershell
.\.venv-testgen\Scripts\python.exe induce_structure.py `
  evaluation/gdpr_github/legislation/gdpr_articles_1_99.txt `
  --out profiles/gdpr.yaml --write-config corpus.gdpr.yaml --model gpt-4o
```

Inspect the generated files before continuing. The acceptance conditions are:

- exactly 99 provisions;
- identifiers are `1` through `99`;
- `Article N` starts a provision and chapter/section headings do not;
- Article titles and every numbered/lettered paragraph remain inside the article text;
- `node_prefix` is `GDPR_` and is unused according to `python graph_registry.py`;
- the prompt examples name GDPR Articles rather than Australian provisions.

Run the free gates, then the build:

```powershell
$env:CORPUS_CONFIG = "corpus.gdpr.yaml"
.\.venv-testgen\Scripts\python.exe build_corpus.py `
  evaluation/gdpr_github/legislation/gdpr_articles_1_99.txt --dry-run
.\.venv-testgen\Scripts\python.exe build_corpus.py `
  evaluation/gdpr_github/legislation/gdpr_articles_1_99.txt --model gpt-4o-mini
```

Stop if the profile does not yield 99 articles, references such as Articles 6, 22, 46,
47 and 49 do not resolve, or nearly every extracted norm receives one modality.

## 5. Generate the Gherkins

First generate one pilot feature from Article 13:

```powershell
.\.venv-testgen\Scripts\python.exe -m kg_testgen --corpus corpus.gdpr.yaml `
  --provision 13 --context-mode spires --llm-model gpt-4o-mini `
  --temperature 0 --output-dir runs/gdpr_github/pilot/spires_r1 `
  --run-label "gdpr13|spires|r1"
```

Before scaling, reject or repair a generation if it:

- asks the policy to cite GDPR or an Article number;
- combines several Article 13 lettered requirements into an undecidable assertion;
- treats conditional requirements as unconditional;
- tries to infer operational compliance from policy wording;
- omits the `# Derives from:` traceability comment;
- produces a `Then` step that cannot be decided using only the policy.

For the full comparison, run three repeats at temperature 0 for each of `none`,
`full-corpus` and `spires`. A new parameterised runner is required for `none` and
`full-corpus`; the production CLI exposes only `spires`. Use the same model, output-token
limit, Article 13 input and prompt contract for all cells. The only independent variable
must be Block 3 context.

Store each cell under:

`runs/gdpr_github/experiment/article13__<arm>__r<repeat>/`

Each cell must retain `generated.feature`, `prompt.txt`, `raw_response.txt` and
`run_record.json`.

## 6. Establish the human reference before policy judging

Use `gdpr_article13_sample.feature` only as a seed. Expand `requirements.yaml` into a
complete Article 13 element list before reading generated outputs. At minimum, give every
lettered item in 13(1) and 13(2) its own element and record whether it is conditional.

For each generated scenario, have a human label:

- `sound`, `unsound`, `unverifiable` or `trivial`;
- which Article 13 element(s) it covers;
- whether its condition is correctly represented;
- whether it can be decided from policy text alone.

Only sound and policy-testable scenarios enter the primary policy-discrimination metric.
This prevents a fabricated test from earning credit merely because the 2017 policy fails
it and the 2018 policy happens to contain similar words.

## 7. Evaluate both policies independently

For each generated feature run:

```powershell
.\.venv-testgen\Scripts\python.exe -m evaluation.compare_policies `
  runs/gdpr_github/experiment/article13__spires__r1/generated.feature `
  --policy historical=evaluation/gdpr_github/policies/github_2017.md `
  --policy gdpr_aligned=evaluation/gdpr_github/policies/github_2018.md `
  --out-dir runs/gdpr_github/policy/article13__spires__r1 `
  --llm-model gpt-4o-mini --temperature 0
```

Run the same command separately with 2018 and 2026 for the secondary persistence check.
Do not relabel 2026 as the positive ground truth for the primary experiment.

The comparator writes `comparison.json` and `comparison.md`, verifies supporting quotes
against the policy text, and records SHA-256 hashes of its inputs. A `not_satisfied`
verdict normally has no supporting quotation because it asserts absence; manually search
the complete policy before accepting every negative.

## 8. Adjudicate and report

Blind the reviewer to generation arm. Preserve the LLM verdict and add separate fields:

- `human_verdict`;
- `reviewer` and `reviewed_at`;
- `article_element_ids`;
- `soundness`;
- `notes` and exact policy location.

Report per arm and repeat:

- number of generated scenarios;
- proportion sound and policy-testable;
- Article 13 element recall;
- `stable_satisfied`, `gap_closed`, `persistent_gap`, and `regression` counts;
- primary gap-closure rate among sound, testable scenarios;
- evidence-quote verification failures;
- disagreement between automated and human policy verdicts;
- stability across the three repeats.

Do not report “GDPR compliance rate.” This experiment measures whether generated policy
tests detect disclosure differences between two documents, not GitHub's complete legal or
operational compliance.
