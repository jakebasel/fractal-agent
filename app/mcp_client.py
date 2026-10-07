"""Minimal client for fvg-mcp's MCP endpoint (FastMCP, stateless_http + json_response).

Stateless means every tools/call is a standalone POST; no session handshake is required.
We still accept an SSE-framed reply in case the server setting ever changes.
"""
import itertools
import json

import httpx

from . import config

_ids = itertools.count(1)


class MCPError(RuntimeError):
    pass


def _parse_body(resp: httpx.Response) -> dict:
    ctype = resp.headers.get("content-type", "")
    text = resp.text
    if "text/event-stream" in ctype:
        # take the last "data:" line that holds a JSON-RPC message
        msg = None
        for line in text.splitlines():
            if line.startswith("data:"):
                try:
                    msg = json.loads(line[5:].strip())
                except ValueError:
                    continue
        if msg is None:
            raise MCPError(f"no JSON in SSE reply: {text[:200]}")
        return msg
    return resp.json()


def _unwrap(result: dict):
    """tools/call result -> python value. FastMCP puts JSON in structuredContent and/or
    in content[0].text; lists are wrapped as {"result": [...]} in structuredContent."""
    if result.get("isError"):
        texts = [c.get("text", "") for c in result.get("content", [])]
        raise MCPError("tool error: " + " ".join(texts)[:500])
    sc = result.get("structuredContent")
    if sc is not None:
        if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
            return sc["result"]
        return sc
    content = result.get("content") or []
    if not content:
        return None
    if len(content) == 1:
        txt = content[0].get("text", "")
        try:
            val = json.loads(txt)
        except ValueError:
            return txt
        if isinstance(val, dict) and set(val.keys()) == {"result"}:
            return val["result"]
        return val
    out = []
    for c in content:
        try:
            out.append(json.loads(c.get("text", "")))
        except ValueError:
            out.append(c.get("text", ""))
    return out


class FVG:
    """Read-only wrapper around the fvg-mcp tools the agent needs."""

    def __init__(self, url: str | None = None, client: httpx.Client | None = None):
        self.url = url or config.FVG_MCP_URL
        self.http = client or httpx.Client(timeout=30)

    def call(self, name: str, **arguments):
        payload = {"jsonrpc": "2.0", "id": next(_ids), "method": "tools/call",
                   "params": {"name": name, "arguments": arguments}}
        resp = self.http.post(self.url, json=payload, headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        })
        if resp.status_code >= 400:
            raise MCPError(f"{name}: HTTP {resp.status_code} {resp.text[:200]}")
        msg = _parse_body(resp)
        if "error" in msg:
            raise MCPError(f"{name}: {msg['error']}")
        return _unwrap(msg.get("result") or {})

    # convenience wrappers -------------------------------------------------------------------
    def entries(self, symbol, limit=20):
        return self.call("entries", symbol=symbol, limit=limit) or []

    def setups(self, symbol):
        return self.call("setups", symbol=symbol) or {}

    def confluence(self, symbol, limit_per_source=5):
        return self.call("confluence", symbol=symbol, limit_per_source=limit_per_source) or {}

    def mt_events(self, symbol, limit=12):
        return self.call("recent_events", symbol=symbol, source="market_translator",
                         limit=limit) or []
