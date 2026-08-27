Feature: APP Privacy Policy Requirements

  @s1-4 @collect-personal-information
  Scenario: The privacy policy must disclose the kinds of personal information collected
    # Derives from: "the kinds of personal information that the entity collects and holds"
    Given the APP entity has a privacy policy
    Then the privacy policy states the kinds of personal information that the entity collects and holds

  @s1-4 @collection-methods
  Scenario: The privacy policy must explain how personal information is collected and held
    # Derives from: "how the entity collects and holds personal information"
    Given the APP entity has a privacy policy
    Then the privacy policy explains how the entity collects and holds personal information

  @s1-4 @purposes-of-collection
  Scenario: The privacy policy must specify the purposes for collecting personal information
    # Derives from: "the purposes for which the entity collects, holds, uses and discloses personal information"
    Given the APP entity has a privacy policy
    Then the privacy policy states the purposes for which the entity collects, holds, uses, and discloses personal information

  @s1-4 @access-to-personal-information
  Scenario: The privacy policy must outline how individuals can access their personal information
    # Derives from: "how an individual may access personal information about the individual that is held by the entity"
    Given the APP entity has a privacy policy
    Then the privacy policy explains how an individual may access personal information about themselves that is held by the entity

  @s1-4 @correction-of-personal-information
  Scenario: The privacy policy must describe how individuals can seek correction of their personal information
    # Derives from: "how an individual may seek the correction of such information"
    Given the APP entity has a privacy policy
    Then the privacy policy explains how an individual may seek the correction of their personal information

  @s1-4 @complaints-process
  Scenario: The privacy policy must detail how individuals can complain about breaches
    # Derives from: "how an individual may complain about a breach of the Australian Privacy Principles"
    Given the APP entity has a privacy policy
    Then the privacy policy states how an individual may complain about a breach of the Australian Privacy Principles

  @s1-4 @complaints-handling
  Scenario: The privacy policy must explain how the entity will deal with complaints
    # Derives from: "how the entity will deal with such a complaint"
    Given the APP entity has a privacy policy
    Then the privacy policy explains how the entity will deal with complaints about breaches of the Australian Privacy Principles

  @s1-4 @disclosure-to-overseas-recipients
  Scenario: The privacy policy must indicate if personal information is likely to be disclosed to overseas recipients
    # Derives from: "whether the entity is likely to disclose personal information to overseas recipients"
    Given the APP entity has a privacy policy
    Then the privacy policy states whether the entity is likely to disclose personal information to overseas recipients

  @s1-4 @countries-of-overseas-recipients
  Scenario: The privacy policy must specify the countries of overseas recipients if practicable
    # Derives from: "if the entity is likely to disclose personal information to overseas recipients - the countries in which such recipients are likely to be located if it is practicable to specify those countries in the policy"
    Given the APP entity has a privacy policy
    Then the privacy policy specifies the countries in which overseas recipients are likely to be located, if practicable
