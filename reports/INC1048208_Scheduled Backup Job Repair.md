# Scheduled Backup Job Repair

the backup job stopped because the scheduler entry pointed to an expired credentials file. Once the secret path was corrected, the job resumed and the nightly dump completed without errors.

1. Inspect the backup scheduler and cron entry

2. Update the credentials reference to the current secret

3. Run a manual backup to validate the fix

4. Confirm the automated job succeeds on the next cycle

Manual dump and scheduler check
```bash
pg_dump -Fc appdb > /backups/appdb_$(date +%F).dump
crontab -l | grep backup
systemctl restart backup-scheduler
```

Related incident: INC1048310