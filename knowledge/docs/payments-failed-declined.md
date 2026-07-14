---
doc_id: payments-failed-declined
title: Failed and declined payments
version: 1
effective_date: 2026-07-01
---

# Failed and declined payments

## Decline reasons

Payments decline for insufficient funds (code P-051), daily limit reached (P-062), suspected fraud hold (P-090), or an expired card on file (P-014). The app shows the code under Activity > Declined. A P-090 hold requires the customer to confirm the transaction in the app or by phone before retrying.

## Double charges

If a merchant shows a charge twice, one is usually a pre-authorization that drops off within 5 business days. Only charges with status 'Posted' are actually withdrawn. Customers should not be refunded for pending pre-authorizations.

## Retry guidance

After fixing the cause, payments can be retried immediately except fraud holds, which need 24 hours after confirmation to clear fully.
