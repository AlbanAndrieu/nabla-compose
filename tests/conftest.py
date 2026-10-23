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
