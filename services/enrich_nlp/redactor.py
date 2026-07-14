"""PII detection and reversible redaction.

Presidio AnalyzerEngine (spaCy en_core_web_sm) plus custom Canadian recognizers:
  - CA_SIN: 3-3-3 digits, validated with the Luhn checksum SINs actually use
    (kills false positives on order numbers)
  - CA_POSTAL_CODE: letter-digit alternation, e.g. M5V 2T6

Redaction replaces each entity with a numbered placeholder ([EMAIL_1], [PHONE_2] ...)
and returns the reversible mapping separately — the mapping is stored in the
fenced-off pii-map table, never alongside the ticket.
"""

import re
from functools import lru_cache

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider

GATED_ENTITIES = [
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "CA_SIN",
    "CA_POSTAL_CODE",
]
_PLACEHOLDER_NAMES = {
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "CREDIT_CARD": "CARD",
    "CA_SIN": "SIN",
    "CA_POSTAL_CODE": "POSTAL",
    "PERSON": "NAME",
}


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class SinRecognizer(PatternRecognizer):
    def __init__(self) -> None:
        super().__init__(
            supported_entity="CA_SIN",
            patterns=[Pattern("ca_sin", r"\b\d{3}[- ]?\d{3}[- ]?\d{3}\b", 0.5)],
            context=["sin", "social insurance", "insurance number"],
        )

    def validate_result(self, pattern_text: str) -> bool:
        return _luhn_ok(re.sub(r"\D", "", pattern_text))


class PostalRecognizer(PatternRecognizer):
    def __init__(self) -> None:
        super().__init__(
            supported_entity="CA_POSTAL_CODE",
            patterns=[
                Pattern(
                    "ca_postal",
                    r"\b[ABCEGHJ-NPRSTVXYabceghj-nprstvxy]\d[A-Za-z][ -]?\d[A-Za-z]\d\b",
                    0.6,
                )
            ],
            context=["postal", "address", "mailing"],
        )


@lru_cache(maxsize=1)
def analyzer() -> AnalyzerEngine:
    # Pin the spaCy model explicitly: Presidio's default is en_core_web_lg, which
    # would trigger a runtime download inside the (network-restricted) Lambda.
    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        }
    )
    engine = AnalyzerEngine(nlp_engine=provider.create_engine())
    engine.registry.add_recognizer(SinRecognizer())
    engine.registry.add_recognizer(PostalRecognizer())
    return engine


def detect(text: str, entities: list[str] | None = None) -> list[RecognizerResult]:
    results = analyzer().analyze(text=text, language="en", entities=entities or GATED_ENTITIES)
    # drop overlapping lower-score hits (e.g. SIN digits also matching phone)
    results.sort(key=lambda r: (r.start, -r.score))
    kept: list[RecognizerResult] = []
    for r in results:
        if any(r.start < k.end and r.end > k.start for k in kept):
            continue
        kept.append(r)
    return kept


def redact(text: str) -> tuple[str, dict[str, str]]:
    """Return (redacted_text, {placeholder: original})."""
    found = detect(text)
    counters: dict[str, int] = {}
    mapping: dict[str, str] = {}
    out, cursor = [], 0
    for r in sorted(found, key=lambda r: r.start):
        name = _PLACEHOLDER_NAMES.get(r.entity_type, r.entity_type)
        counters[name] = counters.get(name, 0) + 1
        placeholder = f"[{name}_{counters[name]}]"
        mapping[placeholder] = text[r.start : r.end]
        out.append(text[cursor : r.start])
        out.append(placeholder)
        cursor = r.end
    out.append(text[cursor:])
    return "".join(out), mapping
