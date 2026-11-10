"""Bounded requests to the organizer-configured proxy. No external search."""
from __future__ import annotations
import json
import os
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler


class ProviderError(RuntimeError):
    pass


def env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value and value != name:
            return value
    return default


def integer(name: str, default: int, low: int, high: int) -> int:
    try:
        return min(high, max(low, int(env(name, default=str(default)))))
    except ValueError:
        return default


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError("redirect_not_allowed")


class ProxyClient:
    def __init__(self, deadline: float):
        self.base = env("LLM_BASE_URL", "OPENAI_BASE_URL").rstrip("/")
        self.key = env("LLM_API_KEY", "OPENAI_API_KEY")
        self.model = env("LLM_MODEL", "OPENAI_MODEL", "GEN_MODEL")
        self.deadline = deadline
        parsed = urlparse(self.base)
        if not self.key or not self.model or parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ProviderError("missing_proxy_configuration")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ProviderError("invalid_proxy_url")
        self.opener = build_opener(NoRedirect())
        self.calls = 0

    def complete(self, system: str, payload: dict) -> dict:
        self.calls += 1
        if self.calls > 4:
            raise ProviderError("question_call_budget")
        try:
            temperature = min(2., max(0., float(env("TEMPERATURE", default="0"))))
        except ValueError:
            temperature = 0.
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            "temperature": temperature,
            "max_tokens": integer("MAX_TOKENS", 2000, 256, 8192),
        }, ensure_ascii=False).encode()
        for attempt in range(3):
            remaining = self.deadline - time.monotonic()
            if remaining <= 1:
                raise ProviderError("run_deadline")
            request = Request(self.base + "/chat/completions", data=body, method="POST",
                              headers={"Authorization": "Bearer " + self.key,
                                       "Content-Type": "application/json"})
            delay = 1 + attempt
            try:
                with self.opener.open(request, timeout=min(45., remaining)) as response:
                    raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ProviderError("response_size_limit")
                result = json.loads(raw)
                choice = result["choices"][0]
                if choice.get("finish_reason") == "length":
                    raise ProviderError("truncated_model_output")
                content = choice["message"]["content"].strip()
                if content.startswith("```") and content.endswith("```"):
                    content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                value = json.loads(content)
                if not isinstance(value, dict):
                    raise ValueError("expected_object")
                return value
            except HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504}:
                    raise ProviderError("http_" + str(exc.code)) from None
                retry = exc.headers.get("Retry-After", "")
                if retry.isdigit():
                    delay = min(30, int(retry))
            except (URLError, socket.timeout, TimeoutError):
                pass
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                raise ProviderError("invalid_model_response") from None
            if attempt == 2:
                break
            remaining = self.deadline - time.monotonic()
            if remaining <= delay + 1:
                raise ProviderError("run_deadline")
            time.sleep(delay)
        raise ProviderError("proxy_unavailable")
