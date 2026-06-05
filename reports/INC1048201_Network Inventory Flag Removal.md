# Network Inventory Flag Removal

flagged records remained in netops.inventory_device after the circuit repair was confirmed. The root cause was stale status values left behind by a partial workflow rollback, so the cleanup had to remove only the obsolete flagged rows and preserve the active inventory history.

1. Verify the affected device list against the change record

2. Run a targeted UPDATE against only stale flagged rows

3. Confirm no active inventory entries were modified

4. Reconcile the audit trail with the network operations log

Targeted cleanup query
```sql
update netops.inventory_device
set status_flag = null, updated_at = now()
where device_id in ('SW-ALB-44', 'RTR-NYC-19')
  and status_flag = 'flagged';
```

| device_id | site | status_before |
| --- | --- | --- |
| SW-ALB-44 | albany-core | flagged |
| RTR-NYC-19 | nyc-edge | flagged |