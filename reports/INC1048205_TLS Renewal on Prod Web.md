# TLS Renewal on Prod Web

the production certificate was nearing expiration and the deploy script kept referencing the old PEM bundle. The new certificate chain was installed on the web server and the service reloaded after the keystore path was corrected.

1. Check certificate expiry and chain details

2. Replace the expiring certificate and key bundle

3. Reload the web server to pick up the new chain

4. Verify HTTPS requests return the renewed certificate

Expiry check and reload
```bash
openssl x509 -in /etc/pki/tls/certs/app-prod.crt -noout -dates
cp app-prod-2026.crt /etc/pki/tls/certs/app-prod.crt
systemctl reload nginx
```

Secondary command or config excerpt
```bash
nginx -t && systemctl reload nginx
```

| Field | Value |
| --- | --- |
| status | resolved |
| owner | Fatima El Amrani |