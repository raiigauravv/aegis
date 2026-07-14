"""Golden PII redaction suite: 50 crafted strings with labeled entities.

Canadian formats emphasized (SIN with valid Luhn, postal codes, phone formats).
Negatives are strings that LOOK like PII but must not be flagged (Luhn-invalid
SINs, order numbers, SKUs). Suite gates detection precision/recall by type+span.

Each case: (text, [(entity_type, substring), ...]) — substring must be unique in text.
"""

# Luhn-valid SINs for testing (standard synthetic test numbers)
VALID_SINS = ["046 454 286", "046454286", "046-454-286", "130 692 544"]

CASES: list[tuple[str, list[tuple[str, str]]]] = [
    # --- SIN positives (valid Luhn) ---
    ("My SIN is 046 454 286 if you need it", [("CA_SIN", "046 454 286")]),
    ("sin: 046454286", [("CA_SIN", "046454286")]),
    ("Social insurance number 046-454-286 attached", [("CA_SIN", "046-454-286")]),
    ("For taxes my sin is 130 692 544 thanks", [("CA_SIN", "130 692 544")]),
    # --- SIN negatives (Luhn-invalid or plain numbers) ---
    ("my order number is 123 456 789", []),
    ("reference 111-111-111 from your letter", []),
    ("the invoice total was 123456789 cents", []),
    # --- postal codes ---
    ("I live at M5V 2T6 downtown", [("CA_POSTAL_CODE", "M5V 2T6")]),
    ("mailing address ends with K1A0B1", [("CA_POSTAL_CODE", "K1A0B1")]),
    ("ship it to H3Z 2Y7 please", [("CA_POSTAL_CODE", "H3Z 2Y7")]),
    ("my postal code is V6B 4Y8.", [("CA_POSTAL_CODE", "V6B 4Y8")]),
    ("new address: T2X 1V4 Calgary", [("CA_POSTAL_CODE", "T2X 1V4")]),
    # --- postal negatives ---
    ("error code D4E 5F6 is not a postal code but looks close", []),  # D not valid lead
    ("product SKU 12ABC3 should not match", []),
    # --- phones ---
    ("call me at 416-555-0134", [("PHONE_NUMBER", "416-555-0134")]),
    ("phone: (604) 555-0189", [("PHONE_NUMBER", "(604) 555-0189")]),
    ("reach me on +1 905 555 0117 after 5", [("PHONE_NUMBER", "+1 905 555 0117")]),
    ("my cell 613.555.0142 anytime", [("PHONE_NUMBER", "613.555.0142")]),
    ("landline is 5145550166", [("PHONE_NUMBER", "5145550166")]),
    # --- emails ---
    ("email me at jane.doe@example.com", [("EMAIL_ADDRESS", "jane.doe@example.com")]),
    ("contact: support+billing@northstar.ca", [("EMAIL_ADDRESS", "support+billing@northstar.ca")]),
    ("it's g.rai_92@mail.example.org ok", [("EMAIL_ADDRESS", "g.rai_92@mail.example.org")]),
    # --- credit cards (test numbers, Luhn-valid) ---
    ("card 4111 1111 1111 1111 was charged twice", [("CREDIT_CARD", "4111 1111 1111 1111")]),
    ("my visa 4012888888881881 expired", [("CREDIT_CARD", "4012888888881881")]),
    ("mastercard 5555-5555-5555-4444 please remove", [("CREDIT_CARD", "5555-5555-5555-4444")]),
    # --- card negatives ---
    ("tracking number 9400 1000 0000 0000 0000 00", []),
    # --- mixed / multi-entity ---
    (
        "I'm at M4B 1B3, call 416-555-0199 or email a@b.ca",
        [
            ("CA_POSTAL_CODE", "M4B 1B3"),
            ("PHONE_NUMBER", "416-555-0199"),
            ("EMAIL_ADDRESS", "a@b.ca"),
        ],
    ),
    (
        "SIN 046 454 286 and card 4111 1111 1111 1111 for verification",
        [("CA_SIN", "046 454 286"), ("CREDIT_CARD", "4111 1111 1111 1111")],
    ),
    (
        "Update my file: phone (403) 555-0173, postal T3A 0H8",
        [("PHONE_NUMBER", "(403) 555-0173"), ("CA_POSTAL_CODE", "T3A 0H8")],
    ),
    # --- clean negatives ---
    ("I just cannot log into the app since Tuesday", []),
    ("the fee of $45 seems way too high for one bounced payment", []),
    ("your branch on Main Street closes too early", []),
    ("transferred $300 to my daughter yesterday", []),
    ("app version 8.3.1 crashes on the payees screen", []),
    ("ticket INC-449201 was never answered", []),
    ("I waited 45 minutes on hold at 3 pm", []),
    ("my balance shows 1,234.56 which is wrong", []),
    ("error NS-403 again after the update", []),
    ("the ATM at 25 King St ate my deposit", []),
    ("routing through account ending 4581 fine", []),
    # --- harder formats ---
    ("Phone# 1-800-555-0155 ext 22", [("PHONE_NUMBER", "1-800-555-0155")]),
    (
        "emails: first@x.io and second@y.io both bounce",
        [("EMAIL_ADDRESS", "first@x.io"), ("EMAIL_ADDRESS", "second@y.io")],
    ),
    ("her sin (130 692 544) was on the form", [("CA_SIN", "130 692 544")]),
    ("code m5v2t6 written lowercase", [("CA_POSTAL_CODE", "m5v2t6")]),
    ("call +14165550134 now", [("PHONE_NUMBER", "+14165550134")]),
    ("amex 3782 822463 10005 on file", [("CREDIT_CARD", "3782 822463 10005")]),
    ("my email is definitely not-an-email@", []),
    ("SIN ending in 286 only", []),
    ("phone number withheld", []),
    ("A1A 1A1 is the classic example postal code", [("CA_POSTAL_CODE", "A1A 1A1")]),
]

assert len(CASES) == 50, f"suite must stay at 50 cases, has {len(CASES)}"
