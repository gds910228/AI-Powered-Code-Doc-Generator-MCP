import os
import subprocess
from typing import Optional
from uuid import uuid4


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _is_dir_empty(path: str) -> bool:
    return os.path.isdir(path) and len(os.listdir(path)) == 0


def get_runtime_root(project_root: str) -> str:
    """
    Get or create runtime directory under project root.
    """
    rt = os.path.join(project_root, "runtime")
    _ensure_dir(rt)
    return rt


def clone_repo(
    repo_url: str,
    work_root: Optional[str] = None,
    dest_dir: Optional[str] = None,
    depth: int = 1,
    timeout: int = 180,
) -> str:
    """
    Clone a git repo.
    - If dest_dir is provided: clone into that exact directory.
        * If dest_dir exists and is not empty -> raise FileExistsError
        * If dest_dir exists but empty -> reuse it
        * Ensure parent directory exists
    - Else: clone into a new temporary directory under work_root (or project runtime).

    Returns:
        The cloned directory path.

    Raises:
        FileNotFoundError: if git is not installed or not in PATH
        subprocess.CalledProcessError: if git returns non-zero exit
        subprocess.TimeoutExpired: if cloning exceeds timeout
        ValueError: if repo_url looks invalid
        FileExistsError: if dest_dir already exists and not empty
    """
    if not isinstance(repo_url, str) or "://" not in repo_url:
        raise ValueError(f"Invalid repo_url: {repo_url!r}")

    if dest_dir:
        dest_dir = os.path.abspath(dest_dir)
        parent = os.path.dirname(dest_dir)
        _ensure_dir(parent)
        if os.path.exists(dest_dir) and not _is_dir_empty(dest_dir):
            raise FileExistsError(f"Destination already exists and is not empty: {dest_dir}")
        if not os.path.exists(dest_dir):
            _ensure_dir(dest_dir)
    else:
        if work_root is None:
            project_root = os.getcwd()
            work_root = get_runtime_root(project_root)
        else:
            _ensure_dir(work_root)
        dest_dir = os.path.join(work_root, f"tmp-{uuid4().hex}")
        _ensure_dir(dest_dir)

    cmd = ["git", "clone", "--depth", str(depth), repo_url, dest_dir]

    # Execute clone
    subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    return dest_dir