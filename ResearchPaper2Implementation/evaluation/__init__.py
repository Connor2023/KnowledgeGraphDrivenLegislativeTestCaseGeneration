"""Measurement of what the pipeline produced. Not part of the pipeline.

Everything in here exists to produce the results section: the multi-arm experiment
harness, the element-coverage and soundness judges, the diversity statistics, and the
policy checker. None of it is needed to take a statute to a knowledge graph, or a graph
to a .feature file.

The separation is physical, not a convention. `kg_testgen` is the installable package
(see pyproject.toml, which lists it alone); this directory is deliberately not installed
and imports one way only -- evaluation may read the pipeline, never the reverse.
`tests/test_pipeline_isolation.py` fails if that ever stops being true.

Run these as modules from the repository root, so the relative paths they use for
`runs/`, `sections/` and `elements/` resolve:

    python -m evaluation.run_experiment
    python -m evaluation.score_elements --help
    python -m evaluation.score_soundness --help
    python -m evaluation.analyse_runs
    python -m evaluation.evaluate runs/final_6_1/generated.feature
"""

__all__ = []
