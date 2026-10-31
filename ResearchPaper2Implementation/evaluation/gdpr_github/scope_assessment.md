# Is GDPR too specific to Europe?

## Conclusion

GDPR is geographically European in its legal authority, institutions and enforcement,
but much of its substantive privacy language is general, technology-neutral and suitable
for this test-generation experiment.

Article 3 makes the territorial connection explicit: GDPR applies to processing connected
with an EU establishment and can also apply to a non-EU controller offering goods or
services to people in the Union or monitoring their behaviour there. It is therefore not
a universal law, even though it can apply to organisations outside Europe.

## Broadly reusable concepts

- Controller transparency and contactability.
- Specific processing purposes.
- A lawful justification for processing.
- Data minimisation, accuracy, security and limited retention.
- Disclosure of recipient categories.
- Access, correction, deletion, objection and portability rights.
- Clear notice and meaningful control over consent.

These are expressed in general organisational and information-handling terms. They are
not specific to a particular technology or industry, and many have analogues in other
privacy regimes.

## Specifically European machinery

- References to the Union, EEA, Member States and Union or Member-State law.
- The GDPR taxonomy of Article 6 legal bases.
- Data Protection Officers where Articles 37–39 require one.
- EU representatives for certain controllers outside the Union.
- National supervisory authorities and the European Data Protection Board.
- Adequacy decisions, Standard Contractual Clauses and other Chapter V transfer tools.
- Enforcement powers and administrative fines denominated in euros.

## Experimental recommendation

Use Article 13 as the first corpus because it contains discrete disclosures that can be
observed in policy text. Tag each scenario as `general` or `eu_specific`, as the sample
feature does. Do not infer real-world compliance with operational duties—such as security,
deletion performance or response deadlines—from a privacy statement alone.

The best historical control is GitHub's October 2017 policy. The best positive artifact
is the current policy, while the May 2018 GDPR-alignment release provides independent
evidence that the policy boundary was driven by GDPR. This makes the comparison a seeded
temporal differential, not a claim that the pre-GDPR policy was unlawful when published.
