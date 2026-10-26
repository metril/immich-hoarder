# xdist report
- pytest-xdist==3.8.0, pytest-split==0.11.0 (exact pins); addopts "-n auto".
- Audit: all DBs/files use tmp_path; pg_url uses uuid DB per test; no fixed ports in tests (e2e_server 8090 is not in the pytest suite). Module globals are per worker process and behave as in serial; no code changes needed.
- Serial: 161s. Parallel (8 cores) x3: 51.6s, 48.2s, 58.2s; all 649 passed, 35 skipped.
- CI: backend-lint job, backend 4-shard matrix (--splits 4 --group N, -n auto), postgres job (-n auto via addopts), frontend-test 2-shard vitest matrix (local run was ~52s); ci-ok depends on all. actionlint clean.
