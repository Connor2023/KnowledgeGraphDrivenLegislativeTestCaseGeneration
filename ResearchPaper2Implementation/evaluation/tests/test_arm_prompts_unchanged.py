"""The comparison arms must still build exactly the prompts they built before.

Moving the arms out of the pipeline is a refactor, and the way a refactor of this kind
goes wrong is silently: a header drifts by a word, a block is assembled in a different
order, an arm quietly starts picking a different header, and every number the spires
results are quoted against shifts underneath them. Nothing would fail. The comparison
would simply stop meaning what it says.

So the check is replay rather than review. Every cell under `runs/experiment/` holds the
prompt that was actually sent. This reads each one back, pulls out the pieces it was
assembled from -- the section text from the run record, the block 3 body from the prompt
itself -- pushes them through the refactored assembly, and demands the result be
byte-identical to what is on disk.

It covers all thirteen arms, including the six format probes, because the probes are
where a header mix-up would be least visible.

Free: no API calls, no database, no network. It needs `runs/experiment/` to exist and
skips with a clear message if it does not, since runs/ is gitignored and a fresh
checkout will not have it.

    python tests/test_arm_prompts_unchanged.py
"""

from __future__ import annotations

import difflib
import glob
import io
import json
import os
import sys

# Three levels up: evaluation/tests -> evaluation -> the repository root. This test
# needs BOTH trees -- the pipeline's prompt assembly and evaluation's arm definitions --
# and it replays the recorded cells under runs/, which are the repository's, not
# evaluation's. pipeline/ goes on the path so corpus_config and kg_testgen resolve.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

RUNS = os.path.join(ROOT, "runs", "experiment")
RULE = "=" * 80

# Every arm the experiment defines. If a cell exists for an arm not in this list the
# test says so rather than quietly ignoring it.
EXPECTED_ARMS = 13


V1_CONTRACT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "fixtures", "prompt_contract_v1.json")


def _cells():
    return sorted(glob.glob(os.path.join(RUNS, "*__*__r*")))


def _v1_contract():
    """The instruction text these runs were actually sent.

    This test is about ASSEMBLY -- block order, header selection, how a provision key is
    rendered -- not about the wording of the instructions. Replaying against whatever the
    module currently says would conflate the two: a deliberate rewrite of the contract
    would fail here as though a header had drifted, and the only way to make it pass
    again would be to regenerate 117 cells and, with them, every number the results are
    quoted against.

    So the contract is pinned to what was in force when these runs were recorded. If the
    assembly changes, this still fails, which is the point.
    """
    from kg_testgen import prompting

    with io.open(V1_CONTRACT, encoding="utf-8") as fh:
        frozen = json.load(fh)
    return prompting.Contract(frozen["system_instruction_template"],
                              frozen["output_contract"])


def _replay(cell):
    """Rebuild one cell's prompt from its recorded parts. Returns (rebuilt, stored)."""
    import corpus_config
    from kg_testgen import prompting
    from evaluation import arms
    from evaluation.run_experiment import ARM_CONFIG

    record = json.load(io.open(os.path.join(cell, "run_record.json"), encoding="utf-8"))
    stored = io.open(os.path.join(cell, "prompt.txt"), encoding="utf-8",
                     newline="").read().replace("\r\n", "\n")

    arm = os.path.basename(cell).split("__")[1]
    config = ARM_CONFIG.get(arm)
    if config is None:
        raise AssertionError("cell %s names an arm the experiment does not define" % cell)
    mode = config.get("context_mode")
    fmt = config.get("block3_format", "default")
    section_text = record["input_section_text"]

    # The block 3 body sits between the header's closing rule and the rule that opens
    # OUTPUT FORMAT. Taking it from the prompt rather than rebuilding it is deliberate:
    # this test is about assembly and header selection, not about whether retrieval is
    # reproducible -- seeding calls an LLM and is not.
    marker = stored.find("BLOCK 3 of 3")
    body_start = stored.find(RULE, stored.find("\n", marker)) + len(RULE)
    tail = stored.find("OUTPUT FORMAT")
    body_end = stored.rfind(RULE, body_start, tail)
    context_block = stored[body_start:body_end].strip() or None

    # Same fallback chain the pipeline uses, in the same order.
    provision_id = ((record.get("spires_context") or {}).get("target_provision")
                    or (record.get("seeding") or {}).get("provision_id")
                    or corpus_config.detect_provision_id(section_text))

    header = arms.block3_header(mode, fmt) if mode in arms.ARM_MODES else None
    rebuilt = prompting.build_prompt(section_text, context_block, provision_id,
                                     context_mode=mode, block3_format=fmt,
                                     block3_header=header, contract=_v1_contract())
    return rebuilt.strip(), stored.strip()


def test_every_recorded_prompt_is_reproduced():
    cells = _cells()
    if not cells:
        print("  SKIP  no runs/experiment/ in this checkout")
        return
    bad = []
    for cell in cells:
        if not os.path.exists(os.path.join(cell, "prompt.txt")):
            continue
        rebuilt, stored = _replay(cell)
        if rebuilt != stored:
            bad.append((cell, rebuilt, stored))
    if bad:
        cell, rebuilt, stored = bad[0]
        diff = "\n".join(list(difflib.unified_diff(
            stored.split("\n"), rebuilt.split("\n"), "stored", "rebuilt", lineterm=""))[:24])
        raise AssertionError(
            "%d of %d prompts changed. First: %s\n%s" % (len(bad), len(cells), cell, diff))


def test_replay_still_detects_assembly_drift():
    """Pinning the contract must not have turned the replay into a no-op.

    The risk in fixing the contract is that the comparison stops depending on the code
    under test. It still does: with the contract held constant, changing what the
    assembly is given changes the prompt. If this passes while the replay above fails,
    the failure is real drift; if this fails, the guard has stopped guarding.
    """
    from kg_testgen import prompting

    v1 = _v1_contract()
    base = prompting.build_prompt("6.1 text", "some context", "6.1",
                                  context_mode="spires", contract=v1)
    other_header = prompting.build_prompt("6.1 text", "some context", "6.1",
                                          context_mode="spires",
                                          block3_header="DIFFERENT HEADER", contract=v1)
    other_tag = prompting.build_prompt("6.1 text", "some context", "11.2",
                                       context_mode="spires", contract=v1)
    assert base != other_header, "block 3 header no longer reaches the prompt"
    assert base != other_tag, "provision tag no longer reaches the prompt"

    # And the pin is load-bearing: the live contract has moved away from v1, so an
    # unpinned replay would now be comparing against text these runs never saw.
    assert prompting.CURRENT.fingerprint != v1.fingerprint, \
        "live contract equals v1 -- either the pin is unnecessary or the fixture is stale"


def test_every_arm_is_covered():
    """A replay that silently covered only two arms would prove very little."""
    cells = _cells()
    if not cells:
        print("  SKIP  no runs/experiment/ in this checkout")
        return
    arms_seen = {os.path.basename(c).split("__")[1] for c in cells}
    assert len(arms_seen) == EXPECTED_ARMS, \
        "expected %d arms, replayed %d: %s" % (EXPECTED_ARMS, len(arms_seen), sorted(arms_seen))


def test_spires_context_is_reproduced():
    """The replay above cannot catch this, so it is checked separately.

    test_every_recorded_prompt_is_reproduced takes block 3 out of the stored prompt
    rather than rebuilding it, because seeding calls an LLM and is not reproducible. That
    makes it blind to a change in how the spires arm serialises -- which is exactly what
    replacing the hard-coded "subclause %s" strings with corpus_config.provision_key
    touches. This rebuilds the context against the live graph and demands the same bytes.

    Needs Neo4j. Skips with a message when no credentials can be found.

    A .env counts. Gating on os.environ alone made this skip silently on exactly the
    setup the runbook now recommends -- credentials in .env rather than dot-sourced into
    a shell -- so the one check that can catch a serialisation change was quietly not
    running for anyone following the documented instructions.
    """
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    if not os.environ.get("NEO4J_URI"):
        print("  SKIP  no Neo4j credentials in the environment or .env")
        return
    from kg_testgen.config import Config, secrets_from_env
    from kg_testgen.neo4j_client import GraphUnavailable, Neo4jClient
    from kg_testgen import spires_query

    # An unreachable instance is an environment condition, not a regression in the code
    # under test. Aura free-tier instances pause after inactivity and lose their DNS
    # record, which is a normal resting state for this project -- failing the whole suite
    # for it would train the reader to ignore a red suite. Skipping loudly is the right
    # answer; a serialisation change simply goes unchecked until the instance is resumed.
    secrets = secrets_from_env()
    differing = []
    for cell, hybrid in (("line34__spires__r1", False), ("line49__spires__r1", False),
                         ("line60__spires__r1", False), ("line60__spires-hybrid__r1", True)):
        directory = os.path.join(RUNS, cell)
        if not os.path.exists(directory):
            continue
        record = json.load(io.open(os.path.join(directory, "run_record.json"), encoding="utf-8"))
        stored = io.open(os.path.join(directory, "prompt.txt"), encoding="utf-8",
                         newline="").read().replace("\r\n", "\n")
        marker = stored.find("BLOCK 3 of 3")
        body_start = stored.find(RULE, stored.find("\n", marker)) + len(RULE)
        tail = stored.find("OUTPUT FORMAT")
        stored_block = stored[body_start:stored.rfind(RULE, body_start, tail)].strip()

        config = Config(context_mode="spires", spires_include_provision_text=hybrid)
        config.validate()
        try:
            with Neo4jClient(secrets, config) as client:
                rebuilt = spires_query.build_context(client, record["input_section_text"],
                                                     config)
        except GraphUnavailable as exc:
            print("  SKIP  Neo4j unreachable (%s)"
                  % str(exc).splitlines()[0].rstrip("."))
            return
        if rebuilt.text.strip() != stored_block:
            differing.append(cell)
    assert not differing, "spires context changed for: %s" % differing


def test_pipeline_refuses_arm_modes_it_no_longer_builds():
    """Asking the pipeline for a moved arm must fail loudly, not return no context."""
    from kg_testgen.config import Config
    from kg_testgen.errors import ContextError
    from kg_testgen.pipeline import run

    for mode in ("kg", "rp1", "full-corpus", "none"):
        config = Config(context_mode=mode)
        try:
            run("6.1 An APP entity must not use the information.", config, secrets=None)
        except ContextError as exc:
            assert "evaluation/arms" in str(exc), \
                "the error for %r should point at where the arm went: %s" % (mode, exc)
        else:
            raise AssertionError("context_mode=%r was accepted by the pipeline" % mode)


def main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("  PASS  %s" % name)
        except AssertionError as exc:
            failed += 1
            print("  FAIL  %s\n        %s" % (name, exc))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("  ERROR %s\n        %s: %s" % (name, type(exc).__name__, exc))
    print("\n%d/%d passed" % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
