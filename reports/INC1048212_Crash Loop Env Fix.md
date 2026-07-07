# Crash Loop Env Fix

the pod kept restarting because an environment variable was renamed in the chart but the container still required the old value. The deployment was corrected by restoring the missing variable and rolling out the updated manifest.

1. Inspect pod logs and events for the crash reason

2. Fix the missing or renamed environment variable

3. Roll out the corrected deployment manifest

4. Wait for the pod to become Ready and stable

Set env and restart deployment
```bash
kubectl -n payments set env deployment/gateway SERVICE_MODE=production
kubectl -n payments rollout restart deployment/gateway
kubectl -n payments describe pod gateway-7d9c8f4b7c-2kq9m
```

![Crash loop event capture](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==)
Screenshot from kubectl describe and pod events.

![Evidence Capture](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==)
Visual evidence from the incident timeline.