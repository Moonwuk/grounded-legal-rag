"""Bounded requests to the organizer-configured proxy. No external search."""
from __future__ import annotations
import json
import os
import socket
import sys
import time
from http.client import HTTPException
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


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("nonfinite_json_number")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


# Logical model calls per question. The policy plans its attempts within it.
QUESTION_CALL_LIMIT = 4


# Reasoning effort: measured on deepseek-flash, "low" kept accuracy on the demo
# and the synthetic holdout and roughly halved the time. "default" omits the
# parameter. A truncated reply whose reasoning used the token budget is retried
# at "low" when a higher level was used; a provider that rejects the parameter is retried without it,
# and the parameter is not sent again in this run.
EFFORTS = ("none", "low", "high", "max")
DEFAULT_EFFORT = "low"
# Never "none": on the demo it gave false refusals in generation, and as a
# truncation retry it rejected a supported provision in verification (matrix
# 5502269, question 5, both runs). A weak verifier is unsafe either way.
LOWER_EFFORT = {None: "low", "max": "low", "high": "low"}
REASONING_BUDGET_SHARE = 0.8


class ProxyClient:
    effort_rejected = False

    def __init__(self, deadline: float, position: int | None = None):
        self.base = env("LLM_BASE_URL", "OPENAI_BASE_URL", "BASE_URL").rstrip("/")
        self.key = env("LLM_API_KEY", "OPENAI_API_KEY")
        self.model = env("LLM_MODEL", "OPENAI_MODEL", "GEN_MODEL")
        self.deadline = deadline
        self.position = position if type(position) is int and 0 <= position <= 50000 else None
        parsed = urlparse(self.base)
        if not self.key or not self.model or parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ProviderError("missing_proxy_configuration")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ProviderError("invalid_proxy_url")
        if len(self.base) > 2048 or len(self.model) > 256 or any(ord(c) < 32 for c in self.base + self.key + self.model):
            raise ProviderError("invalid_proxy_configuration")
        self.opener = build_opener(NoRedirect())
        self.calls = 0

    def complete(self, system: str, payload: dict) -> dict:
        self.calls += 1
        if self.calls > QUESTION_CALL_LIMIT:
            raise ProviderError("question_call_budget")
        try:
            temperature = min(2., max(0., float(env("TEMPERATURE", default="0"))))
        except ValueError:
            temperature = 0.
        request_body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            "temperature": temperature,
            "max_tokens": integer("MAX_TOKENS", 8192, 256, 65536),
        }
        effort = env("LLM_REASONING_EFFORT", default=DEFAULT_EFFORT)
        if effort != "default" and effort not in EFFORTS:
            raise ProviderError("invalid_reasoning_configuration")
        if effort in EFFORTS and not ProxyClient.effort_rejected:
            request_body["reasoning_effort"] = effort
        body = json.dumps(request_body, ensure_ascii=False).encode()
        if len(body) > 512000:
            raise ProviderError("request_size_limit")
        truncation_retry = False
        effort_dropped = False
        for attempt in range(3):
            remaining = self.deadline - time.monotonic()
            if remaining <= 1:
                raise ProviderError("run_deadline")
            request = Request(self.base + "/chat/completions", data=body, method="POST",
                              headers={"Authorization": "Bearer " + self.key,
                                       "Content-Type": "application/json"})
            delay = 1 + attempt
            request_started = time.monotonic()
            try:
                with self.opener.open(request, timeout=min(45., remaining)) as response:
                    chunks, size = [], 0
                    while True:
                        if time.monotonic() >= self.deadline:
                            raise ProviderError("run_deadline")
                        chunk = response.read1(min(65536, 2_000_001 - size))
                        if not chunk:
                            break
                        chunks.append(chunk)
                        size += len(chunk)
                        if size > 2_000_000:
                            raise ProviderError("response_size_limit")
                result = strict_json(b"".join(chunks))
                choice = result["choices"][0]
                finish = choice.get("finish_reason")
                event = {"event":"model_response", "stage":"verify" if "candidate" in payload else "generate",
                         "attempt":attempt + 1, "position":self.position, "logical_call":self.calls, "finish":finish if finish in {"stop","length"} else "other",
                         "max_tokens":request_body["max_tokens"]}
                usage = result.get("usage")
                if isinstance(usage,dict):
                    count = usage.get("completion_tokens")
                    if type(count) is int and 0 <= count <= 1000000000:
                        event["completion_tokens"] = count
                    detail = usage.get("completion_tokens_details")
                    if isinstance(detail,dict):
                        count = detail.get("reasoning_tokens")
                        if type(count) is int and 0 <= count <= 1000000000:
                            event["reasoning_tokens"] = count
                print(json.dumps(event), file=sys.stderr)
                if finish == "length":
                    # Never parse or publish a truncated candidate. One bounded
                    # fresh attempt shares the three-attempt transport budget.
                    if not truncation_retry and attempt < 2:
                        truncation_retry = True
                        # Reasoning that used the budget is not shortened by an
                        # instruction about the answer; the effort level is.
                        # Without usage details: every visible token is at least one
                        # character, so a short visible text means hidden reasoning.
                        message = choice.get("message")
                        visible = message.get("content") if isinstance(message, dict) else None
                        budget = request_body["max_tokens"]
                        spent = event.get("reasoning_tokens")
                        hidden = (spent >= REASONING_BUDGET_SHARE * budget if spent is not None
                                  else len(visible if isinstance(visible, str) else "") < budget / 2)
                        lower = LOWER_EFFORT.get(request_body.get("reasoning_effort"))
                        if lower and not ProxyClient.effort_rejected and hidden:
                            request_body["reasoning_effort"] = lower
                        request_body["messages"][0]["content"] += (
                            "\nПовтор после обрезки: верни только минимальный JSON по заданной схеме, "
                            "без пояснений, без повторения контекста. Сохрани необходимые условия.")
                        body = json.dumps(request_body, ensure_ascii=False).encode()
                        if len(body) > 512000:
                            raise ProviderError("request_size_limit")
                        continue
                    raise ProviderError("truncated_model_output")
                if choice.get("finish_reason") != "stop":
                    raise ProviderError("unsupported_model_finish")
                content = choice["message"]["content"].strip()
                if content.startswith("```") and content.endswith("```"):
                    content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                value = strict_json(content)
                if not isinstance(value, dict):
                    raise ValueError("expected_object")
                if effort_dropped:
                    # Only a success without the parameter shows that it was the cause.
                    ProxyClient.effort_rejected = True
                return value
            except HTTPError as exc:
                code = exc.code
                print(json.dumps({"event":"provider_failure", "stage":"verify" if "candidate" in payload else "generate",
                    "position":self.position, "logical_call":self.calls, "attempt":attempt + 1,
                    "kind":"http_" + str(code) if type(code) is int and 100 <= code <= 599 else "http_other",
                    "elapsed_ms":round((time.monotonic() - request_started) * 1000)}), file=sys.stderr)
                retry = exc.headers.get("Retry-After", "")
                exc.close()
                if code in {400, 422} and "reasoning_effort" in request_body and attempt < 2:
                    # The provider may not know the parameter: retry once without
                    # it. Another cause of the error repeats and is reported.
                    effort_dropped = True
                    del request_body["reasoning_effort"]
                    body = json.dumps(request_body, ensure_ascii=False).encode()
                    continue
                if code not in {429, 500, 502, 503, 504}:
                    raise ProviderError("http_" + str(code)) from None
                if len(retry) <= 6 and retry.isascii() and retry.isdigit():
                    delay = min(30, int(retry))
            except (URLError, socket.timeout, TimeoutError, HTTPException, ConnectionError) as error:
                reason = getattr(error, "reason", None)
                kind = "timeout" if isinstance(error, (socket.timeout, TimeoutError)) or isinstance(reason, (socket.timeout, TimeoutError)) else (
                    "connection" if isinstance(error, ConnectionError) else "protocol" if isinstance(error, HTTPException) else "network")
                print(json.dumps({"event":"provider_failure", "stage":"verify" if "candidate" in payload else "generate",
                    "position":self.position, "logical_call":self.calls, "attempt":attempt + 1, "kind":kind,
                    "elapsed_ms":round((time.monotonic() - request_started) * 1000)}), file=sys.stderr)
            except (ValueError, KeyError, IndexError, TypeError, AttributeError, RecursionError):
                raise ProviderError("invalid_model_response") from None
            if attempt == 2:
                break
            remaining = self.deadline - time.monotonic()
            if remaining <= delay + 1:
                raise ProviderError("run_deadline")
            time.sleep(delay)
        raise ProviderError("proxy_unavailable")
