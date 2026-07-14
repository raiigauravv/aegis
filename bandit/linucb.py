"""LinUCB contextual bandit, implemented from scratch (disjoint linear models).

Per arm a: A_a = I*lambda + sum(x x^T), b_a = sum(r x). Selection maximizes the
upper confidence bound  theta_a . x + alpha * sqrt(x^T A_a^-1 x)  where
theta_a = A_a^-1 b_a. Sufficient statistics (A, b) serialize to plain lists so
they round-trip through DynamoDB items.

Reward design (ADR-004): +1 approved-unedited, +0.5 approved-light-edit,
0 heavy-edit, -0.5 rejected, -1 escalation-after-auto-send, minus a small
latency penalty. Governance rule: Tier-3 tickets NEVER go through the bandit
(governance > optimization).
"""

from typing import Any

import numpy as np

ARMS = [
    "fast_draft",  # A: Micro, k=3 retrieval
    "deep_research",  # B: Lite, k=8 + history tool
    "clarify_first",  # C: ask the customer a clarifying question
    "escalate_human",  # D: hand to a human immediately
]
DIM = 15  # see context.py


class LinUCB:
    def __init__(self, n_arms: int = len(ARMS), dim: int = DIM, alpha: float = 1.0) -> None:
        self.n_arms = n_arms
        self.dim = dim
        self.alpha = alpha
        self.A = [np.eye(dim) for _ in range(n_arms)]
        self.b = [np.zeros(dim) for _ in range(n_arms)]
        self.pulls = [0] * n_arms

    def ucb_scores(self, x: np.ndarray) -> np.ndarray:
        scores = np.empty(self.n_arms)
        for a in range(self.n_arms):
            a_inv = np.linalg.inv(self.A[a])
            theta = a_inv @ self.b[a]
            scores[a] = theta @ x + self.alpha * float(np.sqrt(x @ a_inv @ x))
        return scores

    def select(self, x: np.ndarray) -> int:
        scores = self.ucb_scores(x)
        best = np.flatnonzero(scores == scores.max())
        return int(np.random.default_rng().choice(best))

    def update(self, arm: int, x: np.ndarray, reward: float) -> None:
        self.A[arm] += np.outer(x, x)
        self.b[arm] += reward * x
        self.pulls[arm] += 1

    # --- DynamoDB round-trip ----------------------------------------------------

    def to_state(self) -> list[dict[str, Any]]:
        return [
            {
                "arm": ARMS[a] if a < len(ARMS) else str(a),
                "A": [[float(v) for v in row] for row in self.A[a]],
                "b": [float(v) for v in self.b[a]],
                "pulls": self.pulls[a],
            }
            for a in range(self.n_arms)
        ]

    @classmethod
    def from_state(cls, state: list[dict[str, Any]], alpha: float = 1.0) -> "LinUCB":
        dim = len(state[0]["b"])
        model = cls(n_arms=len(state), dim=dim, alpha=alpha)
        for a, item in enumerate(state):
            model.A[a] = np.array(item["A"], dtype=float)
            model.b[a] = np.array(item["b"], dtype=float)
            model.pulls[a] = int(item.get("pulls", 0))
        return model
