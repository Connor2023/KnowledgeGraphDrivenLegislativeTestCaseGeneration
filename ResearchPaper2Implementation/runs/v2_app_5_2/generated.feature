Feature: Notification of the collection of personal information

  @s5-2 @identity-and-contact-details
  Scenario: The privacy policy must disclose the identity and contact details of the APP entity.
  # Derives from: the identity and contact details of the APP entity
    Given the APP entity is collecting personal information
    When an individual reviews the privacy policy
    Then the privacy policy states the identity and contact details of the APP entity

  @s5-2 @collection-from-third-party
  Scenario: The privacy policy must disclose if personal information is collected from someone other than the individual.
  # Derives from: if the APP entity collects the personal information from someone other than the individual
    Given the APP entity is collecting personal information
    When an individual reviews the privacy policy
    Then the privacy policy states whether personal information is collected from someone other than the individual

  @s5-2 @fact-of-collection
  Scenario: The privacy policy must disclose the fact that personal information has been collected and the circumstances of that collection.
  # Derives from: the fact that the entity so collects, or has collected, the information and the circumstances of that collection
    Given the APP entity has collected personal information
    When an individual reviews the privacy policy
    Then the privacy policy states that personal information has been collected and describes the circumstances of that collection

  @s5-2 @collection-authorised-by-law
  Scenario: The privacy policy must disclose if the collection of personal information is required or authorised by Australian law or a court/tribunal order.
  # Derives from: if the collection of the personal information is required or authorised by or under an Australian law or a court/tribunal order
    Given the APP entity is collecting personal information
    When an individual reviews the privacy policy
    Then the privacy policy states whether the collection is required or authorised by Australian law or a court/tribunal order

  @s5-2 @purposes-of-collection
  Scenario: The privacy policy must disclose the purposes for which personal information is collected.
  # Derives from: the purposes for which the APP entity collects the personal information
    Given the APP entity is collecting personal information
    When an individual reviews the privacy policy
    Then the privacy policy states the purposes for which personal information is collected

  @s5-2 @consequences-of-non-collection
  Scenario: The privacy policy must disclose the main consequences for the individual if personal information is not collected.
  # Derives from: the main consequences (if any) for the individual if all or some of the personal information is not collected by the APP entity
    Given the APP entity is collecting personal information
    When an individual reviews the privacy policy
    Then the privacy policy states the main consequences for the individual if personal information is not collected

  @s5-2 @disclosure-to-third-parties
  Scenario: The privacy policy must disclose any other entities to which personal information is usually disclosed.
  # Derives from: any other APP entity, body or person, or the types of any other APP entities, bodies or persons, to which the APP entity usually discloses personal information of the kind collected by the entity
    Given the APP entity is collecting personal information
    When an individual reviews the privacy policy
    Then the privacy policy states the types of entities to which personal information is usually disclosed

  @s5-2 @access-and-correction
  Scenario: The privacy policy must contain information about how the individual may access and correct their personal information.
  # Derives from: that the APP privacy policy of the APP entity contains information about how the individual may access the personal information about the individual that is held by the entity and seek the correction of such information
    Given the APP entity holds personal information about the individual
    When an individual reviews the privacy policy
    Then the privacy policy states how the individual may access and correct their personal information

  @s5-2 @complaints-process
  Scenario: The privacy policy must contain information about how the individual may complain about a breach of the Australian Privacy Principles.
  # Derives from: that the APP privacy policy of the APP entity contains information about how the individual may complain about a breach of the Australian Privacy Principles
    Given the APP entity is subject to the Australian Privacy Principles
    When an individual reviews the privacy policy
    Then the privacy policy states how the individual may complain about a breach of the Australian Privacy Principles

  @s5-2 @disclosure-to-overseas-recipients
  Scenario: The privacy policy must disclose whether personal information is likely to be disclosed to overseas recipients.
  # Derives from: whether the APP entity is likely to disclose the personal information to overseas recipients
    Given the APP entity is collecting personal information
    When an individual reviews the privacy policy
    Then the privacy policy states whether personal information is likely to be disclosed to overseas recipients

  @s5-2 @countries-of-overseas-recipients
  Scenario: The privacy policy must specify the countries where overseas recipients are likely to be located if practicable.
  # Derives from: if it is practicable to specify those countries in the notification or to otherwise make the individual aware of them
    Given the APP entity is likely to disclose personal information to overseas recipients
    When an individual reviews the privacy policy
    Then the privacy policy states the countries where overseas recipients are likely to be located if practicable
