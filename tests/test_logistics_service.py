from datetime import datetime, timezone

from fastapi.testclient import TestClient

from logistics_service import MetricsClient, app, get_metrics_client


class RecordingMetrics(MetricsClient):
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def report(self, **point):
        self.calls.append(point)
        return {"accepted": True}


def test_late_delivery_requires_proof_and_reports_delay() -> None:
    recorder = RecordingMetrics()
    app.dependency_overrides[get_metrics_client] = lambda: recorder
    client = TestClient(app)

    response = client.post(
        "/shipment-events",
        json={
            "event_id": "evt-204",
            "shipment_id": "SHP-204",
            "carrier": "northline",
            "route": "sha-hgh",
            "status": "delivered",
            "occurred_at": "2026-08-18T10:45:00Z",
            "promised_at": "2026-08-18T10:00:00Z",
            "proof": {
                "object_key": "pod/SHP-204.jpg",
                "signed_by": "receiving-desk",
                "captured_at": "2026-08-18T10:44:00Z",
            },
        },
    )

    assert response.status_code == 200
    assert [call["name"] for call in recorder.calls] == [
        "logistics.shipment_events",
        "logistics.deliveries",
        "logistics.delivery_delay_minutes",
    ]
    assert recorder.calls[-1]["value"] == 45.0
    assert recorder.calls[-1]["type"] == "gauge"
    assert recorder.calls[0]["idempotency_key"] == "shipment-event:evt-204:0"
    app.dependency_overrides.clear()


def test_exception_without_classification_is_rejected() -> None:
    client = TestClient(app)
    response = client.post(
        "/shipment-events",
        json={
            "event_id": "evt-205",
            "shipment_id": "SHP-205",
            "carrier": "northline",
            "route": "sha-hgh",
            "status": "exception",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "promised_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert response.status_code == 422

