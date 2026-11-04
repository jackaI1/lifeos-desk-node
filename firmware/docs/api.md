# Desk API v1

Base URL: configured adapter origin. `Authorization: Bearer <device-token>` on
every request; JSON bodies. HTTPS required by default. No redirects followed.

## GET /v1/next

200 with exactly one `next` field:

```json
{"next":{"kind":"class","title":"Calculus","when":"Wed 10:30"}}
```

`kind` is `class` or `deadline`; title is 1..95 ASCII characters and when 1..31.
`{"next":null}` means no upcoming event, whereas a failed request preserves the
previous cache. Date-only deadlines use e.g. `Wed time unknown`.

## POST /v1/readings

```json
{"device":"aabbccddeeff","session":"0123456789abcdef","dropped":0,"readings":[{"sequence":1,"timestamp":0,"temperature_mc":22500,"humidity_mpermil":45000}]}
```

Device is the 12 lowercase hexadecimal MAC digits. Session is 16 lowercase hex
characters chosen on cold boot; sequence is strictly increasing within the batch
(1..4294967295). Batch contains 1..64 readings. `timestamp` is UTC Unix seconds or
0 for unknown; future timestamps beyond five minutes are rejected. Temperature is
integer milli-degrees C (-45000..125000); RH is integer thousandths of a percent
(0..100000). `dropped` is the cumulative saturating 32-bit FIFO loss counter for
this boot session; the firmware displays it. The adapter validates this diagnostic
counter but daily notes currently contain the individual sample data only.

200 only after LifeOS accepts all daily notes:

```json
{"accepted":1,"last_sequence":1}
```

`accepted` counts the input batch, including identical previously received samples.
The ESP32 verifies both fields before removing the full FIFO. Timeout, oversized,
malformed, partial, mismatched acknowledgment or non-200 status leaves it intact.

401: token invalid. 400: invalid fields/ranges or conflicting reused sample ID.
413: payload outside 1..12288 bytes or chunked request. 415: JSON required.
503: LifeOS unavailable/conflict/edited managed note; retry on a later wake.
The adapter database retains accepted receipts even when upstream publication
fails, but does not acknowledge them until publication succeeds. A deep-sleep
FIFO cannot survive power removal, so unsent samples can still be lost then.

No real LifeOS URL, account cookie, token or private schedule is included here.
