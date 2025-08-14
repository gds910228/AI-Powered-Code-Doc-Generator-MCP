from __future__ import annotations

import os
import ast
from typing import Any, Dict, List, Optional, Tuple

from app.services.parser import ModuleDoc, ClassDoc, FunctionDoc, parse_python_project
from app.services.ai import get_ai_service


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


def _generate_for_function(
    file_path: str,
    func: FunctionDoc,
    style: str,
    language: str,
    class_ctx: Optional[Tuple[str, int]] = None,
) -> Dict[str, Any]:
    """
    Generate docstring for a single function/method using AI.
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
    return {
        "signature": signature,
        "lineno": func.lineno,
        "generated_docstring": doc,
        "is_method": func.is_method,
    }


def generate_missing_docstrings(
    project_dir: str,
    style: str = "google",
    language: str = "en",
    max_items: Optional[int] = None,
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
    modules: List[ModuleDoc] = parse_python_project(target_dir)

    scanned = 0
    generated = 0
    skipped = 0
    errors = 0
    results: List[Dict[str, Any]] = []

    remaining = max_items if max_items is not None else float("inf")

    for m in modules:
        # Top-level functions
        for f in m.functions:
            if remaining <= 0:
                break
            scanned += 1
            if f.docstring:
                skipped += 1
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
            except Exception:
                errors += 1

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
                except Exception:
                    errors += 1

            if remaining <= 0:
                break

        if remaining <= 0:
            break

    return {
        "target_dir": target_dir,
        "summary": {
            "scanned": scanned,
            "generated": generated,
            "skipped": skipped,
            "errors": errors,
        },
        "results": results,
    }