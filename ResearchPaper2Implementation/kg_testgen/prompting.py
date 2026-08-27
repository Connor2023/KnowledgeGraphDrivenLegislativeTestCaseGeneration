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
state, or any other software behaviour.\
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
- `Then` asserts what the privacy policy must state, disclose or commit to.

Output the Gherkin only. No markdown code fences, no commentary before or after.\
"""

TARGET_HEADER = """\
================================================================================
BLOCK 2 of 3 — TARGET SECTION (verbatim)
This is the legislation the test cases must be derived from. Write scenarios for THIS
text and only this text.
================================================================================\
"""

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


def build_prompt(section_text: str, context_block: Optional[str],
                 provision_id: Optional[str]) -> str:
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
        CONTEXT_HEADER if context_block else NO_CONTEXT_NOTICE,
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
