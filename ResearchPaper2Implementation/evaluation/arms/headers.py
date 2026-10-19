"""Block 3 headers for the comparison arms.

Each arm's block 3 holds a different kind of thing, so each states its own terms. Reusing
one header would put a false claim in the prompt: the KG header asserts the statements
come from other provisions, which is untrue of the pasted corpus (it includes the target)
and of the RP1 graph (it has no provisions at all).

These moved out of kg_testgen.prompting with the arms they belong to. **They are
byte-identical to what produced the recorded results and must stay that way.** Improving
a control's header would change what the spires numbers are quoted against, which is a
silent way to manufacture a result.

The two perturbation formats are imported from the pipeline rather than copied, because
they apply to the spires arm too: fmt-spires-terse and fmt-spires-neutral vary the header
over context the pipeline builds.
"""

from __future__ import annotations

from kg_testgen.prompting import NEUTRAL_HEADER, NO_CONTEXT_NOTICE, TERSE_HEADER

CONTEXT_HEADER = """\
================================================================================
BLOCK 3 of 3 — SUPPLEMENTARY CONTEXT (NOT part of the target section)
The statements below were retrieved from a knowledge graph built over the wider
legislation. They come from OTHER provisions, not from the target section above.

Use them only to understand how the target section's concepts connect to the rest of
the legislation. Do NOT write scenarios testing these statements. Do NOT treat them as
text of the target section.
================================================================================\
"""

RP1_HEADER = """\
================================================================================
BLOCK 3 of 3 — BACKGROUND CONCEPT GRAPH (NOT part of the target section)
Below is a concept graph built from a separate analysis of this legislation. It defines
the terms the target section uses and records how they relate to one another.

It contains NO provision references and NO statutory text, so nothing in it can be
cited. Use it to understand what the target section's terms mean. Write scenarios for
the TARGET SECTION in Block 2 only.
================================================================================\
"""

# "The complete Schedule" is Schedule 1's wording and does not generalise. It is left
# exactly as it was: this header produced the full-corpus results the spires arm is
# compared against, and rewording it would change the control.
FULL_CORPUS_HEADER = """\
================================================================================
BLOCK 3 of 3 — FULL LEGISLATION TEXT
The complete Schedule is reproduced below, one provision per line. It INCLUDES the
target section shown above, alongside every other provision in the instrument.

Use it to understand how the target section relates to the rest of the legislation.
Write scenarios for the TARGET SECTION in Block 2 only — not for the other provisions.
================================================================================\
"""


def for_mode(context_mode: str, block3_format: str = "default") -> str:
    """The header an arm's block 3 carries.

    The non-default formats deliberately collapse the distinction between arms -- that is
    what they are measuring. They are not proposals, they are perturbations.
    """
    if block3_format == "terse":
        return TERSE_HEADER
    if block3_format == "neutral":
        return NEUTRAL_HEADER
    if context_mode == "none":
        return NO_CONTEXT_NOTICE
    return {
        "full-corpus": FULL_CORPUS_HEADER,
        "rp1": RP1_HEADER,
    }.get(context_mode, CONTEXT_HEADER)
