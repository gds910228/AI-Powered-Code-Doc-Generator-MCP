from typing import Optional, Dict, Any, List
import os

from fastapi import APIRouter
from pydantic import BaseModel, HttpUrl

from app.services.parser import parse_python_project

router = APIRouter()


class GenerateRequest(BaseModel):
    # Placeholder for future Git clone; for now we parse local dir
    repo_url: HttpUrl
    # Minimal working path: when provided, we parse this local directory
    local_path: Optional[str] = None


class GenerateResponse(BaseModel):
    task_id: str
    status: str
    message: Optional[str] = None
    target_dir: str
    summary: Dict[str, Any]


def _resolve_target_dir(local_path: Optional[str]) -> str:
    """
    Minimal working path resolution:
    1) explicit local_path if exists
    2) env DOCGEN_LOCAL_REPO if exists
    3) current working directory
    """
    if local_path and os.path.isdir(local_path):
        return os.path.abspath(local_path)
    env_dir = os.getenv("DOCGEN_LOCAL_REPO")
    if env_dir and os.path.isdir(env_dir):
        return os.path.abspath(env_dir)
    return os.getcwd()


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


@router.post("/generate", response_model=GenerateResponse, tags=["generate"])
async def generate_docs(payload: GenerateRequest) -> GenerateResponse:
    target_dir = _resolve_target_dir(payload.local_path)
    docs = parse_python_project(target_dir)
    summary = _summarize(docs)

    return GenerateResponse(
        task_id="stub-parse-local-001",
        status="completed",
        message=(
            "Parsed local directory successfully. Git cloning based on repo_url "
            "is not implemented yet in this minimal flow."
        ),
        target_dir=target_dir,
        summary=summary,
    )