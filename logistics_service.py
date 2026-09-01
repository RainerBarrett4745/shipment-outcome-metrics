"""Turn a shipment event into business metrics and expose it over HTTP."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

from infrai_metrics import InfraiError, MetricsClient


class ShipmentStatus(str, Enum):
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    EXCEPTION = "exception"


class ProofOfDelivery(BaseModel):
    object_key: str = Field(min_length=1)
    signed_by: str = Field(min_length=1)
    captured_at: datetime


class ShipmentEvent(BaseModel):
    event_id: str = Field(min_length=1)
    shipment_id: str = Field(min_length=1)
    carrier: str = Field(min_length=1)
    route: str = Field(min_length=1)
    status: ShipmentStatus
    occurred_at: datetime
    promised_at: datetime
    proof: ProofOfDelivery | None = None
    exception_kind: str | None = None

    @model_validator(mode="after")
    def validate_status_details(self) -> "ShipmentEvent":
        if self.status is ShipmentStatus.DELIVERED and self.proof is None:
            raise ValueError("delivered shipments require proof")
        if self.status is ShipmentStatus.EXCEPTION and not self.exception_kind:
            raise ValueError("exception shipments require exception_kind")
        return self


class MetricPoint(BaseModel):
    name: str
    value: float
    type: str
    tags: dict[str, str]


class ReportResult(BaseModel):
    shipment_id: str
    reported: list[MetricPoint]


def metric_plan(event: ShipmentEvent) -> list[MetricPoint]:
    """Make the observable business decision without performing I/O."""
    tags = {"carrier": event.carrier, "route": event.route}
    points = [
        MetricPoint(name="logistics.shipment_events", value=1, type="counter", tags={**tags, "status": event.status.value})
    ]
    if event.status is ShipmentStatus.DELIVERED:
        delay_minutes = max(0.0, (event.occurred_at - event.promised_at).total_seconds() / 60)
        points.extend(
            [
                MetricPoint(name="logistics.deliveries", value=1, type="counter", tags=tags),
                MetricPoint(name="logistics.delivery_delay_minutes", value=delay_minutes, type="gauge", tags=tags),
            ]
        )
    elif event.status is ShipmentStatus.EXCEPTION:
        points.extend(
            [
                MetricPoint(
                    name="logistics.exceptions",
                    value=1,
                    type="counter",
                    tags={**tags, "kind": event.exception_kind or "unspecified"},
                ),
                MetricPoint(name="logistics.open_exceptions", value=1, type="gauge", tags=tags),
            ]
        )
    return points


def get_metrics_client() -> MetricsClient:
    return MetricsClient()


app = FastAPI(title="Logistics metric reporter")


@app.post("/shipment-events", response_model=ReportResult)
def report_shipment_event(
    event: ShipmentEvent,
    client: Annotated[MetricsClient, Depends(get_metrics_client)],
) -> ReportResult:
    points = metric_plan(event)
    try:
        for index, point in enumerate(points):
            client.report(
                name=point.name,
                value=point.value,
                type=point.type,
                tags=point.tags,
                idempotency_key=f"shipment-event:{event.event_id}:{index}",
            )
    except InfraiError as exc:
        client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=client_status, detail={"code": exc.code, "error": exc.detail}) from exc
    return ReportResult(shipment_id=event.shipment_id, reported=points)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("logistics_service:app", host="127.0.0.1", port=8000)

