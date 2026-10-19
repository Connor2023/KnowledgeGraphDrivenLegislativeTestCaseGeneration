Feature: Access to personal information under Australian Privacy Principle 12

  @s12-1 @access-to-personal-information
  Scenario: Individual requests access to personal information
    # Derives from: "if an APP entity holds personal information about an individual, the entity must, on request by the individual, give the individual access to the information."
    Given the APP entity holds personal information about an individual
    When the individual requests access to their personal information
    Then the privacy policy states that the individual will be given access to their personal information upon request

  @s12-1 @no-charge-for-access
  Scenario: Individual requests access without charge
    # Derives from: "the entity must not charge for making of the request."
    Given the APP entity holds personal information about an individual
    When the individual requests access to their personal information
    Then the privacy policy states that the individual will not be charged for making the request
