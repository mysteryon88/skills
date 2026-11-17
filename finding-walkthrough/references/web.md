# Web evidence checklist

Capture exact method/target, relevant headers, content type and redacted body bytes, authentication identity, session binding and initial state. Trace routing, parsing/normalization, middleware authorization and handler validation in source order. Record redirects, cache/proxy boundaries, downstream calls and persistence effects separately. Match the concrete response status/body to actual behavior; protocol-level success alone does not establish the finding's business effect. Inspect failures and transaction rollback. Missing middleware, consumer or upstream service requires a gap, even when an endpoint name suggests its behavior.

Primary orientation: [HTTP semantics, RFC 9110](https://httpwg.org/specs/rfc9110.html). Use it for protocol questions while verifying the examined application's actual interpretation and deployment.
