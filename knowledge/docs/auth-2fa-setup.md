---
doc_id: auth-2fa-setup
title: Two-factor authentication setup and recovery
version: 1
effective_date: 2026-07-01
---

# Two-factor authentication setup and recovery

## Supported methods

NorthStar supports SMS codes, authenticator apps (TOTP), and hardware security keys (FIDO2) as second factors. Authenticator apps are the recommended default. SMS is not available for accounts registered with a landline number.

## Losing a second factor

If a customer loses access to their second factor, they can recover using their backup codes (issued at setup, 10 single-use codes). Without backup codes, recovery requires a video identity check in the app, which takes up to 2 business days to review.

## Trusted devices

Marking a device as trusted skips the second factor for 90 days on that device. Trust is revoked automatically when the password changes or when the device has been inactive for 45 days.
