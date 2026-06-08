Scenario: Empty Mandatory Fields: Validation Message Displayed
  Given the user is on the checkout page
  When the user leaves all mandatory fields empty
  Then a validation message is displayed