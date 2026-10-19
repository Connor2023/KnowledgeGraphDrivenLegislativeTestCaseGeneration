# Evaluation: APP Privacy Policy Requirements

Source: `runs\v2_app_1_4\generated.feature`  
Generated: 2026-08-28T02:13:01.091544+10:00

| Classification | Count | Meaning |
|---|---|---|
| Satisfied (2016) | 5 | Satisfied by the 2016 policy. |
| Gap later closed | 0 | Not satisfied in 2016 but satisfied in 2026 - a real gap that was later closed, which also corroborates the test case. |
| Needs review | 4 | Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review. |

## 1. [PASS] The privacy policy must disclose the kinds of personal information collected

Tags: @s1-4 @collect-personal-information

Derives from: *the kinds of personal information that the entity collects and holds*

```gherkin
@s1-4 @collect-personal-information
Scenario: The privacy policy must disclose the kinds of personal information collected
  Derives from: the kinds of personal information that the entity collects and holds
  Given the APP entity has a privacy policy
  Then the privacy policy states the kinds of personal information that the entity collects and holds
```

**2016 policy — satisfied** (high confidence)

The policy explicitly lists various types of personal information collected, including name, contact data, credentials, demographic data, interests, payment data, usage data, contacts, location data, and content, thereby satisfying the requirement.

> The data we collect depends on the services and features you use, and includes the following. Name and contact data. We collect your first and last name, email address, postal address, phone number, and other similar contact data. Credentials. We collect passwords, password hints, and similar security information used for authentication and account access. Demographic data. We collect data about you such as your age, gender, country and preferred language. Interests and favorites. We collect data about your interests and favorites, such as the teams you follow in a sports app, the stocks you track in a finance app, or the favorite cities you add to a weather app. In addition to those you explicitly provide, your interests and favorites may also be inferred or derived from other data we collect. Payment data. We collect data necessary to process your payment if you make purchases, such as your payment instrument number (such as a credit card number), and the security code associated with your payment instrument. Usage data. We collect data about how you and your device interact with our services. This includes data, such as the features you use, the items you purchase, the web pages you visit, and the search terms you enter. This also includes data about your device and the network you use to connect to our services, including IP address, device identifiers (such as the IMEI number for phones), regional and language settings. It includes information about the operating systems and other software installed on your device, including product keys. And it includes data about the performance of the services and any problems you experience with them. Contacts and relationships. We collect data about your contacts and relationships if you use a Microsoft service to manage contacts, or to communicate or interact with other people or organizations. Location data. We collect data about your location, which can be either precise or imprecise. Precise location data can be Global Position System (GPS) data, as well as data identifying nearby cell towers and Wi-Fi hotspots, we collect when you enable location-based services or features. Imprecise location data includes, for example, a location derived from your IP address or data that indicates where you are located with less precision, such as at a city or postal code level. Content. We collect content of your files and communications when necessary to provide you with the services you use.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 2. [PASS] The privacy policy must explain how personal information is collected and held

Tags: @s1-4 @collection-methods

Derives from: *how the entity collects and holds personal information*

```gherkin
@s1-4 @collection-methods
Scenario: The privacy policy must explain how personal information is collected and held
  Derives from: how the entity collects and holds personal information
  Given the APP entity has a privacy policy
  Then the privacy policy explains how the entity collects and holds personal information
```

**2016 policy — satisfied** (high confidence)

The policy explicitly explains how personal information is collected by detailing various methods, such as creating an account, submitting queries, and uploading documents.

> Microsoft collects data to operate effectively and provide you the best experiences with our services. You provide some of this data directly, such as when you create a Microsoft account, submit a search query to Bing, speak a voice command to Cortana, upload a document to OneDrive, or contact us for support.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 3. [PASS] The privacy policy must specify the purposes for collecting personal information

Tags: @s1-4 @purposes-of-collection

Derives from: *the purposes for which the entity collects, holds, uses and discloses personal information*

```gherkin
@s1-4 @purposes-of-collection
Scenario: The privacy policy must specify the purposes for collecting personal information
  Derives from: the purposes for which the entity collects, holds, uses and discloses personal information
  Given the APP entity has a privacy policy
  Then the privacy policy states the purposes for which the entity collects, holds, uses, and discloses personal information
```

**2016 policy — satisfied** (high confidence)

The policy explicitly states the purposes for which Microsoft collects, holds, uses, and discloses personal information, thus satisfying the requirement.

> Microsoft uses the data we collect for three basic purposes, described in more detail below: (1) to operate our business and provide (including improving and personalizing) the services we offer, (2) to send communications, including promotional communications, and (3) to display advertising.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 4. [PASS] The privacy policy must outline how individuals can access their personal information

Tags: @s1-4 @access-to-personal-information

Derives from: *how an individual may access personal information about the individual that is held by the entity*

```gherkin
@s1-4 @access-to-personal-information
Scenario: The privacy policy must outline how individuals can access their personal information
  Derives from: how an individual may access personal information about the individual that is held by the entity
  Given the APP entity has a privacy policy
  Then the privacy policy explains how an individual may access personal information about themselves that is held by the entity
```

**2016 policy — satisfied** (high confidence)

The policy explicitly states that individuals can view or edit their personal data, which satisfies the requirement of explaining how they may access their personal information.

> You can view or edit your personal data online for many Microsoft services.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 5. [REVIEW] The privacy policy must describe how individuals can seek correction of their personal information

Tags: @s1-4 @correction-of-personal-information

Derives from: *how an individual may seek the correction of such information*

```gherkin
@s1-4 @correction-of-personal-information
Scenario: The privacy policy must describe how individuals can seek correction of their personal information
  Derives from: how an individual may seek the correction of such information
  Given the APP entity has a privacy policy
  Then the privacy policy explains how an individual may seek the correction of their personal information
```

**2016 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state how individuals can seek correction of their personal information.

_No supporting passage cited._

**2026 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state how individuals can seek correction of their personal information, making the requirement not satisfied.

_No supporting passage cited._

**Classification: red_cross** — Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review.

---

## 6. [REVIEW] The privacy policy must detail how individuals can complain about breaches

Tags: @s1-4 @complaints-process

Derives from: *how an individual may complain about a breach of the Australian Privacy Principles*

```gherkin
@s1-4 @complaints-process
Scenario: The privacy policy must detail how individuals can complain about breaches
  Derives from: how an individual may complain about a breach of the Australian Privacy Principles
  Given the APP entity has a privacy policy
  Then the privacy policy states how an individual may complain about a breach of the Australian Privacy Principles
```

**2016 policy — not_satisfied** (high confidence)

The privacy policy does not provide any information on how individuals may complain about a breach of the Australian Privacy Principles.

_No supporting passage cited._

**2026 policy — not_satisfied** (high confidence)

The privacy policy does not provide any information on how an individual may complain about a breach of the Australian Privacy Principles.

_No supporting passage cited._

**Classification: red_cross** — Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review.

---

## 7. [REVIEW] The privacy policy must explain how the entity will deal with complaints

Tags: @s1-4 @complaints-handling

Derives from: *how the entity will deal with such a complaint*

```gherkin
@s1-4 @complaints-handling
Scenario: The privacy policy must explain how the entity will deal with complaints
  Derives from: how the entity will deal with such a complaint
  Given the APP entity has a privacy policy
  Then the privacy policy explains how the entity will deal with complaints about breaches of the Australian Privacy Principles
```

**2016 policy — not_satisfied** (high confidence)

The privacy policy does not explain how Microsoft will deal with complaints about breaches of the Australian Privacy Principles, nor does it mention any specific process for handling such complaints.

_No supporting passage cited._

**2026 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly explain how Microsoft will deal with complaints about breaches of the Australian Privacy Principles.

_No supporting passage cited._

**Classification: red_cross** — Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review.

---

## 8. [PASS] The privacy policy must indicate if personal information is likely to be disclosed to overseas recipients

Tags: @s1-4 @disclosure-to-overseas-recipients

Derives from: *whether the entity is likely to disclose personal information to overseas recipients*

```gherkin
@s1-4 @disclosure-to-overseas-recipients
Scenario: The privacy policy must indicate if personal information is likely to be disclosed to overseas recipients
  Derives from: whether the entity is likely to disclose personal information to overseas recipients
  Given the APP entity has a privacy policy
  Then the privacy policy states whether the entity is likely to disclose personal information to overseas recipients
```

**2016 policy — satisfied** (high confidence)

The policy explicitly states that personal data may be disclosed as part of corporate transactions, which implies that such disclosures could involve overseas recipients.

> We may also disclose personal data as part of a corporate transaction such as a merger or sale of assets.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 9. [REVIEW] The privacy policy must specify the countries of overseas recipients if practicable

Tags: @s1-4 @countries-of-overseas-recipients

Derives from: *if the entity is likely to disclose personal information to overseas recipients - the countries in which such recipients are likely to be located if it is practicable to specify those countries in the policy*

```gherkin
@s1-4 @countries-of-overseas-recipients
Scenario: The privacy policy must specify the countries of overseas recipients if practicable
  Derives from: if the entity is likely to disclose personal information to overseas recipients - the countries in which such recipients are likely to be located if it is practicable to specify those countries in the policy
  Given the APP entity has a privacy policy
  Then the privacy policy specifies the countries in which overseas recipients are likely to be located, if practicable
```

**2016 policy — not_satisfied** (high confidence)

The privacy policy does not specify the countries in which overseas recipients are likely to be located, nor does it indicate any practicability in doing so.

_No supporting passage cited._

**2026 policy — not_satisfied** (high confidence)

The privacy policy does not specify the countries in which overseas recipients are likely to be located, nor does it indicate that it is practicable to do so.

_No supporting passage cited._

**Classification: red_cross** — Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review.

---
