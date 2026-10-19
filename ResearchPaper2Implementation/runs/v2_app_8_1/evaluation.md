# Evaluation: Cross-border disclosure of personal information

Source: `runs\v2_app_8_1\generated.feature`  
Generated: 2026-08-28T02:16:40.885271+10:00

| Classification | Count | Meaning |
|---|---|---|
| Satisfied (2016) | 0 | Satisfied by the 2016 policy. |
| Gap later closed | 0 | Not satisfied in 2016 but satisfied in 2026 - a real gap that was later closed, which also corroborates the test case. |
| Needs review | 1 | Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review. |

## 1. [REVIEW] Ensure overseas recipient does not breach Australian Privacy Principles

Tags: @s8-1 @ensure-non-breach

Derives from: *the entity must take such steps as are reasonable in the circumstances to ensure that the overseas recipient does not breach the Australian Privacy Principles*

```gherkin
@s8-1 @ensure-non-breach
Scenario: Ensure overseas recipient does not breach Australian Privacy Principles
  Derives from: the entity must take such steps as are reasonable in the circumstances to ensure that the overseas recipient does not breach the Australian Privacy Principles
  Given the entity discloses personal information to an overseas recipient
  Then the privacy policy states that the entity takes reasonable steps to ensure the overseas recipient does not breach the Australian Privacy Principles in relation to the information.
```

**2016 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state that Microsoft takes reasonable steps to ensure that overseas recipients do not breach the Australian Privacy Principles in relation to the information.

_No supporting passage cited._

**2026 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state that Microsoft takes reasonable steps to ensure that overseas recipients do not breach the Australian Privacy Principles in relation to the information disclosed.

_No supporting passage cited._

**Classification: red_cross** — Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review.

---
