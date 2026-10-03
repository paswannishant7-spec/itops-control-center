# CI/CD and release process

## Continuous integration

`.github/workflows/ci.yml` runs on pull requests and pushes to `main`, with stale runs cancelled per
ref and bounded job timeouts.

| Job        | Gates                                                                                                                                    |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Frontend   | npm advisory audit, Oxlint, application/E2E TypeScript, Vitest, production build, Playwright desktop/mobile cases, Prettier |
| Backend    | Python advisory audit, empty PostgreSQL 17 + pgvector migration/check, Ruff, Mypy, Pytest and coverage floor |
| Agent      | Ruff, strict Mypy, and four Pytest cases                                                                                                 |
| Containers | Development and production Compose rendering plus backend/frontend image builds                                                          |

JUnit, coverage, and Playwright reports are retained as short-lived workflow artifacts. The workflow
has read-only repository permission; it does not receive production credentials or deploy.
Dependabot checks npm, pip, Docker, and Actions dependencies weekly.

This table describes configured gates, not a successful remote run. No public GitHub CI result has
been observed. Step 7 recorded seven pre-existing whole-backend Mypy errors, so the current
workflow must not be described as green until those errors and any other remote failures are fixed.

## Continuous delivery

`.github/workflows/release.yml` publishes API and frontend OCI images to GitHub Container Registry
for `v*` tags and explicit manual runs. It uses the repository `GITHUB_TOKEN` with only package-write
and content-read permissions, builds Linux AMD64 images, attaches OCI labels, emits SBOM and maximum
provenance attestations, and uses isolated BuildKit caches per component.

Release tags produce semantic-version and commit-SHA image tags. Manual runs produce a unique
`manual-<run>` tag plus the SHA tag. Deployment must pin one immutable tag or digest; never deploy a
floating `latest` reference. Image publication is delivery, not unattended production deployment.

## Release procedure

1. Require a green CI run and reviewed changes on the release commit.
2. Choose a semantic version and document schema compatibility, rollback, and operator actions.
3. Create and push the signed `vX.Y.Z` tag.
4. Verify both GHCR packages, their digest, SBOM, provenance, and vulnerability policy.
5. Rehearse `docker-compose.prod.yml` against a restored backup in staging.
6. Promote the exact digests through the deployment process in [the operations runbook](DEPLOYMENT.md).
7. Record deployment time, operator, image digests, migration revision, smoke results, and rollback
   point.

Repository/environment protection rules should require reviewer approval for any future automated
production deployment. Registry retention must preserve every currently deployed and rollback
digest. Compromise of a build token, runner, signing identity, or image requires stopping promotion,
revoking access, rebuilding from a reviewed commit, and rotating affected runtime secrets.

## Workflow maintenance

Keep Actions on supported major versions and let Dependabot propose changes. Review action release
notes, permissions, runtime requirements, and provenance before merging. For higher supply-chain
assurance, pin third-party actions to reviewed full commit SHAs while retaining Dependabot-driven
updates.
