"""The pipeline must not depend on the code that measures it.

`kg_testgen` is the proposed artefact: statute in, knowledge graph out, Gherkin out. The
judges, the coverage scorer, the diversity statistics and the multi-arm harness exist to
produce a results section and are not part of what is being proposed. Keeping them apart
matters for two reasons: an installed pipeline should not be able to spend API credits on
scoring, and a reader should be able to see the boundary rather than take it on trust.

The boundary is one-directional. `evaluation` imports `kg_testgen` freely -- it has to,
since it runs the pipeline it measures. The reverse is a defect.

This is a static check: it parses the import statements rather than importing anything,
so it runs in any of the three virtualenvs and does not need neo4j, openai or a network.

    python tests/test_pipeline_isolation.py     # standalone, prints a report
    pytest tests/test_pipeline_isolation.py     # also works, if pytest is installed
"""

from __future__ import annotations

import ast
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE_PKG = "kg_testgen"
EVALUATION_PKG = "evaluation"

# Modules that were moved out of kg_testgen when the boundary was drawn. Re-adding one
# under its old name is the most likely way for this to regress, and an import-based
# check would not notice because the name would resolve again.
#
# The first four are the judges and the harness. The rest are the comparison arms: the
# EDC triple pipeline (seeding, retrieval, ranking, serialisation, the EDC bridge and the
# provision-text fetch it uses) and the RP1 concept graph. The pipeline builds one context
# mode, `spires`, and everything these implement is measured against it.
MOVED_OUT = ("evaluate", "evaluation", "policy_check", "gherkin",
             "seeding", "retrieval", "ranking", "serialisation", "edc_bridge",
             "rp1_query", "provision_text")

# Third-party packages that only make sense on the measurement side. `openai` is not
# here: the pipeline legitimately calls an LLM to extract norms and to generate Gherkin.
# `transformers`, `torch` and `edc` come in through the EDC bridge, which only the `kg`
# control arm uses -- installing the pipeline should not install a sentence-transformer
# stack to run an arm the pipeline does not have.
EVALUATION_ONLY_DEPS = ("docx", "transformers", "torch", "edc", "sentence_transformers")


def _module_files(package: str):
    directory = os.path.join(ROOT, package)
    for name in sorted(os.listdir(directory)):
        if name.endswith(".py"):
            yield name, os.path.join(directory, name)


def _imported_roots(path: str):
    """Every top-level module name this file imports, as (name, lineno) pairs.

    Relative imports are ignored: `from .config import X` inside kg_testgen cannot reach
    outside the package, so it is never the thing this test is looking for.
    """
    with io.open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0], node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level:                      # relative -- stays inside the package
                continue
            if node.module:
                yield node.module.split(".")[0], node.lineno


def check():
    problems = []

    for name, path in _module_files(PIPELINE_PKG):
        for root, lineno in _imported_roots(path):
            if root == EVALUATION_PKG:
                problems.append(
                    "%s/%s:%d imports %r -- the pipeline must not depend on the code "
                    "that measures it" % (PIPELINE_PKG, name, lineno, root))
            if root in EVALUATION_ONLY_DEPS:
                problems.append(
                    "%s/%s:%d imports %r, which only the measurement side needs"
                    % (PIPELINE_PKG, name, lineno, root))

    present = {name[:-3] for name, _ in _module_files(PIPELINE_PKG)}
    for name in MOVED_OUT:
        if name in present:
            problems.append(
                "%s/%s.py exists again -- it belongs in %s/"
                % (PIPELINE_PKG, name, EVALUATION_PKG))

    # The installable package is the other half of the guarantee: `pip install .` must
    # not ship the judges or the arms. Read the `packages = [...]` declaration, since that
    # is what setuptools acts on -- an earlier version scanned the whole file and fired on
    # a comment explaining why numpy had been removed.
    pyproject = os.path.join(ROOT, "pyproject.toml")
    if os.path.exists(pyproject):
        with io.open(pyproject, encoding="utf-8") as fh:
            text = fh.read()
        match = re.search(r"^packages\s*=\s*\[([^\]]*)\]", text, re.M)
        if match is None:
            problems.append(
                "pyproject.toml has no explicit packages list, so setuptools may "
                "auto-discover and ship %r" % EVALUATION_PKG)
        elif EVALUATION_PKG in match.group(1):
            problems.append(
                "pyproject.toml declares %r as an installable package -- it must stay "
                "uninstalled" % EVALUATION_PKG)

    return problems


def test_pipeline_does_not_import_evaluation():
    problems = check()
    assert not problems, "\n".join(problems)


def main():
    problems = check()
    if problems:
        print("FAIL: the pipeline/evaluation boundary has been crossed\n")
        for p in problems:
            print("  " + p)
        return 1
    n = len(list(_module_files(PIPELINE_PKG)))
    print("OK: %d modules in %s/, none importing %s/" % (n, PIPELINE_PKG, EVALUATION_PKG))
    return 0


if __name__ == "__main__":
    sys.exit(main())
