# Yellow Duplicate Cleanup

duplicate customer rows were inserted by an upstream import job that retried after a timeout. The stored function was used to keep the latest canonical row and delete only yellow-highlighted duplicates that matched the same external_reference.

1. Export the duplicate set from the staging spreadsheet

2. Validate the function scope against the import batch ID

3. Execute the stored function for the duplicate group

4. Re-run the count query to confirm only one canonical row remains

Stored function invocation
```sql
select dedupe_cleanup.remove_duplicate_customers('cust_import_2024_03_07');
```

Related incident: INC1048301