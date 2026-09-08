"""Judge a single Gherkin scenario against a privacy policy.

The whole policy goes into the prompt -- 23k tokens for the 2016 statement, 37k for
2026, both well inside the context window -- so there is no retrieval layer over the
policy to introduce its own recall errors.

Every verdict must carry a verbatim quote from the policy. That quote is then checked
against the policy text programmatically, so a fabricated citation is caught rather than
trusted. A verdict whose evidence cannot be located is marked unverified and should not
be relied on without reading it yourself.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from kg_testgen.config import Config, Secrets
from .gherkin import Scenario
from kg_testgen.llm import MAX_ATTEMPTS, LLMError

logger = logging.getLogger(__name__)

SATISFIED = "satisfied"
NOT_SATISFIED = "not_satisfied"

JUDGE_PROMPT = """\
You are auditing a company's published privacy policy against a single compliance test
case derived from privacy legislation.

Decide whether the policy SATISFIES the requirement asserted in the test case's Then
step(s). Judge only what the policy actually says. Do not credit the policy for
requirements it does not address, and do not infer commitments from silence.

A requirement is "satisfied" only if the policy explicitly states, discloses, or commits
to what the Then step asserts. If the policy is silent, vague, or addresses a different
matter, the verdict is "not_satisfied".

--------------------------------------------------------------------------------
PRIVACY POLICY ({policy_label})
--------------------------------------------------------------------------------
{policy_text}

--------------------------------------------------------------------------------
TEST CASE
--------------------------------------------------------------------------------
{scenario_text}

The requirement being tested is asserted by these step(s):
{assertion_steps}

--------------------------------------------------------------------------------
RESPONSE FORMAT
--------------------------------------------------------------------------------
Respond with a single JSON object and nothing else:

{{
  "verdict": "satisfied" or "not_satisfied",
  "confidence": "high" or "medium" or "low",
  "evidence_quote": "a VERBATIM span copied exactly from the policy above that most \
directly supports your verdict, or an empty string if the policy says nothing relevant",
  "reasoning": "one or two sentences explaining the verdict"
}}

The evidence_quote must be copied character-for-character from the policy text. Do not
paraphrase it, do not add ellipses, do not correct its punctuation. It will be checked
against the policy automatically.\
"""


@dataclass
class PolicyVerdict:
    policy_label: str
    verdict: str
    confidence: str = "unknown"
    evidence_quote: str = ""
    reasoning: str = ""
    evidence_verified: bool = False
    parse_error: Optional[str] = None

    @property
    def evidence_status(self) -> str:
        """Three distinct states -- an absent citation is not a failed one.

        'no_quote' is expected and correct for a not_satisfied verdict; 'unverified'
        means a quote WAS given but could not be found in the policy, which is the
        fabrication signal.
        """
        if not self.evidence_quote.strip():
            return "no_quote"
        return "verified" if self.evidence_verified else "unverified"

    def as_dict(self) -> dict:
        return {
            "policy_label": self.policy_label, "verdict": self.verdict,
            "confidence": self.confidence, "evidence_quote": self.evidence_quote,
            "reasoning": self.reasoning, "evidence_verified": self.evidence_verified,
            "evidence_status": self.evidence_status,
            "parse_error": self.parse_error,
        }


def _normalise_for_match(text: str) -> str:
    """Collapse whitespace and quote styles so a genuine quote still matches."""
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("—", "-").replace("–", "-").replace("‑", "-")
    return re.sub(r"\s+", " ", text).strip().lower()


def verify_evidence(quote: str, policy_text: str) -> bool:
    """Confirm the cited span really appears in the policy."""
    if not quote.strip():
        return False
    return _normalise_for_match(quote) in _normalise_for_match(policy_text)


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_response(text: str, policy_label: str) -> PolicyVerdict:
    match = _JSON_RE.search(text or "")
    if not match:
        return PolicyVerdict(policy_label=policy_label, verdict=NOT_SATISFIED,
                             parse_error="no JSON object in response: %r" % (text or "")[:200])
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        return PolicyVerdict(policy_label=policy_label, verdict=NOT_SATISFIED,
                             parse_error="invalid JSON (%s): %r" % (exc, match.group(0)[:200]))

    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in (SATISFIED, NOT_SATISFIED):
        return PolicyVerdict(policy_label=policy_label, verdict=NOT_SATISFIED,
                             parse_error="unrecognised verdict %r" % data.get("verdict"))

    return PolicyVerdict(
        policy_label=policy_label,
        verdict=verdict,
        confidence=str(data.get("confidence", "unknown")).strip().lower(),
        evidence_quote=str(data.get("evidence_quote", "")),
        reasoning=str(data.get("reasoning", "")).strip(),
    )


def judge(scenario: Scenario, policy_text: str, policy_label: str,
          config: Config, secrets: Secrets) -> PolicyVerdict:
    """One LLM call: does this policy satisfy this scenario's assertion?"""
    from openai import OpenAI

    assertions = scenario.assertion_steps() or scenario.steps
    prompt = JUDGE_PROMPT.format(
        policy_label=policy_label,
        policy_text=policy_text,
        scenario_text=scenario.as_text(),
        assertion_steps="\n".join("  " + s for s in assertions),
    )

    client = OpenAI(api_key=secrets.llm_api_key)
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            completion = client.chat.completions.create(
                model=config.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=config.temperature,
                max_tokens=800,
                response_format={"type": "json_object"},
            )
            result = _parse_response(completion.choices[0].message.content, policy_label)
            result.evidence_verified = verify_evidence(result.evidence_quote, policy_text)
            if result.evidence_quote and not result.evidence_verified:
                logger.warning("    evidence quote NOT found in %s policy -- treat with "
                               "caution: %r", policy_label, result.evidence_quote[:80])
            return result
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("    judge call failed (attempt %d/%d): %s",
                           attempt, MAX_ATTEMPTS, exc)
    raise LLMError("policy judge failed after %d attempts: %s" % (MAX_ATTEMPTS, last_error))
