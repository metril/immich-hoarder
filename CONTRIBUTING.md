# Contributing

## Commits and PR titles
Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `chore:`, `ci:`, ...). PRs are squash-merged, so the PR title becomes the commit message and is checked by the `PR title` workflow.

## CI
CI runs only on pull requests (no push triggers). Branch protection requires the single `ci-ok` check, which passes when no job failed or was cancelled (skipped jobs count as success).

## Releases
1. Merges to `main` update a release-please PR (version bump + `CHANGELOG.md`).
2. Merging that PR creates the tag and GitHub release, then the `publish` workflow builds and pushes the multi-arch image to `ghcr.io/metril/immich-hoarder`. It can also be run manually with a `tag` input.

Events created with the default `GITHUB_TOKEN` do not trigger other workflows, so release PRs would never get the required `ci-ok` check. Add a `RELEASE_PLEASE_TOKEN` repository secret (fine-grained PAT, or a GitHub App token, with contents and pull-requests write). Without it the workflow falls back to `GITHUB_TOKEN`; the release PR then needs its checks triggered manually (e.g. close and reopen it) or an admin merge. `ci.yml` skips all jobs (and reports success) only for same-repo PRs whose changed files are all release-please outputs (CHANGELOG.md, manifest, backend/app/_version.py, version.txt).
