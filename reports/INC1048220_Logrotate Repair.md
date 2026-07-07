## Logrotate Repair

logs were filling the disk because logrotate stopped running after a malformed include file was introduced. The rotation config was fixed, a manual run was successful, and the log files resumed normal compression and retention.

1. Validate the logrotate configuration syntax

2. Force one clean rotation to clear the backlog

3. Restart the timer or cron job that runs rotation

4. Confirm log files are compressing and aging out

Check and force log rotation
```bash
/usr/sbin/logrotate -d /etc/logrotate.conf
/usr/sbin/logrotate -f /etc/logrotate.conf
systemctl restart logrotate.timer
```

Related incident: INC1048320