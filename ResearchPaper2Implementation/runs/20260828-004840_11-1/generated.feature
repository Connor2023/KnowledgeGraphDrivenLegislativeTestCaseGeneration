Feature: Compliance with Australian Privacy Principle 11

  @s11-1 @protect-personal-information
  Scenario: Protecting personal information from misuse, interference, and loss
    # Derives from: "the entity must take such steps as are reasonable in the circumstances to protect the information from misuse, interference and loss."
    Given the APP entity holds personal information
    When reviewing the privacy policy
    Then the privacy policy must state the steps taken to protect personal information from misuse, interference, and loss
