#!/usr/bin/env python3
"""Apply compatibility patches to the upstream Dockerfile before building.

Why this exists
---------------
A project can publish a Dockerfile that no longer builds: usually because it is
not exercised by its own CI. Vendoring a fixed copy here would silently drift
from upstream, so instead each fix is declared below as an anchor/replacement
pair and applied to a temporary copy at build time.

A patch is applied only when its anchor matches exactly one line. When an anchor
is gone — typically because upstream fixed it — the patch is reported as not
applicable and upstream's Dockerfile is used untouched, which keeps this file
honest about what it is still doing.

Usage: patch_dockerfile.py <upstream-dockerfile> <output-dockerfile>

Current patches
---------------
1. emdash@0.38.0 and later: `pnpm-workspace.yaml` sets `verifyDepsBeforeRun:
   error`, pnpm's guard against running scripts on a stale install. The Dockerfile
   installs dependencies from a partial workspace copy (`deps` stage copies only
   some projects) and then runs `COPY . .`, which adds the remaining projects
   (`apps/*`, `docs`, `i18n`, `infra/*`, `fixtures/*`, ...). `pnpm build` then
   aborts with:

       ERR_PNPM_VERIFY_DEPS_BEFORE_RUN  The workspace structure has changed since
       last install -- Run "pnpm install"

   Adding one install in the build stage makes the installed tree match the
   workspace being built, keeping upstream's guard enabled.
"""

from __future__ import annotations

import difflib
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Patch:
    why: str
    anchor: str
    replacement: str


PATCHES: list[Patch] = [
    Patch(
        why="pnpm refuses to build when the install predates the full workspace copy",
        anchor="RUN pnpm build && pnpm --filter @emdash-cms/template-blog build",
        replacement=(
            "RUN pnpm install --frozen-lockfile"
            " && pnpm build"
            " && pnpm --filter @emdash-cms/template-blog build"
        ),
    ),
]


def apply(text: str) -> tuple[str, list[str]]:
    """Return the patched text plus one line of report per patch."""
    lines = text.splitlines(keepends=True)
    report: list[str] = []

    for patch in PATCHES:
        indexes = [i for i, line in enumerate(lines) if line.strip() == patch.anchor]
        if len(indexes) != 1:
            report.append(
                f"NOT APPLIED ({len(indexes)} matches) — {patch.why}"
            )
            continue
        index = indexes[0]
        indent = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
        lines[index] = f"{indent}{patch.replacement}\n"
        report.append(f"applied at line {index + 1} — {patch.why}")

    return "".join(lines), report


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {Path(argv[0]).name} <upstream-dockerfile> <output-dockerfile>", file=sys.stderr)
        return 2

    source, destination = Path(argv[1]), Path(argv[2])
    original = source.read_text(encoding="utf-8")
    patched, report = apply(original)
    destination.write_text(patched, encoding="utf-8")

    print(f"patches evaluated: {len(PATCHES)}")
    for line in report:
        print(f"  {line}")

    if patched != original:
        print("--- diff applied to the Dockerfile ---")
        for line in difflib.unified_diff(
            original.splitlines(),
            patched.splitlines(),
            fromfile=str(source),
            tofile=str(destination),
            lineterm="",
        ):
            print(line)

    if any(res.startswith("NOT APPLIED") for res in report):
        print(
            "::notice::At least one patch no longer applies; upstream probably "
            "changed the Dockerfile."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
