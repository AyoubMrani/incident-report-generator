## Alert Threshold Correction

the alert storm came from a threshold that was set far too low after a metric label change. The rule was corrected to use a percentile-based alert and the false positives dropped immediately.

### Remediation

1. Review the alert rule and recent metric changes

2. Raise the threshold or switch to a percentile-based rule

3. Mute the noisy notification channel temporarily

4. Verify the false positive rate returns to normal

Updated alert rule snippet
```yaml
groups:
  - name: api_latency
    rules:
    - alert: HighLatency
      expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 0.8
```

Secondary command or config excerpt
```bash
promtool check rules alert-rules.yml
```

| Field | Value |
| --- | --- |
| status | resolved |
| owner | Emma Davis |