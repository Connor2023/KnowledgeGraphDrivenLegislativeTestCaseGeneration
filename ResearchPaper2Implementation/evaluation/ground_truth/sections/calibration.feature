Feature: Judge calibration control

  @control @obviously-satisfied
  Scenario: Policy discloses what personal data is collected
    # Derives from: control case - the 2016 policy plainly does this
    Given a company publishes a privacy policy
    When the company collects personal data from users
    Then the privacy policy states what personal data the company collects

  @control @obviously-satisfied
  Scenario: Policy discloses sharing of personal data with third parties
    # Derives from: control case - the 2016 policy plainly does this
    Given a company publishes a privacy policy
    When the company shares personal data with other organisations
    Then the privacy policy discloses that personal data may be shared with third parties

  @control @obviously-absurd
  Scenario: Policy commits to a named Australian statutory time limit
    # Derives from: control case - no Microsoft policy would ever say this
    Given a company publishes a privacy policy
    When an individual requests access to their personal information
    Then the privacy policy states that the company will respond within 30 days as required by Australian Privacy Principle 12
