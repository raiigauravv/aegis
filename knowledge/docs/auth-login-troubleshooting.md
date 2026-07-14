---
doc_id: auth-login-troubleshooting
title: Troubleshooting sign-in problems
version: 1
effective_date: 2026-07-01
---

# Troubleshooting sign-in problems

## Common causes

Most NorthStar sign-in failures are caused by an outdated app version, an incorrect password after a recent reset, or a locked profile following repeated attempts. Error code NS-403 always means the profile is locked, not that the password is wrong. Error NS-408 indicates a session timeout on our side and resolves on retry.

## Unlocking a profile

A locked profile (error NS-403) unlocks automatically after 30 minutes. Customers who need immediate access can unlock through 'Forgot password' with SMS verification, or an agent can unlock manually after identity verification. Manual unlocks require the customer's date of birth and the answer to their chosen security question.

## Password rules

Passwords must be 10-64 characters with at least one number and one symbol. The previous 5 passwords cannot be reused. Password resets invalidate all active sessions on every device.
