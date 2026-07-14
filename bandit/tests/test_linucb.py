import numpy as np
import pytest

from bandit.context import DIM, build_context
from bandit.linucb import ARMS, LinUCB


def test_converges_to_best_arm_in_stationary_env() -> None:
    rng = np.random.default_rng(7)
    true_theta = [rng.normal(size=DIM) for _ in ARMS]
    best_gap_wins = 0
    model = LinUCB(alpha=1.0)
    for t in range(3000):
        x = rng.normal(size=DIM)
        x /= np.linalg.norm(x)
        arm = model.select(x)
        reward = float(true_theta[arm] @ x + rng.normal(scale=0.1))
        model.update(arm, x, reward)
        if t >= 2500:  # after burn-in, choices should mostly be optimal
            best = int(np.argmax([th @ x for th in true_theta]))
            best_gap_wins += arm == best
    assert best_gap_wins / 500 > 0.8


def test_ucb_prefers_unexplored_arm() -> None:
    model = LinUCB(alpha=2.0)
    x = np.ones(DIM) / np.sqrt(DIM)
    for _ in range(50):
        model.update(0, x, 0.2)  # arm 0 well-known, mediocre
    scores = model.ucb_scores(x)
    assert scores[1] > scores[0]  # unexplored arm keeps a wide bonus


def test_state_roundtrip_preserves_decisions() -> None:
    rng = np.random.default_rng(3)
    model = LinUCB()
    for _ in range(100):
        x = rng.normal(size=DIM)
        model.update(rng.integers(len(ARMS)), x, float(rng.normal()))
    clone = LinUCB.from_state(model.to_state())
    x = rng.normal(size=DIM)
    np.testing.assert_allclose(model.ucb_scores(x), clone.ucb_scores(x), rtol=1e-10)


def test_context_layout() -> None:
    meta = {"sentiment": "-0.8", "modality": "audio", "risk_tier": 2, "intent": "pending_bedrock"}
    x = build_context(meta, retrieval_confidence=0.7)
    assert x[5] == 1.0  # unknown intent -> "other"
    assert x[6] == pytest.approx(-0.8)
    assert x[7] == 1.0  # urgent
    assert x[11] == 1.0  # audio
    assert x[12] == pytest.approx(0.7)
    assert x[14] == 1.0  # tier 2
    assert x.shape == (DIM,)
