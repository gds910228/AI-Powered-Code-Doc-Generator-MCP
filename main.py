"""
MCP Server entrypoint for AI-Powered Code Documentation Generator.

Run:
  python main.py

Notes:
  - Starts an MCP server using SSE transport.
  - Tools:
      - parse_local(local_path)
      - generate_from_repo(repo_url, local_path?, dest_dir?, work_root?, depth?, timeout?)
      - generate_docstrings(local_path?, repo_url?, style?, language?, max_items?, depth?, timeout?)
  - FastAPI backend remains available via scripts/run_api.py (REST/Swagger).
"""

from __future__ import annotations

import os
import sys
import subprocess
from typing import Any, Dict, List, Optional

# Ensure project root is importable
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# MCP server
try:
    from mcp.server.fastmcp import FastMCP
except Exception as e:
    print('Missing "mcp" package. Install with: pip install "mcp[cli]>=1.12.3"')
    raise

# Services
from app.services.parser import parse_python_project
from app.services.repo import clone_repo, get_runtime_root
from app.services.documentation import generate_missing_docstrings


def _summarize(docs) -> Dict[str, Any]:
    modules = len(docs)
    classes = sum(len(m.classes) for m in docs)
    functions = sum(len(m.functions) for m in docs)
    methods = sum(len(c.methods) for m in docs for c in m.classes)
    missing_module_docs = sum(1 for m in docs if not m.docstring)
    missing_function_docs = sum(1 for m in docs for f in m.functions if not f.docstring)
    missing_method_docs = sum(
        1 for m in docs for c in m.classes for f in c.methods if not f.docstring
    )
    top_modules: List[Dict[str, Any]] = [
        {
            "module": m.module,
            "path": m.path,
            "classes": len(m.classes),
            "functions": len(m.functions),
            "has_doc": bool(m.docstring),
        }
        for m in docs[:10]
    ]
    return {
        "modules": modules,
        "classes": classes,
        "functions": functions,
        "methods": methods,
        "missing_module_docs": missing_module_docs,
        "missing_function_docs": missing_function_docs,
        "missing_method_docs": missing_method_docs,
        "top_modules": top_modules,
    }


mcp = FastMCP("docgen-mcp")


@mcp.tool()
def parse_local(local_path: str) -> Dict[str, Any]:
    """
    Parse and summarize a Python project at the given local path.
    Returns:
      { "target_dir": "...", "summary": { ... } }
    """
    if not os.path.isdir(local_path):
        raise ValueError(f"local_path not found or not a directory: {local_path}")
    target_dir = os.path.abspath(local_path)
    docs = parse_python_project(target_dir)
    return {"target_dir": target_dir, "summary": _summarize(docs)}


@mcp.tool()
def generate_from_repo(
    repo_url: str,
    local_path: Optional[str] = None,
    dest_dir: Optional[str] = None,
    work_root: Optional[str] = None,
    depth: int = 1,
    timeout: int = 180,
) -> Dict[str, Any]:
    """
    Generate documentation summary from a Git repository.
    Priority:
      1) If local_path exists, parse it directly (developer convenience)
      2) Else if dest_dir provided, clone into that exact directory
      3) Else clone under work_root/tmp-<uuid> (work_root default: project runtime)

    Returns:
      { "status": "completed" | "error",
        "mode": "local" | "cloned",
        "target_dir": "...",
        "summary": { ... },
        "note"?: str }
    """
    try:
        if local_path and os.path.isdir(local_path):
            target_dir = os.path.abspath(local_path)
            docs = parse_python_project(target_dir)
            return {
                "status": "completed",
                "mode": "local",
                "target_dir": target_dir,
                "summary": _summarize(docs),
            }

        # Clone flow
        wr = work_root
        if wr:
            wr = os.path.abspath(wr)
        else:
            wr = get_runtime_root(PROJECT_ROOT)

        repo_dir = clone_repo(
            repo_url,
            work_root=wr,
            dest_dir=dest_dir,
            depth=depth,
            timeout=timeout,
        )
        docs = parse_python_project(repo_dir)
        note = f"Cloned to {repo_dir}. You may remove it after inspection."
        if dest_dir:
            note = f"Cloned to explicit destination {repo_dir}."
        return {
            "status": "completed",
            "mode": "cloned",
            "target_dir": repo_dir,
            "summary": _summarize(docs),
            "note": note,
        }

    except FileExistsError as e:
        return {"status": "error", "message": str(e), "repo_url": repo_url, "dest_dir": dest_dir}
    except FileNotFoundError:
        return {
            "status": "error",
            "message": "git not found. Please install Git and ensure it's in PATH.",
            "repo_url": repo_url,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "status": "error",
            "message": f"git clone timeout after {e.timeout}s",
            "repo_url": repo_url,
        }
    except subprocess.CalledProcessError as e:
        return {
            "status": "error",
            "message": "git clone failed",
            "repo_url": repo_url,
            "returncode": e.returncode,
            "stdout": e.stdout,
            "stderr": e.stderr,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"unexpected error: {type(e).__name__}: {e}",
            "repo_url": repo_url,
            "dest_dir": dest_dir,
        }


@mcp.tool()
def generate_docstrings(
    local_path: Optional[str] = None,
    repo_url: Optional[str] = None,
    style: str = "google",
    language: str = "en",
    max_items: Optional[int] = None,
    depth: int = 1,
    timeout: int = 180,
    exclude_patterns: Optional[List[str]] = None,
    skip_imports: Optional[List[str]] = None,
    batch_size: Optional[int] = None,
    single_file_timeout: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Generate missing docstrings for a project using AI.
    - If local_path exists -> use it
    - Else if repo_url provided -> git clone (shallow) then run
    Returns:
      {
        "status": "completed" | "error",
        "mode": "local" | "cloned",
        "target_dir": "...",
        "summary": { scanned, generated, skipped, errors },
        "results": [ { module, path, class, function, lineno, signature, generated_docstring }, ... ]
      }
    """
    try:
        target_dir: Optional[str] = None
        mode = "local"

        if local_path and os.path.isdir(local_path):
            target_dir = os.path.abspath(local_path)
            mode = "local"
        elif repo_url:
            wr = get_runtime_root(PROJECT_ROOT)
            target_dir = clone_repo(repo_url, work_root=wr, depth=depth, timeout=timeout)
            mode = "cloned"
        else:
            return {
                "status": "error",
                "message": "Provide either a valid local_path or repo_url.",
            }

        out = generate_missing_docstrings(
            project_dir=target_dir,
            style=style,
            language=language,
            max_items=max_items,
            exclude_patterns=exclude_patterns,
            skip_imports=skip_imports,
            batch_size=batch_size,
            single_file_timeout=single_file_timeout,
            dry_run=dry_run,
        )
        return {
            "status": "completed",
            "mode": mode,
            "target_dir": out["target_dir"],
            "summary": out["summary"],
            "results": out["results"],
            "errors_detail_path": out.get("errors_detail_path"),
        }

    except FileNotFoundError:
        return {
            "status": "error",
            "message": "git not found. Please install Git and ensure it's in PATH.",
            "repo_url": repo_url,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "status": "error",
            "message": f"git clone timeout after {e.timeout}s",
            "repo_url": repo_url,
        }
    except subprocess.CalledProcessError as e:
        return {
            "status": "error",
            "message": "git clone failed",
            "repo_url": repo_url,
            "returncode": e.returncode,
            "stdout": e.stdout,
            "stderr": e.stderr,
        }
    except RuntimeError as e:
        # Likely AIService configuration or HTTP error
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"unexpected error: {type(e).__name__}: {e}"}


if __name__ == "__main__":
    # Prefer SSE transport; fallback if SDK doesn't support the parameter.
    try:
        mcp.run(transport="sse")
    except TypeError:
        mcp.run()