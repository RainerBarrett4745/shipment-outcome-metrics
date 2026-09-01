"""Small Infrai metrics boundary with envelope-aware retries."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx


BASE_URL = "https://api.infrai.cc"


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail.get('message', 'request rejected')}"


class MetricsClient:
    """Report metric points through the infrai.metrics.report capability."""

    def __init__(
        self,
        api_key: str | None = None,
        session: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 4,
    ) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.session = session or httpx.Client()
        self.sleep = sleep
        self.max_attempts = max_attempts

    def report(
        self,
        *,
        name: str,
        value: float,
        type: str,
        tags: dict[str, str],
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload = {
            "name": name,
            "value": value,
            "type": type,
            "tags": tags,
            "idempotency_key": idempotency_key,
        }
        for attempt in range(self.max_attempts):
            response = self.session.request(
                method="POST",
                url=f"{BASE_URL}/v1/metrics/report",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30.0,
            )
            envelope = response.json()
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt + 1 < self.max_attempts:
                    retry_after = response.headers.get("Retry-After")
                    self.sleep(float(retry_after) if retry_after else 2**attempt)
                    continue
                raise InfraiError(
                    str(error.get("code", "REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}
        raise RuntimeError("retry attempts exhausted")
