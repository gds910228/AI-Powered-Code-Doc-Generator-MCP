from __future__ import annotations

import os
import ast
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.services.parser import ModuleDoc, ClassDoc, FunctionDoc, parse_python_project
from app.services.ai import get_ai_service

# Server root (project root) -> runtime/logs
_SERVER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
_LOG_DIR = os.path.join(_SERVER_ROOT, "runtime", "logs")
os.makedirs(_LOG_DIR, exist_ok=True)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _open_log_file(prefix: str = "docgen") -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(_LOG_DIR, f"{prefix}-{ts}.log")
    # touch file
    with open(path, "a", encoding="utf-8") as _:
        pass
    return path


def _append_log(log_path: str, message: str) -> None:
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{_now()}] {message}\n")
    except Exception:
        # do not break main flow
        pass


def _file_contains_imports(file_path: str, modules: List[str]) -> bool:
    """
    Lightweight check: if file contains 'import X' or 'from X ' for any X in modules.
    """
    if not modules:
        return False
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return False
    for m in modules:
        key1 = f"import {m}"
        key2 = f"from {m} "
        if key1 in txt or key2 in txt:
            return True
    return False


def _build_signature(func: FunctionDoc) -> str:
    """
    Build a human-readable function signature using parsed metadata.
    Note: defaults are not included; annotations shown when available.
    """
    parts: List[str] = []
    for p in func.parameters:
        name = p.name
        if p.kind == "vararg":
            name = f"*{name}"
        elif p.kind == "varkw":
            name = f"**{name}"
        annot = f": {p.annotation}" if p.annotation else ""
        parts.append(f"{name}{annot}")
    params_str = ", ".join(parts)
    ret = f" -> {func.returns}" if func.returns else ""
    return f"{func.name}({params_str}){ret}"


def _find_function_node(
    file_path: str,
    func_name: str,
    func_lineno: int,
    class_name: Optional[str] = None,
    class_lineno: Optional[int] = None,
) -> Optional[ast.AST]:
    """
    Re-parse a file to locate the AST node of a target function/method by name and lineno.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        src = f.read()
    mod = ast.parse(src, filename=file_path)

    if class_name is None:
        for node in mod.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == func_name and getattr(node, "lineno", -1) == func_lineno:
                    return node
        return None

    # Method within a class
    for node in mod.body:
        if isinstance(node, ast.ClassDef):
            if node.name != class_name:
                continue
            if class_lineno is not None and getattr(node, "lineno", -1) != class_lineno:
                continue
            for b in node.body:
                if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if b.name == func_name and getattr(b, "lineno", -1) == func_lineno:
                        return b
    return None


def _extract_source_segment(file_path: str, node: ast.AST) -> str:
    """
    Extract source code segment for a given AST node using lineno and end_lineno.
    """
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if start is None:
        return ""
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if end is None:
        # Fallback: read only the starting line
        return lines[start - 1].rstrip("\n")
    return "".join(lines[start - 1 : end]).rstrip("\n")


def _insert_docstring_after_def(file_path: str, node: ast.AST, docstring: str) -> bool:
    """
    Insert a triple-quoted docstring as the first statement in a function/method body.

    Returns:
        bool: True if written successfully, False otherwise.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        def_line = getattr(node, "lineno", None)
        # Prefer the first body statement line for correct indentation
        body = getattr(node, "body", [])
        first_body_line = None
        if body:
            first_body_line = getattr(body[0], "lineno", None)

        # Compute insertion line (0-based index)
        insert_at = (first_body_line - 1) if first_body_line else (def_line if def_line else 1)

        # Derive indentation from the first body line; fallback to 4 spaces
        indent_str = ""
        if first_body_line:
            raw = lines[first_body_line - 1]
            indent_str = raw[: len(raw) - len(raw.lstrip())]
        else:
            # Fallback: use indentation from def line + 4 spaces
            if def_line and def_line - 1 < len(lines):
                def_raw = lines[def_line - 1]
                base_indent = def_raw[: len(def_raw) - len(def_raw.lstrip())]
                indent_str = base_indent + "    "
            else:
                indent_str = "    "

        # Sanitize docstring delimiters
        safe_doc = docstring.replace('"""', '\\"\\"\\"').rstrip()

        block = []
        block.append(f'{indent_str}"""')
        if safe_doc:
            for ln in safe_doc.splitlines():
                block.append(f"{indent_str}{ln.rstrip()}")
        block.append(f'{indent_str}"""')
        block.append("\n")  # ensure spacing after docstring

        # Insert block
        lines[insert_at:insert_at] = [l + ("\n" if not l.endswith("\n") else "") for l in block]

        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return True
    except Exception:
        return False


def _generate_for_function(
    file_path: str,
    func: FunctionDoc,
    style: str,
    language: str,
    class_ctx: Optional[Tuple[str, int]] = None,
) -> Dict[str, Any]:
    """
    Generate docstring for a single function/method using AI and write it back to source.
    """
    node = _find_function_node(
        file_path=file_path,
        func_name=func.name,
        func_lineno=func.lineno,
        class_name=class_ctx[0] if class_ctx else None,
        class_lineno=class_ctx[1] if class_ctx else None,
    )
    code = _extract_source_segment(file_path, node) if node else ""
    signature = _build_signature(func)
    ai = get_ai_service()
    doc = ai.generate_docstring(code=code, signature=signature, style=style, language=language)

    written = False
    if node is not None and doc:
        written = _insert_docstring_after_def(file_path, node, doc)

    return {
        "signature": signature,
        "lineno": func.lineno,
        "generated_docstring": doc,
        "is_method": func.is_method,
        "written": written,
    }


def generate_missing_docstrings(
    project_dir: str,
    style: str = "google",
    language: str = "en",
    max_items: Optional[int] = None,
    exclude_patterns: Optional[List[str]] = None,
    skip_imports: Optional[List[str]] = None,
    batch_size: Optional[int] = None,
    single_file_timeout: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Orchestrate parsing + AI generation for missing docstrings in functions/methods.

    Returns:
      {
        "target_dir": "...",
        "summary": {
          "scanned": int,
          "generated": int,
          "skipped": int,
          "errors": int
        },
        "results": [
          {
            "module": str,
            "path": str,
            "class": str | null,
            "function": str,
            "lineno": int,
            "signature": str,
            "generated_docstring": str
          },
          ...
        ]
      }
    """
    target_dir = os.path.abspath(project_dir)

    # Defaults for stability
    default_exclude = [
        "**/ui/**",
        "**/tools/**",
        "**/tests/**",
        "**/.venv/**",
        "**/venv/**",
        "**/env/**",
        "**/.env/**",
    ]
    default_skip_imports = [
        "streamlit",
        "ray",
        "torch",
        "stable_baselines3",
        "matplotlib",
        "plotly",
        "gym",
    ]
    exclude_patterns = exclude_patterns if exclude_patterns is not None else default_exclude
    skip_imports = skip_imports if skip_imports is not None else default_skip_imports
    # batch_size优先于max_items
    if batch_size and not max_items:
        max_items = batch_size

    # parse with exclude
    modules: List[ModuleDoc] = parse_python_project(target_dir, exclude_patterns=exclude_patterns)

    # open log
    log_path = _open_log_file(prefix="docgen")
    _append_log(log_path, f"Start doc generation")
    _append_log(log_path, f"target_dir={target_dir}")
    _append_log(log_path, f"style={style}, language={language}, max_items={max_items}, dry_run={dry_run}")
    _append_log(log_path, f"exclude_patterns={exclude_patterns}")
    _append_log(log_path, f"skip_imports={skip_imports}")

    scanned = 0
    generated = 0
    skipped = 0
    errors = 0
    results: List[Dict[str, Any]] = []

    remaining = max_items if max_items is not None else float("inf")

    for m in modules:
        # Detect heavy imports once per module
        mod_blocked = _file_contains_imports(m.path, skip_imports) if skip_imports else False
        if mod_blocked:
            _append_log(log_path, f"SKIP MODULE by imports: {m.path}")

        # Top-level functions
        for f in m.functions:
            if remaining <= 0:
                break
            scanned += 1
            if f.docstring:
                skipped += 1
                continue
            # module-level skip by heavy imports
            if mod_blocked:
                skipped += 1
                _append_log(log_path, f"SKIP FUNC (module blocked): {m.path}::{f.name}:{f.lineno}")
                continue
            if dry_run:
                skipped += 1
                _append_log(log_path, f"DRY RUN skip generate: {m.path}::{f.name}:{f.lineno}")
                continue
            try:
                out = _generate_for_function(
                    file_path=m.path,
                    func=f,
                    style=style,
                    language=language,
                    class_ctx=None,
                )
                results.append(
                    {
                        "module": m.module,
                        "path": m.path,
                        "class": None,
                        "function": f.name,
                        "lineno": out["lineno"],
                        "signature": out["signature"],
                        "generated_docstring": out["generated_docstring"],
                    }
                )
                generated += 1
                remaining -= 1
                _append_log(log_path, f"GENERATED: {m.path}::{f.name}:{f.lineno}")
            except Exception as e:
                errors += 1
                _append_log(log_path, f"ERROR GEN FUNC: {m.path}::{f.name}:{f.lineno} -> {type(e).__name__}: {e}")
                _append_log(log_path, traceback.format_exc())

        if remaining <= 0:
            break

        # Methods in classes
        for c in m.classes:
            for f in c.methods:
                if remaining <= 0:
                    break
                scanned += 1
                if f.docstring:
                    skipped += 1
                    continue
                # module-level skip by heavy imports
                if mod_blocked:
                    skipped += 1
                    _append_log(log_path, f"SKIP METHOD (module blocked): {m.path}::{c.name}.{f.name}:{f.lineno}")
                    continue
                if dry_run:
                    skipped += 1
                    _append_log(log_path, f"DRY RUN skip generate: {m.path}::{c.name}.{f.name}:{f.lineno}")
                    continue
                try:
                    out = _generate_for_function(
                        file_path=m.path,
                        func=f,
                        style=style,
                        language=language,
                        class_ctx=(c.name, c.lineno),
                    )
                    results.append(
                        {
                            "module": m.module,
                            "path": m.path,
                            "class": c.name,
                            "function": f.name,
                            "lineno": out["lineno"],
                            "signature": out["signature"],
                            "generated_docstring": out["generated_docstring"],
                        }
                    )
                    generated += 1
                    remaining -= 1
                    _append_log(log_path, f"GENERATED: {m.path}::{c.name}.{f.name}:{f.lineno}")
                except Exception as e:
                    errors += 1
                    _append_log(log_path, f"ERROR GEN METHOD: {m.path}::{c.name}.{f.name}:{f.lineno} -> {type(e).__name__}: {e}")
                    _append_log(log_path, traceback.format_exc())

            if remaining <= 0:
                break

        if remaining <= 0:
            break

    _append_log(log_path, f"Done: scanned={scanned}, generated={generated}, skipped={skipped}, errors={errors}")

    return {
        "target_dir": target_dir,
        "summary": {
            "scanned": scanned,
            "generated": generated,
            "skipped": skipped,
            "errors": errors,
        },
        "results": results,
        "errors_detail_path": log_path,
    }
