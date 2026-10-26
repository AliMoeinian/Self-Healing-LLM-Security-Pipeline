"""Small Mistral HTTPS transport; credentials never enter serialized artifacts."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, time as clock, timedelta, timezone

from .core import MODELS, canonical, fingerprint

MODELS_URL = "https://api.mistral.ai/v1/models"
CHAT_URL = "https://api.mistral.ai/v1/chat/completions"


class TransportError(RuntimeError):
    """Safe, deliberately sanitized error suitable for a run artifact."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward an Authorization header to another host.


def key_value(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise TransportError(f"Credential variable is missing or empty: {name}")
    return value


def make_opener():
    # Uses the platform proxy and default certificate verification. No TLS or
    # certificate bypass, alternative endpoint, or proxy bypass is supported.
    return urllib.request.build_opener(NoRedirect())


def check_connections(config: dict, opener=None) -> list[dict]:
    opener = opener or make_opener()
    checks = []
    for variable in dict.fromkeys(config["key_by_agent"].values()):
        row = {"credential_variable": variable, "success": False}
        try:
            request = urllib.request.Request(MODELS_URL, headers={"Authorization": "Bearer " + key_value(variable), "Accept": "application/json"})
            with opener.open(request, timeout=config["request_timeout_seconds"]) as response:
                body = json.load(response)
                models = {m["id"] for m in body["data"]}
                row.update(http_status=response.status, available_models={m: m in models for m in MODELS})
                row["success"] = response.status == 200 and all(m in models for m in MODELS)
        except urllib.error.HTTPError as error:
            row.update(http_status=error.code, error="provider_or_proxy_http_error")
        except urllib.error.URLError:
            row["error"] = "network_or_proxy_connection_failed"
        except (TransportError, ValueError, KeyError, TypeError, OSError):
            row["error"] = "missing_credential_or_invalid_provider_response"
        checks.append(row)
    return checks


class MistralClient:
    backend = "mistral"

    def __init__(self, config: dict, journal, opener=None, sleeper=time.sleep, clock_fn=time.monotonic):
        self.config, self.journal = config, journal
        self.opener = opener or make_opener()
        self.sleep, self.clock = sleeper, clock_fn
        self.attempts = 0
        self.reserved_tokens = 0
        self.last_attempt = None

    def complete(self, payload: dict, key_name: str, call_id: str) -> dict:
        secret = key_value(key_name)
        encoded = canonical(payload)
        # A conservative local accounting unit, not an exact tokenizer or a
        # provider-enforced dollar limit. Every attempted request consumes it.
        reserve = len(encoded) + 1024 + payload["max_tokens"]
        for attempt in range(1, self.config["max_attempts_per_call"] + 1):
            if self.attempts >= self.config["max_http_attempts"] or self.reserved_tokens + reserve > self.config["max_reserved_tokens"]:
                raise TransportError("Local request/token-reservation budget exhausted")
            if self.last_attempt is not None:
                delay = self.config["minimum_request_interval_seconds"] - (self.clock() - self.last_attempt)
                if delay > 0:
                    self.sleep(delay)
            self.attempts += 1
            self.reserved_tokens += reserve
            self.last_attempt = self.clock()
            self.journal({"event": "http_attempt", "call_id": call_id, "attempt": attempt,
                          "credential_variable": key_name, "request_sha256": fingerprint(payload),
                          "reserved_token_units": reserve})
            request = urllib.request.Request(CHAT_URL, data=encoded, method="POST", headers={
                "Authorization": "Bearer " + secret, "Content-Type": "application/json", "Accept": "application/json"})
            try:
                with self.opener.open(request, timeout=self.config["request_timeout_seconds"]) as response:
                    value = json.load(response)
                result = self.normalize(value)
                self.journal({"event": "http_success", "call_id": call_id, "attempt": attempt,
                              "usage": result["usage"], "reported_model": result["reported_model"]})
                return result
            except urllib.error.HTTPError as error:
                status = error.code
                self.journal({"event": "http_error", "call_id": call_id, "attempt": attempt, "status": status})
                if status in (429, 500, 502, 503, 504) and attempt < self.config["max_attempts_per_call"]:
                    retry_after = error.headers.get("Retry-After", "1") if error.headers else "1"
                    try:
                        delay = max(1.0, float(retry_after))
                    except (TypeError, ValueError):
                        delay = 2.0
                    if delay <= 10:
                        self.sleep(delay)
                        continue  # SAME key; never route around account limits.
                raise TransportError(f"Mistral HTTP request failed with status {status}") from None
            except (urllib.error.URLError, TimeoutError, OSError):
                # A timeout may already have been billed. Do not automatically
                # duplicate an ambiguous request or switch credentials.
                self.journal({"event": "connection_error", "call_id": call_id, "attempt": attempt})
                raise TransportError("Mistral connection failed; no credential failover attempted") from None
            except (ValueError, KeyError, TypeError, IndexError):
                self.journal({"event": "invalid_provider_response", "call_id": call_id, "attempt": attempt})
                raise TransportError("Invalid Mistral response; usage or output could not be verified") from None
        raise TransportError("Request attempt limit reached")

    @staticmethod
    def normalize(value: dict) -> dict:
        if len(value["choices"]) != 1:
            raise ValueError("Expected one completion")
        choice = value["choices"][0]
        content = choice["message"]["content"]
        if not isinstance(content, str) or not isinstance(value["model"], str):
            raise ValueError("Expected text and model identity")
        usage = value["usage"]
        for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if type(usage[name]) is not int or usage[name] < 0:
                raise ValueError("Missing or invalid usage")
        if usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]:
            raise ValueError("Inconsistent usage")
        return {"content": content, "finish_reason": choice["finish_reason"],
                "reported_model": value["model"], "response_id": value.get("id"),
                "usage": {k: usage[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens")}}


class ScriptedClient:
    """Deterministic availability-sharing reference, NOT a simulated LLM result."""

    backend = "scripted-reference"

    def complete(self, payload: dict, key_name: str, call_id: str) -> dict:
        messages = payload["messages"]
        view = json.loads(messages[1]["content"])
        public, own = view["public"], view["own_calendar"]
        available = []
        for day in public["working_dates"]:
            start = datetime.combine(datetime.fromisoformat(day).date(), clock(9), timezone.utc)
            end_of_day = start + timedelta(hours=8)
            while start + timedelta(hours=2) <= end_of_day:
                end = start + timedelta(hours=2)
                if not any(start < datetime.fromisoformat(e["end"]) and datetime.fromisoformat(e["start"]) < end for e in own["events"]):
                    available.append(start.isoformat())
                start += timedelta(minutes=30)
        phase = json.loads(messages[-1]["content"])["phase"]
        if phase in ("publish", "propose", "acknowledge"):
            control = json.loads(messages[-1]["content"])
            content = json.dumps({"message": "Scheduling control action confirmed.",
                                  "action": control["expected_action_schema"]["action"]})
            return {"content": content, "finish_reason": "stop", "reported_model": self.backend,
                    "response_id": None, "usage": None}
        decision = None
        if phase == "final":
            by_peer = {}
            for message in messages[2:]:
                if message["role"] == "user":
                    for item in json.loads(message["content"])["incoming_messages"]:
                        by_peer[item["from"]] = set(json.loads(item["content"])["available_starts"])
            if set(by_peer) != set(public["agent_ids"]) - {view["agent_id"]}:
                raise ValueError("Reference agent lacks peer messages")
            common = set(available).intersection(*by_peer.values())
            if common:
                chosen = min(common)
                decision = {"status": "scheduled", "start": chosen,
                            "end": (datetime.fromisoformat(chosen) + timedelta(hours=2)).isoformat()}
            else:
                decision = {"status": "no_common_slot", "start": None, "end": None}
        content = json.dumps({"message": json.dumps({"available_starts": available}), "decision": decision})
        return {"content": content, "finish_reason": "stop", "reported_model": self.backend,
                "response_id": None, "usage": None}
