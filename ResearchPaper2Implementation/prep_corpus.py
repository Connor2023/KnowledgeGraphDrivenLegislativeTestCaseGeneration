"""Turn a statute into provisions, driven by a structural profile.

This is what `prep_app.py` becomes once the parser stops being per-statute code. It
knows nothing about Australian Privacy Principles, or about sections numbered 26WE; it
reads an ordered list of line classifiers from `profiles/<name>.yaml` and applies them.

The profile is produced by `induce_structure.py`, which asks a model to describe the
instrument's layout and then validates the answer against the whole file. That tool
imports the model and the interpreter from here rather than the other way round: this
module is what runs on every build, and it must not depend on a one-off tool that pulls
in an OpenAI client.

Equivalence with the parser it replaces was measured, not assumed. On Schedule 1 this
produces the same 62 provision identifiers as `enrich_graph.raw_clause_text()` and all 62
texts are byte-identical, which is what makes it safe to swap in under the SPIRES
extraction. See tests/test_induce_structure.py.

    python prep_corpus.py                 # summary: how many provisions, first and last
    python prep_corpus.py --list          # every identifier, in document order
    python prep_corpus.py --show 6.1      # one provision's verbatim text
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import corpus_config  # noqa: E402

ROLES = ("heading", "container", "provision", "body")

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

    corpus.yaml is generated from it: `induce_structure.py --write-config` derives the
    file and node prefixes, the paths, the identifier pattern and the key prefix, so a new
    statute is a .txt file and two generated configs rather than a config someone had to
    reason their way to.
    """
    name: str
    description: str
    levels: List[Level]
    id_template: str                     # "{section}({subsection})" or "{clause}"
    # Finds an identifier inside running text, e.g. "see subclause 6.2". Distinct from
    # the level patterns, which classify whole lines: this one has to match a citation
    # mid-sentence. Group 1 is the identifier.
    identifier_pattern: Optional[str] = None
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
            identifier_pattern=d.get("identifier_pattern") or None,
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
            "identifier_pattern": self.identifier_pattern,
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


# --- the corpus API ----------------------------------------------------------------
# Everything above is the profile model and the interpreter. Everything below is what
# the rest of the pipeline calls.

_CACHE: Dict[str, "Segmentation"] = {}


def profile_path() -> str:
    """Where this corpus's structural profile lives."""
    return corpus_config.PROFILE_PATH


def load_profile(path: Optional[str] = None) -> Profile:
    """Read and compile the profile. Refuses a profile with broken patterns."""
    import yaml
    path = path or profile_path()
    if not os.path.exists(path):
        raise SystemExit(
            "No structural profile at %s.\n"
            "Produce one with:  python induce_structure.py %s\n"
            "or point corpus.yaml's `profile:` at an existing one."
            % (path, corpus_config.RAW_PATH))
    with io.open(path, encoding="utf-8") as fh:
        profile = Profile.from_dict(yaml.safe_load(fh))
    problems = compile_profile(profile)
    if problems:
        raise SystemExit("Structural profile %s is unusable:\n  %s"
                         % (path, "\n  ".join(problems)))
    return profile


def segmentation(path: Optional[str] = None, raw_path: Optional[str] = None) -> Segmentation:
    """Segment the configured corpus. Cached, because several callers want it per run."""
    key = "%s|%s" % (path or profile_path(), raw_path or corpus_config.RAW_PATH)
    if key not in _CACHE:
        profile = load_profile(path)
        with io.open(raw_path or corpus_config.RAW_PATH, encoding="utf-8") as fh:
            _CACHE[key] = segment(fh.read().splitlines(), profile)
    return _CACHE[key]


def provisions(path: Optional[str] = None, raw_path: Optional[str] = None) -> Dict[str, str]:
    """`{"6.1": "6.1 If an APP entity holds ...", ...}` in document order.

    The replacement for `enrich_graph.raw_clause_text()`, with one difference that
    matters: the keys are bare identifiers, not `subclause 6.1`. Callers that need the
    prefixed form ask `corpus_config.provision_key` for it, rather than every caller
    stripping a hard-coded prefix back off -- which is what four of them used to do.
    """
    return dict(segmentation(path, raw_path).provisions)


def order(path: Optional[str] = None, raw_path: Optional[str] = None) -> List[str]:
    """Provision identifiers in the order the instrument states them.

    This is the sort key. Deriving one from the identifier grammar means parsing
    "26WE(1)" into something comparable, and two places in the codebase tried it with
    `[int(x) for x in pid.split(".")]`, which raises on any statute that does not number
    clauses N.M. Document order is already known and is always right.
    """
    return list(segmentation(path, raw_path).order)


def main() -> int:
    ap = argparse.ArgumentParser(description="Segment the configured corpus into provisions.")
    ap.add_argument("--profile", default=None, help="Override the configured profile.")
    ap.add_argument("--raw", default=None, help="Override the configured statute file.")
    ap.add_argument("--list", action="store_true", help="Print every identifier.")
    ap.add_argument("--show", default=None, help="Print one provision's text.")
    args = ap.parse_args()

    seg = segmentation(args.profile, args.raw)
    if args.show:
        text = seg.provisions.get(args.show)
        if text is None:
            print("No provision %r. Try --list." % args.show, file=sys.stderr)
            return 1
        print(text)
        return 0
    if args.list:
        for pid in seg.order:
            print(pid)
        return 0

    # Report what was actually read, not what is configured: --profile/--raw override
    # both, and printing the configured values instead is how you convince yourself a
    # second corpus segmented correctly when you were looking at the first.
    print("corpus     : %s" % (args.raw or corpus_config.RAW_PATH))
    print("profile    : %s" % (args.profile or profile_path()))
    print("provisions : %d" % len(seg.provisions))
    print("orphans    : %d leading, %d interior" % (seg.leading_orphans, seg.interior_orphans))
    print("first      : %s" % ", ".join(seg.order[:8]))
    print("last       : %s" % ", ".join(seg.order[-4:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
