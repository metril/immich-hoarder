# Contributing

## Commits and PR titles
Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `chore:`, `ci:`, ...). PRs are squash-merged, so the PR title becomes the commit message and is checked by the `PR title` workflow.

## CI
CI runs only on pull requests (no push triggers). Branch protection requires the single `ci-ok` check, which passes when no job failed or was cancelled (skipped jobs count as success).

## Tests
Tests run in parallel (pytest-xdist `-n auto` is the default via `addopts`) and must stay xdist-safe: use `tmp_path` for files and DBs, no fixed ports, no cross-test global state.
- Backend: `uv run pytest -q` (all cores). Serial: `uv run pytest -q -n 0`. One shard as CI does: `uv run pytest -q --splits 4 --group 1`.
- Postgres: `IH_TEST_PG_URL=postgresql://postgres:pg@localhost:5432/postgres uv run pytest -m pg -q` (each test gets its own uuid-named database).
- Frontend: `pnpm test` (vitest threads); a CI shard: `pnpm test --shard=1/2`.
- CI splits backend tests into 4 shards and frontend tests into 2; all feed the single `ci-ok` check.

## E2E with real Immich
Needs Docker; skipped unless `IH_E2E_IMMICH=1`. It starts a real Immich (plus Postgres, Valkey, a mock OIDC provider and a fixture site) on random host ports, runs the full upload, link, re-run and Immich-delete cycle, and removes the stack afterwards. The first run pulls the large Immich image.
```
docker build -t immich-hoarder:e2e . && IH_E2E_IMMICH=1 uv run pytest backend/tests/e2e_immich -n 0 -q
```
Set `IH_E2E_IMAGE` to test another image tag and `IH_E2E_LOG_DIR` to keep the compose logs. CI runs this as the `e2e-immich` job.

## Releases
1. Merges to `main` update a release-please PR (version bump + `CHANGELOG.md`).
2. Merging that PR creates the tag and GitHub release, then the `publish` workflow builds and pushes the multi-arch image to `ghcr.io/metril/immich-hoarder`. It can also be run manually with a `tag` input.

The only setup needed is Settings → Actions → General → Workflow permissions: enable "Allow GitHub Actions to create and approve pull requests". Release PRs opened with `GITHUB_TOKEN` do not trigger `ci.yml`, so the release workflow posts a `ci-ok` commit status on them, only when they touch nothing but version files (CHANGELOG.md, manifest, backend/app/_version.py, version.txt).

## Load test
`backend/loadtest/dedupe.py` seeds `assets_seen` and times the real `DedupeStore` lookups (`url_seen`, `match_sha1`, `match_phash` with max distance 3, half hits and half misses). It is not part of pytest or `ci.yml`; the only workflow is the manual `loadtest.yml` (Actions → Load test → Run workflow, `rows` input, default 5,000,000). It exits 1 if any p99 is >= `--p99-ms` (default 5).
- Quick run (about 1 min): `cd backend && uv run python -m loadtest.dedupe --rows 1000000 --db /tmp/lt.db`
- Full run: `cd backend && uv run python -m loadtest.dedupe --rows 100000000 --db /fast/disk/lt.db`. Needs about 25 GB free (roughly 210 bytes per row) and an SSD; expect 1-3 h of seeding. Add `--keep` to retain the DB.
- Pass criterion: p99 < 5 ms for all three lookups.

## Frontend
The web UI lives in `frontend/` (Vite, React, TanStack Router). Use Node 24.21.0 and pnpm 12.12.1 (`corepack enable`).
- `pnpm install --frozen-lockfile`, then `pnpm dev` (proxies `/api` to `127.0.0.1:8080`).
- Checks: `pnpm lint && pnpm typecheck && pnpm test && pnpm build && pnpm budget`.
- API types are generated. After backend API changes run `cd backend && uv run python -m app.openapi_dump ../frontend/openapi.json`, then `pnpm gen:api`; CI fails on a stale client.
- E2E: `pnpm build && pnpm exec playwright install chromium && pnpm e2e`. It starts `backend/tests/e2e_server.py` (test-only auto-login on port 8090, never shipped in the image).
- Lighthouse (desktop performance and accessibility >= 0.95): with that server running, `CHROME_PATH=<playwright chromium> pnpm lhci`.
- The Docker image builds the bundle in a `node` stage and serves it from `/srv/web`.

## Docs
The documentation site is built with MkDocs Material from `docs/`.
- Preview: `uv run --only-group docs mkdocs serve`. Check as CI does with `uv run --only-group docs mkdocs build --strict`.
- `docs/reference/configuration.md` is generated from the settings models. Regenerate it with `uv run python -m app.configdoc`; CI fails when it is stale.
- Screenshots in `docs/assets/screenshots/` are generated with `pnpm screenshots` (run from `frontend/`, Playwright).
