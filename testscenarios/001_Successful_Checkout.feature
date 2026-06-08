Scenario: Successful Checkout
  Given the user is logged in with valid credentials
  When the user proceeds to checkout
  And the user fills in shipping details
  And the user reviews the order summary
  Then the user confirms checkout
  Then the Cart icon reflects the correct item count
  Then the user sees a confirmation screen after successful checkout