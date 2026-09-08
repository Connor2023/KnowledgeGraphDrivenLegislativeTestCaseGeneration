"""Stage 0: learn a statute's structure from the statute, so a new corpus is a .txt file.

The pipeline was coupled to Schedule 1 in seven places, and the worst of them was the
structural parser: `prep_app.py` knows that an Australian Privacy Principle is announced
by "N Australian Privacy Principle N-title" and that clauses are numbered "N.M". Nothing
about that transfers. Part IIIC numbers sections "26WE", nests subsections "(1)" inside
them, and marks divisions with an em dash.

Writing a parser per statute is the obvious answer and the wrong one. The extraction step
already spends an LLM call on every provision -- roughly $1.40 for a Part the size of
IIIC -- so spending ONE more call on the whole document to learn its shape costs about
$0.02, which is noise. That call replaces the parser.

A model asked for regexes will confidently return regexes that are wrong, so the call is
only half the design. The other half is `validate()`, which runs the induced profile over
the whole file and checks it mechanically:

    orphan rate       lines that reached no provision -- the signature of a missed pattern
    provision count   not 1, not one per line
    unique ids        a numbering scheme that collides is not the numbering scheme
    largest share     one provision holding a quarter of the text means under-segmentation
    empty provisions  an id with no words under it

None of those need a human or a second model. A profile that fails is retried once with
the failure report appended to the prompt; a profile that fails twice stops the run and
names the pattern that did not match, because an empty graph discovered three stages
later is the expensive outcome this is meant to prevent.

The same methodology as the soundness judge: do not trust the model, check it against
something that cannot lie.

    python induce_structure.py APPartIIIC.txt --dry-run      # prompt size and cost, no call
    python induce_structure.py APPartIIIC.txt --profile profiles/part_iiic.yaml
                                                             # validate a written profile, no call
    python induce_structure.py APPartIIIC.txt                # induce, validate, write the profile
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional

try:
    import truststore  # noqa: F401  - routes TLS through the Windows cert store
    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001 - absent outside the proxied environment
    pass

ENV_LLM_KEY_PRIMARY = "OPENAI_API_KEY"
ENV_LLM_KEY_FALLBACK = "OPENAI_KEY"

# gpt-4o list price, USD per 1M tokens.
PRICE_IN, PRICE_OUT = 2.50, 10.00

# A line class is one of these. `heading` closes whatever provision is open and belongs
# to none; `container` opens an identifier namespace and may become a provision itself if
# nothing below it does; `provision` is the unit the graph is keyed on; `body` continues
# the open provision.
ROLES = ("heading", "container", "provision", "body")

# Legislative drafting has a closed vocabulary for citations. This is not per-statute and
# is not asked of the model -- it is only offered, so an instrument using a subset says so.
CITATION_NOUNS = ("section", "subsection", "paragraph", "subparagraph", "clause",
                  "subclause", "article", "regulation", "schedule", "division", "part",
                  "item", "rule")

# --- thresholds --------------------------------------------------------------------
# Calibrated against the hand-written Schedule 1 parser, whose output is known: 62
# provisions from 337 non-blank lines, no orphans. They are deliberately loose -- this is
# a smoke alarm for "the regexes did not match", not a quality score.
MAX_ORPHAN_RATE = 0.10
MIN_PROVISIONS = 5
MAX_LARGEST_SHARE = 0.25
MAX_PATTERN_HIT_RATE = 0.60      # a line class matching most of the file classifies nothing
MIN_PROVISION_WORDS = 8          # below this a "provision" is a sub-heading, not a rule


def normalise(text: str) -> str:
    """Fold the typographic characters legislation is published with into plain ASCII.

    Shared with prep_app.normalise deliberately: a pattern induced against text that has
    been through this must be applied to text that has been through this, or an em dash
    in the pattern will not meet the em dash in the file.
    """
    text = text.replace("‑", "-")                              # non-breaking hyphen
    text = text.replace("—", " - ").replace("–", "-")     # em / en dash
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


# --- pre-flight --------------------------------------------------------------------

@dataclass
class Hygiene:
    """What the input file looks like before anything tries to parse it.

    The likeliest failure of this whole design is not an exotic statute, it is a .txt
    extracted from a PDF: wrapped lines, running headers, page numbers. No line
    classifier survives that, induced or hand-written, so it is worth naming up front
    rather than debugging as a coverage failure three steps later.
    """
    lines: int
    non_blank: int
    mean_words: float
    short_line_rate: float          # lines under 5 words: headings, or PDF wrap damage
    repeated_lines: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def hygiene(raw_lines: List[str]) -> Hygiene:
    non_blank = [l for l in raw_lines if l.strip()]
    words = [len(l.split()) for l in non_blank] or [0]
    mean_words = sum(words) / float(len(words))
    short = sum(1 for w in words if w < 5) / float(len(words))

    counts: Dict[str, int] = {}
    for line in non_blank:
        key = normalise(line)
        if 0 < len(key) < 80:
            counts[key] = counts.get(key, 0) + 1
    repeated = sorted((k for k, v in counts.items() if v >= 5), key=lambda k: -counts[k])

    h = Hygiene(len(raw_lines), len(non_blank), mean_words, short, repeated[:10])
    if mean_words < 8:
        h.warnings.append(
            "mean line length is %.1f words -- this looks like wrapped PDF text, where "
            "one sentence spans several lines. Line-based classification will not work "
            "on it. Re-extract with layout preserved, or unwrap first." % mean_words)
    if short > 0.5:
        h.warnings.append(
            "%.0f%% of non-blank lines are under 5 words. Expect headings to be "
            "indistinguishable from fragments." % (100 * short))
    if repeated:
        h.warnings.append(
            "%d line(s) repeat 5+ times, e.g. %r -- running headers or page furniture. "
            "Strip them before inducing, or they will be classified as structure."
            % (len(repeated), repeated[0][:60]))
    return h


# --- the profile -------------------------------------------------------------------

@dataclass
class Level:
    name: str
    role: str
    pattern: str
    regex: Optional[re.Pattern] = None


@dataclass
class Profile:
    """The structural description of one instrument. This is the contract.

    Everything downstream -- segmentation here, and the generic prep_corpus that replaces
    prep_app -- reads this and nothing else. It is written to profiles/<name>.yaml so that
    an induction that got something slightly wrong can be corrected by hand without
    touching code, and so that what was induced is auditable rather than implicit.

    Not yet wired into corpus.yaml: this is stage 0, and the generic prep_corpus that
    consumes a profile is the next step. `segment()` below is that consumer in embryo --
    it is the whole of what prep_app.py's line classification does, driven by data.
    """
    name: str
    description: str
    levels: List[Level]
    id_template: str                     # "{section}({subsection})" or "{clause}"
    citation_nouns: List[str] = field(default_factory=list)
    note_pattern: Optional[str] = None
    min_provision_words: int = MIN_PROVISION_WORDS

    @property
    def provision_level(self) -> Optional[Level]:
        for lv in self.levels:
            if lv.role == "provision":
                return lv
        return None

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        levels = [Level(name=str(l["name"]), role=str(l["role"]), pattern=str(l["pattern"]))
                  for l in d.get("levels", [])]
        return cls(
            name=str(d.get("name", "corpus")),
            description=str(d.get("description", "")),
            levels=levels,
            id_template=str(d.get("id_template", "")),
            citation_nouns=[str(x) for x in d.get("citation_nouns", [])],
            note_pattern=d.get("note_pattern") or None,
            min_provision_words=int(d.get("min_provision_words", MIN_PROVISION_WORDS)),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "levels": [{"name": l.name, "role": l.role, "pattern": l.pattern}
                       for l in self.levels],
            "id_template": self.id_template,
            "citation_nouns": list(self.citation_nouns),
            "note_pattern": self.note_pattern,
            "min_provision_words": self.min_provision_words,
        }


# Constructs that make a regex take exponential time on a non-matching line. A statute is
# a few hundred lines, so a pathological pattern hangs the run rather than failing it, and
# `re` has no timeout to fall back on.
_CATASTROPHIC = re.compile(r"\([^)]*[+*]\)[+*]|\[[^\]]*\][+*][+*]")


def compile_profile(profile: Profile) -> List[str]:
    """Compile every pattern. Returns the problems found; the regexes land on the Levels."""
    problems = []
    for lv in profile.levels:
        if lv.role not in ROLES:
            problems.append("level %r has role %r, expected one of %s"
                            % (lv.name, lv.role, ", ".join(ROLES)))
        if _CATASTROPHIC.search(lv.pattern):
            problems.append("level %r pattern has a nested quantifier and can hang on a "
                            "non-matching line: %s" % (lv.name, lv.pattern))
            continue
        if not lv.pattern.startswith("^"):
            problems.append("level %r pattern is not anchored at ^; a line classifier "
                            "must match from the start of the line: %s"
                            % (lv.name, lv.pattern))
        try:
            lv.regex = re.compile(lv.pattern)
        except re.error as exc:
            problems.append("level %r pattern does not compile (%s): %s"
                            % (lv.name, exc, lv.pattern))
    if not profile.provision_level:
        problems.append("no level has role 'provision' -- nothing says what the graph is "
                        "keyed on")
    return problems


# --- segmentation ------------------------------------------------------------------

def unclaimed_heading_shapes(raw_lines: List[str], profile: Profile, limit: int = 5):
    """Short, title-cased, recurring lines that no level claims.

    Not a failure -- unclaimed text is still attached to the open provision, so nothing
    is lost. But it is where a missed heading form shows up, and a heading swallowed into
    the previous provision quietly corrupts that provision's text.

    Found exactly this on the first induced Part IIIC profile: the division pattern
    matched "Division 1 - Introduction" and missed "Subdivision A - Suspected eligible
    data breaches", so three Subdivision titles were glued onto the end of the provision
    above them. The identifiers were still right, which is why a count-based check would
    not have noticed.
    """
    counts: Dict[str, int] = {}
    examples: Dict[str, str] = {}
    for raw in raw_lines:
        line = normalise(raw)
        if not line:
            continue
        if any(lv.regex is not None and lv.regex.match(line) for lv in profile.levels):
            continue
        words = line.split()
        if not (2 <= len(words) <= 12) or not words[0][:1].isupper():
            continue
        key = words[0]
        counts[key] = counts.get(key, 0) + 1
        examples.setdefault(key, line)
    common = [(k, v) for k, v in counts.items() if v >= 3]
    common.sort(key=lambda kv: -kv[1])
    return [(k, v, examples[k]) for k, v in common[:limit]]


@dataclass
class Segmentation:
    provisions: Dict[str, str]
    order: List[str]
    leading_orphans: int
    interior_orphans: int
    unmatched_lines: int
    non_blank: int
    hits: Dict[str, int]
    discarded: int

    @property
    def orphan_lines(self) -> int:
        return self.leading_orphans + self.interior_orphans


def segment(raw_lines: List[str], profile: Profile) -> Segmentation:
    """Apply a profile to a file. This is the interpreter the per-statute parser becomes.

    A container (a section) opens a provisional block under its own identifier. If a
    provision level opens underneath it before that block has accumulated real text, the
    block is discarded -- that is the case of `26WH  Assessment...` followed by the
    sub-heading `Scope` and then `(1)`. If nothing opens underneath it, the block stands
    on its own, which is the case of `26WB  Entity` followed by a single sentence. Both
    shapes occur in Part IIIC and neither occurs in Schedule 1, which is precisely why
    this cannot be a constant.

    Orphans are counted in two places, because they mean different things. Text before
    the first provision is front matter -- Schedule 1 opens with a page of overview, Part
    IIIC with a Guide -- and is expected. Text after a provision has been seen that
    belongs to none is the real signal: some structural form went unrecognised in the
    middle of the instrument. Only the second kind is a failure.
    """
    provisions: Dict[str, str] = {}
    order: List[str] = []
    captures: Dict[str, str] = {}
    hits = {lv.name: 0 for lv in profile.levels}
    leading = interior = unmatched = discarded = 0
    non_blank = 0
    seen_provision = False

    open_id: Optional[str] = None
    open_head: str = ""                             # the line that opened the block
    open_buf: List[str] = []                        # everything under it
    open_is_container = False

    def flush():
        nonlocal open_id, open_head, open_buf, open_is_container, discarded
        if open_id is not None and (open_head or open_buf):
            body = " ".join(open_buf).strip()
            text = (open_head + " " + body).strip()
            # Substance is judged on the body alone. A section heading is often long
            # enough on its own to clear the threshold -- "26WH Assessment of suspected
            # eligible data breach" is seven words before a single word of rule -- so
            # counting it would keep exactly the blocks this is meant to drop.
            if open_is_container and len(body.split()) < profile.min_provision_words:
                discarded += 1                     # a bare sub-heading, not a rule
            elif open_id in provisions:
                provisions[open_id] += " " + text  # duplicate id: keep both, flag later
            else:
                provisions[open_id] = text
                order.append(open_id)
        open_id, open_head, open_buf, open_is_container = None, "", [], False

    for raw in raw_lines:
        line = normalise(raw)
        if not line:
            continue
        non_blank += 1

        matched = None
        for idx, lv in enumerate(profile.levels):
            if lv.regex is None:
                continue
            m = lv.regex.match(line)
            if m:
                matched, hits[lv.name] = (lv, m, idx), hits[lv.name] + 1
                break

        if matched is None:
            unmatched += 1
            if open_id is None:
                if seen_provision:
                    interior += 1
                else:
                    leading += 1
            else:
                open_buf.append(line)
            continue

        lv, m, idx = matched
        # Opening any level invalidates the captures of every level below it. Without
        # this, a section with no subsections inherits the previous section's subsection
        # number and 26WB silently becomes 26WB(2).
        for deeper in profile.levels[idx + 1:]:
            captures.pop(deeper.name, None)
        # An optional group ("^Note( \d+)?:") captures None rather than "". Only
        # container and provision levels use the capture at all.
        capture = ((m.group(1) or "") if m.groups() else "").strip()

        if lv.role == "heading":
            flush()
            captures.pop(lv.name, None)
        elif lv.role == "container":
            flush()
            captures[lv.name] = capture
            try:
                open_id = profile.id_template.format(**captures)
            except (KeyError, IndexError):
                open_id = capture
            open_head, open_buf, open_is_container = line, [], True
            seen_provision = True
        elif lv.role == "provision":
            flush()
            captures[lv.name] = capture
            try:
                open_id = profile.id_template.format(**captures)
            except (KeyError, IndexError):
                open_id = capture
            open_head, open_buf, open_is_container = line, [], False
            seen_provision = True
        else:                                       # body
            if open_id is None:
                if seen_provision:
                    interior += 1
                else:
                    leading += 1
            else:
                open_buf.append(line)

    flush()
    return Segmentation(provisions, order, leading, interior, unmatched, non_blank,
                        hits, discarded)


# --- validation --------------------------------------------------------------------

@dataclass
class Validation:
    problems: List[str]
    metrics: Dict[str, object]
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def validate(raw_lines: List[str], profile: Profile) -> Validation:
    """Check an induced profile against the whole file. Free, and the point of the design."""
    problems = compile_profile(profile)
    if problems:
        return Validation(problems, {})

    non_blank = [normalise(l) for l in raw_lines if l.strip()]
    total_nb = len(non_blank)
    seg = segment(raw_lines, profile)

    # Both checks below measure what a level EFFECTIVELY claims, not what its pattern
    # matches in isolation. Segmentation is first-match-wins down an ordered list, so a
    # later level only ever sees the lines the levels above it did not take.
    #
    # Measuring patterns in isolation instead produced a false rejection worth recording:
    # an induced profile whose paragraph level was `^\((\w)\)\s+(.+)$` was rejected for
    # "matching 66% of lines", because `\w` matches a digit and so the pattern also
    # matches every "(1)" subsection opening. Ordered after the subsection level it in
    # fact claimed 46%, and the profile was correct -- it produced the same 106 provisions
    # as the hand-written one. The check was wrong, not the profile.
    for lv in profile.levels:
        hit = seg.hits.get(lv.name, 0)
        if total_nb and hit / float(total_nb) > MAX_PATTERN_HIT_RATE:
            problems.append(
                "level %r claims %.0f%% of non-blank lines -- it is not distinguishing "
                "anything: %s" % (lv.name, 100.0 * hit / total_nb, lv.pattern))
        elif hit == 0:
            problems.append(
                "level %r claims no lines -- either it matches nothing, or a level above "
                "it already takes everything it would match: %s" % (lv.name, lv.pattern))

    n = len(seg.provisions)
    orphan_rate = seg.interior_orphans / float(seg.non_blank or 1)
    words = {k: len(v.split()) for k, v in seg.provisions.items()}
    total_words = sum(words.values()) or 1
    largest = max(words.values()) if words else 0
    largest_share = largest / float(total_words)
    thin = sorted(k for k, w in words.items() if w < profile.min_provision_words)

    metrics = {
        "provisions": n,
        "non_blank_lines": seg.non_blank,
        "leading_orphans": seg.leading_orphans,
        "interior_orphans": seg.interior_orphans,
        "orphan_rate": round(orphan_rate, 4),
        "unmatched_lines": seg.unmatched_lines,
        "level_hits": seg.hits,
        "discarded_container_blocks": seg.discarded,
        "largest_provision_share": round(largest_share, 4),
        "thin_provisions": thin[:10],
        "first_ids": seg.order[:8],
        "last_ids": seg.order[-4:],
    }

    if n < MIN_PROVISIONS:
        problems.append(
            "only %d provision(s) found in %d non-blank lines -- the provision pattern "
            "%r did not match. This is what an empty graph looks like three stages early."
            % (n, seg.non_blank, (profile.provision_level or Level("?", "?", "?")).pattern))
    if n > seg.non_blank / 2.0:
        problems.append(
            "%d provisions from %d non-blank lines -- the provision pattern is matching "
            "body text, not clause openings" % (n, seg.non_blank))
    if orphan_rate > MAX_ORPHAN_RATE:
        problems.append(
            "%.1f%% of non-blank lines (%d) sit after a provision has been seen but "
            "belong to none, above the %.0f%% ceiling -- a structural form is "
            "unrecognised mid-instrument and its text is being dropped"
            % (100 * orphan_rate, seg.interior_orphans, 100 * MAX_ORPHAN_RATE))
    if largest_share > MAX_LARGEST_SHARE:
        problems.append(
            "one provision holds %.0f%% of all text -- under-segmentation, usually a "
            "provision pattern that matches the first clause form and not the rest"
            % (100 * largest_share))
    if thin:
        problems.append(
            "%d provision(s) have fewer than %d words, e.g. %s -- these are sub-headings "
            "being read as rules" % (len(thin), profile.min_provision_words, ", ".join(thin[:5])))

    duplicate = len(seg.order) != len(set(seg.order))
    if duplicate:
        problems.append("provision identifiers are not unique -- the id template %r does "
                        "not capture enough of the numbering scheme" % profile.id_template)

    warnings = []
    for word, count, example in unclaimed_heading_shapes(raw_lines, profile):
        warnings.append(
            "%d line(s) begin %r and match no level, e.g. %r -- if that is a heading "
            "form, it is being absorbed into the provision above it"
            % (count, word, example[:70]))

    return Validation(problems, metrics, warnings)


# --- induction ---------------------------------------------------------------------

def sample_for_prompt(raw_lines: List[str], budget_lines: int = 160) -> str:
    """Head, middle and tail. The head alone would miss forms a Part introduces later."""
    non_blank = [normalise(l) for l in raw_lines if l.strip()]
    if len(non_blank) <= budget_lines:
        return "\n".join(non_blank)
    third = budget_lines // 3
    mid = len(non_blank) // 2
    parts = (non_blank[:third],
             non_blank[mid - third // 2: mid + third // 2],
             non_blank[-third:])
    return "\n\n[...]\n\n".join("\n".join(p) for p in parts)


PROMPT = """You are given a sample of an Act. Describe its LINE STRUCTURE so that a
program can split the whole file into provisions.

Return JSON only, with this exact shape:

{{
  "name": "short_snake_case_identifier_for_this_instrument",
  "description": "one line, e.g. Part IIIC of the Privacy Act 1988 (Cth)",
  "levels": [
    {{"name": "section", "role": "container", "pattern": "^(\\\\d{{2}}[A-Z]{{1,3}})\\\\s\\\\s+(.+)$"}}
  ],
  "id_template": "{{section}}({{subsection}})",
  "citation_nouns": ["section", "subsection"],
  "note_pattern": "^Note(\\\\s+\\\\d+)?:",
  "min_provision_words": 8
}}

Rules, all of which matter:

* `levels` is ORDERED, outermost first, and the first pattern that matches a line wins.
  Put narrower patterns before wider ones. "(a)" and "(i)" overlap: bound them so that
  roman numerals and letters do not both match the same line.
* Every pattern is a Python regex, anchored with ^, matching ONE line, with the
  IDENTIFIER as capture group 1. No nested quantifiers such as (\\\\w+)+.
* `role` is one of:
    heading    structural signpost belonging to no provision (a Part or Division title)
    container  opens an identifier namespace and may stand alone as a provision if
               nothing below it opens (a section that is a single sentence)
    provision  THE unit the knowledge graph is keyed on -- exactly one level has this
    body       a continuation of whatever provision is open (lettered paragraphs)
* Choose the provision level so that each provision is one self-contained rule. If
  sections carry numbered subsections, the subsection is the provision, not the section.
* `id_template` composes the identifier from the captures of the enclosing levels, using
  their level names, e.g. "{{section}}({{subsection}})" or "{{clause}}".
* `citation_nouns` are the words this instrument uses to cite itself, drawn from:
  {nouns}.

Do not describe the meaning of the text. Describe only how lines are laid out.

SAMPLE
------
{sample}
"""

RETRY_SUFFIX = """

Your previous answer was applied to the whole file and rejected. Fix these and return
corrected JSON only:

{problems}

Measurements from the attempt:
{metrics}
"""


def build_prompt(raw_lines: List[str], problems=None, metrics=None) -> str:
    prompt = PROMPT.format(nouns=", ".join(CITATION_NOUNS),
                           sample=sample_for_prompt(raw_lines))
    if problems:
        prompt += RETRY_SUFFIX.format(
            problems="\n".join("  - " + p for p in problems),
            metrics=json.dumps(metrics, indent=2, default=str))
    return prompt


def llm_key_from_env() -> str:
    key = os.environ.get(ENV_LLM_KEY_PRIMARY) or os.environ.get(ENV_LLM_KEY_FALLBACK)
    if not key:
        raise RuntimeError("Set %s (or %s). Run `. .\\setup_env.ps1` first."
                           % (ENV_LLM_KEY_PRIMARY, ENV_LLM_KEY_FALLBACK))
    return key


def induce(prompt: str, model: str) -> tuple:
    """One call. Returns (profile_dict, prompt_tokens, completion_tokens)."""
    from openai import OpenAI
    client = OpenAI(api_key=llm_key_from_env())
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    usage = response.usage
    return (json.loads(response.choices[0].message.content),
            usage.prompt_tokens, usage.completion_tokens)


# --- output ------------------------------------------------------------------------

def write_profile(path: str, profile: Profile, metrics: dict, source: str) -> None:
    """Write the profile as YAML, with the evidence for it in comments.

    Hand-editable on purpose. An induction that gets one pattern slightly wrong should be
    correctable here rather than by re-running the call or patching code.
    """
    try:
        import yaml
    except ImportError:
        with io.open(path.replace(".yaml", ".json"), "w", encoding="utf-8") as fh:
            json.dump(profile.to_dict(), fh, indent=2)
        return

    header = [
        "# Structural profile induced by induce_structure.py -- NOT hand-written.",
        "#",
        "# Source: %s" % source,
        "# Validated against the whole file before being written:",
    ]
    for key in ("provisions", "non_blank_lines", "leading_orphans", "interior_orphans",
                "largest_provision_share", "discarded_container_blocks"):
        header.append("#   %-24s %s" % (key, metrics.get(key)))
    header += [
        "#   %-24s %s" % ("first ids", ", ".join(map(str, metrics.get("first_ids", [])))),
        "#",
        "# Correct it by hand if a pattern is slightly wrong -- that is cheaper than",
        "# re-inducing, and this file is what the pipeline actually reads.",
        "",
    ]
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(header))
        yaml.safe_dump(profile.to_dict(), fh, sort_keys=False, allow_unicode=True,
                       default_flow_style=False)


def report(hy: Hygiene, val: Validation, profile: Optional[Profile]) -> None:
    print("input")
    print("  lines            : %d (%d non-blank)" % (hy.lines, hy.non_blank))
    print("  mean line length : %.1f words" % hy.mean_words)
    for w in hy.warnings:
        print("  WARNING: %s" % w)

    if profile:
        print("\nprofile %r" % profile.name)
        for lv in profile.levels:
            print("  %-14s %-10s %s" % (lv.name, lv.role, lv.pattern))
        print("  %-14s %-10s %s" % ("id template", "", profile.id_template))

    if val.metrics:
        m = val.metrics
        print("\nvalidation")
        print("  provisions       : %s" % m["provisions"])
        print("  orphans          : %s leading (front matter, expected), %s interior (%.1f%%)"
              % (m["leading_orphans"], m["interior_orphans"], 100 * m["orphan_rate"]))
        print("  unmatched lines  : %s" % m["unmatched_lines"])
        print("  largest share    : %.1f%%" % (100 * m["largest_provision_share"]))
        print("  discarded blocks : %s" % m["discarded_container_blocks"])
        print("  level hits       : %s" % m["level_hits"])
        print("  first ids        : %s" % ", ".join(map(str, m["first_ids"])))
        print("  last ids         : %s" % ", ".join(map(str, m["last_ids"])))

    for w in val.warnings:
        print("  NOTE: %s" % w)

    if val.problems:
        print("\nREJECTED")
        for p in val.problems:
            print("  - %s" % p)
    elif profile:
        print("\nACCEPTED")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Induce and validate a statute's line structure from the text itself.")
    ap.add_argument("corpus", help="Plain-text statute, one line per structural element.")
    ap.add_argument("--profile", default=None,
                    help="Validate this existing profile instead of calling the model. "
                         "Free, and the way to check the format by hand.")
    ap.add_argument("--out", default=None,
                    help="Where to write the accepted profile (default: profiles/<name>.yaml).")
    ap.add_argument("--model", default="gpt-4o")
    ap.add_argument("--retries", type=int, default=1,
                    help="Re-ask once with the failure report appended.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the prompt size and cost estimate, make no call.")
    args = ap.parse_args()

    if not os.path.exists(args.corpus):
        print("No such file: %s" % args.corpus, file=sys.stderr)
        return 2
    raw_lines = io.open(args.corpus, encoding="utf-8").read().splitlines()
    hy = hygiene(raw_lines)

    # --- offline path: validate a profile someone wrote --------------------------
    if args.profile:
        import yaml
        with io.open(args.profile, encoding="utf-8") as fh:
            profile = Profile.from_dict(yaml.safe_load(fh))
        val = validate(raw_lines, profile)
        report(hy, val, profile)
        return 0 if val.ok else 1

    # --- dry run ------------------------------------------------------------------
    prompt = build_prompt(raw_lines)
    approx_in = len(prompt) // 4
    if args.dry_run:
        report(hy, Validation([], {}), None)
        cost = (approx_in * PRICE_IN + 900 * PRICE_OUT) / 1e6
        print("\ndry run")
        print("  sample lines     : %d of %d non-blank" % (
            len(sample_for_prompt(raw_lines).splitlines()), hy.non_blank))
        print("  prompt           : ~%d tokens" % approx_in)
        print("  calls            : 1 (+%d retry on rejection)" % args.retries)
        print("  cost             : ~$%.4f on %s, ~$%.4f worst case with retries"
              % (cost, args.model, cost * (1 + args.retries)))
        return 0

    # --- induce, validate, retry once ----------------------------------------------
    problems, metrics, spent_in, spent_out = None, None, 0, 0
    for attempt in range(args.retries + 1):
        prompt = build_prompt(raw_lines, problems, metrics)
        print("attempt %d: asking %s for a structural profile..." % (attempt + 1, args.model))
        raw, p_tok, c_tok = induce(prompt, args.model)
        spent_in, spent_out = spent_in + p_tok, spent_out + c_tok
        profile = Profile.from_dict(raw)
        val = validate(raw_lines, profile)
        report(hy, val, profile)
        if val.ok:
            out = args.out or os.path.join("profiles", "%s.yaml" % profile.name)
            os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
            write_profile(out, profile, val.metrics, args.corpus)
            print("\nwrote %s" % out)
            print("cost: $%.4f (%d in, %d out)"
                  % ((spent_in * PRICE_IN + spent_out * PRICE_OUT) / 1e6, spent_in, spent_out))
            return 0
        problems, metrics = val.problems, val.metrics

    print("\nGiving up after %d attempt(s). The patterns above did not fit the file."
          % (args.retries + 1), file=sys.stderr)
    print("Write the profile by hand and check it with --profile; that is the escape "
          "hatch, and it is meant to be used rather than worked around.", file=sys.stderr)
    print("cost: $%.4f" % ((spent_in * PRICE_IN + spent_out * PRICE_OUT) / 1e6), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
