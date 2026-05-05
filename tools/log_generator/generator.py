"""Fake log generator for LogIQ development. Pushes structured JSON logs to Loki."""

import asyncio
import json
import os
import random
import time
import uuid
from datetime import datetime, timezone

import httpx

LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100")
ENVIRONMENT = "production"


# ---------------------------------------------------------------------------
# Log event construction
# ---------------------------------------------------------------------------

def make_log_event(
    service: str,
    severity: str,
    message: str,
    metadata: dict | None = None,
    trace_id: str | None = None,
) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "service": service,
        "environment": ENVIRONMENT,
        "trace_id": trace_id or uuid.uuid4().hex[:16],
        "span_id": uuid.uuid4().hex[:8],
        "message": message,
        "metadata": metadata or {},
    }


def make_loki_payload(events: list[dict]) -> dict:
    streams: dict[tuple[str, str, str], list] = {}
    for event in events:
        key = (event["service"], event["environment"], event["severity"])
        if key not in streams:
            streams[key] = []
        ts_ns = str(time.time_ns())
        streams[key].append([ts_ns, json.dumps(event)])

    return {
        "streams": [
            {
                "stream": {
                    "service": service,
                    "environment": env,
                    "severity": severity,
                },
                "values": values,
            }
            for (service, env, severity), values in streams.items()
        ]
    }


# ---------------------------------------------------------------------------
# Failure cycle scheduling
# ---------------------------------------------------------------------------

class FailureCycle:
    def __init__(self, name: str, interval_seconds: float, duration_seconds: float) -> None:
        self.name = name
        self.interval_seconds = interval_seconds
        self.duration_seconds = duration_seconds
        self._next_start: float = 0.0
        self._initialized: bool = False

    def is_active(self) -> bool:
        now = time.monotonic()
        if not self._initialized:
            self._next_start = now + random.uniform(30, self.interval_seconds)
            self._initialized = True
            return False
        if now < self._next_start:
            return False
        if now < self._next_start + self.duration_seconds:
            return True
        # Burst ended — advance to next cycle
        while self._next_start + self.duration_seconds <= now:
            self._next_start += self.interval_seconds
        return False


# ---------------------------------------------------------------------------
# Log templates
# ---------------------------------------------------------------------------

NORMAL_TEMPLATES: dict[str, list] = {
    "auth-service": [
        ("INFO",  "User login successful",         lambda: {"user_id": f"user_{random.randint(1000, 9999)}"}),
        ("INFO",  "Token validated successfully",  lambda: {"token_type": "bearer", "expires_in": 3600}),
        ("INFO",  "User logout",                   lambda: {"user_id": f"user_{random.randint(1000, 9999)}", "session_duration_s": random.randint(30, 3600)}),
        ("WARN",  "Failed login attempt",          lambda: {"reason": "invalid_password", "attempt": random.randint(1, 3), "ip": f"192.168.1.{random.randint(1, 255)}"}),
        ("DEBUG", "Session token refreshed",       lambda: {"expires_in": 3600}),
    ],
    "api-gateway": [
        ("INFO",  "Request routed to auth-service",     lambda: {"method": "POST", "path": "/auth/login",     "duration_ms": random.randint(10, 150)}),
        ("INFO",  "Request routed to payments-service", lambda: {"method": "POST", "path": "/payments/charge","duration_ms": random.randint(50, 300)}),
        ("INFO",  "Request routed to user-service",     lambda: {"method": "GET",  "path": "/users/profile",  "duration_ms": random.randint(5, 80)}),
        ("WARN",  "Rate limit approaching for client",  lambda: {"client_ip": f"10.0.0.{random.randint(1, 255)}", "requests_per_min": random.randint(80, 95)}),
        ("DEBUG", "Health check passed",                lambda: {}),
    ],
    "payments-service": [
        ("INFO",  "Transaction processed successfully", lambda: {"transaction_id": f"txn_{uuid.uuid4().hex[:8]}", "amount": round(random.uniform(1, 500), 2), "currency": "USD"}),
        ("INFO",  "Refund issued",                      lambda: {"transaction_id": f"txn_{uuid.uuid4().hex[:8]}", "amount": round(random.uniform(1, 200), 2)}),
        ("WARN",  "Payment provider slow response",     lambda: {"provider": "stripe", "latency_ms": random.randint(1000, 2500)}),
        ("DEBUG", "Idempotency key validated",          lambda: {"key": uuid.uuid4().hex}),
    ],
    "user-service": [
        ("INFO",  "User profile fetched",  lambda: {"user_id": f"user_{random.randint(1000, 9999)}", "cache_hit": random.choice([True, False])}),
        ("INFO",  "User profile updated",  lambda: {"user_id": f"user_{random.randint(1000, 9999)}", "fields": random.sample(["email", "name", "avatar", "preferences"], k=random.randint(1, 3))}),
        ("DEBUG", "Cache hit",             lambda: {"user_id": f"user_{random.randint(1000, 9999)}"}),
        ("DEBUG", "DB query executed",     lambda: {"duration_ms": random.randint(1, 50), "rows": random.randint(0, 10)}),
    ],
}

FAILURE_TEMPLATES: dict[str, dict] = {
    "db_pool_exhaustion": {
        "logs": {
            "auth-service": [
                ("ERROR", "connection pool exhausted after 3 retries",             lambda: {"pool_size": 10, "active_connections": 10, "db_host": "postgres:5432"}),
                ("ERROR", "failed to acquire DB connection: timeout after 5000ms", lambda: {"pool_size": 10, "wait_ms": 5000, "queue_depth": random.randint(10, 50)}),
                ("WARN",  "falling back to read replica",                          lambda: {"replica_host": "postgres-replica:5432"}),
            ],
        },
    },
    "auth_spike": {
        "logs": {
            "auth-service": [
                ("ERROR", "401 Unauthorized: brute force detected",  lambda: {"ip": f"185.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}", "attempts": random.randint(5, 20)}),
                ("ERROR", "account locked after 5 failed attempts",  lambda: {"user_id": f"user_{random.randint(1000, 9999)}", "ip": f"185.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"}),
            ],
            "api-gateway": [
                ("ERROR", "rate limit exceeded for client",          lambda: {"client_ip": f"185.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}", "limit": 100, "window": "1m", "requests": random.randint(150, 500)}),
                ("WARN",  "suspicious request pattern detected",     lambda: {"client_ip": f"10.0.0.{random.randint(1,255)}", "requests_per_min": random.randint(120, 500)}),
            ],
        },
    },
    "payment_timeout": {
        "logs": {
            "payments-service": [
                ("ERROR", "upstream timeout after 30s waiting for payment provider", lambda: {"provider": "stripe", "timeout_ms": 30000, "transaction_id": f"txn_{uuid.uuid4().hex[:8]}"}),
                ("ERROR", "transaction rolled back due to provider timeout",         lambda: {"transaction_id": f"txn_{uuid.uuid4().hex[:8]}", "amount": round(random.uniform(1, 500), 2), "currency": "USD"}),
                ("WARN",  "retrying payment request",                                lambda: {"attempt": random.randint(1, 3), "provider": "stripe"}),
            ],
        },
    },
    "user_service_degradation": {
        "logs": {
            "user-service": [
                ("WARN",  "high latency detected on DB query",                lambda: {"duration_ms": random.randint(2000, 5000), "query": "SELECT * FROM users WHERE id = $1", "threshold_ms": 1000}),
                ("WARN",  "response time degraded",                           lambda: {"p95_ms": random.randint(3000, 8000)}),
                ("ERROR", "DB query failed: connection reset by peer",        lambda: {"host": "postgres:5432", "duration_ms": random.randint(5000, 10000)}),
                ("ERROR", "request timeout: user profile fetch exceeded 10s", lambda: {"user_id": f"user_{random.randint(1000, 9999)}", "timeout_ms": 10000}),
            ],
        },
    },
}

FAILURE_CYCLES: dict[str, FailureCycle] = {
    "db_pool_exhaustion":       FailureCycle("db_pool_exhaustion",       interval_seconds=600,  duration_seconds=60),
    "auth_spike":               FailureCycle("auth_spike",               interval_seconds=1200, duration_seconds=90),
    "payment_timeout":          FailureCycle("payment_timeout",          interval_seconds=900,  duration_seconds=45),
    "user_service_degradation": FailureCycle("user_service_degradation", interval_seconds=1500, duration_seconds=120),
}


# ---------------------------------------------------------------------------
# Async generation loops
# ---------------------------------------------------------------------------

async def push_to_loki(payload: dict, client: httpx.AsyncClient) -> None:
    await client.post(
        f"{LOKI_URL}/loki/api/v1/push",
        json=payload,
        timeout=10.0,
    )


async def generate_baseline(client: httpx.AsyncClient) -> None:
    """Generate ~2 logs/second across all services continuously."""
    services = list(NORMAL_TEMPLATES.keys())
    while True:
        service = random.choice(services)
        severity, message, metadata_fn = random.choice(NORMAL_TEMPLATES[service])
        event = make_log_event(service, severity, message, metadata_fn())
        try:
            await push_to_loki(make_loki_payload([event]), client)
        except Exception as exc:
            print(f"[generator] baseline push failed: {exc}", flush=True)
        await asyncio.sleep(0.5)


async def generate_failures(client: httpx.AsyncClient) -> None:
    """Drive failure bursts on scheduled cycles. Shared trace_id across services per burst."""
    active_traces: dict[str, str] = {}
    while True:
        events = []
        for cycle_name, cycle in FAILURE_CYCLES.items():
            if cycle.is_active():
                if cycle_name not in active_traces:
                    active_traces[cycle_name] = uuid.uuid4().hex[:16]
                trace_id = active_traces[cycle_name]
                for service, logs in FAILURE_TEMPLATES[cycle_name]["logs"].items():
                    severity, message, metadata_fn = random.choice(logs)
                    events.append(make_log_event(service, severity, message, metadata_fn(), trace_id))
            else:
                active_traces.pop(cycle_name, None)

        if events:
            try:
                await push_to_loki(make_loki_payload(events), client)
            except Exception as exc:
                print(f"[generator] failure push failed: {exc}", flush=True)

        await asyncio.sleep(0.1)


async def wait_for_loki(client: httpx.AsyncClient) -> None:
    print("[generator] waiting for Loki...", flush=True)
    for _ in range(30):
        try:
            resp = await client.get(f"{LOKI_URL}/ready", timeout=5.0)
            if resp.status_code == 200:
                print("[generator] Loki ready — starting log generation", flush=True)
                return
        except Exception:
            pass
        await asyncio.sleep(2)
    raise RuntimeError("Loki did not become ready after 60 seconds")


async def main() -> None:
    async with httpx.AsyncClient() as client:
        await wait_for_loki(client)
        await asyncio.gather(
            generate_baseline(client),
            generate_failures(client),
        )


if __name__ == "__main__":
    asyncio.run(main())
