# GitHub/GDPR pilot — provisional manual results

This pilot compares GitHub's policy effective 11 October 2017 with its policy effective
27 April 2026. GitHub's official release notes say that the intervening 25 May 2018
release was specifically intended to bring its policies into alignment with GDPR.

The 2017 policy predates GDPR applicability. Its failures below are counterfactual test
outcomes, not allegations that GitHub breached a law that was not yet applicable.

| Requirement | October 2017 | April 2026 | Transition | Manual reason |
|---|---|---|---|---|
| Controller identity and contact details | satisfied | satisfied | stable_satisfied | The old statement identifies GitHub in its title and directs privacy questions to GitHub's privacy contact; the current policy is more precise, identifying GitHub, Inc. and GitHub B.V. and giving postal addresses. |
| DPO contact details | **not satisfied** | satisfied | **gap_closed** | The old policy mentions a Privacy Counsel but does not identify DPO contact details; the current policy gives `dpo@github.com`. |
| Processing purposes and legal bases | **not satisfied** | satisfied | **gap_closed** | The old policy explains purposes but does not disclose GDPR legal bases; the current policy identifies contract, legal obligation, legitimate interests and consent. |
| Legitimate interests pursued | **not satisfied** | satisfied | **gap_closed** | The old policy does not identify legitimate interests as a legal basis. The current policy identifies interests including service security, communications, and service and AI development. |
| Recipients or recipient categories | satisfied | satisfied | stable_satisfied | Both identify categories such as vendors/service providers, public users, legal authorities and transaction counterparties. |
| International transfers and safeguards | satisfied | satisfied | stable_satisfied | The old policy identifies US processing, Privacy Shield and SCC arrangements; the current policy identifies non-adequate countries and European Commission SCCs. |
| Retention period or criteria | satisfied | satisfied | stable_satisfied | Both use account activity, service need and legal obligations as criteria; the old policy also gives a 30-day profile-deletion target in ordinary cases. |
| Complete Article 13(2)(b) rights notice | **not satisfied** | satisfied | **gap_closed** | The old policy provides access, alteration and deletion but omits restriction, objection and portability; the current policy states the complete tested set. |
| Complete withdrawal-of-consent notice | **not satisfied** | **not satisfied** | **persistent_gap** | The current policy says consent may be withdrawn at any time, but does not clearly state that withdrawal does not affect the lawfulness of earlier processing. The old policy omits both parts as a legal right. |
| Complaint to a supervisory authority | **not satisfied** | satisfied | **gap_closed** | The old policy provides GitHub/JAMS/FTC complaint routes but not the GDPR right to complain to a data-protection supervisory authority; the current policy states that right and links European users to authority contacts. |

Totals: 4 `stable_satisfied`, 5 `gap_closed`, 1 `persistent_gap`, and 0
`regression`.

This is a strong pilot outcome for the planned experiment: more than half the sample
requirements produce the expected historical-fail/current-pass transition, while the
stable and persistent results show that the judge must compare specific legal assertions
rather than merely detecting modern privacy vocabulary.

These labels should be independently reviewed before being treated as dissertation ground
truth. They do not amount to legal advice or a complete GDPR compliance assessment.
