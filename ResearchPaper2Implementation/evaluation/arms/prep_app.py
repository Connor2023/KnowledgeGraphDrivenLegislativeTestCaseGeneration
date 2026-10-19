"""Turn APPschedule1.txt into an EDC-ready dataset: one self-contained clause per line.

NOT part of the pipeline. This is the parser prep_corpus.py replaced -- it knows that
an Australian Privacy Principle is announced by "N Australian Privacy Principle
N-title" and that clauses are numbered N.M, none of which transfers to another
instrument. It survives for one reason: EDC ingests one document per line, and the
flattening that produces those documents is roughly eighty lines of sentence-splicing
tuned to APP phrasing. The `full-corpus` control arm reads the same file.

Both of those are evaluation arms, so this moved here with them. prep_corpus.py
reproduces its provision segmentation exactly -- the same 62 identifiers with
byte-identical text -- which is what made the swap safe; see
tests/test_induce_structure.py.

EDC's run.py treats every line of the input file as an independent document, so the raw
Schedule -- with its hanging-paragraph structure -- has to be flattened first. A bare
"(a) free of charge; and" has no subject; here each emitted line carries its Part, its
Australian Privacy Principle, its clause stem and, where one exists, the closing tail
that completes the sentence.
"""

import argparse
import io
import re
import unicodedata

# Line classification
RE_PART = re.compile(r"^Part\s+(\d+)\s*[-—]\s*(.+)$")
RE_APP = re.compile(r"^(\d+)\s+Australian Privacy Principle\s+(\d+)\s*[-—]\s*(.+)$")
RE_CLAUSE = re.compile(r"^(\d+\.\d+)\s+(.*)$")
RE_SUBCLAUSE = re.compile(r"^\(([a-z]{1,2}|[ivx]{1,4})\)\s+(.*)$")
RE_ROMAN = re.compile(r"^[ivx]{1,4}$")
RE_NOTE = re.compile(r"^Note(\s+\d+)?:\s*(.*)$")
RE_PRINCIPLE_ITEM = re.compile(r"^Australian Privacy Principle\s+(\d+)\s*[-—]\s*(.+)$")

# Notes that are pure cross-references carry no extractable relation of interest.
RE_XREF_NOTE = re.compile(
    r"^(For .*,\s*)?see\s+(section|subsection|subclause|paragraph|Australian Privacy Principle)",
    re.IGNORECASE,
)

# Split a clause block into per-subclause documents once it passes this many words.
SPLIT_WORD_THRESHOLD = 110


def normalise(text):
    """Fold the typographic characters the Schedule uses into plain ASCII."""
    text = text.replace("‑", "-")                          # non-breaking hyphen
    text = text.replace("—", " - ").replace("–", "-")  # em / en dash
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


# Words that stay capitalised when a stem is spliced in after "provides that".
PROPER_STARTS = ("Australian", "APP", "Commonwealth", "Division", "Despite")


def is_tail(line):
    """A continuation that closes a hanging clause always starts lower-case.

    'the entity must, within a reasonable period...' is a tail; 'Availability of APP
    privacy policy etc.' is the next cross-head. Case is what separates them -- length
    and trailing punctuation are not reliable, since several cross-heads end in a stop.
    """
    return line[:1].islower()


def decapitalise(text):
    """Lower-case a clause stem so it reads on from '...provides that'."""
    first = text.split(" ", 1)[0]
    if first.isupper() or text.startswith(PROPER_STARTS):
        return text
    return text[:1].lower() + text[1:]


def join_sentence(*parts):
    """Join fragments into one sentence, tidying the seams between them."""
    out = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if not out:
            out = part
            continue
        if out.endswith((":", ";", ",")):
            out = out[:-1].rstrip() + " " + part
        else:
            out = out + " " + part
    out = re.sub(r"\s+([;:,.])", r"\1", out)
    if not out.endswith("."):
        out = out.rstrip(";:, ") + "."
    return out


class ClauseBlock:
    """One numbered clause (e.g. 3.3) plus every subclause, tail and note under it."""

    def __init__(self, number, stem, part, app_num, app_title, heading):
        self.number = number
        self.stem = stem
        self.part = part
        self.app_num = app_num
        self.app_title = app_title
        self.heading = heading
        self.items = []   # [label, text] for top-level (a)/(b)/(aa)
        self.tails = []   # unmarked continuation lines that close the whole clause
        self.notes = []
        self.last_was_roman = False

    def add_subclause(self, label, text):
        if RE_ROMAN.match(label) and self.items:
            # A roman numeral belongs to the letter above it, not to the clause.
            self.items[-1][1] = join_sentence(self.items[-1][1], text)[:-1]
            self.last_was_roman = True
        else:
            self.items.append([label, text])
            self.last_was_roman = False

    def add_tail(self, text):
        """Attach a continuation to whatever it actually closes.

        After a nested (i)/(ii) group the continuation closes that one lettered
        paragraph -- in 5.2 the 'the fact that the entity so collects...' tail belongs
        to (b) alone. After a lettered paragraph it closes the clause as a whole, as in
        4.1 where 'the entity must... determine whether' applies to (a) and (b) together.
        """
        if self.last_was_roman and self.items:
            self.items[-1][1] = join_sentence(self.items[-1][1], text)[:-1]
        else:
            self.tails.append(text)

    def context(self):
        bits = ["Under Australian Privacy Principle {} ({})".format(self.app_num, self.app_title)]
        if self.heading:
            bits.append(", under the heading '{}'".format(self.heading.rstrip(".")))
        bits.append(", subclause {} of Schedule 1 of the Privacy Act provides that".format(self.number))
        return "".join(bits)

    def documents(self):
        docs = []
        tail = " ".join(self.tails)
        stem = decapitalise(self.stem)
        body = stem + " " + " ".join(t for _, t in self.items) + " " + tail

        if not self.items or len(body.split()) <= SPLIT_WORD_THRESHOLD:
            docs.append(join_sentence(self.context(), stem,
                                      " ".join(t for _, t in self.items), tail))
        else:
            # Too long for one document: one document per top-level subclause, each
            # repeating the stem and the closing tail so it still reads as a whole rule.
            for label, text in self.items:
                docs.append(join_sentence(self.context(), stem,
                                          "({}) {}".format(label, text), tail))

        for note in self.notes:
            docs.append(join_sentence(
                "Australian Privacy Principle {} ({}) includes the following note in relation"
                " to subclause {}".format(self.app_num, self.app_title, self.number), note))
        return docs


def parse(lines):
    part = None
    app_num = app_title = None
    heading = None
    blocks = []
    current = None
    overview = []
    seen_first_app = False

    for raw in lines:
        line = normalise(raw)
        if not line:
            continue

        m = RE_PART.match(line)
        if m:
            part = "Part {} - {}".format(m.group(1), m.group(2))
            heading = None
            continue

        m = RE_APP.match(line)
        if m:
            app_num, app_title = m.group(2), m.group(3)
            heading = None
            current = None
            seen_first_app = True
            continue

        if not seen_first_app:
            # Overview material before APP 1.
            m = RE_PRINCIPLE_ITEM.match(line)
            if m:
                overview.append(
                    "Australian Privacy Principle {} is titled '{}' and is one of the thirteen"
                    " Australian Privacy Principles set out in Schedule 1 of the Privacy"
                    " Act.".format(m.group(1), m.group(2)))
            elif line.startswith("Part ") and " sets out " in line:
                # Anchor the Part summaries to the Schedule; on their own they name no
                # instrument, which leaves the extracted triples floating free.
                overview.append("In Schedule 1 of the Privacy Act, " + decapitalise(line))
            elif line.startswith("This Schedule"):
                overview.append(line)
            continue

        m = RE_CLAUSE.match(line)
        if m:
            current = ClauseBlock(m.group(1), m.group(2), part, app_num, app_title, heading)
            blocks.append(current)
            continue

        m = RE_NOTE.match(line)
        if m:
            body = m.group(2)
            if current is not None and not RE_XREF_NOTE.match(body):
                current.notes.append(body)
            continue

        m = RE_SUBCLAUSE.match(line)
        if m and current is not None:
            current.add_subclause(m.group(1), m.group(2))
            continue

        if current is not None and is_tail(line):
            # Unmarked continuation: the tail that closes an "If:" style clause.
            if current.items:
                current.add_tail(line)
            else:
                current.stem = join_sentence(current.stem, line)[:-1]
            continue

        # Anything else at this point is a cross-head, which scopes the clauses below it.
        heading = line
        current = None

    return overview, blocks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="APPschedule1.txt")
    ap.add_argument("--output", default="evaluation/edc/edc-main/datasets/app_schedule1.txt")
    args = ap.parse_args()

    with io.open(args.input, encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    overview, blocks = parse(lines)

    docs = list(overview)
    for block in blocks:
        docs.extend(block.documents())

    docs = [d for d in docs if len(d.split()) >= 6]

    with io.open(args.output, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(docs) + "\n")

    words = [len(d.split()) for d in docs]
    print("clause blocks : {}".format(len(blocks)))
    print("documents     : {}".format(len(docs)))
    print("words/doc     : min {} / mean {} / max {}".format(
        min(words), sum(words) // len(words), max(words)))
    print("written to    : {}".format(args.output))


if __name__ == "__main__":
    main()
