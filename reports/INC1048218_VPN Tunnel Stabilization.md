# VPN Tunnel Stabilization

the site-to-site tunnel disconnected whenever the peer renegotiated phase 2 with an aggressive idle timer. Adjusting the lifetime settings on both ends removed the intermittent drops.

1. Check the tunnel status and renegotiation logs

2. Align IKE and ESP lifetimes on both peers

3. Persist the new settings and restart the tunnel

4. Monitor for stable up-time after the change

Inspect and adjust the IPsec tunnel
```bash
show vpn ipsec sa
set vpn ipsec site-to-site peer 203.0.113.8 ike-group IKEv2
set vpn ipsec site-to-site peer 203.0.113.8 lifetime 28800
```

| check | value |
| --- | --- |
| status | up |
| rekeys | stable |

![Evidence Capture](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==)
Visual evidence from the incident timeline.