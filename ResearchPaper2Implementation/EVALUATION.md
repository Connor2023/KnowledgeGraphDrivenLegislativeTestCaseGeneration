# Evaluation

How the pipeline's output was measured. **None of this is part of the pipeline.**

`PIPELINE_RUNBOOK.md` ends where a `.feature` file exists. Everything here exists to
produce a results section: the multi-arm comparison, the coverage and soundness judges,
the diversity statistics, and the policy check. The code lives in `evaluation/`, which
is deliberately not an installed package — `pyproject.toml` lists `kg_testgen` alone, so
`pip install .` gives you a pipeline that cannot spend credits on judging itself.

The boundary is one-directional and enforced:

```bash
python tests/test_pipeline_isolation.py
```

`evaluation` may import `kg_testgen` — it has to, since it runs the pipeline it
measures. The reverse is a defect, and the test fails on it. It is a static check over
import statements, so it runs in any of the three virtualenvs without a network.

Paths that only the measurement code needs — the element decomposition, the manual test
cases, the two policies — are declared in `evaluation/eval_config.yaml`, never in
`corpus.yaml`.

```bash
python -m evaluation.eval_config        # print what is configured
```

---

## 1. Reproducing the comparison

```powershell
python -m evaluation.run_experiment                  # every arm x every section x 3 repeats
python -m evaluation.run_experiment --repeats 1      # quick pass
python -m evaluation.run_experiment --report-only    # rebuild the comparison document only
```

Completed cells are skipped, so the grid is resumable across the hours it takes. Output
lands in `runs/experiment/`, with `comparison.md` putting every arm's scenarios beside
the hand-written reference cases.

Reading the manual cases needs `python-docx`, which is an evaluation dependency and is
**not** in the pipeline's requirements.

```powershell
pip install python-docx
```

---

## 2. Scoring, in increasing order of cost

```powershell
python -m evaluation.analyse_runs                    # free: diversity, stability, cost
python -m evaluation.score_elements --dry-run        # count calls and cost first
python -m evaluation.score_elements --judge-model gpt-4o
python -m evaluation.score_soundness --self-test     # 7 known-answer controls, ~$0.20
python -m evaluation.score_soundness --per-arm 14 --judge-model gpt-4o
```

**Run `--self-test` before spending on a full soundness pass.** An earlier version of
that judge reasoned that the statute never requires a policy to contain any particular
sentence, and therefore marked a third of all scenarios unsound — a test no scenario in
this project could pass. The controls catch that class of failure for 20 cents.

Both scorers are resumable and cache per judgement, so re-running only fills gaps.

Two things that cost real money to rediscover:

- **Rate limits lose judgements silently.** The soundness judge sends the whole Schedule
  per call (~8,400 tokens) against a 30,000 TPM ceiling. An early pass dropped 14 of 98
  judgements without failing, leaving one arm reporting on n=4. There is backoff now, but
  check the per-arm counts in the report before quoting a figure.
- **Serialisation dominates.** Rendering the graph as readable sentences instead of
  pipe-delimited triples moved coverage by +11pp — larger than switching graphs (~5pp) or
  rephrasing a header (1.8–3.5pp). Any comparison between arms has to hold it fixed.

---

## 3. Checking the policy verdicts

```powershell
python -m evaluation.evaluate runs/final_6_1/generated.feature
```

Two stages. Every scenario is judged against the 2016 Microsoft privacy policy; the 2016
failures are re-judged against the 2026 policy, which acts as ground truth for whether a
failure was a real gap the policy later closed. Every verdict must carry a verbatim quote,
and that quote is then located in the policy text programmatically — a fabricated citation
is caught rather than trusted.

---

## 4. Validating a judge before believing it

```powershell
python -m evaluation.score_elements --sample-for-human 60   # blinded worksheet + answer key
# ... annotate human_sample_answers.csv by hand ...
python -m evaluation.score_elements --kappa runs\elements\human_sample_answers.csv
```

The worksheet never names the arm — sets are labelled "Set A/B/C" — and the judge's own
verdicts sit in a separate key file.

Measured against one human annotator the element judge scored **κ = 0.451**: moderate
agreement, with precision 0.56 against recall 0.90. It is systematically lenient rather
than randomly noisy, which means **every coverage figure it produces is an upper bound**,
and the direction of the bias is known rather than assumed.

`score_soundness` has the same `--sample-for-human` / `--kappa` pair. It has not been
run, so the soundness figures currently rest on the seven known-answer controls alone.

---

## 5. Cost, for planning

Measured on 62 clauses and three subclauses at three repeats:

| Stage | Cost | Part of the pipeline? |
|---|---|---|
| SPIRES graph construction | ~$2.50 | yes |
| Running all seven arms | ~$0.09 | one arm is; the other six are the comparison |
| Evaluating them | ~$13 | no |

**Evaluation costs roughly five times construction.** Budget accordingly — the usual
assumption is the other way round. It is also the reason the boundary in section 0 is
worth enforcing: the expensive half is the half nobody is proposing to run again.
