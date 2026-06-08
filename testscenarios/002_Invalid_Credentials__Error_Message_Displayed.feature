Scenario: Invalid Credentials: Error Message Displayed
  Given the user is on the login page
  When the user enters invalid credentials
  Then an error message is displayed