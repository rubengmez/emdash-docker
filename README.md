# emdash-docker

Container images for [**EmDash**](https://github.com/emdash-cms/emdash), an
Astro-based TypeScript CMS, built from upstream releases and published to the
GitHub Container Registry.

This repository is a **builder, not a fork**: it holds no application code. Each
run checks out the upstream repository at a released tag, builds the Dockerfile
that ships with that tag, and publishes the result. Upstream is maintained by
the EmDash team; this project is not affiliated with it.

[![Build image](https://github.com/rubengmez/emdash-docker/actions/workflows/build-image.yml/badge.svg)](https://github.com/rubengmez/emdash-docker/actions/workflows/build-image.yml)

## Pull

```bash
docker pull ghcr.io/rubengmez/emdash:latest
```

| Tag | Points to |
| --- | --- |
| `latest` | newest upstream release, available for every platform |
| `0.38.0` | exact release (`emdash@0.38.0`) |
| `0.38` | newest patch of that minor line |
| `sha-8975a8504bc9` | the upstream commit the image was built from |

Platforms: `linux/amd64`, `linux/arm64`. Images carry build provenance and an
SBOM, inspectable with `docker buildx imagetools inspect ghcr.io/rubengmez/emdash:0.38.0`.

## Run

The image serves the upstream **blog** template as a standalone Node.js + SQLite
deployment on port `4321`, with state in `/app/data` (database) and `/app/uploads`
(media).

```yaml
services:
  emdash:
    image: ghcr.io/rubengmez/emdash:latest
    ports:
      - "4321:4321"
    volumes:
      - emdash-data:/app/data
      - emdash-uploads:/app/uploads
    restart: unless-stopped

volumes:
  emdash-data:
  emdash-uploads:
```

Admin panel: <http://localhost:4321/_emdash/admin>. The package is public, so
Kubernetes needs no `imagePullSecret`.

## How it works

| Job | What it does |
| --- | --- |
| **Plan** | Resolves the newest upstream release of the core package, verifies the tag, resolves its commit and inspects GHCR to see which platforms are already published. Nothing missing means the run ends here. |
| **Build** | One job per platform, each on a native runner (no QEMU emulation). Every platform is pushed by digest and uploaded as an artifact. |
| **Publish** | Stitches the digests into a single multi-arch manifest list and tags it. |

Properties that make re-runs safe:

- **Idempotent** — an already complete image is never rebuilt.
- **No half-finished release tags** — `0.38.0`, `0.38` and `latest` are published
  only when every requested platform succeeded; a partial build publishes an
  immutable `sha-<commit>` tag instead.
- **`latest` only moves forward** — it follows the newest upstream release, so
  rebuilding an older version manually never steals the tag.
- **Cached** — layer cache is kept per platform in the GitHub Actions cache.

## Triggers

| Trigger | Behaviour |
| --- | --- |
| `schedule` (hourly, minute 23) | Polls upstream releases and builds the newest one that lacks a complete image. |
| `workflow_dispatch` | Manual build with `ref`, `platforms` and `force` inputs. |
| `repository_dispatch` (`upstream-release`) | Build on demand, e.g. from an external webhook, publishing minutes after upstream. |
| `push` (workflow or scripts) | Validates changes to the pipeline itself. |

GitHub delivers `release` events only to the repository that publishes the
release, and forks do not receive upstream events, so releases are polled. To
publish within seconds instead of waiting for the next poll, send:

```bash
curl -X POST \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/rubengmez/emdash-docker/dispatches \
  -d '{"event_type":"upstream-release"}'
```

Manual build:

```bash
gh workflow run build-image.yml -f ref=0.38.0 -f platforms=amd64 -f force=true
```

## Configuration

Everything project-specific lives in the `env` block of
`.github/workflows/build-image.yml`:

| Variable | Meaning |
| --- | --- |
| `UPSTREAM` | Repository the image is built from. |
| `RELEASE_PREFIX` | Tag prefix identifying a release of its core package (`emdash@`). Monorepos publish one release per package, so the prefix selects the ones that matter. |
| `IMAGE` | Published image, `<registry>/<owner>/<name>`. |
| `PLATFORMS` | Build matrix: platform plus the runner that builds it natively. |

## Upstream Dockerfile patch

`emdash@0.38.0` cannot be built with upstream's Dockerfile as it stands. Their
`pnpm-workspace.yaml` sets `verifyDepsBeforeRun: error` (pnpm refuses to run
scripts on top of a stale install), while the Dockerfile installs dependencies
from a **partial** workspace copy and then runs `COPY . .`, which brings in the
remaining workspace projects and makes `pnpm build` abort:

```
ERR_PNPM_VERIFY_DEPS_BEFORE_RUN  The workspace structure has changed since last install
```

`.github/scripts/patch_dockerfile.py` rewrites a single line before the build so
that the install matches the workspace being built:

```diff
-RUN pnpm build && pnpm --filter @emdash-cms/template-blog build
+RUN pnpm install --frozen-lockfile && pnpm build && pnpm --filter @emdash-cms/template-blog build
```

The patch keeps upstream's guard enabled and touches no source file. Patches are
declared as anchor/replacement pairs in the script and applied only when the
anchor matches; once upstream fixes the Dockerfile, the script says so and the
build uses their file untouched.

## Maintenance

- Actions are pinned to commit SHAs; Dependabot opens weekly grouped updates.
- New platforms or release patterns are an `env` change.
- If a release fails to build, read the build log first: a broken Dockerfile
  upstream is the usual cause, and it is fixed by adding a patch pair to
  `patch_dockerfile.py` rather than vendoring a Dockerfile here.

## License

The pipeline in this repository is MIT licensed (see [LICENSE](LICENSE)). The
images it builds contain
[emdash-cms/emdash](https://github.com/emdash-cms/emdash), which is MIT licensed
and copyright its contributors.
