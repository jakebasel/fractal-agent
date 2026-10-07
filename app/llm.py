"""OpenRouter calls: a cheap vision model reads the chart, DeepSeek decides and writes lessons."""
import base64
import json
import re

import httpx

from . import config


class LLMError(RuntimeError):
    pass


def _post(model: str, messages: list, max_tokens: int = 1500, temperature: float = 0.1) -> str:
    if not config.OPENROUTER_API_KEY:
        raise LLMError("OPENROUTER_API_KEY is not set")
    body = {"model": model, "messages": messages, "max_tokens": max_tokens,
            "temperature": temperature}
    r = httpx.post(config.OPENROUTER_URL, json=body, timeout=config.LLM_TIMEOUT_S, headers={
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://fvg.motivationpro.tech",
        "X-Title": "fractal-agent",
    })
    if r.status_code >= 400:
        raise LLMError(f"{model}: HTTP {r.status_code} {r.text[:300]}")
    data = r.json()
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as e:
        raise LLMError(f"{model}: unexpected reply {str(data)[:300]}") from e


def parse_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply (tolerates ```json fences / prose)."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    raw = m.group(1) if m else text
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise LLMError(f"no JSON in reply: {text[:300]}")
    return json.loads(raw[start:end + 1])


def read_chart(image_bytes: bytes, prompt: str, mime: str = "image/jpeg") -> dict:
    b64 = base64.b64encode(image_bytes).decode()
    messages = [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
    ]}]
    return parse_json(_post(config.VISION_MODEL, messages, max_tokens=1800))


def decide(system: str, user: str) -> dict:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    return parse_json(_post(config.DECISION_MODEL, messages, max_tokens=1500))
