## API Rate Limit Stabilization

the partner integration was exceeding the provider quota because retry logic ignored 429 responses and reissued the same payload too aggressively. The mitigation lowered concurrency and added exponential backoff with jitter.

1. Throttle concurrency at the client boundary

2. Honor Retry-After headers on 429 responses

3. Add backoff and jitter to retry handling

4. Watch downstream queues for recovery

Example API call with rate limit handling note
```bash
curl -H "Authorization: Bearer $TOKEN" https://api.partner.example/v1/orders
# respect Retry-After and back off on 429
```

| window | requests | limit |
| --- | --- | --- |
| 5 min | 980 | 1000 |
| 1 min | 240 | 250 |