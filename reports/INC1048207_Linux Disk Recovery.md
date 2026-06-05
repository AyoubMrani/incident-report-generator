# Linux Disk Recovery

the server filled its root filesystem because archived logs and a leftover core dump were never rotated out. The cleanup removed the largest stale artifacts and restored headroom for the scheduled jobs.

### Remediation

1. Identify the largest directories on the mounted filesystem

2. Remove stale archives and obsolete core files

3. Verify free space after cleanup

4. Tune retention to prevent the issue recurring

Find large files and prune logs
```bash
du -sh /var/log/* /opt/app/* 2>/dev/null | sort -h
find /var/log -type f -name "*.gz" -mtime +30 -delete
```

![Disk usage before cleanup](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==)
Screenshot of the disk utilization graph.