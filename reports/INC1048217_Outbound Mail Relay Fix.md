# Outbound Mail Relay Fix

outbound messages were rejected because the relay host name no longer matched the receiving mail server policy. The SMTP configuration was aligned with the approved sender domain and the queue drained normally.

### Remediation

1. Update the relay host and authenticated sender details

2. Reload the mail service to apply the change

3. Flush the outbound queue

4. Verify the receiving server accepts new mail

Adjust Postfix relay settings
```bash
postconf -e "relayhost = [smtp-relay.example.net]:587"
postfix reload
mailq
```

![Mail queue snapshot](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==)
Screenshot of the outbound queue before the fix.