# ITEM-002: OpenTelemetry traces, opt-in

| Meta | Value |
| :- | :- |
| **Status** | IDEA |
| **Type** | feature |
| **Origin** | Discussion of observability before the first code, 2026-10-26 |
| **Created** | 2026-10-26 |
| **Author** | loxy (drafted with Claude) |

## Summary

Let a deployment send Enterich's traces to an OpenTelemetry collector, so that a request can be followed from the ingress through Enterich to ERPNext. Off unless configured.

## Context

Enterich's first versions report through their JSON log ([REQ-002-PRS-NF008](../specs/req-002-service.md#req-002-prs-nf008-log)) and `/healthz`. Each `operation` line carries the total duration and the number and duration of its ERPNext calls, so a log store can derive rates, error ratios and latencies, and alert on them.

The MCP SDK depends on `opentelemetry-api`, which does nothing without an OpenTelemetry SDK and exporter; Enterich installs neither.

What traces would add: one request followed across the ingress, Enterich and its ERPNext calls, next to other services' traces. ERPNext itself likely emits no traces, so a trace ends at Enterich's ERPNext calls.

## Triggers

Take this up when:

- a deployment runs an OpenTelemetry collector and wants Enterich's requests in its traces, or
- alerting from log lines becomes awkward, or several Enterich instances need comparing.

## Conditions

- **Opt-in:** configured only through the standard `OTEL_*` environment variables (`OTEL_EXPORTER_OTLP_ENDPOINT` and friends); nothing is exported and no exporter starts unless they are set.
- **HTTP exporter (OTLP over HTTP/protobuf),** not gRPC, to keep the dependency set small.
- **Spans carry no secrets and no raw arguments:** operation name, outcome category, durations, ERPNext call count and status codes. No tokens, keys, document contents, party names or outside text; the same rules as the log (REQ-002-URS-NF006, REQ-001-URS-NF002).
- **Log lines carry the trace and span IDs** when tracing is on, so logs and traces link.
- **Incoming trace context** (`traceparent`) is accepted, but never decides anything.
- A REQ-001 change first (new variables, what spans contain), then tests, then code; the image grows only by the SDK and the HTTP exporter.

## Open Questions

- Metrics too (OpenTelemetry metrics or a Prometheus endpoint), or are log-derived numbers enough?
