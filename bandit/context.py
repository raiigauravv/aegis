"""Ticket -> 15-dim context vector for the routing bandit.

Layout (keep stable; the sufficient statistics depend on it):
  0-5   intent one-hot (billing, access, technical, fraud_dispute, info, other)
        -- intent is "pending_bedrock" until the LLM triage lands; slot reserved
  6     sentiment (VADER compound, [-1, 1])
  7     urgency proxy (1 if sentiment <= -0.6 else 0)
  8-11  modality one-hot (text, pdf, image, audio)
  12    retrieval confidence (top KB hit score, 0 if unknown)
  13-14 risk tier one-hot for tiers 1-2 (tier 3 never reaches the bandit)
"""

from typing import Any

import numpy as np

INTENTS = ["billing", "access", "technical", "fraud_dispute", "info", "other"]
MODALITIES = ["text", "pdf", "image", "audio"]
DIM = 15


def build_context(meta: dict[str, Any], retrieval_confidence: float = 0.0) -> np.ndarray:
    x = np.zeros(DIM)
    intent = str(meta.get("intent", "other"))
    if intent in INTENTS:
        x[INTENTS.index(intent)] = 1.0
    else:
        x[INTENTS.index("other")] = 1.0
    try:
        sentiment = float(meta.get("sentiment", 0.0))
    except (TypeError, ValueError):
        sentiment = 0.0
    x[6] = sentiment
    x[7] = 1.0 if sentiment <= -0.6 else 0.0
    modality = str(meta.get("modality", "text"))
    if modality in MODALITIES:
        x[8 + MODALITIES.index(modality)] = 1.0
    x[12] = retrieval_confidence
    tier = int(meta.get("risk_tier", 1) or 1)
    if tier == 1:
        x[13] = 1.0
    elif tier == 2:
        x[14] = 1.0
    return x
