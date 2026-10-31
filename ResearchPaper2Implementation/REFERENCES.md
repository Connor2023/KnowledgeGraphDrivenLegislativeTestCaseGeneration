# References

Every work this pipeline stands on, and where in the code it does its work.

Two conventions, because the difference matters when these go into a bibliography:

- **[verified]** — the full reference was checked against the publisher or the project's
  own citation guidance while writing this file.
- **[unverified]** — the code names the work (author and venue), and the fuller detail
  here is an identification that has *not* been checked against the paper. Confirm each
  one before it reaches a reference list.

---

## 1. Methods the pipeline executes

These run on every build. They are not background reading.

### SPIRES — the extraction method **[verified]**

> Caufield, J.H., Hegde, H., Emonet, V., Harris, N.L., Joachimiak, M.P., Matentzoglu, N.,
> Kim, H., Moxon, S., Reese, J.T., Haendel, M.A., Robinson, P.N., and Mungall, C.J.
> "Structured Prompt Interrogation and Recursive Extraction of Semantics (SPIRES): a
> method for populating knowledge bases using zero-shot learning."
> *Bioinformatics* 40(3), btae104, 2024. doi:10.1093/bioinformatics/btae104
> Preprint: arXiv:2304.02711

Populates a knowledge base by interrogating an LLM against a user-defined schema,
recursing into each nested slot the schema declares rather than asking for a whole
structure in one call. Implemented in OntoGPT.

**Everything this pipeline ships is SPIRES output** — 146 norms for Schedule 1, 202 for
Part IIIC. Its schema-as-prompt design is why the `description:` fields in
`pipeline/spires/norm.yaml` read as instructions rather than documentation: they are
sent to the model verbatim. Its recursion — a root call plus one per
`CompoundExpression` slot — is why extraction costs more than one call per provision,
and why cost tracks provision count rather than corpus size.

*Do not repeat the "the whole schema is resent with every call" claim without checking
it.* Measured here, the recorded root prompts average 223 tokens across Part IIIC's 106
provisions, against a 2,373-token schema file — SPIRES sends the slot descriptions of the
class being extracted, not the file. The cost estimator assumes otherwise and still lands
near the measured spend, so its breakdown is not established even though its total is
calibrated. See the note in `pipeline/spires/extract_corpus.py`.

The OntoGPT project asks that this paper be cited for the software as well; it gives no
separate citation for the tool.

*Adaptation worth claiming:* SPIRES was built for biomedical text and grounds matched
terms against ontologies. There is no ontology to ground legislative actors or acts
against, so the `NamedEntity` slots carry no `annotators` and the hand-written deontic
schema does the work alone.

Used in: `pipeline/spires/extract_corpus.py` · `.venv-ontogpt` (ontogpt 1.1.1)

### LinkML — the schema language **[verified]**

> Moxon, S.A.T., Solbrig, H., Harris, N.L., Kalita, P., Miller, M.A., Patil, S.,
> Schaper, K., Bizon, C., Caufield, J.H., et al. "LinkML: an open data modeling
> framework." *GigaScience* 15, giaf152, 2026. doi:10.1093/gigascience/giaf152

The earlier conference paper, if a 2021 reference is wanted instead:

> Moxon, S.T., Solbrig, H.R., Unni, D.R., Jiao, D., Bruskiewich, R.M., Balhoff, J.P.,
> Vaidya, G., Duncan, W.D., Hegde, H.B., Miller, M., Brush, M.H., Harris, N.L.,
> Haendel, M.A., and Mungall, C.J. "The Linked Data Modeling Language (LinkML): A
> General-Purpose Data Modeling Framework Grounded in Machine-Readable Semantics."
> *International Conference on Biomedical Ontology (ICBO)*, CEUR-WS Vol-3073, 2021.

The YAML modelling language `pipeline/spires/norm.yaml` is written in. Its
`CompoundExpression` / `NamedEntity` distinction is load-bearing rather than
presentational: `Norm`, `Condition` and `Exemption` are compound and each gets its own
extraction call, while `Actor`, `Action` and `InformationType` are named entities and do
not.

Used in: `pipeline/spires/norm.yaml` · `.venv-ontogpt` (linkml 1.11.1)

### Gherkin — the output syntax **[specification, not a paper]**

> Gherkin Reference, Cucumber documentation. https://cucumber.io/docs/gherkin/reference/

There is no canonical paper; cite the specification.

The borrowing is deliberate but unorthodox and the write-up should say so early: these
scenarios are **not executable**. A `Then` step asserts what a published privacy policy
states — a claim about a document, not about a running system — so nothing here can be
handed to Cucumber and run. What the syntax buys is the decomposition: one circumstance,
one trigger, one checkable consequence.

Used in: `pipeline/kg_testgen/prompting.py`
Checked by: `pipeline/kg_testgen/llm.py check_gherkin_structure`

---

## 2. Foundations

### EDC — Extract, Define, Canonicalize **[verified from the paper in this repo]**

> Zhang, B., and Soh, H. "Extract, Define, Canonicalize: An LLM-based Framework for
> Knowledge Graph Construction." *Proceedings of the 2024 Conference on Empirical Methods
> in Natural Language Processing (EMNLP)*, pp. 9820–9836, 2024. arXiv:2404.03868

A three-phase framework — open information extraction, schema definition, post-hoc
canonicalization — that builds a KG with or without a predefined target schema.

The original construction pipeline here, and the source of the `kg` and `kg-text-only`
comparison arms the SPIRES results are quoted against. This implementation documented
three of its limits from the outside: no entity-mention canonicalization (which its
authors state), the enriched schema is held in memory and never written out, and its
dependency pins could not be reproduced on Windows.

*Worth engaging with directly:* EDC's motivating claim is that putting the schema in the
prompt does not scale. This project bears on that claim but does not settle it, and the
distinction matters. Cost here tracks provision count rather than corpus size, which is
consistent with EDC's premise — but the mechanism is SPIRES' recursion, not schema bulk:
the measured root prompt is 223 tokens, not the 2,373-token schema file. So this is
evidence that per-provision schema-driven extraction is expensive, not evidence that a
large schema in the prompt is what makes it expensive. Claiming the latter would overstate
what was measured.

Used in: `evaluation/edc/edc-main/` · `evaluation/arms/edc_bridge.py`
Written up in: `docs/KG_Construction_Report.docx`
PDF: `docs/2024.emnlp-main.548.pdf`

### SPECMATE **[verified from the paper's cover page]**

> Fischbach, J., Vogelsang, A., Junker, M., et al. "SPECMATE: Automated Creation of Test
> Cases from Acceptance Criteria." *IEEE International Conference on Software Testing,
> Verification and Validation (ICST)*, 2020. doi:10.1109/ICST46399.2020.00040

Recovers the cause–effect structure of a natural-language acceptance criterion and
generates a minimal test set from it.

The precedent for the output half of this pipeline. A statutory provision substitutes for
an acceptance criterion and a privacy policy for a system under test, but the
decomposition-then-generate shape is the same — and the conditions / exemptions split in
`pipeline/spires/norm.yaml` is recognisably the same move.

PDF: `../Literature/SPECMATE-Automated-Creation-of-Test-Cases-from-Acceptance-Criteria.pdf`

### RAGcceptance M2RE **[authors verified from the paper; VENUE AND YEAR NOT VERIFIED]**

> Wang, F., Arora, C., Liu, Y., Huang, K., Tantithamthavorn, C., Aleti, A. (Monash
> University), Sambathkumar, D. (Monash eSolutions), and Lo, D. (Singapore Management
> University). "Multi-Modal Requirements Data-based Acceptance Criteria Generation using
> LLMs."

Generates acceptance criteria from multi-modal requirements — text plus visual UI
information — using retrieval-augmented generation, evaluated in an industrial case study
on a system with roughly 100,000 users.

The RAG-over-a-structured-source pattern the generation half implements, and the source
of its evaluation vocabulary: relevance, correctness and comprehensibility as separate
axes is the same instinct as the split between element coverage and soundness here.

**The venue and year are not printed on the copy in `Literature/`. Establish both before
citing.**

PDF: `../Literature/RAGcceptanceM2RE.pdf`

---

## 3. Evaluation methodology

All of these are already cited inline at the point where they are applied. The shorthand
below is what the code says; the fuller detail is **[unverified]** identification.

| Work | As the code cites it | What it contributes | Applied in |
|---|---|---|---|
| BLEU | Papineni et al., ACL 2002 | N-gram precision; the base measure self-BLEU is built from | `evaluation/analyse_runs.py` `sentence_bleu()` |
| BLEU smoothing | Chen & Cherry, method 2 | Scenarios run to a few dozen tokens, so one unmatched 4-gram sends unsmoothed sentence-BLEU to zero and every cell reads as maximally diverse | `evaluation/analyse_runs.py` `sentence_bleu()` |
| Self-BLEU | Zhu et al., SIGIR 2018 | Whether an 11-scenario run is eleven tests or five paraphrased — the check that stops scenario count masquerading as coverage | `evaluation/analyse_runs.py` `self_bleu()` |
| distinct-n | Li et al., NAACL 2016 | Vocabulary-level diversity alongside phrasing-level self-BLEU | `evaluation/analyse_runs.py` `distinct_n()` |
| G-Eval | Liu et al., EMNLP 2023 | Licenses LLM-as-judge and documents its self-preference bias; both mitigations here (`--judge-model`, `--sample-for-human` with Cohen's κ) come from it | `evaluation/score_elements.py`, `evaluation/score_soundness.py` |
| Prompt format sensitivity | Sclar et al., ICLR 2024 | Justifies the six format probes — whether the gaps between arms survive plausible rephrasing of the framing | `evaluation/arms/`, `pipeline/kg_testgen/prompting.py` |
| Non-determinism at temperature 0 | Ouyang et al., arXiv:2308.02828 | Why the experiment runs repeats and reports a mean; one run's count is a sample, not a measurement | `evaluation/run_experiment.py` |
| Privacy-policy completeness | Amaral et al., IEEE TSE 2022 | Completeness and correctness as separate measures — why `evaluation/score_soundness.py` exists at all | `evaluation/score_soundness.py` |
| Relevance vs completeness | Hassani et al., IST 2026 | Rating Relevance apart from Completeness | `evaluation/score_soundness.py` |
| Perturbation checklists | Sai et al., EMNLP 2021 | The known-answer controls that check each judge before a full run is paid for | `evaluation/score_soundness.py` `SELF_TEST` |
| Fault classes | Basili & Selby, IEEE TSE 1987 | Testing techniques differ by fault *class*, not only count — why unsound scenarios are broken down by class rather than reported as a rate | `evaluation/score_soundness.py` report |

`Hassani et al., IST 2026` could not be identified at all when this file was written.
Check the volume and pages with particular care.

---

## 4. Primary sources

- **Privacy Act 1988 (Cth), Schedule 1** — the Australian Privacy Principles. 62
  provisions; the primary corpus and the source of the element decomposition in
  `evaluation/ground_truth/elements/legal_elements.yaml`.
- **Privacy Act 1988 (Cth), Part IIIC** — notification of eligible data breaches. 106
  provisions; the second corpus, and the instrument that tested whether the pipeline
  generalised beyond the one it was built on.
- **Microsoft Privacy Statement (2016)** — the policy the generated scenarios are judged
  against in `evaluation/evaluate.py`.

---

## 5. Unresolved

The `rp1` comparison arm serialises a 21-entity, 31-triple concept graph loaded from
`../ResearchPaper1/output.json`. **Nothing in either repository records which paper that
implements.** It needs attributing before it can be described as a baseline.

Used in: `evaluation/arms/rp1_query.py` · `../ResearchPaper1/load_rp1_kg.py`
