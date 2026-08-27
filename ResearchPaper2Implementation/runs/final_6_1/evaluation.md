# Evaluation: Use or disclosure of personal information under Australian Privacy Principle 6

Source: `runs\final_6_1\generated.feature`  
Generated: 2026-08-28T02:01:35.987656+10:00

| Classification | Count | Meaning |
|---|---|---|
| Satisfied (2016) | 0 | Satisfied by the 2016 policy. |
| Gap later closed | 0 | Not satisfied in 2016 but satisfied in 2026 - a real gap that was later closed, which also corroborates the test case. |
| Needs review | 3 | Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review. |

## 1. [REVIEW] Prohibition on using or disclosing personal information for a secondary purpose

Tags: @s6-1 @prohibit-secondary-use

Derives from: *the entity must not use or disclose the information for another purpose (the secondary purpose)*

```gherkin
@s6-1 @prohibit-secondary-use
Scenario: Prohibition on using or disclosing personal information for a secondary purpose
  Derives from: the entity must not use or disclose the information for another purpose (the secondary purpose)
  Given an APP entity holds personal information about an individual
  When the personal information was collected for a primary purpose
  Then the privacy policy states that the entity must not use or disclose the information for a secondary purpose unless certain conditions are met
```

**2016 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state that the entity must not use or disclose personal information for a secondary purpose unless certain conditions are met. It lacks the necessary language to satisfy the requirement.

_No supporting passage cited._

**2026 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state that the entity must not use or disclose personal information for a secondary purpose unless certain conditions are met. It lacks the necessary language to satisfy the requirement.

_No supporting passage cited._

**Classification: red_cross** — Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review.

---

## 2. [REVIEW] Requirement for individual consent for secondary use or disclosure

Tags: @s6-1 @require-consent

Derives from: *unless the individual has consented to the use or disclosure of the information*

```gherkin
@s6-1 @require-consent
Scenario: Requirement for individual consent for secondary use or disclosure
  Derives from: unless the individual has consented to the use or disclosure of the information
  Given an APP entity holds personal information about an individual
  When the entity intends to use or disclose the information for a secondary purpose
  Then the privacy policy states that the entity requires the individual's consent for such use or disclosure
```

**2016 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state that the entity requires the individual's consent for secondary use or disclosure of personal information.

_No supporting passage cited._

**2026 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state that the entity requires the individual's consent for secondary use or disclosure of personal information.

_No supporting passage cited._

**Classification: red_cross** — Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review.

---

## 3. [REVIEW] Application of subclauses for secondary use or disclosure

Tags: @s6-1 @apply-subclauses

Derives from: *unless subclause 6.2 or 6.3 applies in relation to the use or disclosure of the information*

```gherkin
@s6-1 @apply-subclauses
Scenario: Application of subclauses for secondary use or disclosure
  Derives from: unless subclause 6.2 or 6.3 applies in relation to the use or disclosure of the information
  Given an APP entity holds personal information about an individual
  When the entity considers using or disclosing the information for a secondary purpose
  Then the privacy policy states the conditions under which subclauses 6.2 or 6.3 apply to the use or disclosure of the information
```

**2016 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state the conditions under which subclauses 6.2 or 6.3 apply to the use or disclosure of personal information for secondary purposes.

_No supporting passage cited._

**2026 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state the conditions under which subclauses 6.2 or 6.3 apply to the use or disclosure of personal information for secondary purposes.

_No supporting passage cited._

**Classification: red_cross** — Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review.

---
