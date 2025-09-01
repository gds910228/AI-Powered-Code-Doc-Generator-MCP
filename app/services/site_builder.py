from __future__ import annotations

import fnmatch
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from app.services.repo import get_runtime_root


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ts() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def _write_text(path: str, content: str) -> None:
    _ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _should_exclude(rel_path: str, exclude_patterns: Optional[List[str]]) -> bool:
    if not exclude_patterns:
        return False
    # Normalize to forward slashes for glob matching
    rp = rel_path.replace("\\", "/")
    for pat in exclude_patterns:
        if fnmatch.fnmatch(rp, pat):
            return True
    return False


def _discover_top_modules(project_dir: str, exclude_patterns: Optional[List[str]]) -> Tuple[List[str], List[str]]:
    """
    Discover top-level python modules/packages to document.

    Returns:
      (module_names, sys_path_additions)
    """
    module_names: List[str] = []
    sys_path_additions: List[str] = []

    # Always consider project root on sys.path
    sys_path_additions.append(project_dir)

    # src layout
    src_dir = os.path.join(project_dir, "src")
    if os.path.isdir(src_dir):
        sys_path_additions.append(src_dir)
        # find top-level packages under src
        for name in os.listdir(src_dir):
            abs_p = os.path.join(src_dir, name)
            rel_p = os.path.relpath(abs_p, project_dir)
            if _should_exclude(rel_p, exclude_patterns):
                continue
            if os.path.isdir(abs_p):
                if os.path.isfile(os.path.join(abs_p, "__init__.py")):
                    module_names.append(name)
            elif name.endswith(".py") and name != "__init__.py":
                module_names.append(os.path.splitext(name)[0])

    # top-level packages in project root (non-src)
    for name in os.listdir(project_dir):
        if name in {".git", ".mcp_docsite", "_site", ".venv", "venv", "env", ".env"}:
            continue
        abs_p = os.path.join(project_dir, name)
        rel_p = os.path.relpath(abs_p, project_dir)
        if _should_exclude(rel_p, exclude_patterns):
            continue

        if os.path.isdir(abs_p):
            if os.path.isfile(os.path.join(abs_p, "__init__.py")):
                if name not in module_names:
                    module_names.append(name)
        elif name.endswith(".py"):
            mod = os.path.splitext(name)[0]
            if mod not in module_names:
                module_names.append(mod)

    # Deduplicate preserving order
    seen = set()
    dedup: List[str] = []
    for m in module_names:
        if m not in seen:
            seen.add(m)
            dedup.append(m)

    return dedup, sys_path_additions


def _prepare_mkdocs_project(
    project_dir: str,
    modules: List[str],
    docformat: str,
    temp_root: str,
) -> Tuple[str, str]:
    """
    Create a temporary mkdocs project with mkdocstrings pages.
    Returns:
      (mkdocs_yml_path, docs_dir)
    """
    mk_root = os.path.join(temp_root, ".mcp_docsite", _ts())
    docs_dir = os.path.join(mk_root, "docs")
    _ensure_dir(docs_dir)

    # index.md from README.md if exists
    readme_src = os.path.join(project_dir, "README.md")
    index_md = os.path.join(docs_dir, "index.md")
    if os.path.isfile(readme_src):
        try:
            shutil.copyfile(readme_src, index_md)
        except Exception:
            _write_text(index_md, "# 项目文档\n\n本文档由 MCP DocSite 自动生成。")
    else:
        _write_text(index_md, "# 项目文档\n\n本文档由 MCP DocSite 自动生成。")

    # api.md with mkdocstrings directives
    api_md = os.path.join(docs_dir, "api.md")
    lines = ["# API 参考\n"]
    if modules:
        for m in modules:
            lines.append(f"## {m}\n")
            # mkdocstrings directive
            # Use options to set docstring style
            lines.append(f"::: {m}\n    options:\n      docstring_style: {docformat}\n      show_root_heading: true\n      show_source: true\n      merge_init_into_class: true\n")
    else:
        lines.append("暂无可识别模块。\n")
    _write_text(api_md, "\n".join(lines))

    # mkdocs.yml
    mkdocs_yml = os.path.join(mk_root, "mkdocs.yml")
    mk = f"""site_name: Project Documentation
site_url: ""
theme:
  name: material
plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          options:
            docstring_style: {docformat}
            show_root_heading: true
            merge_init_into_class: true
            show_source: true
            inherited_members: true
            members_order: source
markdown_extensions:
  - toc
  - admonition
  - tables
  - codehilite
nav:
  - 首页: index.md
  - API 参考: api.md
"""
    _write_text(mkdocs_yml, mk)

    return mkdocs_yml, docs_dir


def _run_subprocess(cmd: List[str], cwd: Optional[str], env: Dict[str, str], timeout: int, log_lines: List[str]) -> int:
    log_lines.append(f"$ {' '.join(cmd)}")
    try:
        res = subprocess.run(cmd, cwd=cwd, env=env, timeout=timeout, capture_output=True, text=True)
        if res.stdout:
            log_lines.append(res.stdout)
        if res.stderr:
            log_lines.append(res.stderr)
        return res.returncode
    except subprocess.TimeoutExpired as e:
        log_lines.append(f"Timeout: {e}")
        return 124
    except Exception as e:
        log_lines.append(f"Exception: {type(e).__name__}: {e}")
        return 1


def _write_log(lines: List[str]) -> str:
    runtime_root = get_runtime_root(PROJECT_ROOT)
    logs_dir = os.path.join(runtime_root, "logs")
    _ensure_dir(logs_dir)
    path = os.path.join(logs_dir, f"docsite-{_ts()}.log")
    _write_text(path, "\n".join(lines))
    return path


def build_static_site(
    project_dir: str,
    site_dir: Optional[str] = None,
    generator: str = "mkdocs",
    include_paths: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    docformat: str = "google",
    language: str = "zh",
    install_deps: bool = False,
    timeout: int = 300,
) -> Dict[str, Any]:
    """
    Build a static documentation site for a Python project.
    Prefers mkdocs + mkdocstrings (griffe) which doesn't import target code.
    Falls back to pdoc if requested or mkdocs not available.

    Returns:
      {
        "status": "completed" | "error",
        "site_dir": "...",
        "generator_used": "mkdocs" | "pdoc",
        "errors_detail_path": "...",
      }
    """
    log_lines: List[str] = []
    try:
        project_dir = os.path.abspath(project_dir)
        if not os.path.isdir(project_dir):
            raise ValueError(f"Project directory not found: {project_dir}")

        # Defaults
        if site_dir is None:
            site_dir = os.path.join(project_dir, "_site")
        site_dir = os.path.abspath(site_dir)
        _ensure_dir(site_dir)

        # Discover modules
        modules, sys_paths = _discover_top_modules(project_dir, exclude_patterns)
        log_lines.append(f"Discovered modules: {modules}")
        log_lines.append(f"sys.path additions: {sys_paths}")

        # Prepare temporary mkdocs project
        mkdocs_yml, docs_dir = _prepare_mkdocs_project(
            project_dir=project_dir, modules=modules, docformat=docformat, temp_root=project_dir
        )
        mkdocs_root = os.path.dirname(mkdocs_yml)

        # Environment
        env = os.environ.copy()
        # Prepend PYTHONPATH with project root and src if present
        extra_paths = sys_paths
        pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (os.pathsep.join(extra_paths) + (os.pathsep + pp if pp else ""))

        py = sys.executable

        def _ensure_mkdocs_deps() -> None:
            if not install_deps:
                return
            pkgs = ["mkdocs", "mkdocstrings[python]", "mkdocs-material", "griffe"]
            cmds = [
                [py, "-m", "pip", "install", "-U", "--default-timeout", "180", "-i", "https://pypi.org/simple"] + pkgs,
                [py, "-m", "pip", "install", "-U", "--default-timeout", "180", "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"] + pkgs,
            ]
            rc = 1
            for c in cmds:
                rc = _run_subprocess(c, cwd=mkdocs_root, env=env, timeout=timeout, log_lines=log_lines)
                log_lines.append(f"pip install deps rc={rc}")
                if rc == 0:
                    break

        def _try_mkdocs() -> int:
            cmd = ["mkdocs", "build", "-f", mkdocs_yml, "-d", site_dir]
            # Prefer module execution if mkdocs command not on PATH
            if shutil.which("mkdocs") is None:
                cmd = [py, "-m", "mkdocs", "build", "-f", mkdocs_yml, "-d", site_dir]
            return _run_subprocess(cmd, cwd=mkdocs_root, env=env, timeout=timeout, log_lines=log_lines)

        def _try_pdoc() -> int:
            # Prefer filesystem paths to reduce import coupling
            targets: List[str] = []
            if include_paths:
                for p in include_paths:
                    ap = os.path.join(project_dir, p) if not os.path.isabs(p) else p
                    if os.path.exists(ap):
                        targets.append(ap)
            if not targets:
                # prefer src dir
                srcp = os.path.join(project_dir, "src")
                if os.path.isdir(srcp):
                    targets.append(srcp)
                # add discovered module dirs if exist under root or src
                for m in modules:
                    cand1 = os.path.join(project_dir, m)
                    cand2 = os.path.join(srcp, m) if os.path.isdir(srcp) else None
                    if os.path.isdir(cand1):
                        targets.append(cand1)
                    elif cand2 and os.path.isdir(cand2):
                        targets.append(cand2)
                if not targets:
                    targets = [project_dir]
            cmd = [py, "-m", "pdoc", "--docformat", docformat, "-o", site_dir] + targets
            return _run_subprocess(cmd, cwd=project_dir, env=env, timeout=timeout, log_lines=log_lines)

        generator_used = None

        if generator.lower() in ("mkdocs", "auto"):
            _ensure_mkdocs_deps()
            rc = _try_mkdocs()
            if rc == 0:
                generator_used = "mkdocs"
            elif generator.lower() == "auto":
                # Fallback to pdoc
                log_lines.append("mkdocs failed, trying pdoc as fallback...")
                if install_deps:
                    _run_subprocess([py, "-m", "pip", "install", "-U", "pdoc"], cwd=project_dir, env=env, timeout=timeout, log_lines=log_lines)
                rc2 = _try_pdoc()
                if rc2 == 0:
                    generator_used = "pdoc"
                else:
                    log_path = _write_log(log_lines)
                    return {"status": "error", "message": "mkdocs and pdoc both failed", "errors_detail_path": log_path}
            else:
                if rc != 0:
                    log_path = _write_log(log_lines)
                    return {"status": "error", "message": "mkdocs failed", "errors_detail_path": log_path}
        elif generator.lower() == "pdoc":
            if install_deps:
                _run_subprocess([py, "-m", "pip", "install", "-U", "pdoc"], cwd=project_dir, env=env, timeout=timeout, log_lines=log_lines)
            rc = _try_pdoc()
            if rc == 0:
                generator_used = "pdoc"
            else:
                log_path = _write_log(log_lines)
                return {"status": "error", "message": "pdoc failed", "errors_detail_path": log_path}
        else:
            log_path = _write_log(log_lines)
            return {"status": "error", "message": f"Unknown generator: {generator}", "errors_detail_path": log_path}

        # Success
        log_path = _write_log(log_lines)
        return {
            "status": "completed",
            "site_dir": site_dir,
            "generator_used": generator_used or generator,
            "errors_detail_path": log_path,
        }

    except Exception as e:
        log_path = _write_log(log_lines + [f"Fatal: {type(e).__name__}: {e}"])
        return {"status": "error", "message": f"{type(e).__name__}: {e}", "errors_detail_path": log_path}