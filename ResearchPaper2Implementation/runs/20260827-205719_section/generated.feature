Feature: Compliance with privacy legislation regarding the alpine marmot

  @section @hibernation-location
  Scenario: The privacy policy must disclose the hibernation location of the alpine marmot
    # Derives from: "The alpine marmot hibernates in burrows above the treeline in the Carpathian mountains."
    Given the privacy policy is reviewed
    When the hibernation location of the alpine marmot is considered
    Then the privacy policy must state that the alpine marmot hibernates in burrows above the treeline in the Carpathian mountains

  @section @feeding-habits
  Scenario: The privacy policy must disclose the feeding habits of the alpine marmot
    # Derives from: "feeding on grasses and lichen during the brief summer."
    Given the privacy policy is reviewed
    When the feeding habits of the alpine marmot are considered
    Then the privacy policy must state that the alpine marmot feeds on grasses and lichen during the brief summer
