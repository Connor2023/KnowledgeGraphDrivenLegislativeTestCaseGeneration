# Evaluation: Use or disclosure of personal information

Source: `runs\v2_app_6_1\generated.feature`  
Generated: 2026-08-28T02:16:06.585049+10:00

| Classification | Count | Meaning |
|---|---|---|
| Satisfied (2016) | 0 | Satisfied by the 2016 policy. |
| Gap later closed | 0 | Not satisfied in 2016 but satisfied in 2026 - a real gap that was later closed, which also corroborates the test case. |
| Needs review | 2 | Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review. |

## 1. [REVIEW] Prohibition on using personal information for secondary purposes

Tags: @s6-1 @prohibit-secondary-use

Derives from: *the entity must not use or disclose the information for another purpose (the secondary purpose) unless the individual has consented*

```gherkin
@s6-1 @prohibit-secondary-use
Scenario: Prohibition on using personal information for secondary purposes
  Derives from: the entity must not use or disclose the information for another purpose (the secondary purpose) unless the individual has consented
  Given the APP entity holds personal information about an individual
  When the personal information was collected for a particular purpose
  Then the privacy policy states that the personal information will not be used for another purpose without the individual's consent
```

**2016 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state that personal information will not be used for another purpose without the individual's consent. It discusses data usage but does not address the prohibition on secondary use without consent.

_No supporting passage cited._

**2026 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state that personal information will not be used for another purpose without the individual's consent. It lacks a clear commitment regarding the prohibition of secondary use of personal information.

_No supporting passage cited._

**Classification: red_cross** — Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review.

---

## 2. [REVIEW] Requirement for consent to use personal information for secondary purposes

Tags: @s6-1 @consent-for-secondary-use

Derives from: *the entity must not use or disclose the information for another purpose... unless the individual has consented*

```gherkin
@s6-1 @consent-for-secondary-use
Scenario: Requirement for consent to use personal information for secondary purposes
  Derives from: the entity must not use or disclose the information for another purpose... unless the individual has consented
  Given the APP entity holds personal information about an individual
  When the personal information was collected for a particular purpose
  Then the privacy policy states that the entity will obtain the individual's consent before using the personal information for a secondary purpose
```

**2016 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state that the entity will obtain the individual's consent before using personal information for a secondary purpose. It discusses data usage but does not address consent for secondary uses.

_No supporting passage cited._

**2026 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state that the entity will obtain the individual's consent before using personal information for a secondary purpose.

_No supporting passage cited._

**Classification: red_cross** — Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review.

---
