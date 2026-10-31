Feature: Use or disclosure of personal information

  @s6-1 @prohibit-secondary-use
  Scenario: Prohibition on using or disclosing personal information for a secondary purpose
    # Derives from: "the entity must not use or disclose the information for another purpose (the secondary purpose)"
    Given an APP entity holds personal information about an individual
    When the information was collected for a particular purpose (the primary purpose)
    Then the privacy policy must state that the entity will not use or disclose the information for another purpose unless certain conditions are met

  @s6-1 @require-consent-for-secondary-use
  Scenario: Requirement for individual consent for secondary use or disclosure
    # Derives from: "unless the individual has consented to the use or disclosure of the information"
    Given an APP entity holds personal information about an individual
    When the entity intends to use or disclose the information for a secondary purpose
    Then the privacy policy must disclose that the entity requires the individual's consent for such use or disclosure

  @s6-1 @apply-subclauses-6-2-6-3
  Scenario: Conditions under which secondary use or disclosure is permitted
    # Derives from: "unless subclause 6.2 or 6.3 applies in relation to the use or disclosure of the information"
    Given an APP entity holds personal information about an individual
    When the entity considers using or disclosing the information for a secondary purpose
    Then the privacy policy must explain the conditions under which subclauses 6.2 or 6.3 may apply to permit such use or disclosure
