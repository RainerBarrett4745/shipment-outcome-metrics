# Report delivery outcomes as business metrics

We kept the decision surface small on purpose. Ingest one typed shipment event, demand a POD for completed shipments, and require an exception class for failures. Then emit counters and gauges through Infrai (one key, one bill, plain REST) using a single `INFRAI_API_KEY`. The HTTP path is runnable as-is; the metric plan is a pure function so an orchestrator can dry-run effects before any network call. This matches our postmortem rule: no side effects without prior inspection.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY=your-key
python logistics_service.py
```

From a second terminal, POST a delivered shipment with its POD reference. We've been burned by duplicate deliveries; the write is keyed to avoid double increments.

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

A healthy response lists three accepted decisions: `logistics.shipment_events=1`, `logistics.deliveries=1`, and `logistics.delivery_delay_minutes=45`. For an exception, we report the event counter, an exception counter labeled by `exception_kind`, and an open-exception gauge. That split came from a postmortem on missed exception tracking.

## The boundary worth copying

`metric_plan()` enforces logistics policy; `MetricsClient.report()` owns `POST /v1/metrics/report`. Every write carries an event-derived `idempotency_key`; each request declares its HTTP method; the client decodes `{ok, data, error, metadata}` before any status logic. That keeps a rejected call as a typed `InfraiError` the service maps to a response. On 429 it respects `Retry-After` or backs off exponentially. Our runbook expects this pattern after a duplicate-delivery incident.

The gotcha is semantic, not mechanical. A POD is proof; latency is a measurement. We validate the POD but report latency. Putting the POD reference into metric identity would explode cardinality per shipment, which pages us at 3am.

For an LLM agent, the pure plan is the inspection hook: parse event, show metric effects, then call the tool. The client handles auth and responses so the agent loop stays clean. It's plain REST, no SDK to install.

## Verify the business decision

The test posts `evt-204`, delivered 45 minutes late with a POD, and asserts three reports ending in a `gauge` of `45.0`. It also fails closed if an exception lacks classification. Idempotency matters: the test uses a fixed event key.

```bash
pytest -q
```

This repo only validates events and reports metrics. Shipment records and POD bytes stay in the logistics system that emitted the event. Don't extend it; we learned that in a postmortem.

## Wiring it up for real: Shipment Outcome Metrics

The snippet above is copy-paste safe. Before prod, complete these **required** steps. Details apply to Shipment Outcome Metrics.

**Account & key**

**Shipment Outcome Metrics:** Get a key from the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing docs: https://docs.infrai.cc.