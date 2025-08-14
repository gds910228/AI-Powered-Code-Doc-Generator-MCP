from __future__ import annotations

import os
import ast
from dataclasses import dataclass
from typing import List, Optional, Union

from pydantic import BaseModel


# ---------------------------
# Data Models
# ---------------------------

class ParameterDoc(BaseModel):
    name: str
    annotation: Optional[str] = None
    has_default: bool = False
    kind: str = "positional"  # positional | vararg | kwonly | varkw


class FunctionDoc(BaseModel):
    name: str
    lineno: int
    docstring: Optional[str] = None
    parameters: List[ParameterDoc] = []
    returns: Optional[str] = None
    is_method: bool = False


class ClassDoc(BaseModel):
    name: str
    lineno: int
    docstring: Optional[str] = None
    methods: List[FunctionDoc] = []


class ModuleDoc(BaseModel):
    path: str               # absolute file path
    module: str             # dotted module name (relative to project root)
    docstring: Optional[str] = None
    classes: List[ClassDoc] = []
    functions: List[FunctionDoc] = []


# ---------------------------
# AST Parsing Utilities
# ---------------------------

_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
    "venv",
    ".venv",
    "env",
    ".env",
}


def _should_skip_dir(dir_name: str) -> bool:
    return dir_name in _SKIP_DIRS or dir_name.startswith(".")


def _rel_module_name(project_root: str, file_path: str) -> str:
    """
    Convert a file path to a dotted module path relative to project_root.
    e.g., project_root=/repo, file=/repo/pkg/sub/mod.py -> pkg.sub.mod
          if file endswith __init__.py, module -> pkg.sub
    """
    rel = os.path.relpath(file_path, project_root)
    rel_no_ext = rel[:-3] if rel.endswith(".py") else rel
    parts = rel_no_ext.split(os.sep)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join([p for p in parts if p and p != "."])


def _unparse(node: Optional[ast.AST]) -> Optional[str]:
    if node is None:
        return None
    try:
        # Python 3.9+ has ast.unparse
        return ast.unparse(node)  # type: ignore[attr-defined]
    except Exception:
        return None


def _parse_parameters(args: ast.arguments) -> List[ParameterDoc]:
    params: List[ParameterDoc] = []

    def handle_arg(a: ast.arg, has_default: bool, kind: str) -> None:
        params.append(
            ParameterDoc(
                name=a.arg,
                annotation=_unparse(a.annotation),
                has_default=has_default,
                kind=kind,
            )
        )

    # Positional-only (Python 3.8+)
    posonly_defaults_start = len(args.posonlyargs) - len(args.defaults)
    for idx, a in enumerate(args.posonlyargs):
        has_default = idx >= max(0, posonly_defaults_start)
        handle_arg(a, has_default, "positional")

    # Positional-or-keyword
    pk_defaults_start = len(args.args) - len(args.defaults)
    for idx, a in enumerate(args.args):
        has_default = idx >= max(0, pk_defaults_start)
        handle_arg(a, has_default, "positional")

    # *vararg
    if args.vararg:
        handle_arg(args.vararg, False, "vararg")

    # Keyword-only
    for i, a in enumerate(args.kwonlyargs):
        has_default = False
        if args.kw_defaults and i < len(args.kw_defaults):
            has_default = args.kw_defaults[i] is not None
        handle_arg(a, has_default, "kwonly")

    # **varkw
    if args.kwarg:
        handle_arg(args.kwarg, False, "varkw")

    return params


def _parse_function(node: Union[ast.FunctionDef, ast.AsyncFunctionDef], is_method: bool = False) -> FunctionDoc:
    params = _parse_parameters(node.args)
    # Exclude 'self' for methods in parameters display but retain metadata otherwise if desired
    if is_method and params and params[0].name == "self":
        params = params[1:]

    return FunctionDoc(
        name=node.name,
        lineno=getattr(node, "lineno", 1),
        docstring=ast.get_docstring(node),
        parameters=params,
        returns=_unparse(node.returns),
        is_method=is_method,
    )


def _parse_class(node: ast.ClassDef) -> ClassDoc:
    methods: List[FunctionDoc] = []
    for b in node.body:
        if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(_parse_function(b, is_method=True))
    return ClassDoc(
        name=node.name,
        lineno=getattr(node, "lineno", 1),
        docstring=ast.get_docstring(node),
        methods=methods,
    )


def parse_file(file_path: str, project_root: str) -> ModuleDoc:
    with open(file_path, "r", encoding="utf-8") as f:
        src = f.read()

    module_node = ast.parse(src, filename=file_path, mode="exec")
    mod_doc = ast.get_docstring(module_node)

    classes: List[ClassDoc] = []
    functions: List[FunctionDoc] = []

    for node in module_node.body:
        if isinstance(node, ast.ClassDef):
            classes.append(_parse_class(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(_parse_function(node, is_method=False))

    return ModuleDoc(
        path=os.path.abspath(file_path),
        module=_rel_module_name(project_root, file_path),
        docstring=mod_doc,
        classes=classes,
        functions=functions,
    )


def parse_python_project(root_dir: str) -> List[ModuleDoc]:
    """
    Traverse a project directory, parse all .py files (excluding skipped dirs),
    and return a list of ModuleDoc structures.
    """
    root_dir = os.path.abspath(root_dir)
    results: List[ModuleDoc] = []

    for current_root, dirs, files in os.walk(root_dir):
        # mutate dirs in-place to prune traversal
        dirs[:] = [d for d in dirs if not _should_skip_dir(d)]

        for fn in files:
            if not fn.endswith(".py"):
                continue
            file_path = os.path.join(current_root, fn)
            try:
                results.append(parse_file(file_path, project_root=root_dir))
            except SyntaxError:
                # Skip files with syntax errors; could log if needed
                continue
            except UnicodeDecodeError:
                continue
            except Exception:
                # Be robust; upstream can collect errors as needed
                continue

    return results


# Optional: quick self-check when run directly
if __name__ == "__main__":
    import json
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "."
    docs = parse_python_project(target)
    print(json.dumps([d.model_dump() for d in docs], ensure_ascii=False, indent=2))