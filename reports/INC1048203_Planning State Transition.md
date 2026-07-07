## Planning State Transition

the property remained in the old planning state because the downstream sync never picked up the approved transition from construction to available. The fix was to update the planning record and refresh the status in the dependent registry.

1. Confirm the source-of-truth system has the approved completion date

2. Update the planning record to the target state

3. Trigger the downstream refresh job

4. Verify the dashboard and planning queue now match

Planning record update
```sql
update planning.homes
set planning_state = 'AVAILABLE', status_updated_at = current_timestamp
where home_reference = 'H-77219';
```

![Planning timeline snapshot](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==)
Screenshot of the planning transition review.