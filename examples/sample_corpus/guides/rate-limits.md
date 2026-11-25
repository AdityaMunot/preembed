# Rate Limits

The public API allows 600 requests per minute per API key. Requests above the limit receive
HTTP 429 with a `Retry-After` header that tells the client how many seconds to wait.

## Burst handling

Short bursts are absorbed by a token bucket that refills at ten tokens per second. Clients
that retry immediately after a 429 response drain the bucket faster and stay throttled
longer, so always honor the `Retry-After` value and add jitter between retries.

## Raising the limit

Enterprise customers can request a higher limit through their account manager. Include the
expected peak request rate, the endpoints involved, and whether traffic is read or write
heavy so the platform team can size the quota correctly.
