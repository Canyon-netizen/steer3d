# WebSocket Protocol (Reasoning3D v0.2)

All messages are UTF-8 JSON over a single WebSocket per session.

## Server → Client (one Frame per token)

```jsonc
{
  "ts": 1737400000.123,        // unix seconds, server clock
  "step_id": 17,                // monotonic token index within this session
  "token": "the",               // predicted token (decoded text)
  "token_id": 1745,             // tokenizer id (debugging)

  "point": { "x": 0.12, "y": -0.04, "z": 1.7 },

  "perplexity": 3.4,            // 1 / p(top-1). May be null if unknown.
  "entropy": 1.23,              // Shannon entropy of the policy (nats)
  "loss": null,                 // optional generic loss scalar

  "is_self_check": false,       // token looks like "wait"/"actually"/"hmm"
  "is_revisit": true            // the path direction reversed vs previous step
}
```

### Field-by-field

| Field        | Notes |
|--------------|-------|
| `point`      | 3-D projection of the residual stream activation at the configured layer for the *current* token. Coordinates come from the server's online projector (PCA / UMAP). |
| `is_self_check` | Frontend highlights the corresponding token in the reasoning-trace panel and the path segment. |
| `is_revisit`   | The path's velocity reversed vs the previous step. Used to flag "the model went back". |
| `perplexity`, `entropy` | Optional. If the model can't provide a distribution (e.g. some APIs), send `null`. |

## Server → Client (one-shot on connect)

```jsonc
{
  "kind": "ready",
  "payload": {
    "presets": [],          // reserved for future vector-injection presets
    "layer": 14,
    "d_model": 4096,
    "sample_every": 1
  }
}
```

## Server → Client (status)

```jsonc
{ "kind": "error",     "payload": { "message": "..." } }
{ "kind": "reset_ack" }
```

## Client → Server (ControlMessages)

```jsonc
{ "kind": "start",      "payload": { "prompt": "Why is the sky blue?", "layer": 14 } }
{ "kind": "cancel" }
{ "kind": "pause" }
{ "kind": "resume" }
{ "kind": "set_layer",  "payload": { "value": 16 } }
{ "kind": "set_prompt", "payload": { "value": "..." } }
{ "kind": "set_speed",  "payload": { "value": 1.0 } }
{ "kind": "reset" }
```

## Lifecycle

```
client                              server
  |                                    |
  | --- ws connect -------------------->|
  |                                    |
  | <----- {kind: "ready", ...} -------|
  |                                    |
  | --- {kind: "start", prompt, layer}>|
  |                                    |
  | <----- {ts, step_id, ...} ---------|
  | <----- {ts, step_id, ...} ---------|
  | (frames keep coming)               |
  |                                    |
  | --- {kind: "pause"} ------------->|
  |                                    |
  | --- {kind: "resume"} ------------>|
  |                                    |
  | --- {kind: "set_speed", value} -->|
  |                                    |
  | --- {kind: "reset"} -------------->|
  | <----- {kind: "reset_ack"} --------|
```

## Versioning

Currently `v0.2`. Backwards-incompatible changes will be
signalled by adding a `protocol_version` key to `ready`.