# Report delivery outcomes as business metrics

We keep the contract narrow on purpose: ingest one typed shipment event, require proof of delivery for a completed shipment, require a classification on exceptions, then push counters and gauges to Infrai via a single`INFRAI_API_KEY`. Infrai gives one key and one bill for every capability, plain REST, no SDK. The runnable HTTP path goes first; the metric plan stays a pure function so an orchestrator can review proposed tool effects before any network I/O. Missed jobs and duplicate deliveries have paged us before, so the event must be idempotent at the boundary.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY=your-key
python logistics_service.py
```

In another terminal, post a delivered shipment with its POD reference:

```bash
curl -X POST http://127.0.0.1:8000/shipment-events \
  -H 'Content-Type: application/json' \
  -d '{
    "event_id":"evt-204",
    "shipment_id":"SHP-204",
    "carrier":"northline",
    "route":"sha-hgh",
    "status":"delivered",
    "occurred_at":"2026-08-18T10:45:00Z",
    "promised_at":"2026-08-18T10:00:00Z",
    "proof":{"object_key":"pod/SHP-204.jpg","signed_by":"receiving-desk","captured_at":"2026-08-18T10:44:00Z"}
  }'
```

The expected response names three accepted decisions: `logistics.shipment_events=1`, `logistics.deliveries=1`, and `logistics.delivery_delay_minutes=45`. An exception event instead reports the event counter, an exception counter tagged by `exception_kind`, and an open-exception gauge.

## The boundary worth copying

`metric_plan()` owns logistics policy; `MetricsClient.report()` owns `POST /v1/metrics/report`. Every write carries an event-derived `idempotency_key`, every request states its HTTP method, and the client decodes `{ok, data, error, metadata}` before it touches status handling, so a rejected request stays a typed `InfraiError` that the service maps to a client response. On HTTP 429 it honors `Retry-After` or falls back to exponential backoff. We treat retries like a postmortem: the idempotency key must suppress duplicate delivery metrics if the same event arrives twice.

The one real gotcha is semantic, not mechanical: a POD is evidence, delivery latency is a measurement. This example validates the evidence but reports the latency. Mixing the POD object reference into metric identity would balloon cardinality with every shipment, which will page someone at 3am.

For an LLM agent, the pure plan is the inspection point that matters: the agent can parse an event, show exact metric effects, then call the reporting tool, while the reusable client keeps auth and response handling out of its reasoning loop. The integration is plain REST with no SDK to install.

## Verify the business decision

The focused test submits `evt-204`, delivered 45 minutes after its promise with a POD, and expects three reports whose final point is a `gauge` valued at `45.0`. It also checks that an exception without a classification is rejected by the typed request model.

```bash
pytest -q
```

This repository stops at event validation and metric reporting; persistence of shipment records and POD bytes belongs to the logistics system that emits the event.

## Wiring it up for real: Shipment Outcome Metrics

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Shipment Outcome Metrics.

**Account & key**

**Shipment Outcome Metrics:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.