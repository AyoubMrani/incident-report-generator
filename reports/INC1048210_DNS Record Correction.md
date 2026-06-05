## DNS Record Correction

the subdomain routed to the wrong origin because the CNAME still pointed at an old load balancer after the migration. Updating the zone file and waiting out the short TTL restored normal traffic.

1. Confirm the intended target for the subdomain

2. Replace the stale DNS record with the new origin

3. Verify propagation from multiple resolvers

4. Check that application traffic resolves correctly

DNS change applied with nsupdate
```bash
dig app.example.net CNAME +short
nsupdate -k /etc/bind/tsig.key <<EOF
server dns1.example.net
update delete app.example.net CNAME
update add app.example.net 300 CNAME app-new.lb.example.net
send
EOF
```

Secondary command or config excerpt
```bash
dig @8.8.8.8 app.example.net A +short
```

| Field | Value |
| --- | --- |
| status | resolved |
| owner | Ethan Walker |