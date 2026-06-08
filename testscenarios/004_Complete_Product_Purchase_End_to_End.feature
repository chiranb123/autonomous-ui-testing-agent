Scenario: Complete Product Purchase End to End
  Given the user is on the login page
  When the user enters a valid username
  And the user enters a valid password
  And the user clicks the Login button
  Then the Products page is displayed
  When the user clicks the Add to cart button
  And the user clicks the shopping cart link
  And the user clicks the Checkout button
  And the user enters "Test" in the First Name field
  And the user enters "User" in the Last Name field
  And the user enters "12345" in the Postal Code field
  And the user clicks the Continue button
  And the user clicks the Finish button
  Then "Thank you for your order!" is displayed