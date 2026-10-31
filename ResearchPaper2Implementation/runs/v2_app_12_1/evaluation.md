# Evaluation: Access to personal information

Source: `runs\v2_app_12_1\generated.feature`  
Generated: 2026-08-28T02:17:51.343781+10:00

| Classification | Count | Meaning |
|---|---|---|
| Satisfied (2016) | 1 | Satisfied by the 2016 policy. |
| Gap later closed | 0 | Not satisfied in 2016 but satisfied in 2026 - a real gap that was later closed, which also corroborates the test case. |
| Needs review | 1 | Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review. |

## 1. [PASS] Individual requests access to personal information

Tags: @s12-1 @access-to-personal-information

Derives from: *the entity must, on request by the individual, give the individual access to the information.*

```gherkin
@s12-1 @access-to-personal-information
Scenario: Individual requests access to personal information
  Derives from: the entity must, on request by the individual, give the individual access to the information.
  Given the entity holds personal information about the individual
  When the individual requests access to their personal information
  Then the privacy policy states that the individual will be given access to their personal information upon request
```

**2016 policy — satisfied** (high confidence)

The policy explicitly states that individuals can view or edit their personal data, which implies access to their personal information upon request.

> you can view or edit your personal data online for many Microsoft services.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 2. [REVIEW] No charge for access request

Tags: @s12-1 @no-charge-for-access

Derives from: *the entity must not charge for making of the request.*

```gherkin
@s12-1 @no-charge-for-access
Scenario: No charge for access request
  Derives from: the entity must not charge for making of the request.
  Given the individual requests access to their personal information
  When the individual makes the request
  Then the privacy policy states that the individual will not be charged for making the request
```

**2016 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state that individuals will not be charged for making a request to access their personal information.

_No supporting passage cited._

**2026 policy — not_satisfied** (high confidence)

The privacy policy does not mention anything about charging individuals for making a request to access their personal information.

_No supporting passage cited._

**Classification: red_cross** — Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review.

---
