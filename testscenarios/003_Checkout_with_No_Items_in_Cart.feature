Scenario: Checkout with No Items in Cart
  Given the user is logged in with valid credentials
  When the user proceeds to checkout
  Then an error message is displayed indicating no items in cart