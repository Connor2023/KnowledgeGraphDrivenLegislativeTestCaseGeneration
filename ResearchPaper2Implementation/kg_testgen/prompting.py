"""Prompt assembly.

Four clearly delimited blocks: the task instruction, the verbatim target section, the
supplementary KG context, and the output format contract. The separation between blocks
2 and 3 is load-bearing -- the KG holds no source text, so retrieved triples come from
elsewhere in the legislation and must not be mistaken for the target section's content.
"""

from __future__ import annotations

from typing import Optional

SYSTEM_INSTRUCTION = """\
You derive compliance test cases from a section of privacy legislation.

The test cases are NOT executable software tests. Each one will be checked, by a person
reading a company's published privacy policy, to decide whether that policy satisfies
the legislative requirement. Every scenario you write must therefore be verifiable by
reading a privacy policy document and nothing else.

Write steps as assertions about what a privacy policy states, discloses, or commits to.
Never write steps describing user interface actions, API calls, button clicks, database
state, or any other software behaviour.

Three rules govern every Then step, because a scenario that breaks them cannot be
checked against a real policy and is worthless:

1. NEVER require the policy to cite, name or number a legislative provision. A company
   privacy policy will not say "Australian Privacy Principle 6", "subclause 6.2", "the
   Privacy Act" or "as required by Australian law". Test the SUBSTANCE the provision
   requires, not the provision's identity.

2. Write in the vocabulary a privacy policy actually uses -- "personal data", "collect",
   "share", "purposes", "retain", "access", "correct", "consent", "third parties",
   "transfer" -- rather than the statute's terms of art where the two differ.

3. Make each Then step ONE specific, self-contained claim that a reader can confirm or
   deny from the policy text alone. Never defer to unstated conditions.

   BAD:  Then the privacy policy states that the entity must not use the information for
         another purpose unless certain conditions are met
         (untestable: "certain conditions" names nothing)
   BAD:  Then the privacy policy explains when subclause 6.2 applies
         (untestable: no policy references Australian subclauses)
   GOOD: Then the privacy policy states that personal data collected for one purpose will
         not be used for an unrelated purpose without the individual's consent
         (a reader can confirm or deny this from the policy)

4. NEVER gesture at a condition instead of naming it. These phrasings are all banned,
   because each one hides the thing being tested:
      "where an exception applies"        "if permitted"
      "unless certain conditions are met" "as applicable"
      "one of the exceptions applies"     "unless otherwise permitted"
      "in certain circumstances"          "subject to conditions"
   Name the specific instrument, purpose, consent or circumstance every time.

5. State the legal consequence in the direction the provision actually runs. Read the
   condition, then ask what it PERMITS or REQUIRES — do not restate the condition as
   though it were the outcome.

   BAD:  Given it is impracticable to deal with individuals who have not identified
           themselves
         Then the privacy policy states the entity may deal with individuals who have
           not identified themselves
         (backwards: impracticability is what lets the entity REQUIRE identification)
   GOOD: Given it is impracticable to deal with individuals who have not identified
           themselves
         Then the privacy policy states that identification may be required where
           dealing anonymously is not practicable

COMPREHENSIVENESS

A provision that packs several alternatives into one sentence must be decomposed, not
summarised. Split into separate scenarios along EVERY one of these axes:

  * each alternative joined by "or" in a condition
  * each named instrument -- "an Australian law, or a court/tribunal order" is THREE
    (an Australian law, a court order, a tribunal order)
  * each modality verb -- "required or authorised" is TWO
  * each protected behaviour or right affected -- "anonymity or pseudonymity" is TWO
  * each combination where the alternatives can hold independently -- if one mode is
    impracticable while the other remains practicable, that is its own scenario

   BAD (one scenario collapsing six distinct conditions):
     Given the entity is required or authorised by Australian law or a court/tribunal
       order to deal with identified individuals
   GOOD (six scenarios, one per instrument x modality):
     Given an Australian law requires the entity to deal with identified individuals
     Given an Australian law authorises the entity to deal with identified individuals
     Given a court order requires the entity to deal with identified individuals
     ... and so on for court-authorises, tribunal-requires, tribunal-authorises

For every exception you write, ALSO write the scenario in which that exception does not
apply and the primary rule stands. An exception with no corresponding baseline case
leaves the main obligation untested.

There is no upper limit on the number of scenarios. A two-limb exception spanning three
instruments and two modalities warrants well more than two scenarios. Completeness
matters more than brevity: it is better to write two scenarios that differ only in which
instrument triggers them than to merge them into one that names neither.\
"""

OUTPUT_CONTRACT = """\
Produce a single valid Gherkin feature file.

Structure:
- Exactly one `Feature:` covering the target section.
- One `Scenario:` for each distinct obligation, prohibition, permission, condition or
  exception in the TARGET SECTION. Do not create scenarios for the supplementary
  context; use that context only to inform wording and to catch related requirements
  that the target section depends on.
- Every `Scenario:` must be preceded by a tag identifying which part of the target
  section it derives from, in the form `@{provision_tag}` plus a short obligation
  slug, for example `@{provision_tag} @notify-purpose-of-collection`.
- Immediately under each `Scenario:` line, add a comment line beginning `# Derives from:`
  quoting or closely paraphrasing the words of the target section it tests.

Step style:
- `Given` establishes the entity or circumstance the requirement applies to.
- `When` states the handling activity or the individual's request.
- `Then` asserts what the privacy policy must state, disclose or commit to, obeying the
  three rules above: no legislative citations, policy vocabulary, one checkable claim.

Before writing each scenario, ask yourself: "could a person holding only this company's
privacy policy decide whether this Then step is true?" If the answer is no, rewrite it.

When you have finished, re-read the target section once more and check that every named
instrument, every modality verb, every alternative joined by "or", and every right the
provision affects appears in at least one scenario — and that each exception has a
matching scenario for when it does not apply. Add any that are missing.

Output the Gherkin only. No markdown code fences, no commentary before or after.\
"""

TARGET_HEADER = """\
================================================================================
BLOCK 2 of 3 — TARGET SECTION (verbatim)
This is the legislation the test cases must be derived from. Write scenarios for THIS
text and only this text.
================================================================================\
"""

SPIRES_HEADER = """\
================================================================================
BLOCK 3 of 3 — STRUCTURED NORMS (NOT part of the target section)

Below is the target provision and the provisions connected to it, each broken into the
rule it states: its modality (MUST / MUST NOT / MAY), who it binds, the act it governs,
the conditions that trigger it, and the exceptions that switch it off.

Read the modality labels literally. APPLIES-WHEN provisions grant nothing on their own —
they supply the conditions under which an exception used by ANOTHER provision is met, so
satisfying one does not by itself make conduct lawful. DISAPPLIES provisions switch off
the provision they name.

Lines marked EXCEPT are the carve-outs. Write a separate scenario for each of them.
================================================================================
"""
# MEASURED AND REVERTED: an earlier version of this header forbade writing scenarios for
# the connected provisions and required every scenario to carry the target's tag. It
# worked on its own terms -- on-target rose from 39% to 100% -- and cost 28 points of
# cross-referenced element coverage (55% -> 27%), because those "off-target" scenarios
# were what covered elements 6.1-E13..E17 and 2.2-E01/E02 in the first place. Those
# elements ARE the content of the cross-referenced provisions, and the element
# decomposition scores content, not tags. See runs/spires_v2/ for the losing run.
# If the tags are ever worth fixing, fix ONLY the tag: do not suppress the scenarios.

NO_CONTEXT_NOTICE = """\
================================================================================
BLOCK 3 of 3 — SUPPLEMENTARY CONTEXT
No supplementary context was retrieved for this section. Derive the test cases from the
target section alone.
================================================================================\
"""


def provision_tag(provision_id: Optional[str]) -> str:
    """Tag stem identifying the source provision, for manual evaluation."""
    if not provision_id:
        return "section"
    return "s" + provision_id.strip().lower().replace("subclause", "").strip().replace(".", "-")


# Plausible alternative phrasings of the block 3 header, for measuring how much of an
# arm's score is the context and how much is the framing around it. Both are things a
# reasonable developer might have written; neither is adversarial. Sclar et al. (ICLR
# 2024) found up to 76 accuracy points of variation from formatting alone and argue for
# reporting a range over plausible formats rather than one number, which is the point of
# these: if an arm's spread across the three exceeds the gaps between arms, the gaps
# between arms are not measuring the arms.
TERSE_HEADER = """\
================================================================================
BLOCK 3 of 3 — SUPPLEMENTARY CONTEXT
================================================================================\
"""

NEUTRAL_HEADER = """\
================================================================================
BLOCK 3 of 3 — REFERENCE MATERIAL
The material below is provided for reference while writing the scenarios.
================================================================================\
"""


def _block3_header(context_mode: str, block3_format: str = "default") -> str:
    """The header for context the pipeline built, which is only ever the spires arm.

    The comparison arms carry their own headers -- see evaluation/arms/headers.py -- and
    pass them to build_prompt, because each arm's block 3 holds a different kind of thing
    and reusing one header would put a false claim in the prompt. The KG header asserts
    its statements come from other provisions, which is untrue of the pasted corpus (it
    includes the target) and of the RP1 graph (it has no provisions at all).

    TERSE and NEUTRAL stay here rather than moving with the arms, because they apply to
    the spires arm too: fmt-spires-terse and fmt-spires-neutral vary the framing over
    context this module's caller built. The non-default formats deliberately DO collapse
    the distinction between arms -- that is what they are measuring. They are not
    proposals, they are perturbations.
    """
    if block3_format == "terse":
        return TERSE_HEADER
    if block3_format == "neutral":
        return NEUTRAL_HEADER
    if context_mode == "spires":
        return SPIRES_HEADER
    return NO_CONTEXT_NOTICE


def build_prompt(section_text: str, context_block: Optional[str],
                 provision_id: Optional[str], context_mode: str = "spires",
                 block3_format: str = "default",
                 block3_header: Optional[str] = None) -> str:
    """Assemble the four-block prompt.

    The block 3 header differs by arm. The KG header asserts that its statements come
    from other provisions — true of retrieval, but false of the pasted corpus, which
    contains the target section as well. `block3_header` lets an evaluation arm supply
    its own; without it the pipeline picks the spires header, which is the only context
    it builds.
    """
    tag = provision_tag(provision_id)
    parts = [
        "================================================================================",
        "BLOCK 1 of 3 — TASK",
        "================================================================================",
        SYSTEM_INSTRUCTION,
        "",
        TARGET_HEADER,
        section_text.strip(),
        "",
        (block3_header or _block3_header(context_mode, block3_format))
        if context_block else NO_CONTEXT_NOTICE,
    ]
    if context_block:
        parts.append(context_block.strip())
    parts += [
        "",
        "================================================================================",
        "OUTPUT FORMAT",
        "================================================================================",
        OUTPUT_CONTRACT.format(provision_tag=tag),
    ]
    return "\n".join(parts)
