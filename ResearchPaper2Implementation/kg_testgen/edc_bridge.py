"""Bridge to the vendored EDC code, so the query pipeline reuses the construction
vocabulary rather than reinventing it.

Two pieces of EDC are reused:

* ``EntityExtractor`` (``edc/entity_extraction.py``) for pulling candidate terms out of
  the input section.
* ``normalise`` (``build_graph.py``) -- the function that produced the ``key`` property
  on every node in the graph. Seeding *must* use it, or extracted surface forms will not
  match what was stored.

``edc.entity_extraction`` imports ``transformers`` and ``numpy`` at module scope, and
``edc.utils.llm_utils`` additionally imports ``torch`` and ``sentence_transformers`` --
roughly 2 GB of install for a code path that only makes an HTTPS request. Since the
OpenAI branch touches none of them, they are stubbed before import. The same technique is
used by ``check_setup.py`` in this repository.
"""

from __future__ import annotations

import os
import re
import sys
import types
from typing import List

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EDC_ROOT = os.path.join(_REPO_ROOT, "edc-main", "edc-main")

# numpy is deliberately NOT stubbed: the neo4j driver detects it and calls into it
# (np.bool_), so a fake module breaks the driver. It is a real dependency.
_HEAVY_MODULES = ("torch", "transformers", "sentence_transformers")


def _install_stubs() -> List[str]:
    """Stub the heavy ML imports EDC pulls in but the OpenAI path never calls."""
    stubbed = []
    for name in _HEAVY_MODULES:
        if name in sys.modules:
            continue
        try:
            __import__(name)
            continue  # genuinely installed, leave it alone
        except ImportError:
            pass
        module = types.ModuleType(name)
        module.__getattr__ = lambda attr, _n=name: type(attr, (), {})  # type: ignore[attr-defined]
        sys.modules[name] = module
        stubbed.append(name)
    return stubbed


STUBBED_MODULES = _install_stubs()

if _EDC_ROOT not in sys.path:
    sys.path.insert(0, _EDC_ROOT)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from edc.entity_extraction import EntityExtractor  # noqa: E402
import edc.utils.llm_utils as edc_llm_utils  # noqa: E402
from build_graph import normalise as normalise_mention  # noqa: E402


# ---------------------------------------------------------------------------
# EDC's parse_raw_entities calls .index("[") outside its try block, so a response
# without brackets raises ValueError instead of returning nothing. Patch it here rather
# than editing the vendored file, so the construction pipeline is untouched.
# ---------------------------------------------------------------------------
_original_parse_raw_entities = edc_llm_utils.parse_raw_entities


def _safe_parse_raw_entities(raw_entities: str):
    if not raw_entities or "[" not in raw_entities or "]" not in raw_entities:
        return []
    try:
        return _original_parse_raw_entities(raw_entities)
    except (ValueError, SyntaxError):
        return []


edc_llm_utils.parse_raw_entities = _safe_parse_raw_entities


EE_TEMPLATE_PATH = os.path.join(_EDC_ROOT, "prompt_templates", "ee_template.txt")
EE_FEW_SHOT_PATH = os.path.join(_EDC_ROOT, "few_shot_examples", "app", "ee_few_shot_examples.txt")


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def extract_entities(text: str, model: str) -> List[str]:
    """Run EDC's entity extractor over the input section.

    One OpenAI call. Uses the APP-domain few-shot file; the examples EDC ships are
    WebNLG (lakes, films) and would pull proper nouns rather than privacy concepts.
    """
    extractor = EntityExtractor(openai_model=model)
    entities = extractor.extract_entities(text, read_text(EE_FEW_SHOT_PATH), read_text(EE_TEMPLATE_PATH))
    return [e for e in entities if isinstance(e, str) and e.strip()]


# The identifier pattern is the most instrument-specific value in the pipeline: 'N.M'
# suits the APPs, but another statute may number clauses 's 12(3)(a)' or 'Art. 6(1)(b)'.
# It and the key prefix come from corpus.yaml; the defaults there reproduce the literals
# this replaced -- r"\b(?:subclause\s+)?(\d{1,2}\.\d{1,2})\b" and "subclause".
import sys as _sys  # noqa: E402
import os as _os  # noqa: E402

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import corpus_config as _corpus  # noqa: E402

_PROVISION_RE = _corpus.PROVISION_RE


def detect_provision_id(text: str) -> str | None:
    """Find the subclause identifier the input section is about.

    Prefers the first match, which in the corpus format is the clause being stated
    rather than a cross-reference to another clause.
    """
    match = _PROVISION_RE.search(text)
    return match.group(1) if match else None


def provision_key(provision_id: str) -> str:
    """Graph key for a subclause, matching how build_graph stored :Provision nodes."""
    ident = provision_id.strip().lower()
    prefix = _corpus.PROVISION_KEY_PREFIX
    if prefix and not ident.startswith(prefix):
        ident = "%s %s" % (prefix, ident)
    return normalise_mention(ident)[0]
