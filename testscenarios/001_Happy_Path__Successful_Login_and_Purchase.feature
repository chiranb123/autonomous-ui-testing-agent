Scenario: Happy Path: Successful Login and Purchase
  Given the user is on the login page
  When the user enters a valid username
  And the user enters a valid password
  And the user clicks the Login button
  Then the Products page is displayed
  And the list of available products is displayed