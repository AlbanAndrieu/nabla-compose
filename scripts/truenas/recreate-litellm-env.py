#!/usr/bin/env python3
"""Recreate the existing TrueNAS LiteLLM Compose service using its own labels."""
import argparse
import json
import subprocess
import sys

SERVICE = "litellm"
REQUIRED = ("LITELLM_OPENCLAW_CRON_API_KEY", "LITELLM_OPENCLAW_MAIN_API_KEY",
            "LITELLM_REACTIVE_API_KEY", "LITELLM_IDE_API_KEY",
            "LITELLM_API_KEY", "LITELLM_N8N_API_KEY", "LANGFUSE_PUBLIC_KEY")


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, check=False, timeout=90)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    response = run("docker", "inspect", SERVICE)
    if response.returncode:
        print("container=unavailable")
        return 2
    try:
        item = json.loads(response.stdout)[0]
    except (ValueError, KeyError, IndexError):
        print("container=invalid")
        return 2
    labels = item.get("Config", {}).get("Labels") or {}
    project = labels.get("com.docker.compose.project")
    compose_files = labels.get("com.docker.compose.project.config_files")
    workdir = labels.get("com.docker.compose.project.working_dir")
    service = labels.get("com.docker.compose.service")
    if not all((project, compose_files, workdir, service == SERVICE)):
        print("compose_origin=unverified")
        return 2
    # Compose metadata is read from Docker, never from an untrusted CLI argument.
    files = compose_files.split(",")
    command = ["docker", "compose", "--project-directory", workdir]
    for path in files:
        command += ["-f", path]
    command += ["-p", project]
    check = run(*(command + ["config", "--quiet"]))
    if check.returncode:
        print("compose_config=invalid_or_unavailable")
        return 2
    print("compose_config=valid")
    if not args.apply:
        print("container_recreation=planned")
        return 0
    print("container_recreation=requested")
    result = run(*(command + ["up", "--no-deps", "--no-build", "--pull", "never",
                               "--force-recreate", "-d", SERVICE]))
    if result.returncode:
        print("container_recreation=failed")
        return 2
    refreshed = run("docker", "inspect", SERVICE)
    if refreshed.returncode:
        print("container_recreation=unverified")
        return 2
    try:
        instance = json.loads(refreshed.stdout)[0]
    except (ValueError, IndexError, KeyError):
        return 2
    environment = dict(entry.partition("=")[::2]
                       for entry in instance.get("Config", {}).get("Env") or []
                       if "=" in entry)
    missing = [name for name in REQUIRED if not environment.get(name)]
    print("container_running=" + str(bool(instance.get("State", {}).get("Running"))).lower())
    print("secrets_loaded=" + ("yes" if not missing else "no"))
    print("secrets_missing_count=" + str(len(missing)))
    return 0 if not missing and instance.get("State", {}).get("Running") else 2


if __name__ == "__main__":
    sys.exit(main())
