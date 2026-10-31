# Discard review

Every condition/exception field value that `clean_extraction.py` removed, from 62 provisions. Ranked by how much the discard could cost, not by frequency.

| | Count | Share of all values | Risk |
|---|---|---|---|
| `compound_dropped` | 1 | 0% | **HIGH** - a whole condition/exception was lost while its other fields held content |
| `description_echo` | 2 | 1% | MEDIUM - usually a genuine echo, but a real clause could contain the same words |
| `nullish` | 115 | 30% | LOW - the model wrote a word for absence |
| `bracket_only` | 57 | 15% | NONE - the prompt's own fill-in marker |

206 of 381 values kept, 175 discarded (46%).

**How to review:** read the HIGH and MEDIUM sections. For each row ask whether the raw value carried legal content. If it did, the cleaner is deleting extracted data and its rules need narrowing before the graph is built on it.

---

## compound_dropped  (1)

**HIGH** - a whole condition/exception was lost while its other fields held content

| Provision | Field | Discarded value | Sibling fields |
|---|---|---|---|
| 12.6 | `exceptions[1].statement` | <The exception in a single clause, as stated in the text.> | source_provision=<Blank when the exception is stated here; is_exhaustive=<Blank, since text indicating exhaustive |

## description_echo  (2)

MEDIUM - usually a genuine echo, but a real clause could contain the same words

| Provision | Field | Discarded value | Sibling fields |
|---|---|---|---|
| 12.6 | `exceptions[1].source_provision` | <Blank when the exception is stated here in full.> | statement=<The exception in a single clause, as st; is_exhaustive=<Blank, since text indicating exhaustive |
| 3.3 | `conditions[1].source_provision` | <Blank when the condition is stated here.> | statement=<none> |

## nullish  (115)

LOW - the model wrote a word for absence

| Provision | Field | Discarded value |
|---|---|---|
| 1.4 | `conditions[1].statement` | None |
| 1.4 | `exceptions[1].statement` | None |
| 1.4 | `conditions[1].source_provision` | <Blank> |
| 1.6 | `conditions[1].source_provision` | <Blank> |
| 10.2 | `conditions[1].source_provision` | <Blank> |
| 11.1 | `conditions[1].source_provision` | <Blank> |
| 11.2 | `conditions[2].source_provision` | <Blank> |
| 11.2 | `conditions[3].source_provision` | <Blank> |
| 12.1 | `conditions[1].source_provision` | <Blank> |
| 12.1 | `conditions[2].source_provision` | <Blank> |
| 12.2 | `exceptions[1].source_provision` | <Blank> |
| 12.2 | `exceptions[1].is_exhaustive` | <Blank> |
| 12.2 | `conditions[2].source_provision` | <Blank> |
| 12.2 | `conditions[3].source_provision` | <Blank> |
| 12.3 | `conditions[1].source_provision` | <Blank> |
| 12.3 | `exceptions[1].source_provision` | <Blank> |
| 12.3 | `exceptions[1].is_exhaustive` | <Blank> |
| 12.3 | `conditions[1].source_provision` | <Blank> |
| 12.3 | `conditions[2].source_provision` | <Blank> |
| 12.4 | `conditions[2].source_provision` | <Blank> |
| 12.4 | `conditions[2].source_provision` | <Blank> |
| 12.4 | `conditions[1].source_provision` | <Blank> |
| 12.4 | `conditions[2].source_provision` | <Blank> |
| 12.5 | `conditions[1].source_provision` | <Blank> |
| 12.5 | `conditions[1].source_provision` | <Blank> |
| 12.6 | `conditions[1].source_provision` | <Blank> |
| 12.8 | `conditions[2].source_provision` | <Blank> |
| 12.8 | `conditions[2].source_provision` | <Blank> |
| 12.9 | `conditions[2].source_provision` | <Blank> |
| 12.9 | `conditions[2].source_provision` | <Blank> |
| 13.1 | `conditions[1].source_provision` | <Blank> |
| 13.1 | `conditions[2].source_provision` | <Blank> |
| 13.1 | `conditions[1].source_provision` | <Blank> |
| 13.2 | `conditions[1].source_provision` | <Blank> |
| 13.2 | `conditions[2].source_provision` | <Blank> |
| 13.3 | `conditions[1].source_provision` | <Blank> |
| 13.3 | `conditions[1].source_provision` | <Blank> |
| 13.3 | `conditions[1].source_provision` | <Blank> |
| 13.4 | `conditions[1].source_provision` | <Blank> |
| 13.4 | `conditions[2].source_provision` | <Blank> |
| 3.3 | `conditions[1].statement` | <none> |
| 3.3 | `exceptions[2].source_provision` | <Blank> |
| 3.3 | `exceptions[2].is_exhaustive` | <Blank> |
| 3.4 | `conditions[1].source_provision` | <Blank> |
| 3.4 | `conditions[2].source_provision` | <Blank> |
| 3.4 | `conditions[3].source_provision` | <Blank> |
| 3.6 | `conditions[1].source_provision` | <Blank> |
| 3.6 | `conditions[1].source_provision` | <Blank> |
| 3.6 | `conditions[1].source_provision` | <Blank> |
| 3.7 | `conditions[1].source_provision` | <Blank> |
| 4.1 | `conditions[1].source_provision` | <Blank> |
| 4.1 | `conditions[2].source_provision` | <Blank> |
| 4.3 | `conditions[3].source_provision` | <Blank> |
| 4.3 | `conditions[1].source_provision` | <Blank> |
| 4.4 | `conditions[1].source_provision` | <Blank> |
| 5.1 | `conditions[1].source_provision` | <Blank> |
| 5.1 | `conditions[2].source_provision` | <Blank> |
| 5.2 | `conditions[1].source_provision` | <Blank> |
| 5.2 | `conditions[2].source_provision` | <Blank> |
| 5.2 | `conditions[1].source_provision` | <Blank> |
| 5.2 | `conditions[1].source_provision` | <Blank> |
| 5.2 | `conditions[2].source_provision` | <Blank> |
| 6.1 | `exceptions[1].source_provision` | <Blank> |
| 6.1 | `exceptions[1].is_exhaustive` | <Blank> |
| 6.1 | `conditions[1].source_provision` | <Blank> |
| 6.2 | `conditions[1].source_provision` | <Blank> |
| 6.2 | `conditions[2].source_provision` | <Blank> |
| 6.2 | `conditions[1].source_provision` | <Blank> |
| 6.2 | `conditions[2].source_provision` | <Blank> |
| 6.2 | `conditions[3].source_provision` | <Blank> |
| 6.2 | `conditions[1].source_provision` | <Blank> |
| 6.2 | `conditions[2].source_provision` | <Blank> |
| 6.2 | `conditions[1].source_provision` | <Blank> |
| 6.3 | `conditions[1].source_provision` | <Blank> |
| 6.3 | `conditions[1].source_provision` | <Blank> |
| 6.3 | `conditions[1].source_provision` | <Blank> |
| 6.4 | `conditions[2].source_provision` | <Blank> |
| 6.4 | `conditions[3].source_provision` | <Blank> |
| 6.7 | `conditions[1].source_provision` | <Blank> |
| 7.1 | `conditions[1].source_provision` | <Blank> |
| 7.3 | `conditions[2].source_provision` | <Blank> |
| 7.3 | `conditions[1].source_provision` | <Blank> |
| 7.3 | `conditions[1].source_provision` | <Blank> |
| 7.3 | `conditions[2].source_provision` | <Blank> |
| 7.3 | `conditions[1].source_provision` | <Blank> |
| 7.3 | `conditions[1].source_provision` | <Blank> |
| 7.3 | `conditions[2].source_provision` | <Blank> |
| 7.3 | `conditions[1].source_provision` | <Blank> |
| 7.3 | `conditions[1].source_provision` | <Blank> |
| 7.3 | `conditions[2].source_provision` | <Blank> |
| 7.3 | `conditions[1].source_provision` | <Blank> |
| 7.6 | `conditions[1].source_provision` | <Blank> |
| 7.6 | `conditions[1].source_provision` | <Blank> |
| 7.8 | `conditions[2].source_provision` | <Blank> |
| 7.8 | `conditions[3].source_provision` | <Blank> |
| 8.1 | `conditions[1].source_provision` | <Blank> |
| 8.2 | `conditions[1].source_provision` | <Blank> |
| 8.2 | `conditions[2].source_provision` | <Blank> |
| 8.2 | `conditions[1].source_provision` | <Blank> |
| 8.2 | `conditions[2].source_provision` | <Blank> |
| 8.2 | `conditions[1].source_provision` | <Blank> |
| 8.3 | `conditions[1].source_provision` | <Blank> |
| 8.3 | `conditions[1].source_provision` | <Blank> |
| 8.3 | `conditions[1].source_provision` | <Blank> |
| 8.3 | `conditions[2].source_provision` | <Blank> |
| 9.2 | `conditions[1].source_provision` | <Blank> |
| 9.2 | `conditions[1].source_provision` | <Blank> |
| 9.2 | `conditions[1].source_provision` | <Blank> |
| 9.2 | `conditions[1].source_provision` | <Blank> |
| 9.2 | `conditions[1].source_provision` | <Blank> |
| 9.2 | `conditions[2].source_provision` | <Blank> |
| 9.3 | `conditions[1].source_provision` | <Blank> |
| 9.3 | `conditions[1].source_provision` | <Blank> |
| 9.3 | `conditions[2].source_provision` | <Blank> |
| 9.3 | `conditions[1].source_provision` | <Blank> |

## bracket_only  (57)

NONE - the prompt's own fill-in marker

| Provision | Field | Discarded value |
|---|---|---|
| 11.2 | `conditions[1].source_provision` | < > |
| 11.2 | `exceptions[1].source_provision` | <> |
| 11.2 | `exceptions[1].is_exhaustive` | <> |
| 12.3 | `exceptions[1].source_provision` | <> |
| 12.3 | `exceptions[1].is_exhaustive` | <> |
| 12.3 | `exceptions[2].source_provision` | <> |
| 12.3 | `exceptions[2].is_exhaustive` | <> |
| 12.9 | `exceptions[1].source_provision` | <> |
| 12.9 | `exceptions[1].is_exhaustive` | <> |
| 13.1 | `conditions[2].source_provision` | <> |
| 13.2 | `exceptions[1].source_provision` | <> |
| 13.2 | `exceptions[1].is_exhaustive` | <> |
| 13.3 | `exceptions[1].source_provision` | <> |
| 13.3 | `exceptions[1].is_exhaustive` | <> |
| 3.3 | `exceptions[1].source_provision` | <> |

_42 further rows omitted; they are the same marker._

