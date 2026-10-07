"""OpenRouter calls: a cheap vision model reads the chart, DeepSeek decides and writes lessons,
Jev (System One) scores each rule. Every call is logged with its cost (store.api_calls)."""
import base64
import json
import re
import time

import httpx

from . import config


class LLMError(RuntimeError):
    pass


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://fvg.motivationpro.tech", "X-Title": "fractal-agent"}


def _log(purpose, model, usage, ms, ok, err=None):
    from . import store   # late import: store imports config only
    u = usage or {}
    try:
        store.log_api_call(purpose, model, u.get("prompt_tokens", u.get("input_tokens")),
                           u.get("completion_tokens", u.get("output_tokens")), u.get("cost"),
                           ms, ok, err)
    except Exception:
        pass   # spend logging must never break a decision


def _post(model: str, messages: list, max_tokens: int = 1500, temperature: float = 0.1,
          purpose: str = "other") -> str:
    if not config.OPENROUTER_API_KEY:
        raise LLMError("OPENROUTER_API_KEY is not set")
    body = {"model": model, "messages": messages, "max_tokens": max_tokens,
            "temperature": temperature, "usage": {"include": True}}
    if model == config.DECISION_MODEL:
        if config.DECISION_FALLBACK_MODELS:
            body["models"] = [model] + config.DECISION_FALLBACK_MODELS   # OpenRouter model routing
        if config.DECISION_REASONING:
            body["reasoning"] = config.DECISION_REASONING
        body["response_format"] = {"type": "json_object"}   # every decision-model prompt wants one object
    t0 = time.time()
    try:
        r = httpx.post(config.OPENROUTER_URL, json=body, timeout=config.LLM_TIMEOUT_S,
                       headers=_headers())
    except httpx.HTTPError as e:
        _log(purpose, model, None, int((time.time() - t0) * 1000), False, str(e)[:200])
        raise LLMError(f"{model}: {e}") from e
    ms = int((time.time() - t0) * 1000)
    if r.status_code >= 400:
        _log(purpose, model, None, ms, False, f"HTTP {r.status_code}")
        raise LLMError(f"{model}: HTTP {r.status_code} {r.text[:300]}")
    data = r.json()
    _log(purpose, data.get("model") or model, data.get("usage"), ms, True)   # the model that answered
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"{model}: unexpected reply {str(data)[:300]}") from e
    content = msg.get("content") or ""
    if not content.strip():
        # reasoning models can spend the whole budget thinking, or put the answer in the
        # reasoning field; take whatever carries a JSON object
        for alt in (msg.get("reasoning"), msg.get("reasoning_content")):
            if isinstance(alt, str) and "{" in alt:
                content = alt
                break
    if not content.strip():
        fin = (data["choices"][0].get("finish_reason") or "")
        raise LLMError(f"{model}: empty reply (finish_reason={fin}, usage={data.get('usage')})")
    return content


def parse_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply: tolerates ```json fences, <think>
    blocks, prose before and after, and trailing text with braces in it."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    raw = m.group(1) if m else text
    dec = json.JSONDecoder()
    pos = raw.find("{")
    last_err = None
    while pos >= 0:
        try:
            obj, _ = dec.raw_decode(raw, pos)   # first complete object; ignores what follows
            if isinstance(obj, dict):
                return obj
        except ValueError as e:
            last_err = e
        pos = raw.find("{", pos + 1)
    raise LLMError(f"no JSON in reply ({last_err}): {text[:300]}")


def _mime(b: bytes) -> str:
    return "image/png" if b[:4] == b"\x89PNG" else "image/jpeg"


def read_chart(images, prompt: str) -> dict:
    """images: one bytes object or a list of them (one per TradingView window)."""
    if isinstance(images, (bytes, bytearray)):
        images = [images]
    content = [{"type": "text", "text": prompt}]
    for b in images:
        content.append({"type": "image_url", "image_url": {
            "url": f"data:{_mime(b)};base64,{base64.b64encode(b).decode()}"}})
    return parse_json(_post(config.VISION_MODEL, [{"role": "user", "content": content}],
                            max_tokens=2500, purpose="vision"))


def decide(system: str, user: str, purpose: str = "decision") -> dict:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    return parse_json(_post(config.DECISION_MODEL, messages, max_tokens=config.DECISION_MAX_TOKENS,
                            purpose=purpose))


def system_one(state, questions: dict, purpose: str = "jev") -> dict:
    """Jev via OpenRouter's /systemone endpoint. Returns the `answers` map."""
    if not config.OPENROUTER_API_KEY:
        raise LLMError("OPENROUTER_API_KEY is not set")
    body = {"model": config.JEV_MODEL, "state": state, "questions": questions}
    t0 = time.time()
    try:
        r = httpx.post(config.JEV_URL, json=body, timeout=config.JEV_TIMEOUT_S, headers=_headers())
    except httpx.HTTPError as e:
        _log(purpose, config.JEV_MODEL, None, int((time.time() - t0) * 1000), False, str(e)[:200])
        raise LLMError(f"jev: {e}") from e
    ms = int((time.time() - t0) * 1000)
    if r.status_code >= 400:
        _log(purpose, config.JEV_MODEL, None, ms, False, f"HTTP {r.status_code}")
        raise LLMError(f"jev: HTTP {r.status_code} {r.text[:300]}")
    data = r.json()
    _log(purpose, config.JEV_MODEL, data.get("usage"), ms, True)
    return {"answers": data.get("answers") or {}, "model": data.get("model"), "ms": ms}
