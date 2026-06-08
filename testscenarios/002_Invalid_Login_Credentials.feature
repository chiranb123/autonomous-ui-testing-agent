Scenario: Invalid Login Credentials
  Given the user is logged in with invalid credentials
  When the user attempts to log in
  Then an error message is displayed indicating invalid credentials