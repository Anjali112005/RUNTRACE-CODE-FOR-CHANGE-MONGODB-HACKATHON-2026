"""Optional Gemini integration (server-side only).

Stored events and deterministic findings are never modified by AI output. Answers are
returned to the caller labelled ``source: ai_generated`` and are not persisted.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from ..config import Settings
from ..errors import ApiError

log = logging.getLogger("runtrace.ai")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TRANSIENT_STATUSES = {429, 500, 503}
MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DISCLAIMER = ("AI-generated suggestion based on the recorded run data shown in 'context'. It may be wrong; "
              "treat it as a hypothesis and check it against the stored evidence.")
SYSTEM_PROMPT = (
    "You are RunTrace's debugging assistant. Answer using ONLY the JSON context provided. "
    "Clearly separate what the data shows (observations) from what you suspect (hypotheses). "
    "Do not invent source code, file names or line numbers. If the context is insufficient, say so."
)


class AIService:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self._transport = transport
        self._backoff_seconds = 1.5

    def status(self) -> dict[str, Any]:
        if not self.settings.ai_enabled:
            return {"enabled": False, "model": None,
                    "reason": "GEMINI_API_KEY is not configured on the server. Deterministic analysis remains available."}
        return {"enabled": True, "model": self.settings.gemini_model, "reason": None}

    @staticmethod
    def _provider_message(response: httpx.Response) -> str:
        try:
            return str(response.json().get("error", {}).get("message", ""))[:300]
        except ValueError:
            return response.text[:300]

    def available_models(self) -> list[str]:
        """Model IDs this key can call with generateContent (best effort; [] on any error)."""
        try:
            with httpx.Client(timeout=10, transport=self._transport) as client:
                response = client.get(MODELS_URL, headers={"x-goog-api-key": self.settings.gemini_api_key or ""},
                                      params={"pageSize": 200})
            models = response.json().get("models", []) if response.status_code == 200 else []
        except (httpx.HTTPError, ValueError):
            return []
        names = [m.get("name", "").removeprefix("models/") for m in models
                 if "generateContent" in (m.get("supportedGenerationMethods") or [])]
        flash = [n for n in names if "flash" in n]
        return (flash or names)[:12]

    def _post(self, client: httpx.Client, model: str, body: dict[str, Any]) -> httpx.Response:
        return client.post(GEMINI_URL.format(model=model),
                           headers={"x-goog-api-key": self.settings.gemini_api_key or "", "Content-Type": "application/json"},
                           json=body)

    def _generate(self, models: list[str], body: dict[str, Any]) -> tuple[httpx.Response, str]:
        """Call Gemini; retry transient overload (429/500/503) once with backoff, then try fallback models.
        Raises ApiError with the provider's message if every model fails."""
        last: httpx.Response | None = None
        last_model = models[0]
        timed_out: list[str] = []
        try:
            with httpx.Client(timeout=self.settings.gemini_timeout_seconds, transport=self._transport) as client:
                for index, model in enumerate(models):
                    for attempt in range(2):
                        try:
                            response = self._post(client, model, body)
                        except httpx.TimeoutException:
                            timed_out.append(model)
                            log.warning("Gemini model %s timed out after %ss; trying the next model",
                                        model, self.settings.gemini_timeout_seconds)
                            break  # a slow model: move on to the next (usually lighter) model

                        last, last_model = response, model
                        if response.status_code < 400:
                            if index > 0:
                                log.info("Gemini primary model busy; answered with fallback model %s", model)
                            return response, model
                        if response.status_code not in TRANSIENT_STATUSES:
                            break
                        if attempt == 0:
                            time.sleep(self._backoff_seconds)
                    if (last is not None and last_model == model and last.status_code not in TRANSIENT_STATUSES
                            and index == 0):
                        break  # a real error on the primary model (bad key, bad model...): report it
        except httpx.TimeoutException as exc:
            raise ApiError(504, "ai_timeout", "The AI provider did not respond in time.") from exc
        except httpx.HTTPError as exc:
            log.warning("Gemini request failed: %s", type(exc).__name__)
            raise ApiError(502, "ai_unavailable", "Could not reach the AI provider.") from exc
        if last is None or (timed_out and timed_out[-1] == models[-1]):
            raise ApiError(504, "ai_timeout",
                           f"Gemini did not answer within {self.settings.gemini_timeout_seconds:.0f}s "
                           f"(tried: {', '.join(models)}). Try again, or raise GEMINI_TIMEOUT_SECONDS in backend/.env.",
                           {"timed_out_models": timed_out})
        self._raise_for_status(last, last_model, tried=models)
        return last, last_model  # pragma: no cover

    def _raise_for_status(self, response: httpx.Response, model: str, tried: list[str]) -> None:
        provider_msg = self._provider_message(response)
        log.warning("Gemini returned HTTP %s for %s: %s", response.status_code, model, provider_msg)
        if response.status_code == 404:
            available = self.available_models()
            hint = (f" Models available to this key: {', '.join(available)}." if available
                    else " List the models your key can use and set GEMINI_MODEL accordingly.")
            raise ApiError(502, "ai_model_not_found",
                           f"Gemini model '{model}' was not found. Set GEMINI_MODEL in backend/.env to a current "
                           f"model and restart.{hint}", {"available_models": available, "provider_message": provider_msg})
        if response.status_code in TRANSIENT_STATUSES:
            raise ApiError(503, "ai_busy",
                           f"Gemini is temporarily overloaded (tried: {', '.join(tried)}). Please try again in a "
                           f"minute. Deterministic analysis is unaffected. Provider said: {provider_msg}",
                           {"tried_models": tried, "provider_status": response.status_code},
                           headers={"Retry-After": "30"})
        raise ApiError(502, "ai_error", f"The AI provider returned HTTP {response.status_code}: {provider_msg}")

    def chat(self, question: str, context: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.ai_enabled:
            raise ApiError(503, "ai_disabled", "AI assistance is disabled: GEMINI_API_KEY is not set on the server.")
        context_json = json.dumps(context, default=str)[:20_000]
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": f"Context (JSON):\n{context_json}\n\nQuestion: {question}"}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024},
        }
        models = [self.settings.gemini_model] + [m for m in self.settings.gemini_fallback_models
                                                 if m and m != self.settings.gemini_model]
        response, used_model = self._generate(models, body)
        try:
            data = response.json()
            parts = data["candidates"][0]["content"]["parts"]
            answer = "".join(p.get("text", "") for p in parts).strip()
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ApiError(502, "ai_bad_response", "The AI provider returned an unexpected response.") from exc
        return {"source": "ai_generated", "model": used_model, "answer": answer or "(empty response)",
                "context": {k: (v if k != "events" else f"{len(v)} events") for k, v in context.items()},
                "disclaimer": DISCLAIMER}