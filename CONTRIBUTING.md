# Contributing

## Commits and PR titles
Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `chore:`, `ci:`, ...). PRs are squash-merged, so the PR title becomes the commit message and is checked by the `PR title` workflow.

## CI
CI runs only on pull requests (no push triggers). Branch protection requires the single `ci-ok` check, which passes when no job failed or was cancelled (skipped jobs count as success).

## Releases
1. Merges to `main` update a release-please PR (version bump + `CHANGELOG.md`).
2. Merging that PR creates the tag and GitHub release, then the `publish` workflow builds and pushes the multi-arch image to `ghcr.io/metril/immich-hoarder`. It can also be run manually with a `tag` input.

The only setup needed is Settings → Actions → General → Workflow permissions: enable "Allow GitHub Actions to create and approve pull requests". Release PRs opened with `GITHUB_TOKEN` do not trigger `ci.yml`, so the release workflow posts a `ci-ok` commit status on them, only when they touch nothing but version files (CHANGELOG.md, manifest, backend/app/_version.py, version.txt).
