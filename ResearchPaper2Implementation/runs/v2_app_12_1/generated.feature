Feature: Access to personal information

  @s12-1 @access-to-personal-information
  Scenario: Individual requests access to personal information
    # Derives from: "the entity must, on request by the individual, give the individual access to the information."
    Given the entity holds personal information about the individual
    When the individual requests access to their personal information
    Then the privacy policy states that the individual will be given access to their personal information upon request

  @s12-1 @no-charge-for-access
  Scenario: No charge for access request
    # Derives from: "the entity must not charge for making of the request."
    Given the individual requests access to their personal information
    When the individual makes the request
    Then the privacy policy states that the individual will not be charged for making the request
