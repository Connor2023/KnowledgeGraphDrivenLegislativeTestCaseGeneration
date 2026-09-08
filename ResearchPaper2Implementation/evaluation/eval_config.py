"""Loader for eval_config.yaml -- the evaluation counterpart to corpus_config.

Deliberately shaped like corpus_config: defaults that reproduce the previous hard-coded
constants exactly, a file that overrides them, and no failure at import time if PyYAML
is missing. A long judging run should not die because a config file was malformed.

One difference from corpus_config. Its paths resolve against the module, because the
construction scripts are run from several directories. These resolve against the current
working directory, because the evaluation modules read and write `runs/`, `sections/`
and `elements/` and are documented as being run from the repository root. Resolving them
against this file would silently keep working while writing results somewhere else.
"""

from __future__ import annotations

import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_config.yaml")

# Mirrors eval_config.yaml, and matches the constants these values replaced.
_DEFAULTS = {
    "name": "app_schedule1_experiment",
    "description": "Measurement inputs for the 7-arm comparison",
    "elements": os.path.join("elements", "legal_elements.yaml"),
    "statute": "APPschedule1.txt",
    "manual_cases": os.path.join("testcasecomparison", "Test cases FYP.docx"),
    "policies": {
        "2016": os.path.join("..", "MicrosoftPrivacyPolicy", "2016.txt"),
        "2026": os.path.join("..", "MicrosoftPrivacyPolicy", "2026.txt"),
    },
    "output": {
        "elements": "runs/elements",
        "soundness": "runs/soundness",
        "experiment": "runs/experiment",
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
    except Exception:  # noqa: BLE001 - a malformed config must not kill a scoring run
        return _DEFAULTS
    merged = dict(_DEFAULTS)
    merged.update({k: v for k, v in loaded.items() if k not in ("policies", "output")})
    for section in ("policies", "output"):
        merged[section] = dict(_DEFAULTS[section])
        merged[section].update(loaded.get(section) or {})
    return merged


_CFG = _load()

NAME = _CFG["name"]
DESCRIPTION = _CFG["description"]
ELEMENTS_PATH = _CFG["elements"]
STATUTE_PATH = _CFG["statute"]
MANUAL_CASES_PATH = _CFG["manual_cases"]
POLICY_2016 = _CFG["policies"]["2016"]
POLICY_2026 = _CFG["policies"]["2026"]
ELEMENTS_OUT_DIR = _CFG["output"]["elements"]
SOUNDNESS_OUT_DIR = _CFG["output"]["soundness"]
EXPERIMENT_OUT_DIR = _CFG["output"]["experiment"]


def summary() -> str:
    return ("evaluation config %r (%s)\n  elements     : %s\n  statute      : %s\n"
            "  manual cases : %s\n  policies     : %s, %s"
            % (NAME, DESCRIPTION, ELEMENTS_PATH, STATUTE_PATH, MANUAL_CASES_PATH,
               POLICY_2016, POLICY_2026))


if __name__ == "__main__":
    print(summary())
