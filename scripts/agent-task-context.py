from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
)


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def changed_paths() -> list[str]:
    paths: set[str] = set()
    base = os.environ.get("QUALITY_BASE_REF")
    if not base:
        for candidate in ("origin/master", "master"):
            if subprocess.run(
                ["git", "rev-parse", "--verify", candidate],
                cwd=ROOT,
                capture_output=True,
                text=True,
            ).returncode == 0:
                base = candidate
                break
    if base:
        paths.update(
            path
            for path in git("diff", "--name-only", f"{base}...HEAD").splitlines()
            if path
        )

    for args in (
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        paths.update(path for path in git(*args).splitlines() if path)

    return sorted(paths)


def suggested_skills(paths: list[str]) -> list[str]:
    skills: set[str] = set()
    joined = "\n".join(paths).lower()

    if any(
        token in joined
        for token in (
            "config/secrets/",
            "scripts/secrets/",
            ".env",
            "env_file",
        )
    ):
        skills.update(
            {
                "homelab-secrets",
                "docker-compose-orchestration",
                "nabla-service-catalog",
            }
        )

    if any(
        path.startswith("apps/")
        and (
            path.endswith("/compose.yml")
            or "/compose." in path
            or "/docker-compose" in path
        )
        for path in paths
    ):
        skills.update({"docker-compose-orchestration", "nabla-service-catalog"})

    if any(
        token in joined
        for token in (
            "catalog-info.yaml",
            "catalog/",
            "service-catalog",
            "catalog_v2",
            "catalog-v2",
        )
    ):
        skills.add("nabla-service-catalog")

    if any(
        token in joined
        for token in (
            "pfsense",
            "haproxy",
            "pfblocker",
            "snort",
            "suricata",
            "unbound",
            "kea",
        )
    ):
        skills.add("pfsense-api-debugging")

    if any(
        path.startswith("scripts/truenas/")
        or path.startswith("docs/truenas")
        for path in paths
    ):
        skills.add("homelab-runtime-status")

    return sorted(skills)


def main() -> int:
    branch = git("branch", "--show-current")
    status = git("status", "--short")
    paths = changed_paths()
    skills = suggested_skills(paths)

    print(f"branch: {branch or '<detached>'}")
    print("default-branch-protected: " + ("NO" if branch == "master" else "YES"))
    print(f"changed-paths: {len(paths)}")
    for path in paths:
        print(f"  - {path}")

    print("suggested-skills:")
    if skills:
        for skill in skills:
            print(f"  - {skill}")
    else:
        print("  - none inferred; inspect the task before loading a skill")

    print("working-tree:")
    if status:
        for line in status.splitlines():
            print(f"  {line}")
    else:
        print("  clean")

    print("next:")
    print("  1. read AGENTS.md and agent.md")
    print("  2. load only the suggested/relevant skills")
    print("  3. run the narrowest contract before mise run agent-fix")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
