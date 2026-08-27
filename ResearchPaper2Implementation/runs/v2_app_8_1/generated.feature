Feature: Cross-border disclosure of personal information

  @s8-1 @ensure-non-breach
  Scenario: Ensure overseas recipient does not breach Australian Privacy Principles
    # Derives from: "the entity must take such steps as are reasonable in the circumstances to ensure that the overseas recipient does not breach the Australian Privacy Principles"
    Given the entity discloses personal information to an overseas recipient
    Then the privacy policy states that the entity takes reasonable steps to ensure the overseas recipient does not breach the Australian Privacy Principles in relation to the information.
