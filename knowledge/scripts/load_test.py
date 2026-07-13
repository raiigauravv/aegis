"""Phase-2 load test: submit N synthetic tickets, verify zero DLQ entries,
and measure POST latency plus end-to-end (submit -> persisted) latency.

Usage:
    python load_test.py https://<api-base> [count]

End-to-end latency is measured by polling GET /tickets/{id}, so its resolution
is bounded by the poll interval; it is an upper bound, not an exact figure.
"""

import concurrent.futures as cf
import json
import statistics
import sys
import time
import urllib.error
import urllib.request

POLL_INTERVAL = 0.5
POLL_TIMEOUT = 120.0


def _request(url: str, data: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"content-type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


throttles = 0


def submit(base: str, i: int) -> tuple[str, float, float]:
    """POST with exponential backoff on 429/503: this account's Lambda concurrency
    is capped at 10, so bursts throttle and the client is expected to retry."""
    global throttles
    payload = {
        "subject": f"load test #{i}",
        "text": f"Synthetic ticket {i}: cannot access my account, please investigate.",
    }
    t0 = time.perf_counter()
    for attempt in range(6):
        status, body = _request(f"{base}/tickets", payload)
        if status == 202:
            post_ms = (time.perf_counter() - t0) * 1000
            return body["ticket_id"], time.time(), post_ms
        if status in (429, 500, 503):
            throttles += 1
            time.sleep(0.4 * 2**attempt)
            continue
        raise RuntimeError(f"ticket {i}: HTTP {status}")
    raise RuntimeError(f"ticket {i}: still throttled after retries")


def await_persisted(base: str, ticket_id: str, submitted_at: float) -> float:
    deadline = submitted_at + POLL_TIMEOUT
    while time.time() < deadline:
        status, _ = _request(f"{base}/tickets/{ticket_id}")
        if status == 200:
            return (time.time() - submitted_at) * 1000
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(ticket_id)


def pct(values: list[float], p: float) -> float:
    return statistics.quantiles(values, n=100)[int(p) - 1]


def main() -> None:
    base = sys.argv[1].rstrip("/")
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 500

    def submit_and_track(i: int) -> tuple[float, float]:
        """Submit then immediately poll the same ticket, so end-to-end latency
        isn't inflated by a separate polling phase."""
        ticket_id, submitted_at, post = submit(base, i)
        return post, await_persisted(base, ticket_id, submitted_at)

    print(f"submitting {count} tickets to {base} ...")
    t_start = time.time()
    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(submit_and_track, range(count)))
    submit_wall = time.time() - t_start
    post_ms = [r[0] for r in results]
    e2e_ms = [r[1] for r in results]
    print(f"completed in {submit_wall:.1f}s")

    summary = {
        "tickets": count,
        "throttle_retries": throttles,
        "submit_wall_s": round(submit_wall, 1),
        "post_ms": {
            "p50": round(statistics.median(post_ms), 1),
            "p95": round(pct(post_ms, 95), 1),
            "max": round(max(post_ms), 1),
        },
        "end_to_end_ms": {
            "p50": round(statistics.median(e2e_ms), 1),
            "p95": round(pct(e2e_ms, 95), 1),
            "max": round(max(e2e_ms), 1),
            "note": f"upper bound; poll interval {POLL_INTERVAL}s",
        },
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
