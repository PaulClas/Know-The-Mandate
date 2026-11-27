export const DEFAULT_INSTRUCTION = "Manage my money, pay my usual bills and move some savings whenever it makes sense. Do not spend too much.";
export const EXAMPLE_CNL = `PERMIT agent.finance-assistant TO READ_BALANCE ON account.chequing-001.
PERMIT agent.finance-assistant TO PAY_INVOICE FROM account.chequing-001 TO beneficiary.hydro-quebec, beneficiary.videotron WITH MAX_AMOUNT 250.00 CAD PER TRANSACTION.
LIMIT TOTAL_PAYMENTS TO 1500.00 CAD PER CALENDAR_MONTH.
REQUIRE HUMAN_APPROVAL FOR PAYMENTS ABOVE 100.00 CAD.
PROHIBIT EXTERNAL_TRANSFER.
PROHIBIT DELEGATION.
PURPOSE household_bill_management.
EXPIRE AT 2027-01-01T00:00:00Z.
`;
