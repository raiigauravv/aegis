"""Online bandit episodes through the REAL pipeline.

Each episode: POST a synthetic ticket -> wait for enrichment -> POST /route
(live LinUCB picks an arm from live DynamoDB state) -> a synthetic user reacts
(same preference structure as the offline simulator) -> POST /feedback ->
the live policy updates. The learning curve this produces is genuine: real
Lambdas, real DynamoDB sufficient statistics, real SQS feedback loop.

Output: bandit/notebooks/online_learning.png + episodes JSONL.

Usage: python knowledge/scripts/online_episodes.py <api-base> [episodes]
"""

import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bandit.linucb import ARMS  # noqa: E402
from bandit.simulator import draw_reward, sample_context, true_arm_weights  # noqa: E402

REWARD_TO_ACTION = {1.0: "approve", 0.5: "approve_edited", 0.0: "heavy_edit", -0.5: "reject"}

TEMPLATES = [
    ("billing", "The monthly fee on my chequing account looks wrong, why am I paying {n} dollars"),
    ("access", "I cannot sign into the app, it shows error NS-40{d} again and again"),
    ("technical", "The app crashes on the payees screen since the last update, version 8.{d}"),
    ("info", "What are the e-transfer limits for premium accounts exactly"),
    ("other", "Something odd happened with my account this week, hard to describe"),
]


def _req(url: str, data: dict | None = None) -> tuple[int, dict]:
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        headers={"content-type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
            if e.code in (429, 500, 503):
                time.sleep(0.5 * 2**attempt)
                continue
            return e.code, {}
        except Exception:
            time.sleep(0.5 * 2**attempt)
    return 0, {}


def episode(base: str, i: int, rng: np.random.Generator, weights: list) -> dict | None:
    intent, template = TEMPLATES[i % len(TEMPLATES)]
    text = template.format(n=rng.integers(5, 40), d=rng.integers(1, 9))
    if rng.random() < 0.25:
        text += " and honestly I am really frustrated with this whole situation"
    status, r = _req(f"{base}/tickets", {"text": text, "subject": f"episode {i}"})
    if status != 202:
        return None
    tid = r["ticket_id"]
    for _ in range(40):  # wait for enrichment
        time.sleep(1.0)
        status, t = _req(f"{base}/tickets/{tid}")
        if status == 200 and t["meta"]["status"] in ("enriched", "awaiting_approval"):
            break
    else:
        return None
    if t["meta"]["status"] == "awaiting_approval":
        return {"episode": i, "skipped": "tier3"}
    status, route = _req(f"{base}/tickets/{tid}/route", {})
    if status != 200 or not route.get("bandit"):
        return {"episode": i, "skipped": "no_bandit"}
    arm_idx = ARMS.index(route["arm"])
    x = sample_context(rng)  # synthetic-user preference features
    reward = draw_reward(weights[arm_idx], x, rng)
    _req(f"{base}/tickets/{tid}/feedback", {"action": REWARD_TO_ACTION[reward]})
    return {"episode": i, "arm": route["arm"], "reward": reward}


def main() -> None:
    base = sys.argv[1].rstrip("/")
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    rng = np.random.default_rng(11)
    weights = true_arm_weights(np.random.default_rng(42))

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for out in pool.map(lambda i: episode(base, i, rng, weights), range(n)):
            if out:
                results.append(out)
            if len(results) % 25 == 0:
                print(f"  {len(results)} episodes done")

    rewards = [r["reward"] for r in results if "reward" in r]
    out_path = ROOT / "bandit" / "notebooks" / "online_episodes.jsonl"
    out_path.write_text("\n".join(json.dumps(r) for r in results))

    window = 40
    ma = np.convolve(rewards, np.ones(window) / window, mode="valid")
    random_baseline = float(np.mean(rewards[:window]))  # early ≈ exploring ≈ near-random

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(range(window - 1, len(rewards)), ma, linewidth=2, label=f"reward ({window}-ep moving avg)")
    ax.axhline(random_baseline, linestyle="--", alpha=0.6, label="early-exploration baseline")
    ax.set_xlabel("live episodes")
    ax.set_ylabel("reward")
    ax.set_title(f"Online LinUCB on production infra ({len(rewards)} episodes)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(ROOT / "bandit" / "notebooks" / "online_learning.png", dpi=130)

    print(
        json.dumps(
            {
                "episodes": len(rewards),
                "mean_reward_first_50": round(float(np.mean(rewards[:50])), 3),
                "mean_reward_last_50": round(float(np.mean(rewards[-50:])), 3),
                "cumulative_reward": round(float(np.sum(rewards)), 1),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
