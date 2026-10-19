# Evaluation: Judge calibration control

Source: `sections\calibration.feature`  
Generated: 2026-08-28T02:03:00.702422+10:00

| Classification | Count | Meaning |
|---|---|---|
| Satisfied (2016) | 2 | Satisfied by the 2016 policy. |
| Gap later closed | 0 | Not satisfied in 2016 but satisfied in 2026 - a real gap that was later closed, which also corroborates the test case. |
| Needs review | 1 | Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review. |

## 1. [PASS] Policy discloses what personal data is collected

Tags: @control @obviously-satisfied

Derives from: *control case - the 2016 policy plainly does this*

```gherkin
@control @obviously-satisfied
Scenario: Policy discloses what personal data is collected
  Derives from: control case - the 2016 policy plainly does this
  Given a company publishes a privacy policy
  When the company collects personal data from users
  Then the privacy policy states what personal data the company collects
```

**2016 policy — satisfied** (high confidence)

The policy explicitly states the types of personal data collected, including name, contact data, credentials, demographic data, interests, payment data, usage data, contacts, location data, and content.

> The data we collect depends on the services and features you use, and includes the following.
Name and contact data. We collect your first and last name, email address, postal address, phone number, and other similar contact data.
Credentials. We collect passwords, password hints, and similar security information used for authentication and account access.
Demographic data. We collect data about you such as your age, gender, country and preferred language.
Interests and favorites. We collect data about your interests and favorites, such as the teams you follow in a sports app, the stocks you track in a finance app, or the favorite cities you add to a weather app. In addition to those you explicitly provide, your interests and favorites may also be inferred or derived from other data we collect.
Payment data. We collect data necessary to process your payment if you make purchases, such as your payment instrument number (such as a credit card number), and the security code associated with your payment instrument.
Usage data. We collect data about how you and your device interact with our services. This includes data, such as the features you use, the items you purchase, the web pages you visit, and the search terms you enter. This also includes data about your device and the network you use to connect to our services, including IP address, device identifiers (such as the IMEI number for phones), regional and language settings. It includes information about the operating systems and other software installed on your device, including product keys. And it includes data about the performance of the services and any problems you experience with them.
Contacts and relationships. We collect data about your contacts and relationships if you use a Microsoft service to manage contacts, or to communicate or interact with other people or organizations.
Location data. We collect data about your location, which can be either precise or imprecise. Precise location data can be Global Position System (GPS) data, as well as data identifying nearby cell towers and Wi-Fi hotspots, we collect when you enable location-based services or features. Imprecise location data includes, for example, a location derived from your IP address or data that indicates where you are located with less precision, such as at a city or postal code level.
Content. We collect content of your files and communications when necessary to provide you with the services you use.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 2. [PASS] Policy discloses sharing of personal data with third parties

Tags: @control @obviously-satisfied

Derives from: *control case - the 2016 policy plainly does this*

```gherkin
@control @obviously-satisfied
Scenario: Policy discloses sharing of personal data with third parties
  Derives from: control case - the 2016 policy plainly does this
  Given a company publishes a privacy policy
  When the company shares personal data with other organisations
  Then the privacy policy discloses that personal data may be shared with third parties
```

**2016 policy — satisfied** (high confidence)

The policy explicitly states that personal data may be shared with third parties, satisfying the requirement of the test case.

> We share your personal data with your consent or as necessary to complete any transaction or provide any service you have requested or authorized.

(verified in policy text)

**Classification: green_tick** — Satisfied by the 2016 policy.

---

## 3. [REVIEW] Policy commits to a named Australian statutory time limit

Tags: @control @obviously-absurd

Derives from: *control case - no Microsoft policy would ever say this*

```gherkin
@control @obviously-absurd
Scenario: Policy commits to a named Australian statutory time limit
  Derives from: control case - no Microsoft policy would ever say this
  Given a company publishes a privacy policy
  When an individual requests access to their personal information
  Then the privacy policy states that the company will respond within 30 days as required by Australian Privacy Principle 12
```

**2016 policy — not_satisfied** (high confidence)

The privacy policy does not explicitly state that the company will respond within 30 days to requests for access to personal information, nor does it reference Australian Privacy Principle 12.

_No supporting passage cited._

**2026 policy — not_satisfied** (high confidence)

The privacy policy does not mention a specific time frame for responding to requests for access to personal information, including the 30 days required by Australian Privacy Principle 12.

_No supporting passage cited._

**Classification: red_cross** — Not satisfied by either policy. AMBIGUOUS: either a persistent gap or a spurious test case. Needs manual review.

---
