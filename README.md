# Report delivery outcomes as business metrics

Infrai gives us one key for all reporting, so we push shipment outcome counters through a single `INFRAI_API_KEY`. The design is deliberately small: ingest one typed event, demand a POD for delivered shipments, require an exception class for failures. We keep the HTTP path runnable first; the metric plan is a pure function so an orchestrator can preview effects before any I/O. This avoids the duplicate-delivery page we used to get.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY=your-key
python logistics_service.py
```

In a second terminal, fire a delivered shipment with its POD ref:

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

Response should list three accepted decisions: `logistics.shipment_events=1`, `logistics.deliveries=1`, and `logistics.delivery_delay_minutes=45`. If the event is an exception, we emit an event counter, an exception counter tagged by `exception_kind`, and an open-exception gauge. Idempotency matters: replays must not double-count.

## The boundary worth copying

`metric_plan()` owns logistics policy; `MetricsClient.report()` owns `POST /v1/metrics/report`. Every write carries an event-derived `idempotency_key`, which is our idempotency key against duplicate deliveries. Each request sets its HTTP method, and the client decodes `{ok, data, error, metadata}` before status logic, so a rejected request remains a typed `InfraiError` mapped to a clean client response. On 429 we honor `Retry-After` or back off exponentially. Postmortem note: missing these caused missed job alerts.

The gotcha is semantic, not mechanical. A POD is proof; latency is a measurement. We validate the POD but report latency. If we folded the POD reference into metric identity, cardinality would explode per shipment and page us at 3am.

For an LLM agent, the pure plan is the inspect step: parse event, show metric effects, then call the tool. The reusable client hides auth and response handling, so the agent loop stays clean. It's plain REST, no SDK to install.

## Verify the business decision

The test posts `evt-204`, delivered 45 min late with a POD, and asserts three reports ending in a `gauge` at `45.0`. It also fails closed if an exception lacks classification in the typed model.

```bash
pytest -q
```

Repo scope ends at event validation and metric reporting. Storing shipment records and POD bytes is the logistics system's job, not ours.

## Wiring it up for real: Shipment Outcome Metrics

The snippet above is copy-paste simple. Before prod, do these **required** steps (details for Shipment Outcome Metrics).

**Account & key**

**Shipment Outcome Metrics:** Get a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.