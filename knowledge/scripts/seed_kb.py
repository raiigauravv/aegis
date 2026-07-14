"""Seed the NorthStar Banking App knowledge base.

Writes knowledge/docs/<doc_id>.md (frontmatter: doc_id, title, version, effective_date)
and knowledge/golden/retrieval.jsonl (question -> expected doc_id), keeping the golden
retrieval set in lockstep with the corpus.

Run: python knowledge/scripts/seed_kb.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Each entry: (doc_id, title, sections{heading: body}, golden questions)
DOCS: list[tuple[str, str, dict[str, str], list[str]]] = [
    (
        "auth-login-troubleshooting",
        "Troubleshooting sign-in problems",
        {
            "Common causes": "Most NorthStar sign-in failures are caused by an outdated app version, an incorrect password after a recent reset, or a locked profile following repeated attempts. Error code NS-403 always means the profile is locked, not that the password is wrong. Error NS-408 indicates a session timeout on our side and resolves on retry.",
            "Unlocking a profile": "A locked profile (error NS-403) unlocks automatically after 30 minutes. Customers who need immediate access can unlock through 'Forgot password' with SMS verification, or an agent can unlock manually after identity verification. Manual unlocks require the customer's date of birth and the answer to their chosen security question.",
            "Password rules": "Passwords must be 10-64 characters with at least one number and one symbol. The previous 5 passwords cannot be reused. Password resets invalidate all active sessions on every device.",
        },
        [
            "What does error code NS-403 mean?",
            "How long until a locked profile unlocks by itself?",
            "What are the password requirements for the NorthStar app?",
        ],
    ),
    (
        "auth-2fa-setup",
        "Two-factor authentication setup and recovery",
        {
            "Supported methods": "NorthStar supports SMS codes, authenticator apps (TOTP), and hardware security keys (FIDO2) as second factors. Authenticator apps are the recommended default. SMS is not available for accounts registered with a landline number.",
            "Losing a second factor": "If a customer loses access to their second factor, they can recover using their backup codes (issued at setup, 10 single-use codes). Without backup codes, recovery requires a video identity check in the app, which takes up to 2 business days to review.",
            "Trusted devices": "Marking a device as trusted skips the second factor for 90 days on that device. Trust is revoked automatically when the password changes or when the device has been inactive for 45 days.",
        },
        [
            "How can I recover my account if I lost my authenticator app?",
            "How long does marking a device as trusted skip 2FA?",
        ],
    ),
    (
        "payments-etransfer-limits",
        "Interac e-Transfer limits and processing times",
        {
            "Limits": "Default e-Transfer limits are $3,000 per transaction, $10,000 per day, and $20,000 per 7 days. Premium chequing customers have $5,000 / $15,000 / $30,000. Limits reset at midnight Eastern Time, not on a rolling window.",
            "Processing times": "Transfers to recipients registered for Autodeposit complete within 5 minutes. Transfers requiring a security answer can take up to 30 minutes to send and expire after 30 days unclaimed. Expired transfers are refunded automatically within 1 business day.",
            "Cancelling": "An e-Transfer can be cancelled free of charge any time before the recipient deposits it, from Activity > Pending transfers. After deposit, a transfer cannot be reversed; disputes go through the fraud team.",
        },
        [
            "What is the daily e-Transfer limit?",
            "How long does an e-Transfer take with Autodeposit?",
            "Can I cancel an e-Transfer after it was deposited?",
        ],
    ),
    (
        "payments-failed-declined",
        "Failed and declined payments",
        {
            "Decline reasons": "Payments decline for insufficient funds (code P-051), daily limit reached (P-062), suspected fraud hold (P-090), or an expired card on file (P-014). The app shows the code under Activity > Declined. A P-090 hold requires the customer to confirm the transaction in the app or by phone before retrying.",
            "Double charges": "If a merchant shows a charge twice, one is usually a pre-authorization that drops off within 5 business days. Only charges with status 'Posted' are actually withdrawn. Customers should not be refunded for pending pre-authorizations.",
            "Retry guidance": "After fixing the cause, payments can be retried immediately except fraud holds, which need 24 hours after confirmation to clear fully.",
        },
        [
            "What does decline code P-090 mean?",
            "Why do I see the same charge twice on my account?",
        ],
    ),
    (
        "cards-lost-stolen",
        "Lost, stolen, and damaged cards",
        {
            "Immediate steps": "Customers can lock a card instantly from Cards > Lock card; a locked card declines all new purchases but recurring subscriptions continue. Reporting a card lost or stolen cancels it permanently and issues a replacement.",
            "Replacement timelines": "Replacement cards arrive in 5-7 business days by standard mail, or 2 business days by express courier for a $25 fee (waived for Premium). A digital card is available immediately in the app for online purchases and mobile wallets while the physical card ships.",
            "Fraud liability": "Customers are not liable for unauthorized transactions reported within 30 days, provided the PIN was not shared. Transactions made with the correct PIN before the report may be investigated case by case.",
        },
        [
            "How fast does a replacement card arrive?",
            "Does locking my card stop subscription payments?",
            "Am I liable for fraudulent charges on a stolen card?",
        ],
    ),
    (
        "cards-limits-pin",
        "Card limits and PIN management",
        {
            "Spending limits": "Debit purchase limits default to $2,000 per day at point of sale and $1,000 per day at ATMs. Customers can lower limits themselves in Cards > Limits; increases above the default require a branch visit or verified phone call.",
            "PIN changes": "PINs can be changed at any NorthStar ATM or in the app under Cards > Change PIN. Three incorrect PIN attempts at a terminal block chip transactions until the card is used with the correct PIN at a NorthStar ATM. Blocked PINs cannot be reset over the phone.",
        },
        [
            "What is the default daily ATM withdrawal limit?",
            "How do I fix a blocked PIN after too many wrong attempts?",
        ],
    ),
    (
        "accounts-fees-chequing",
        "Chequing account fees and fee waivers",
        {
            "Monthly fees": "Everyday Chequing costs $4.95/month, waived with a $3,000 minimum daily balance. Premium Chequing costs $16.95/month, waived with $6,000 minimum balance or a qualifying mortgage. Student and senior (65+) accounts have no monthly fee.",
            "Transaction fees": "Everyday Chequing includes 25 debit transactions per month; each extra costs $1.25. Premium includes unlimited transactions. Interac e-Transfers are free on all chequing accounts.",
            "NSF and overdraft": "A non-sufficient-funds event costs $45. Overdraft protection costs $5 per month used, covers up to $1,500, and interest accrues at 21% annually on the overdrawn amount.",
        },
        [
            "How can I get the monthly chequing fee waived?",
            "How much is the NSF fee?",
        ],
    ),
    (
        "accounts-statements-documents",
        "Statements and tax documents",
        {
            "Statements": "Monthly e-statements are available in the app under Documents on the 3rd business day of each month and are retained for 7 years. Paper statements cost $2.50/month. Statement PDFs are official documents accepted for proof of address.",
            "Tax slips": "T5 slips for interest income over $50 are issued by the last day of February and appear under Documents > Tax. RRSP contribution receipts are issued twice: March (for first-60-days contributions) and January (for the prior calendar year).",
        },
        [
            "When are T5 tax slips available?",
            "How long are e-statements kept?",
        ],
    ),
    (
        "app-troubleshooting-crashes",
        "App crashes, blank screens, and update problems",
        {
            "First steps": "For crashes on launch, first confirm the app version under Settings > About; versions older than 12 months are unsupported and must be updated. Clearing the app cache (Android: App info > Storage > Clear cache; iOS: reinstall) resolves most blank-screen-after-login reports.",
            "Known issues": "Version 8.2.0 on Android 15 had a crash on the payees screen, fixed in 8.2.1. Biometric login can fail after an OS update until the customer re-enrolls Face ID / fingerprint inside the app, under Settings > Security > Biometrics.",
            "Escalation data": "When escalating a crash, collect: app version, OS version, device model, and the incident ID shown on the crash screen (format INC-XXXXXX). Without an incident ID the app team cannot locate logs.",
        },
        [
            "The app shows a blank screen after login, how do I fix it?",
            "What information is needed to escalate an app crash?",
            "Why did biometric login stop working after my phone updated?",
        ],
    ),
    (
        "app-notifications",
        "Push notifications and alerts",
        {
            "Alert types": "Customers can enable alerts for transactions over a chosen amount, low balance thresholds, deposits, and sign-ins from new devices. Security alerts (new device, password change) cannot be disabled.",
            "Delivery problems": "If notifications stop, verify they are enabled both in the app (Settings > Notifications) and at OS level. Logging out for more than 60 days silently unregisters the device from push; logging back in re-registers it.",
        },
        [
            "Why did I stop receiving push notifications?",
            "Can security alerts be turned off?",
        ],
    ),
    (
        "security-fraud-reporting",
        "Reporting fraud and suspicious activity",
        {
            "How to report": "Suspected fraud should be reported in-app via Support > Report fraud, or by phone at 1-800-NORTHSTAR, available 24/7. Reporting freezes outbound transfers over $100 on the affected account until a fraud analyst completes review, normally within 4 business hours.",
            "Investigation timelines": "Unauthorized card transactions are provisionally credited within 10 business days while investigated. E-Transfer fraud investigations take up to 30 days because they involve the receiving institution. Wire fraud must be reported within 24 hours for any recovery chance.",
            "Phishing": "NorthStar never asks for a full password, 2FA codes, or card PIN by phone, SMS, or email. Customers who entered credentials on a suspicious site should change their password immediately, which invalidates all sessions, and enable 2FA.",
        },
        [
            "How do I report fraud on my account?",
            "How long does a fraud investigation take for card transactions?",
            "Will NorthStar ever ask for my 2FA code by phone?",
        ],
    ),
    (
        "security-privacy-data",
        "Privacy, data access, and account closure",
        {
            "Data requests": "Customers can request an export of their personal data under Settings > Privacy > Download my data; the export is prepared within 30 days as required by PIPEDA. Data collected includes transactions, device identifiers, and support interactions.",
            "Account closure": "Accounts with a zero balance can be closed in-app. Accounts are retained in read-only mode for 90 days after closure, then archived for the 7-year regulatory period. Closure does not delete data subject to retention requirements.",
        },
        [
            "How do I download all my personal data?",
            "What happens to my data after I close my account?",
        ],
    ),
    (
        "mortgage-payments",
        "Mortgage payments and prepayment",
        {
            "Payment changes": "Customers can change payment frequency (monthly, biweekly, accelerated biweekly) once per calendar year without fees, in Mortgage > Payment options. Accelerated biweekly makes the equivalent of one extra monthly payment per year.",
            "Prepayment privileges": "Up to 15% of the original principal can be prepaid each calendar year without penalty, as lump sums of at least $100. Prepaying beyond 15% incurs the greater of 3 months' interest or the interest rate differential (IRD).",
            "Missed payments": "One missed mortgage payment can be deferred per 12-month period through Mortgage > Skip a payment; interest continues to accrue. A second missed payment without deferral triggers a collections call and a credit bureau report after 30 days.",
        },
        [
            "How much of my mortgage can I prepay without penalty?",
            "What happens if I miss a mortgage payment?",
        ],
    ),
    (
        "savings-interest-gic",
        "Savings interest and GICs",
        {
            "Savings rates": "The High-Interest Savings Account pays 3.10% annually, calculated daily and paid monthly. Promotional rates apply only to net new deposits and revert after the stated period; the app shows the applicable rate per dollar under Savings > Rate details.",
            "GICs": "Non-redeemable GICs (1-5 year terms) pay higher rates but cannot be cashed before maturity except on death or demonstrated financial hardship, with a rate reduction to 0.05%. Redeemable GICs can be cashed after 30 days at the early-redemption rate.",
        },
        [
            "Can I cash a non-redeemable GIC before it matures?",
            "How is savings interest calculated and paid?",
        ],
    ),
    (
        "wires-international",
        "International wires and currency exchange",
        {
            "Sending wires": "Outgoing international wires cost $45 flat plus correspondent fees, require the recipient's IBAN or SWIFT/BIC, and must be initiated before 3 PM ET to start processing the same business day. Wires over $10,000 require an in-app confirmation callback.",
            "Timelines and tracking": "Most wires arrive in 1-3 business days; some corridors take up to 5. Wires include a UETR tracking reference shown in Activity, which the receiving bank can use to locate funds. Recalls of sent wires cost $35 and are not guaranteed.",
            "FX rates": "Currency conversion uses the NorthStar daily rate, refreshed at 9 AM ET, with a 2.2% margin over interbank for retail customers (1.5% for Premium).",
        },
        [
            "What does an international wire cost to send?",
            "How long does an international wire take to arrive?",
        ],
    ),
    (
        "release-notes-8-3",
        "Release notes — NorthStar app 8.3",
        {
            "New in 8.3": "Version 8.3 (released 2026-05-14) adds virtual card numbers for online purchases, a redesigned approval flow for e-Transfers over $1,000, and Tap to Pay on Android. Virtual cards are issued instantly under Cards > Virtual cards and can be frozen independently of the physical card.",
            "Fixed issues": "8.3 fixes the payees-screen crash on Android 15 (introduced in 8.2.0), corrects rounding on FX previews, and restores missing push notifications on Pixel devices after OS updates.",
            "Known limitations": "Virtual cards cannot yet be added to Apple Pay (planned for 8.4). Tap to Pay requires Android 13 or newer.",
        },
        [
            "What new features shipped in app version 8.3?",
            "Which version fixed the payees screen crash?",
        ],
    ),
]


# Harder eval wave: casual user voice, minimal vocabulary overlap with the docs.
HARD_QUESTIONS: list[tuple[str, str]] = [
    ("my account got blocked after typing the wrong password a bunch of times", "auth-login-troubleshooting"),
    ("it says NS-403 when I try to get in", "auth-login-troubleshooting"),
    ("got a new phone and my code generator is gone, now what", "auth-2fa-setup"),
    ("do I have to enter the 6 digit code every single time on my own phone?", "auth-2fa-setup"),
    ("whats the most money I can send someone in one shot", "payments-etransfer-limits"),
    (
        "sent money to my landlord a month ago and she never took it, where did it go",
        "payments-etransfer-limits",
    ),
    ("my rent payment keeps getting rejected even though I have money", "payments-failed-declined"),
    ("store billed me two times for one purchase", "payments-failed-declined"),
    ("someone took my wallet, what do I do about my bank card", "cards-lost-stolen"),
    ("if I freeze my card will netflix still charge me", "cards-lost-stolen"),
    ("the machine ate my PIN, says blocked after I fat-fingered it", "cards-limits-pin"),
    ("how much cash can I pull from the machine in a day", "cards-limits-pin"),
    ("why am I paying 5 bucks a month for my account", "accounts-fees-chequing"),
    ("got dinged 45 dollars because a payment bounced", "accounts-fees-chequing"),
    ("need a bank paper that proves where I live", "accounts-statements-documents"),
    ("where do I find the slip for my interest for filing taxes", "accounts-statements-documents"),
    ("app just shows a white screen after I sign in", "app-troubleshooting-crashes"),
    ("face unlock quit working since the ios update", "app-troubleshooting-crashes"),
    ("my phone stopped buzzing when money comes in", "app-notifications"),
    ("I clicked a link in a text pretending to be the bank and typed my login", "security-fraud-reporting"),
    ("theres a charge on my card I never made", "security-fraud-reporting"),
    ("I want a copy of everything the bank knows about me", "security-privacy-data"),
    ("can I throw an extra 20 grand at my mortgage this year without getting charged", "mortgage-payments"),
    ("money is tight, can I skip this month's house payment", "mortgage-payments"),
    ("can I get my money out of that locked-in certificate early", "savings-interest-gic"),
    ("sending money to my family overseas, what will it cost", "wires-international"),
    ("my wire from last week still hasn't shown up at the other bank", "wires-international"),
    ("whats new in the latest app update", "release-notes-8-3"),
]


def main() -> None:
    docs_dir = ROOT / "docs"
    golden_dir = ROOT / "golden"
    docs_dir.mkdir(exist_ok=True)
    golden_dir.mkdir(exist_ok=True)

    golden = []
    for doc_id, title, sections, questions in DOCS:
        body = "\n\n".join(f"## {h}\n\n{t}" for h, t in sections.items())
        front = (
            f"---\ndoc_id: {doc_id}\ntitle: {title}\nversion: 1\n"
            f"effective_date: 2026-07-01\n---\n\n# {title}\n\n"
        )
        (docs_dir / f"{doc_id}.md").write_text(front + body + "\n")
        golden.extend({"question": q, "expected_doc_id": doc_id, "difficulty": "easy"} for q in questions)

    golden.extend({"question": q, "expected_doc_id": d, "difficulty": "hard"} for q, d in HARD_QUESTIONS)

    with (golden_dir / "retrieval.jsonl").open("w") as f:
        for row in golden:
            f.write(json.dumps(row) + "\n")

    print(f"wrote {len(DOCS)} docs, {len(golden)} golden retrieval pairs")


if __name__ == "__main__":
    main()
