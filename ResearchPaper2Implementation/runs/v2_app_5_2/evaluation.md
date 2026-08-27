# Evaluation: Notification of the collection of personal information

Source: `runs\v2_app_5_2\generated.feature`  
Generated: 2026-08-28T02:14:00.687610+10:00

| Classification | Count | Meaning |
|---|---|---|
| Satisfied (2016) | 7 | Satisfied by the 2016 policy. |
| Gap later closed | 0 | Not satisfied in 2016 but satisfied in 2026 - a real gap that was later closed, which also corroborates the test case. |
| Needs review | 4 | Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review. |

## 1. [PASS] The privacy policy must disclose the identity and contact details of the APP entity.

Tags: @s5-2 @identity-and-contact-details

Derives from: *the identity and contact details of the APP entity*

```gherkin
@s5-2 @identity-and-contact-details
Scenario: The privacy policy must disclose the identity and contact details of the APP entity.
  Derives from: the identity and contact details of the APP entity
  Given the APP entity is collecting personal information
  When an individual reviews the privacy policy
  Then the privacy policy states the identity and contact details of the APP entity
```

**2016 policy — satisfied** (high confidence)

The policy explicitly states the identity of the APP entity as Microsoft Corporation and provides its contact details, including address and telephone number.

> Unless otherwise stated, Microsoft Corporation is a data controller for personal data we collect through the services subject to this statement. Our address is Microsoft Privacy, Microsoft Corporation, One Microsoft Way, Redmond, Washington 98052, USA. Telephone: (+1) 425-882-8080.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 2. [PASS] The privacy policy must disclose if personal information is collected from someone other than the individual.

Tags: @s5-2 @collection-from-third-party

Derives from: *if the APP entity collects the personal information from someone other than the individual*

```gherkin
@s5-2 @collection-from-third-party
Scenario: The privacy policy must disclose if personal information is collected from someone other than the individual.
  Derives from: if the APP entity collects the personal information from someone other than the individual
  Given the APP entity is collecting personal information
  When an individual reviews the privacy policy
  Then the privacy policy states whether personal information is collected from someone other than the individual
```

**2016 policy — satisfied** (high confidence)

The policy explicitly states that personal information is collected from third parties, thereby satisfying the requirement.

> We also obtain data from third parties (including other companies). For example, we supplement the data we collect by purchasing demographic data from other companies.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 3. [PASS] The privacy policy must disclose the fact that personal information has been collected and the circumstances of that collection.

Tags: @s5-2 @fact-of-collection

Derives from: *the fact that the entity so collects, or has collected, the information and the circumstances of that collection*

```gherkin
@s5-2 @fact-of-collection
Scenario: The privacy policy must disclose the fact that personal information has been collected and the circumstances of that collection.
  Derives from: the fact that the entity so collects, or has collected, the information and the circumstances of that collection
  Given the APP entity has collected personal information
  When an individual reviews the privacy policy
  Then the privacy policy states that personal information has been collected and describes the circumstances of that collection
```

**2016 policy — satisfied** (high confidence)

The policy explicitly states that Microsoft collects personal data, fulfilling the requirement to disclose that personal information has been collected. It also describes the circumstances of that collection by indicating it is for operating and improving services.

> Microsoft collects data to operate effectively and provide you the best experiences with our services.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 4. [REVIEW] The privacy policy must disclose if the collection of personal information is required or authorised by Australian law or a court/tribunal order.

Tags: @s5-2 @collection-authorised-by-law

Derives from: *if the collection of the personal information is required or authorised by or under an Australian law or a court/tribunal order*

```gherkin
@s5-2 @collection-authorised-by-law
Scenario: The privacy policy must disclose if the collection of personal information is required or authorised by Australian law or a court/tribunal order.
  Derives from: if the collection of the personal information is required or authorised by or under an Australian law or a court/tribunal order
  Given the APP entity is collecting personal information
  When an individual reviews the privacy policy
  Then the privacy policy states whether the collection is required or authorised by Australian law or a court/tribunal order
```

**2016 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state whether the collection of personal information is required or authorised by Australian law or a court/tribunal order.

_No supporting passage cited._

**2026 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state whether the collection of personal information is required or authorised by Australian law or a court/tribunal order.

_No supporting passage cited._

**Classification: red_cross** — Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review.

---

## 5. [PASS] The privacy policy must disclose the purposes for which personal information is collected.

Tags: @s5-2 @purposes-of-collection

Derives from: *the purposes for which the APP entity collects the personal information*

```gherkin
@s5-2 @purposes-of-collection
Scenario: The privacy policy must disclose the purposes for which personal information is collected.
  Derives from: the purposes for which the APP entity collects the personal information
  Given the APP entity is collecting personal information
  When an individual reviews the privacy policy
  Then the privacy policy states the purposes for which personal information is collected
```

**2016 policy — satisfied** (high confidence)

The policy explicitly states the purposes for which personal information is collected, fulfilling the requirement of the test case.

> Microsoft uses the data we collect for three basic purposes, described in more detail below: (1) to operate our business and provide (including improving and personalizing) the services we offer, (2) to send communications, including promotional communications, and (3) to display advertising.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 6. [REVIEW] The privacy policy must disclose the main consequences for the individual if personal information is not collected.

Tags: @s5-2 @consequences-of-non-collection

Derives from: *the main consequences (if any) for the individual if all or some of the personal information is not collected by the APP entity*

```gherkin
@s5-2 @consequences-of-non-collection
Scenario: The privacy policy must disclose the main consequences for the individual if personal information is not collected.
  Derives from: the main consequences (if any) for the individual if all or some of the personal information is not collected by the APP entity
  Given the APP entity is collecting personal information
  When an individual reviews the privacy policy
  Then the privacy policy states the main consequences for the individual if personal information is not collected
```

**2016 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state the main consequences for the individual if personal information is not collected, making the requirement not satisfied.

_No supporting passage cited._

**2026 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state the main consequences for the individual if personal information is not collected, thus failing to satisfy the requirement.

_No supporting passage cited._

**Classification: red_cross** — Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review.

---

## 7. [PASS] The privacy policy must disclose any other entities to which personal information is usually disclosed.

Tags: @s5-2 @disclosure-to-third-parties

Derives from: *any other APP entity, body or person, or the types of any other APP entities, bodies or persons, to which the APP entity usually discloses personal information of the kind collected by the entity*

```gherkin
@s5-2 @disclosure-to-third-parties
Scenario: The privacy policy must disclose any other entities to which personal information is usually disclosed.
  Derives from: any other APP entity, body or person, or the types of any other APP entities, bodies or persons, to which the APP entity usually discloses personal information of the kind collected by the entity
  Given the APP entity is collecting personal information
  When an individual reviews the privacy policy
  Then the privacy policy states the types of entities to which personal information is usually disclosed
```

**2016 policy — satisfied** (high confidence)

The policy explicitly states that personal data is shared with Microsoft-controlled affiliates, subsidiaries, and vendors or agents, thus satisfying the requirement to disclose the types of entities to which personal information is usually disclosed.

> In addition, we share personal data among Microsoft-controlled affiliates and subsidiaries. We also share personal data with vendors or agents working on our behalf for the purposes described in this statement.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 8. [PASS] The privacy policy must contain information about how the individual may access and correct their personal information.

Tags: @s5-2 @access-and-correction

Derives from: *that the APP privacy policy of the APP entity contains information about how the individual may access the personal information about the individual that is held by the entity and seek the correction of such information*

```gherkin
@s5-2 @access-and-correction
Scenario: The privacy policy must contain information about how the individual may access and correct their personal information.
  Derives from: that the APP privacy policy of the APP entity contains information about how the individual may access the personal information about the individual that is held by the entity and seek the correction of such information
  Given the APP entity holds personal information about the individual
  When an individual reviews the privacy policy
  Then the privacy policy states how the individual may access and correct their personal information
```

**2016 policy — satisfied** (high confidence)

The policy explicitly states that individuals can view or edit their personal data, which satisfies the requirement for accessing and correcting personal information.

> You can view or edit your personal data online for many Microsoft services.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 9. [REVIEW] The privacy policy must contain information about how the individual may complain about a breach of the Australian Privacy Principles.

Tags: @s5-2 @complaints-process

Derives from: *that the APP privacy policy of the APP entity contains information about how the individual may complain about a breach of the Australian Privacy Principles*

```gherkin
@s5-2 @complaints-process
Scenario: The privacy policy must contain information about how the individual may complain about a breach of the Australian Privacy Principles.
  Derives from: that the APP privacy policy of the APP entity contains information about how the individual may complain about a breach of the Australian Privacy Principles
  Given the APP entity is subject to the Australian Privacy Principles
  When an individual reviews the privacy policy
  Then the privacy policy states how the individual may complain about a breach of the Australian Privacy Principles
```

**2016 policy — not_satisfied** (high confidence)

The privacy policy does not contain any information about how an individual may complain about a breach of the Australian Privacy Principles.

_No supporting passage cited._

**2026 policy — not_satisfied** (high confidence)

The privacy policy does not contain any information about how an individual may complain about a breach of the Australian Privacy Principles.

_No supporting passage cited._

**Classification: red_cross** — Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review.

---

## 10. [PASS] The privacy policy must disclose whether personal information is likely to be disclosed to overseas recipients.

Tags: @s5-2 @disclosure-to-overseas-recipients

Derives from: *whether the APP entity is likely to disclose the personal information to overseas recipients*

```gherkin
@s5-2 @disclosure-to-overseas-recipients
Scenario: The privacy policy must disclose whether personal information is likely to be disclosed to overseas recipients.
  Derives from: whether the APP entity is likely to disclose the personal information to overseas recipients
  Given the APP entity is collecting personal information
  When an individual reviews the privacy policy
  Then the privacy policy states whether personal information is likely to be disclosed to overseas recipients
```

**2016 policy — satisfied** (high confidence)

The policy explicitly states that personal data may be stored and processed in various countries, indicating that it is likely to be disclosed to overseas recipients.

> Personal data collected by Microsoft may be stored and processed in your region, in the United States or in any other country where Microsoft or its affiliates, subsidiaries or service providers maintain facilities.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 11. [REVIEW] The privacy policy must specify the countries where overseas recipients are likely to be located if practicable.

Tags: @s5-2 @countries-of-overseas-recipients

Derives from: *if it is practicable to specify those countries in the notification or to otherwise make the individual aware of them*

```gherkin
@s5-2 @countries-of-overseas-recipients
Scenario: The privacy policy must specify the countries where overseas recipients are likely to be located if practicable.
  Derives from: if it is practicable to specify those countries in the notification or to otherwise make the individual aware of them
  Given the APP entity is likely to disclose personal information to overseas recipients
  When an individual reviews the privacy policy
  Then the privacy policy states the countries where overseas recipients are likely to be located if practicable
```

**2016 policy — not_satisfied** (high confidence)

The privacy policy does not specify any countries where overseas recipients are likely to be located, nor does it indicate that it is practicable to do so.

_No supporting passage cited._

**2026 policy — not_satisfied** (high confidence)

The privacy policy does not specify any countries where overseas recipients are likely to be located, nor does it indicate that it is practicable to do so.

_No supporting passage cited._

**Classification: red_cross** — Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review.

---
