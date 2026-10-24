"""Isolate the test session from the Git hook environment of the caller.

Git hooks export GIT_DIR, GIT_INDEX_FILE, GIT_WORK_TREE, ... to their
children. A test that creates a throwaway repository would then run
`git add`/`git commit` against the caller's real index (seen as a
"baseline" README.md or 206 fixture module_*.py files staged during a
push). A global init.templateDir would also copy operator hooks into
fixture repositories. Strip the repository-location variables and use an
empty template directory for every subprocess spawned by the tests.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile

import pytest

_REPOSITORY_ENV = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_PREFIX",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)

for _name in _REPOSITORY_ENV:
    os.environ.pop(_name, None)

_TEMPLATE_DIR = tempfile.mkdtemp(prefix="nabla-empty-git-template-")
os.environ["GIT_TEMPLATE_DIR"] = _TEMPLATE_DIR
atexit.register(shutil.rmtree, _TEMPLATE_DIR, ignore_errors=True)


@pytest.fixture
def noexec_safe_bash_mocks(tmp_path):
    """Execute test command stubs via Bash even on TrueNAS /tmp with noexec.

    The tested script still invokes docker/curl/getent normally. BASH_ENV
    defines shell functions forwarding to fixture stubs through /bin/bash,
    which reads a regular file without trying to execute it from /tmp.
    """
    def activate(env: dict[str, str], *commands: str) -> dict[str, str]:
        allowed = {"docker", "curl", "getent", "setpriv", "just"}
        if not commands or any(command not in allowed for command in commands):
            raise ValueError("invalid Bash mock command")
        envfile = tmp_path / "nabla-bash-mock-env.sh"
        envfile.write_text(
            "".join(
                f'{command}() {{ BASH_ENV= /bin/bash "$NABLA_MOCK_BIN/{command}" "$@"; }}'
                + chr(10) for command in commands
            ),
            encoding="utf-8",
        )
        env["NABLA_MOCK_BIN"] = str(tmp_path / "bin")
        env["BASH_ENV"] = str(envfile)
        return env

    return activate
