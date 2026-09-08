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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

RUNS = os.path.join(ROOT, "runs", "experiment")
RULE = "=" * 80

# Every arm the experiment defines. If a cell exists for an arm not in this list the
# test says so rather than quietly ignoring it.
EXPECTED_ARMS = 13


def _cells():
    return sorted(glob.glob(os.path.join(RUNS, "*__*__r*")))


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
                                     block3_header=header)
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


def test_every_arm_is_covered():
    """A replay that silently covered only two arms would prove very little."""
    cells = _cells()
    if not cells:
        print("  SKIP  no runs/experiment/ in this checkout")
        return
    arms_seen = {os.path.basename(c).split("__")[1] for c in cells}
    assert len(arms_seen) == EXPECTED_ARMS, \
        "expected %d arms, replayed %d: %s" % (EXPECTED_ARMS, len(arms_seen), sorted(arms_seen))


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
