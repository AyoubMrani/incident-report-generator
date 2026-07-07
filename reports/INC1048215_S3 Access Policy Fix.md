# S3 Access Policy Fix

the application lost object storage access after a policy change removed the required bucket read action. Restoring the least-privilege allow list on the bucket policy re-enabled downloads and report generation.

1. Check the changed bucket policy against the application needs

2. Restore the missing read and list permissions

3. Re-test object listing and download operations

4. Audit the policy for least-privilege compliance

Apply the corrected bucket policy
```bash
aws s3api put-bucket-policy --bucket reports-prod --policy file://bucket-policy.json
aws s3 ls s3://reports-prod/incoming/
```

Secondary command or config excerpt
```bash
aws s3 cp s3://reports-prod/incoming/sample.csv /tmp/sample.csv
```

| Field | Value |
| --- | --- |
| status | resolved |
| owner | Jade Thompson |