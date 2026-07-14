"""Offline bandit simulator: LinUCB vs epsilon-greedy vs uniform random.

Synthetic ticket environment: contexts drawn from realistic ticket distributions
(intent mix, sentiment skewed negative, modality mix), true reward is linear per
arm with structure that makes routing matter (e.g. deep_research pays off for
technical tickets with low retrieval confidence; fast_draft wins easy billing
questions; escalation is right for angry tier-2 tickets). Rewards are the
discrete feedback values from ADR-004 (+1/+0.5/0/-0.5), chosen stochastically
with probabilities from the linear score — mirroring how the online loop
actually learns from approve/edit/reject clicks.

Output: bandit/notebooks/regret_curves.png + summary stats (README material).

Run: python bandit/simulator.py [rounds] [seeds]
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bandit.context import DIM, INTENTS, MODALITIES  # noqa: E402
from bandit.linucb import ARMS, LinUCB  # noqa: E402

REWARD_LEVELS = np.array([1.0, 0.5, 0.0, -0.5])


def sample_context(rng: np.random.Generator) -> np.ndarray:
    x = np.zeros(DIM)
    x[rng.choice(len(INTENTS), p=[0.25, 0.25, 0.2, 0.1, 0.15, 0.05])] = 1.0
    sentiment = float(np.clip(rng.normal(-0.2, 0.5), -1, 1))
    x[6] = sentiment
    x[7] = 1.0 if sentiment <= -0.6 else 0.0
    x[8 + rng.choice(len(MODALITIES), p=[0.6, 0.2, 0.1, 0.1])] = 1.0
    x[12] = float(rng.beta(3, 2))  # retrieval confidence
    x[13 + rng.choice(2, p=[0.8, 0.2])] = 1.0  # tier 1 or 2
    return x


def true_arm_weights(rng: np.random.Generator) -> list[np.ndarray]:
    """Hand-shaped structure + noise, so the optimal policy is context-dependent."""
    w = [rng.normal(0, 0.05, size=DIM) for _ in ARMS]
    fast, deep, clarify, escalate = w
    fast[0] += 0.8  # billing -> fast draft fine
    fast[12] += 0.6  # high retrieval confidence -> fast draft fine
    deep[2] += 0.9  # technical -> research pays
    deep[12] -= 0.5  # low confidence -> research pays (negative weight on conf)
    deep[9] += 0.4  # pdf tickets benefit from research
    clarify[5] += 0.7  # "other"/unclear intent -> clarify
    clarify[6] -= 0.2
    escalate[7] += 0.9  # urgent-angry -> human
    escalate[14] += 0.6  # tier 2 -> human
    return w


def expected_reward(w: np.ndarray, x: np.ndarray) -> float:
    """Map linear score -> expected discrete feedback reward."""
    p_good = 1 / (1 + np.exp(-4 * (w @ x)))  # sigmoid sharpens the choice
    probs = np.array([p_good * 0.6, p_good * 0.4, (1 - p_good) * 0.5, (1 - p_good) * 0.5])
    return float(REWARD_LEVELS @ probs)


def draw_reward(w: np.ndarray, x: np.ndarray, rng: np.random.Generator) -> float:
    p_good = 1 / (1 + np.exp(-4 * (w @ x)))
    probs = np.array([p_good * 0.6, p_good * 0.4, (1 - p_good) * 0.5, (1 - p_good) * 0.5])
    return float(rng.choice(REWARD_LEVELS, p=probs / probs.sum()))


def run_policy(policy: str, rounds: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    w = true_arm_weights(np.random.default_rng(42))  # env fixed across seeds
    model = LinUCB(alpha=1.0)
    regret = np.zeros(rounds)
    for t in range(rounds):
        x = sample_context(rng)
        exp = [expected_reward(wa, x) for wa in w]
        if policy == "random":
            arm = int(rng.integers(len(ARMS)))
        elif policy == "epsilon":
            arm = (
                int(rng.integers(len(ARMS)))
                if rng.random() < 0.1
                else int(np.argmax([(model.b[a] @ x) for a in range(len(ARMS))]))
            )
        else:
            arm = model.select(x)
        r = draw_reward(w[arm], x, rng)
        if policy in ("linucb", "epsilon"):
            model.update(arm, x, r)
        regret[t] = max(exp) - exp[arm]
    return np.cumsum(regret)


def main() -> None:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    seeds = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    curves = {}
    for policy in ("linucb", "epsilon", "random"):
        runs = np.stack([run_policy(policy, rounds, s) for s in range(seeds)])
        curves[policy] = runs.mean(axis=0)
        print(f"{policy:8s} final cumulative regret: {curves[policy][-1]:8.1f}")

    lift = (curves["random"][-1] - curves["linucb"][-1]) / curves["random"][-1]
    print(f"\nLinUCB regret reduction vs random: {lift:.1%} over {rounds} rounds x {seeds} seeds")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 5))
    labels = {"linucb": "LinUCB (α=1.0)", "epsilon": "ε-greedy (0.1)", "random": "uniform random"}
    for policy, curve in curves.items():
        ax.plot(curve, label=labels[policy], linewidth=2)
    ax.set_xlabel("tickets routed")
    ax.set_ylabel("cumulative regret")
    ax.set_title(f"Routing policy regret ({seeds}-seed mean, simulated feedback)")
    ax.legend()
    ax.grid(alpha=0.3)
    out = Path(__file__).parent / "notebooks" / "regret_curves.png"
    out.parent.mkdir(exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
