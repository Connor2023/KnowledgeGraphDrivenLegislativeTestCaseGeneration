Feature: Compliance with Australian Privacy Principle 6

  @s6-1 @prohibit-secondary-use
  Scenario: Prohibition on using or disclosing personal information for a secondary purpose
    # Derives from: "the entity must not use or disclose the information for another purpose (the secondary purpose)"
    Given the APP entity holds personal information about an individual
    When the information was collected for a primary purpose
    Then the privacy policy must state that the information will not be used or disclosed for a secondary purpose without consent

  @s6-1 @require-consent
  Scenario: Requirement for consent for secondary use or disclosure
    # Derives from: "unless the individual has consented to the use or disclosure of the information"
    Given the APP entity holds personal information about an individual
    When the entity intends to use or disclose the information for a secondary purpose
    Then the privacy policy must disclose that consent from the individual is required for such use or disclosure

  @s6-1 @apply-subclauses
  Scenario: Application of subclauses for secondary use or disclosure
    # Derives from: "or subclause 6.2 or 6.3 applies in relation to the use or disclosure of the information"
    Given the APP entity holds personal information about an individual
    When the entity considers using or disclosing the information for a secondary purpose
    Then the privacy policy must explain the conditions under which subclauses 6.2 or 6.3 may apply to the use or disclosure of the information
