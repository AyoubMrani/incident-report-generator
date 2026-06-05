## ETL Transformation Repair

the transformation step failed because a schema change introduced a null field where the job expected an integer. The pipeline was updated to coerce the new column safely and skip bad rows during the nightly run.

1. Locate the failing transformation stage

2. Patch the schema conversion logic

3. Re-run the batch with a quarantined error path

4. Validate the curated output row counts

Launch the transformation job
```bash
python transform_orders.py --input s3://landing/orders/ --output s3://curated/orders/
# cast new_amount safely and quarantine malformed rows
```

| stage | status | duration |
| --- | --- | --- |
| ingest | ok | 4m |
| transform | failed | 1m |
| load | pending | - |