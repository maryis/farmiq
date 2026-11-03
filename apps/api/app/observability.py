from __future__ import annotations

from collections import defaultdict
from threading import Lock

from fastapi import Request

_lock = Lock()
_requests: dict[tuple[str, str, int], int] = defaultdict(int)
_duration_sum: dict[tuple[str, str], float] = defaultdict(float)


def record_request(method: str, path: str, status: int, duration_seconds: float) -> None:
    with _lock:
        _requests[(method, path, status)] += 1
        _duration_sum[(method, path)] += duration_seconds


def render_prometheus() -> str:
    lines = [
        "# HELP farmiq_http_requests_total Total HTTP requests.",
        "# TYPE farmiq_http_requests_total counter",
    ]
    with _lock:
        for (method, path, status), value in sorted(_requests.items()):
            safe_path = path.replace('"', '\\"')
            lines.append(
                f'farmiq_http_requests_total{{method="{method}",path="{safe_path}",status="{status}"}} {value}'
            )
        lines.extend(
            [
                "# HELP farmiq_http_request_duration_seconds_sum Sum of request durations.",
                "# TYPE farmiq_http_request_duration_seconds_sum counter",
            ]
        )
        for (method, path), value in sorted(_duration_sum.items()):
            safe_path = path.replace('"', '\\"')
            lines.append(
                f'farmiq_http_request_duration_seconds_sum{{method="{method}",path="{safe_path}"}} {value:.6f}'
            )
    return "\n".join(lines) + "\n"
