# Evaluation: Security of Personal Information

Source: `runs\v2_app_11_1\generated.feature`  
Generated: 2026-08-28T02:17:01.729262+10:00

| Classification | Count | Meaning |
|---|---|---|
| Satisfied (2016) | 5 | Satisfied by the 2016 policy. |
| Gap later closed | 0 | Not satisfied in 2016 but satisfied in 2026 - a real gap that was later closed, which also corroborates the test case. |
| Needs review | 1 | Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review. |

## 1. [PASS] Protecting personal information from misuse

Tags: @s11-1 @protect-personal-information

Derives from: *the entity must take such steps as are reasonable in the circumstances to protect the information from misuse*

```gherkin
@s11-1 @protect-personal-information
Scenario: Protecting personal information from misuse
  Derives from: the entity must take such steps as are reasonable in the circumstances to protect the information from misuse
  Given the entity holds personal information
  When the entity processes this information
  Then the privacy policy states that the entity takes reasonable steps to protect personal information from misuse.
```

**2016 policy — satisfied** (high confidence)

The policy explicitly states that Microsoft takes steps to protect personal data from unauthorized access, use, or disclosure, which aligns with the requirement to take reasonable steps to protect personal information from misuse.

> Microsoft is committed to protecting the security of your personal data. We use a variety of security technologies and procedures to help protect your personal data from unauthorized access, use or disclosure.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 2. [PASS] Protecting personal information from interference

Tags: @s11-1 @protect-personal-information

Derives from: *the entity must take such steps as are reasonable in the circumstances to protect the information from interference*

```gherkin
@s11-1 @protect-personal-information
Scenario: Protecting personal information from interference
  Derives from: the entity must take such steps as are reasonable in the circumstances to protect the information from interference
  Given the entity holds personal information
  When the entity processes this information
  Then the privacy policy states that the entity takes reasonable steps to protect personal information from interference.
```

**2016 policy — satisfied** (high confidence)

The policy explicitly states that Microsoft takes steps to protect personal data from unauthorized access, which aligns with the requirement to protect personal information from interference.

> Microsoft is committed to protecting the security of your personal data. We use a variety of security technologies and procedures to help protect your personal data from unauthorized access, use or disclosure.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 3. [PASS] Protecting personal information from loss

Tags: @s11-1 @protect-personal-information

Derives from: *the entity must take such steps as are reasonable in the circumstances to protect the information from loss*

```gherkin
@s11-1 @protect-personal-information
Scenario: Protecting personal information from loss
  Derives from: the entity must take such steps as are reasonable in the circumstances to protect the information from loss
  Given the entity holds personal information
  When the entity processes this information
  Then the privacy policy states that the entity takes reasonable steps to protect personal information from loss.
```

**2016 policy — satisfied** (high confidence)

The policy explicitly states that Microsoft takes steps to protect personal data, which aligns with the requirement to take reasonable steps to protect personal information from loss.

> Microsoft is committed to protecting the security of your personal data. We use a variety of security technologies and procedures to help protect your personal data from unauthorized access, use or disclosure.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 4. [PASS] Protecting personal information from unauthorized access

Tags: @s11-1 @protect-personal-information

Derives from: *the entity must take such steps as are reasonable in the circumstances to protect the information from unauthorised access*

```gherkin
@s11-1 @protect-personal-information
Scenario: Protecting personal information from unauthorized access
  Derives from: the entity must take such steps as are reasonable in the circumstances to protect the information from unauthorised access
  Given the entity holds personal information
  When the entity processes this information
  Then the privacy policy states that the entity takes reasonable steps to protect personal information from unauthorized access.
```

**2016 policy — satisfied** (high confidence)

The policy explicitly states that Microsoft takes steps to protect personal data from unauthorized access, which satisfies the requirement of the test case.

> Microsoft is committed to protecting the security of your personal data. We use a variety of security technologies and procedures to help protect your personal data from unauthorized access, use or disclosure.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 5. [REVIEW] Protecting personal information from modification

Tags: @s11-1 @protect-personal-information

Derives from: *the entity must take such steps as are reasonable in the circumstances to protect the information from modification*

```gherkin
@s11-1 @protect-personal-information
Scenario: Protecting personal information from modification
  Derives from: the entity must take such steps as are reasonable in the circumstances to protect the information from modification
  Given the entity holds personal information
  When the entity processes this information
  Then the privacy policy states that the entity takes reasonable steps to protect personal information from modification.
```

**2016 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state that Microsoft takes reasonable steps to protect personal information from modification. It lacks any mention of measures specifically aimed at preventing modification of personal data.

_No supporting passage cited._

**2026 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state that Microsoft takes reasonable steps to protect personal information from modification.

_No supporting passage cited._

**Classification: red_cross** — Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review.

---

## 6. [PASS] Protecting personal information from disclosure

Tags: @s11-1 @protect-personal-information

Derives from: *the entity must take such steps as are reasonable in the circumstances to protect the information from disclosure*

```gherkin
@s11-1 @protect-personal-information
Scenario: Protecting personal information from disclosure
  Derives from: the entity must take such steps as are reasonable in the circumstances to protect the information from disclosure
  Given the entity holds personal information
  When the entity processes this information
  Then the privacy policy states that the entity takes reasonable steps to protect personal information from disclosure.
```

**2016 policy — satisfied** (high confidence)

The policy explicitly states that Microsoft takes steps to protect personal data from unauthorized access, use, or disclosure, which satisfies the requirement.

> Microsoft is committed to protecting the security of your personal data. We use a variety of security technologies and procedures to help protect your personal data from unauthorized access, use or disclosure.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---
