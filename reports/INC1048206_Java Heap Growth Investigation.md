## Java Heap Growth Investigation

the Java service kept expanding heap usage because a cache entry was never evicted after each request batch. The root cause was an unbounded in-memory map, so the fix tightened cache limits and restarted the process with sane heap flags.

1. Capture a live heap histogram

2. Identify the leaking object type and retention path

3. Apply the cache bound and restart the process

4. Monitor GC and resident memory for stability

JVM diagnostics
```bash
jcmd 28144 GC.class_histogram
jmap -histo:live 28144 | head -20
```

| metric | before | after |
| --- | --- | --- |
| old gen usage | 91% | 54% |
| full GC interval | 2m | 18m |

![Evidence Capture](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==)
Visual evidence from the incident timeline.