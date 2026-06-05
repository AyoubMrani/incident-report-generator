# Firewall Rule Reconciliation

two overlapping firewall rules collided after a policy review, and the deny rule matched traffic that was meant to reach the app tier. The fix was to narrow the deny scope and preserve the allow path for the service subnet.

### Remediation

1. Review rule order and matching scope

2. Remove the overly broad deny condition

3. Reload the firewall policy cleanly

4. Validate application ports are reachable again

Inspect and adjust firewall rules
```bash
iptables -S
firewall-cmd --permanent --remove-rich-rule="rule family=ipv4 source address=10.12.0.0/16 reject"
firewall-cmd --reload
```

| rule | effect |
| --- | --- |
| deny 10.12.0.0/16 | blocked app tier |
| allow 10.12.8.0/24 | restored access |