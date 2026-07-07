# LDAP Outage Recovery

users could not log in because the LDAP endpoint was unreachable after a network change isolated the directory cluster. The service was restored by correcting the route and restarting the auth proxy once connectivity returned.

1. Confirm LDAP reachability from the application subnet

2. Restore network path to the directory service

3. Restart the auth proxy after connectivity is back

4. Verify a sample login succeeds

Reachability test and route restore
```bash
ldapsearch -H ldap://ldap01.example.net -x -b dc=example,dc=net
route add -net 10.40.0.0/24 gw 10.10.1.1
```

Related incident: INC1048314