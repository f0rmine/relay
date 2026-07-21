import json
import logging
import re
import secrets
from collections import defaultdict
from contextvars import ContextVar
from threading import Lock
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

logger = logging.getLogger("relay.http")
REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
KNOWN_HTTP_METHODS = {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"}
request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


class HttpMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._duration_buckets: dict[tuple[str, str, float], int] = defaultdict(int)
        self._duration_counts: dict[tuple[str, str], int] = defaultdict(int)
        self._duration_sums: dict[tuple[str, str], float] = defaultdict(float)

    def observe(self, method: str, route: str, status_code: int, duration: float) -> None:
        with self._lock:
            self._requests[(method, route, status_code)] += 1
            duration_key = (method, route)
            self._duration_counts[duration_key] += 1
            self._duration_sums[duration_key] += duration
            for bucket in LATENCY_BUCKETS:
                if duration <= bucket:
                    self._duration_buckets[(method, route, bucket)] += 1

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()
            self._duration_buckets.clear()
            self._duration_counts.clear()
            self._duration_sums.clear()

    def render(self) -> str:
        lines = [
            "# HELP relay_http_requests_total Total HTTP requests.",
            "# TYPE relay_http_requests_total counter",
        ]
        with self._lock:
            requests = dict(self._requests)
            duration_buckets = dict(self._duration_buckets)
            duration_counts = dict(self._duration_counts)
            duration_sums = dict(self._duration_sums)
        for (method, route, status_code), count in sorted(requests.items()):
            labels = _labels(method=method, route=route, status=str(status_code))
            lines.append(f"relay_http_requests_total{{{labels}}} {count}")
        lines.extend(
            [
                "# HELP relay_http_request_duration_seconds HTTP request latency.",
                "# TYPE relay_http_request_duration_seconds histogram",
            ]
        )
        for (method, route), count in sorted(duration_counts.items()):
            base_labels = {"method": method, "route": route}
            for bucket in LATENCY_BUCKETS:
                labels = _labels(**base_labels, le=str(bucket))
                lines.append(
                    "relay_http_request_duration_seconds_bucket"
                    f"{{{labels}}} {duration_buckets.get((method, route, bucket), 0)}"
                )
            labels = _labels(**base_labels, le="+Inf")
            lines.append(
                f"relay_http_request_duration_seconds_bucket{{{labels}}} {count}"
            )
            labels = _labels(**base_labels)
            lines.append(
                "relay_http_request_duration_seconds_sum"
                f"{{{labels}}} {duration_sums[(method, route)]:.9f}"
            )
            lines.append(
                f"relay_http_request_duration_seconds_count{{{labels}}} {count}"
            )
        return "\n".join(lines) + "\n"


http_metrics = HttpMetrics()


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(**labels: str) -> str:
    return ",".join(
        f'{name}="{_escape_label(value)}"' for name, value in sorted(labels.items())
    )


def _request_id(request: Request) -> str:
    supplied = request.headers.get(REQUEST_ID_HEADER, "")
    return supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid4())


def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


def _method_label(method: str) -> str:
    return method if method in KNOWN_HTTP_METHODS else "OTHER"


def install_observability(app: FastAPI) -> None:
    @app.middleware("http")
    async def observe_request(request: Request, call_next):
        request_id = _request_id(request)
        token = request_id_context.set(request_id)
        started = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        except Exception:
            logger.exception(
                json.dumps(
                    {
                        "event": "http_request_failed",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                    },
                    separators=(",", ":"),
                )
            )
            raise
        finally:
            duration = perf_counter() - started
            route = _route_label(request)
            if route != "/metrics":
                http_metrics.observe(_method_label(request.method), route, status_code, duration)
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": request.method,
                        "route": route,
                        "status": status_code,
                        "duration_ms": round(duration * 1000, 3),
                    },
                    separators=(",", ":"),
                )
            )
            request_id_context.reset(token)


def metrics_response(request: Request, enabled: bool, bearer_token: str | None) -> PlainTextResponse:
    if not enabled:
        return PlainTextResponse("Not found", status_code=404)
    if not bearer_token:
        return PlainTextResponse("Metrics authentication is not configured", status_code=503)
    authorization = request.headers.get("Authorization")
    expected = f"Bearer {bearer_token}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        return PlainTextResponse("Unauthorized", status_code=401)
    return PlainTextResponse(
        http_metrics.render(),
        media_type="text/plain; version=0.0.4",
        headers={"Cache-Control": "no-store"},
    )
