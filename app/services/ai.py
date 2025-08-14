from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


"""
AIService for Tencent Hunyuan (OpenAI-compatible endpoint)

Configuration via environment variables:
- HUNYUAN_OPENAI_BASE: Base URL of Hunyuan OpenAI-compatible endpoint, e.g. https://api.hunyuan.cloud.tencent.com/v1
- HUNYUAN_API_KEY:     API key for Authorization: Bearer <key>
- HUNYUAN_MODEL:       Default model name, e.g. hunyuan-lite or hunyuan-pro (default: hunyuan-lite)

No extra third-party dependency is required (uses urllib from stdlib).
If your endpoint strictly follows OpenAI chat-completions API, this will work out-of-the-box.
"""


@dataclass
class AIServiceConfig:
    base_url: str
    api_key: str
    model: str = "hunyuan-lite"
    timeout: int = 60

    @staticmethod
    def from_env() -> "AIServiceConfig":
        base = os.getenv("HUNYUAN_OPENAI_BASE", "").strip()
        key = os.getenv("HUNYUAN_API_KEY", "").strip()
        model = os.getenv("HUNYUAN_MODEL", "hunyuan-lite").strip()
        if not base or not key:
            raise RuntimeError(
                "AIService not configured. Please set HUNYUAN_OPENAI_BASE and HUNYUAN_API_KEY."
            )
        return AIServiceConfig(base_url=base, api_key=key, model=model)


class AIService:
    def __init__(self, cfg: Optional[AIServiceConfig] = None) -> None:
        self.cfg = cfg or AIServiceConfig.from_env()

    def _chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Call OpenAI-compatible chat completions.
        Endpoint: {base_url}/chat/completions
        Payload: { model, messages, temperature, (optional) max_tokens }
        """
        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        # Allow SSL default context (safer) and configurable timeout
        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout, context=ctx) as resp:
                body = resp.read().decode("utf-8")
                obj = json.loads(body)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
            raise RuntimeError(f"AIService HTTPError {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"AIService URLError: {e.reason}") from e
        except Exception as e:
            raise RuntimeError(f"AIService unexpected error: {type(e).__name__}: {e}") from e

        # OpenAI-compatible: choices[0].message.content
        try:
            return obj["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"AIService unexpected response schema: {obj}") from e

    @staticmethod
    def _style_hint(style: str) -> str:
        s = (style or "google").lower()
        if s in ("google", "google-style", "google docstring"):
            return "Google style"
        if s in ("numpy", "numpydoc", "numpy-style"):
            return "NumPy style"
        if s in ("rst", "restructuredtext", "sphinx"):
            return "reStructuredText (Sphinx) style"
        if s in ("pep257", "pep-257"):
            return "PEP 257 compliant style"
        return "Google style"

    def generate_docstring(
        self,
        code: str,
        signature: str,
        style: str = "google",
        language: str = "en",
    ) -> str:
        """
        Generate a docstring for a function/method given its code and signature.
        - style: google | numpy | rst | pep257
        - language: 'en' or 'zh' (docstring language preference)
        """
        style_hint = self._style_hint(style)
        sys_prompt = (
            "You are an expert Python documentation writer. "
            "Given a function signature and its implementation code, "
            f"produce a complete {style_hint} docstring. "
            "Include a concise summary, detailed parameter descriptions, return value, "
            "raises (if applicable), examples (optional). "
            "Do not include the function definition itself; only output the docstring content. "
        )
        if language == "zh":
            sys_prompt += "请使用专业、清晰的中文撰写文档字符串。"
        else:
            sys_prompt += "Write in clear and professional English."

        user_msg = f"""Function Signature:
```
{signature}
```

Implementation Code:
```python
{code}
```
"""

        content = self._chat(
            messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_msg}],
            temperature=0.2,
        )
        return content.strip()

    def improve_docstring(
        self,
        code: str,
        existing_docstring: str,
        style: str = "google",
        language: str = "en",
    ) -> str:
        """
        Improve an existing docstring to match target style and enhance clarity/completeness.
        """
        style_hint = self._style_hint(style)
        sys_prompt = (
            "You are an expert Python documentation reviewer. "
            f"Rewrite and improve the given docstring to conform to {style_hint}. "
            "Ensure clarity, completeness, parameter/return/raises coverage, and consistent formatting. "
            "Output only the improved docstring content."
        )
        if language == "zh":
            sys_prompt += " 请使用专业、清晰的中文撰写文档字符串。"
        else:
            sys_prompt += " Write in clear and professional English."

        user_msg = f"""Existing Docstring:
```
{existing_docstring}
```

Associated Implementation Code (for context):
```python
{code}
```
"""

        content = self._chat(
            messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_msg}],
            temperature=0.2,
        )
        return content.strip()


def get_ai_service() -> AIService:
    """
    Helper to get a configured AIService instance.
    Raises RuntimeError if not configured.
    """
    return AIService(AIServiceConfig.from_env())


# Quick self test (optional)
if __name__ == "__main__":
    try:
        svc = get_ai_service()
        demo_code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        doc = svc.generate_docstring(code=demo_code, signature="add(a: int, b: int) -> int", style="google", language="en")
        print("Generated docstring:\n", doc)
    except Exception as e:
        print("AIService test failed:", e)