# GitHub/GDPR differential pilot

This package is a small manual feasibility test before running the full generation and
policy-evaluation experiment.

For the complete source-freezing, pipeline-change, generation, evaluation and reporting
procedure, use `EXPERIMENT_RUNBOOK.md`.

## Read these first

- `scope_assessment.md` explains which GDPR concepts are general and which are EU-specific.
- `sources.yaml` freezes the official legal and policy references.
- `requirements.yaml` records the ten sampled requirements and their portability tags.
- `gdpr_article13_sample.feature` contains the hand-authored reference Gherkins.
- `manual_comparison.md` contains the provisional human verdicts and evidence reasons.

## Why these versions

The historical policy is Git tag `2017-10-11`, before GDPR became applicable. GitHub's
official `2018-05-25` release says the update focused on bringing its policies into GDPR
alignment. The comparison policy is the current statement effective 27 April 2026, pinned
to commit `b9578b546d2506febda1da2cd7431644d58e512c` so later edits cannot silently alter
the experiment.

## Expected pilot result

The provisional manual oracle produces 5 gap closures out of 10 scenarios, alongside 4
stable satisfactions and 1 persistent gap. This is enough differential signal to justify
a full experiment.

## Reproducing the source material

Clone GitHub's official policy repository, then extract the two pinned blobs as UTF-8 text:

```powershell
git clone https://github.com/github/site-policy.git tmp/github-site-policy
git -C tmp/github-site-policy show 2017-10-11:Policies/github-privacy-statement.md |
  Set-Content -Encoding utf8 evaluation/gdpr_github/github_privacy_2017.txt
git -C tmp/github-site-policy show b9578b546d2506febda1da2cd7431644d58e512c:Policies/privacy-policies/github-general-privacy-statement.md |
  Set-Content -Encoding utf8 evaluation/gdpr_github/github_privacy_2026.txt
```

Then use the existing two-policy comparator:

```powershell
.\.venv-testgen\Scripts\python.exe -m evaluation.compare_policies `
  evaluation/gdpr_github/gdpr_article13_sample.feature `
  --policy historical=evaluation/gdpr_github/github_privacy_2017.txt `
  --policy current=evaluation/gdpr_github/github_privacy_2026.txt `
  --out-dir runs/gdpr_github/pilot
```

Compare every automated verdict with `manual_comparison.md`; disagreements are evaluation
errors to adjudicate, not reasons to silently change the human labels.
