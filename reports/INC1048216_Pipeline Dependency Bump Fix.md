## Pipeline Dependency Bump Fix

the deployment pipeline failed after a dependency version bump broke an older test helper. Pinning the package and updating the test fixture restored the build and allowed the release job to complete.

1. Identify the failing stage in the pipeline

2. Pin the incompatible dependency version

3. Update any fixtures or mocks that rely on old behavior

4. Run the pipeline again to confirm green status

Re-run install, test, and deploy steps
```bash
npm ci
npm test
# pin the incompatible package and refresh lockfile
```

| job | result |
| --- | --- |
| install | passed |
| test | passed |
| deploy | passed |