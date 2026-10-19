Feature: Use or disclosure of personal information

  @s6-1 @prohibit-secondary-use
  Scenario: Prohibition on using personal information for secondary purposes
    # Derives from: "the entity must not use or disclose the information for another purpose (the secondary purpose) unless the individual has consented"
    Given the APP entity holds personal information about an individual
    When the personal information was collected for a particular purpose
    Then the privacy policy states that the personal information will not be used for another purpose without the individual's consent

  @s6-1 @consent-for-secondary-use
  Scenario: Requirement for consent to use personal information for secondary purposes
    # Derives from: "the entity must not use or disclose the information for another purpose... unless the individual has consented"
    Given the APP entity holds personal information about an individual
    When the personal information was collected for a particular purpose
    Then the privacy policy states that the entity will obtain the individual's consent before using the personal information for a secondary purpose
