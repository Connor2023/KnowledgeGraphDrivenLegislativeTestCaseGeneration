"""Which legislation this checkout is pointed at.

One place for every path, filename prefix, node-label prefix and provision pattern that
was previously hard-coded to the Australian Privacy Principles. See corpus.yaml.

Two deliberate properties:

  Defaults reproduce the old behaviour exactly. Every value here matches what the
  constant it replaced held, so a checkout without corpus.yaml -- or one where PyYAML is
  not installed, which is true of some of the three virtualenvs -- behaves as before
  rather than failing at import time in the middle of a long extraction run.

  Paths resolve against this file, not the working directory. The scripts are run from
  several places (repo root, spires/, a venv's Scripts/) and os.path.join on a relative
  constant silently produced different files depending on where you stood.

This is configuration, not generalisation. The structural parser in prep_app.py and the
citation patterns in enrich_graph.parse_references remain per-statute CODE: they encode
how one instrument numbers and cites itself, which is not expressible as a few strings.
Pointing this file at a new corpus without writing those is how you get an empty graph.
"""

from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "corpus.yaml")

# Mirrors corpus.yaml. Kept in sync by hand, and used verbatim when the file or PyYAML
# is unavailable -- see the module docstring.
_DEFAULTS = {
    "name": "app_schedule1",
    "description": "Schedule 1 of the Privacy Act 1988 (Cth)",
    "file_prefix": "app",
    "node_prefix": "SP_",
    "paths": {
        "raw": "APPschedule1.txt",
        "corpus": os.path.join("edc-main", "edc-main", "datasets", "app_schedule1.txt"),
        "edc_graph_dir": os.path.join("edc-main", "edc-main", "output", "app_full", "graph"),
        "spires_dir": "spires",
    },
    "provision": {
        "pattern": r"\b(?:subclause\s+)?(\d{1,2}\.\d{1,2})\b",
        "key_prefix": "subclause",
    },
}


def _load():
    try:
        import yaml
    except ImportError:
        return _DEFAULTS
    if not os.path.exists(CONFIG_PATH):
        return _DEFAULTS
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
    except Exception:  # noqa: BLE001 - a malformed config must not break an extraction
        return _DEFAULTS
    merged = dict(_DEFAULTS)
    merged.update({k: v for k, v in loaded.items() if k not in ("paths", "provision")})
    for section in ("paths", "provision"):
        merged[section] = dict(_DEFAULTS[section])
        merged[section].update(loaded.get(section) or {})
    return merged


_CFG = _load()

NAME = _CFG["name"]
DESCRIPTION = _CFG["description"]
FILE_PREFIX = _CFG["file_prefix"]
NODE_PREFIX = _CFG["node_prefix"]

PROVISION_PATTERN = _CFG["provision"]["pattern"]
PROVISION_KEY_PREFIX = _CFG["provision"]["key_prefix"]
PROVISION_RE = re.compile(PROVISION_PATTERN, re.IGNORECASE)


def path(key: str) -> str:
    """An absolute path for one of the configured locations."""
    value = _CFG["paths"][key]
    return value if os.path.isabs(value) else os.path.join(ROOT, value)


RAW_PATH = path("raw")
CORPUS_PATH = path("corpus")
EDC_GRAPH_DIR = path("edc_graph_dir")
SPIRES_DIR = path("spires_dir")

SPIRES_INPUT_DIR = os.path.join(SPIRES_DIR, "input")
SPIRES_OUTPUT_DIR = os.path.join(SPIRES_DIR, "output")
SPIRES_GRAPH_DIR = os.path.join(SPIRES_DIR, "graph")
SPIRES_SCHEMA = os.path.join(SPIRES_DIR, "app_norm.yaml")


def detect_provision_id(text: str):
    """The provision identifier a piece of text is about, or None.

    Lives here rather than in kg_testgen.edc_bridge, where it used to sit next to the
    EDC entity extractor. It needs nothing but PROVISION_RE, and putting it beside the
    pattern it applies means the query pipeline no longer imports the EDC bridge -- and
    so no longer drags in transformers and numpy -- to answer a question about a regex.

    Prefers the first match, which in the corpus format is the clause being stated
    rather than a cross-reference to another clause.
    """
    match = PROVISION_RE.search(text)
    return match.group(1) if match else None


def provision_filename(provision_id: str, suffix: str) -> str:
    """`6.1`, `.yaml` -> `app_6_1.yaml`. The dot is not filename-safe on Windows."""
    return "%s_%s%s" % (FILE_PREFIX, provision_id.replace(".", "_"), suffix)


def provision_glob(suffix: str = ".yaml") -> str:
    """Every per-provision artefact of one kind, e.g. `.../output/app_*.clean.yaml`."""
    return os.path.join(SPIRES_OUTPUT_DIR, "%s_*%s" % (FILE_PREFIX, suffix))


def label(name: str) -> str:
    """`Provision` -> `SP_Provision`. Also used for relationship types."""
    return "%s%s" % (NODE_PREFIX, name)


def summary() -> str:
    return ("corpus %r (%s)\n  file prefix : %s_*\n  node prefix : %s\n"
            "  raw         : %s\n  corpus      : %s\n  provision   : %s"
            % (NAME, DESCRIPTION, FILE_PREFIX, NODE_PREFIX,
               RAW_PATH, CORPUS_PATH, PROVISION_PATTERN))


if __name__ == "__main__":
    print(summary())
