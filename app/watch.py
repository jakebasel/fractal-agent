"""Watch layer (2026-10-22): zone / level / chart warnings. Code only, no model call.

Jake: "we should receive warnings about a new day opening gap or blue zones above us",
"warnings for trades that are too close to a particular zone that we're looking to take profit
in", and "if we don't think price could break through a zone, e.g. blue or purple, I would
want to know that". We watch the MIDPOINTS of the NDOG, the NWOG and the 4H FVGs.

Every WATCH_SECONDS the rules run over
  - fvg-mcp `context(symbol)`: computed levels on EVERY tracked symbol (ndog / nwog / 4H and
    daily FVGs with their CE, prior session H/L/C) -- source "data", exact;
  - the stored chart read (app/chartstate.py) on the charted symbols: blue / purple zones with
    their shade, DSD, reversal zones, white lines, the indicator's HTF chips -- source "chart",
    only as good as the vision read;
  - the engine's armed setups (setups snapshot), the agent's open paper trades and the newest
    engine entries board-wide, each with entry / stop / target.

Warnings (table `warnings`, pushed to the Telegram chat, deduped by key inside WATCH_COOLDOWN_MIN):
  new_gap              a new day / new week opening gap printed (once per gap)
  level_near           price is within WATCH_NEAR_PCT of a level's midpoint / a zone's edge
  target_blocked       a trade's path hits a zone / level before WATCH_MIN_R_CLEAR R (the 2R partial)
  zone_against         a STRONG zone (dark blue / dark purple, DSD, an HTF gap against the trade, a
                       reversal zone) sits between the partial and the 3R target: price may not get through
  line_closed          a body closed through a white M / DB line (chart diff)
  reversal_zone_tapped a reversal zone was tapped (chart diff)
Nothing here places, sizes or exits a trade. Paper only.
"""
import logging
import time
from datetime import datetime, timezone

from . import chartstate, config, rules_code, store

log = logging.getLogger("watch")
_last = {"at": 0.0}
_ctx_cache: dict = {}     # symbol -> (ts, ctx)
STRONG_ZONES = {"dark_blue", "maroon"}
ZONE_NAMES = {"purple": "purple zone", "maroon": "dark purple zone", "blue": "blue zone",
              "dark_blue": "dark blue zone", "ndog": "NDOG (chart)", "nwog": "NWOG (chart)",
              "opening_fvg": "opening FVG", "dsd_high": "DSD high", "dsd_low": "DSD low"}
LEVEL_NAMES = {"ndog": "new day opening gap", "nwog": "new week opening gap", "fvg_4h": "4H FVG",
               "fvg_1d": "daily FVG", "pdh": "prior day high", "pdl": "prior day low", "pdc": "prior day close"}


def _num(x):
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def _fmt(x):
    if x is None:
        return "?"
    return f"{x:,.2f}".rstrip("0").rstrip(".") if abs(x) < 1000 else f"{x:,.1f}".rstrip("0").rstrip(".")


# ---- obstacles -------------------------------------------------------------------------------

def obstacles_from(ctx: dict | None, panels: list, price: float | None) -> list:
    """One flat list of levels around the price: {name, kind, top, bottom, ce, source, strong,
    dir}. Chart zones that duplicate a computed level (same gap read off the screen) are
    dropped so one gap never warns twice."""
    out = []
    for lv in (ctx or {}).get("levels") or []:
        top, bottom = _num(lv.get("top")), _num(lv.get("bottom"))
        if top is None or bottom is None:
            continue
        kind = lv.get("kind")
        out.append({"name": LEVEL_NAMES.get(kind, kind), "kind": kind, "top": top, "bottom": bottom,
                    "ce": _num(lv.get("ce")) or (top + bottom) / 2, "source": "data",
                    "strong": kind in ("ndog", "nwog", "fvg_4h", "fvg_1d"), "dir": lv.get("dir"),
                    "at": lv.get("at_et")})
    tol = (price or 0) * 0.001
    for p in panels:
        tf = p.get("timeframe") or "?"
        for z in p.get("zones") or []:
            top, bottom = _num(z.get("top")), _num(z.get("bottom"))
            if top is None or bottom is None:
                continue
            if top < bottom:
                top, bottom = bottom, top
            kind = z.get("type") or "zone"
            ce = (top + bottom) / 2
            if kind in ("ndog", "nwog", "opening_fvg") and any(
                    o["source"] == "data" and o["kind"] in ("ndog", "nwog") and abs(o["ce"] - ce) <= max(tol, 0.01)
                    for o in out):
                continue
            strong = kind in STRONG_ZONES or (z.get("shade") == "dark") or kind.startswith("dsd")
            name = ZONE_NAMES.get(kind, kind)
            if z.get("shade") == "dark" and kind in ("blue", "purple"):
                name = "dark " + name
            out.append({"name": name, "kind": "zone_" + kind, "top": top, "bottom": bottom, "ce": ce,
                        "source": "chart", "strong": strong, "dir": None, "at": f"{tf} chart"})
        for h in p.get("htf_chips") or []:
            top, bottom = _num(h.get("top")), _num(h.get("bottom"))
            if top is None or bottom is None:
                continue
            ce = _num(h.get("ce")) or (top + bottom) / 2
            if any(o["source"] == "data" and o["kind"] in ("fvg_4h", "fvg_1d") and abs(o["ce"] - ce) <= max(tol, 0.01)
                   for o in out):
                continue
            out.append({"name": f"{h.get('tf')} context gap (chart)", "kind": "chip_" + str(h.get("tf")),
                        "top": max(top, bottom), "bottom": min(top, bottom), "ce": ce, "source": "chart",
                        "strong": True, "dir": None, "at": f"{tf} chart"})
        for rz in p.get("reversal_zones") or []:
            top, bottom = _num(rz.get("top")), _num(rz.get("bottom"))
            if top is None or bottom is None:
                continue
            out.append({"name": f"{rz.get('color') or ''} reversal zone".strip(), "kind": "reversal_zone",
                        "top": max(top, bottom), "bottom": min(top, bottom), "ce": (top + bottom) / 2,
                        "source": "chart", "strong": True, "dir": None, "at": f"{tf} chart"})
        dsd = p.get("dsd") or {}
        for k in ("high", "low"):
            v = _num(dsd.get(k))
            if v is not None and not any(o["kind"] == f"zone_dsd_{k}" for o in out):
                out.append({"name": f"DSD {k}", "kind": f"dsd_{k}", "top": v, "bottom": v, "ce": v,
                            "source": "chart", "strong": True, "dir": None, "at": f"{tf} chart"})
    return out


def _against(o: dict, direction: str) -> bool:
    """An HTF gap the trade would have to trade INTO against its direction."""
    if o["kind"] in ("fvg_4h", "fvg_1d") or o["kind"].startswith("chip_"):
        return (direction == "bull" and o["dir"] == "bear") or (direction == "bear" and o["dir"] == "bull") \
            or o["dir"] is None
    return False


# ---- rules -----------------------------------------------------------------------------------

def check_trade(symbol: str, direction: str, entry, stop, target, obstacles: list, label: str,
                entry_id=None, trade_key: str | None = None) -> list:
    """Warnings for one trade (armed setup, open paper trade or engine entry)."""
    entry, stop, target = _num(entry), _num(stop), _num(target)
    if None in (entry, stop, target) or direction not in ("bull", "bear"):
        return []
    risk = abs(entry - stop)
    if risk <= 0:
        return []
    bull = direction == "bull"
    reach = abs(target - entry) / risk
    out = []
    tk = trade_key or (f"e{entry_id}" if entry_id is not None else f"{label}@{_fmt(entry)}")
    for o in obstacles:
        near = o["bottom"] if bull else o["top"]          # the edge price meets first
        ahead = (near - entry) if bull else (entry - near)
        far = (o["top"] - entry) if bull else (entry - o["bottom"])
        if far <= 0 or ahead > (target - entry if bull else entry - target):
            continue                                        # behind the entry, or past the target
        r_to = max(ahead, 0.0) / risk
        strong = o["strong"] or _against(o, direction)
        side = "long" if bull else "short"
        span = f"{_fmt(o['bottom'])}-{_fmt(o['top'])}" if o["top"] != o["bottom"] else _fmt(o["ce"])
        src = "computed" if o["source"] == "data" else "chart read"
        if r_to < config.WATCH_MIN_R_CLEAR:
            kind, sev = "target_blocked", ("high" if strong else "medium")
            if ahead <= 0:
                where = f"the entry {_fmt(entry)} is already inside it"
            else:
                where = f"only {r_to:.1f}R ahead of the entry {_fmt(entry)}"
            text = (f"{symbol} {side} ({label}): {o['name']} {span} is {where}, before the "
                    f"{config.WATCH_MIN_R_CLEAR:g}R partial (target {_fmt(target)} = {reach:.1f}R). "
                    f"Realistic target is the zone edge at {_fmt(near)}"
                    + (" -- a strong zone, price may not get through." if strong else ".")
                    + f" [{src}]")
        elif strong:
            kind, sev = "zone_against", "medium"
            text = (f"{symbol} {side} ({label}): {o['name']} {span} sits {r_to:.1f}R ahead, between the "
                    f"partial and the {reach:.1f}R target {_fmt(target)}. Price may not get through it; "
                    f"take the partial and treat {_fmt(near)} as the final target unless it breaks. [{src}]")
        else:
            continue
        out.append({"symbol": symbol, "kind": kind, "severity": sev, "source": o["source"],
                    "direction": direction, "level": near, "entry_id": entry_id,
                    "key": f"{symbol}|{kind}|{tk}|{o['kind']}|{_fmt(near)}", "text": text,
                    "detail": {"trade": label, "entry": entry, "stop": stop, "target": target,
                               "obstacle": o, "r_to": round(r_to, 2)}})
    return out


def level_warnings(symbol: str, price, obstacles: list, now_ms: float | None = None) -> list:
    """new_gap (once per gap) and level_near (price within WATCH_NEAR_PCT of a midpoint / edge)."""
    price = _num(price)
    out = []
    if price is None:
        return out
    near_pts = price * config.WATCH_NEAR_PCT / 100.0
    for o in obstacles:
        # the midpoint is the watch point of a gap (Jake 10/22); a zone is watched at its edge
        watch = o["ce"] if o["kind"] in ("ndog", "nwog", "fvg_4h", "fvg_1d") else (
            o["bottom"] if o["bottom"] > price else (o["top"] if o["top"] < price else price))
        pos = "above" if watch > price else ("below" if watch < price else "at")
        dist = abs(watch - price)
        span = f"{_fmt(o['bottom'])}-{_fmt(o['top'])}" if o["top"] != o["bottom"] else _fmt(o["ce"])
        src = "computed" if o["source"] == "data" else "chart read"
        if o["kind"] in ("ndog", "nwog") and o.get("at"):
            out.append({"symbol": symbol, "kind": "new_gap", "severity": "medium", "source": o["source"],
                        "direction": o.get("dir"), "level": o["ce"],
                        "key": f"{symbol}|new_gap|{o['kind']}|{_fmt(o['ce'])}",
                        "text": (f"{symbol}: {o['name']} {span} ({o['dir']}), midpoint {_fmt(o['ce'])} -- "
                                 f"{_fmt(dist)} pts {pos} price {_fmt(price)}. Watch the midpoint. [{src}]"),
                        "detail": {"level": o}, "cooldown_s": 7 * 86400})
        if dist <= near_pts:
            what = "midpoint" if o["kind"] in ("ndog", "nwog", "fvg_4h", "fvg_1d") else "edge"
            out.append({"symbol": symbol, "kind": "level_near", "severity": "medium", "source": o["source"],
                        "direction": None, "level": watch,
                        "key": f"{symbol}|level_near|{o['kind']}|{_fmt(watch)}",
                        "text": (f"{symbol} {_fmt(price)} is {_fmt(dist)} pts {'under' if pos == 'above' else 'over' if pos == 'below' else 'at'} "
                                 f"the {o['name']} {what} {_fmt(watch)} ({span}). [{src}]"),
                        "detail": {"level": o, "price": price}})
    return out


def diff_warnings(symbol: str, prev: list, cur: list) -> list:
    """Chart-only events: a white line body-closed through, a reversal zone tapped."""
    def lines(panels):
        d = {}
        for p in panels:
            for w in p.get("white_lines") or []:
                px = _num(w.get("price"))
                if px is not None:
                    d[(w.get("label"), _fmt(px))] = (w.get("body_closed_through"), p.get("timeframe"), px)
        return d

    def rzones(panels):
        d = {}
        for p in panels:
            for z in p.get("reversal_zones") or []:
                top, bottom = _num(z.get("top")), _num(z.get("bottom"))
                if top is not None and bottom is not None:
                    d[(z.get("color"), _fmt(top), _fmt(bottom))] = (z.get("price_inside_or_tapped"), p.get("timeframe"), top, bottom)
        return d
    out = []
    pl, cl = lines(prev), lines(cur)
    for k, (closed, tf, px) in cl.items():
        if closed is True and pl.get(k, (None,))[0] is not True:
            out.append({"symbol": symbol, "kind": "line_closed", "severity": "medium", "source": "chart",
                        "direction": None, "level": px, "key": f"{symbol}|line_closed|{k[0]}|{k[1]}",
                        "text": f"{symbol} {tf}: a body closed through the {k[0]} line at {_fmt(px)}. [chart read]",
                        "detail": {"line": k[0], "price": px, "tf": tf}})
    pz, cz = rzones(prev), rzones(cur)
    for k, (tapped, tf, top, bottom) in cz.items():
        if tapped is True and pz.get(k, (None,))[0] is not True:
            out.append({"symbol": symbol, "kind": "reversal_zone_tapped", "severity": "medium", "source": "chart",
                        "direction": None, "level": (top + bottom) / 2,
                        "key": f"{symbol}|rz_tapped|{k[0]}|{k[1]}|{k[2]}",
                        "text": f"{symbol} {tf}: price tapped the {k[0]} reversal zone {_fmt(bottom)}-{_fmt(top)}. [chart read]",
                        "detail": {"zone": k, "tf": tf}})
    return out


# ---- the run ---------------------------------------------------------------------------------

def _ctx(fvg, symbol):
    hit = _ctx_cache.get(symbol)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    try:
        ctx = fvg.context(symbol) or {}
    except Exception as e:
        log.warning("context %s: %s", symbol, e)
        ctx = {}
    _ctx_cache[symbol] = (time.time(), ctx)
    return ctx


def _trades_for(symbol: str) -> list:
    """(direction, entry, stop, target, label, entry_id, trade_key) for the armed / ready
    engine setups and the agent's open paper TAKEs on a symbol."""
    out = []
    snap = store.kv_get("setups_snapshot") or {}
    for x in ((snap.get("symbols") or {}).get(symbol) or {}).get("setups") or []:
        if x.get("status") in rules_code.VOID_STATUSES:
            continue
        if x.get("entry") is None or x.get("stop") is None or x.get("target") is None:
            continue
        label = f"{x.get('cascade') or ''} {x.get('mt_tf') or ''} {x.get('mt') or ''} {x.get('status') or ''}".strip()
        out.append((x.get("direction"), x.get("entry"), x.get("stop"), x.get("target"), label, None,
                    f"setup|{x.get('cascade')}|{x.get('mt_tf')}|{_fmt(_num(x.get('entry')))}"))
    for r in store.open_decisions():
        if r["symbol"] == symbol and r["decision"] == "TAKE":
            out.append((r["direction"], r["entry"], r["stop"], r["target"],
                        f"open paper trade #{r['entry_id']}", r["entry_id"], None))
    return out


def _board_entries(fvg) -> list:
    """Newest engine entries board-wide (not the charted symbols), young enough to matter."""
    try:
        rows = fvg.call("entries", limit=config.WATCH_BOARD_ENTRIES) or []
    except Exception as e:
        log.warning("board entries: %s", e)
        return []
    cut = datetime.now(timezone.utc).timestamp() - config.WATCH_ENTRY_MAX_AGE_MIN * 60
    out = []
    for e in rows:
        if e.get("later_entry") or e.get("symbol") in config.SYMBOLS:
            continue
        try:
            at = datetime.fromisoformat(str(e.get("at")).replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            at = cut
        if at < cut:
            continue
        out.append(e)
    return out


def emit(warnings: list) -> list:
    """Store the new ones (key not inside its cooldown) and push them to Telegram in one message."""
    from . import telegram_bot
    fresh = []
    for w in warnings:
        cd = w.get("cooldown_s") or config.WATCH_COOLDOWN_MIN * 60
        if store.warning_recent(w["key"], cd):
            continue
        wid = store.add_warning(w["symbol"], w["kind"], w["key"], w["source"], w["severity"], w["text"],
                                direction=w.get("direction"), level=w.get("level"), entry_id=w.get("entry_id"),
                                detail=w.get("detail"))
        w["id"] = wid
        fresh.append(w)
    if fresh and config.WATCH_NOTIFY and config.TELEGRAM_CHAT_ID:
        text = "Watch:\n\n" + "\n\n".join(("!! " if w["severity"] == "high" else "- ") + w["text"] for w in fresh)
        try:
            telegram_bot.send(config.TELEGRAM_CHAT_ID, text)
            for w in fresh:
                store.mark_warning_sent(w["id"])
        except Exception as e:
            log.warning("telegram push: %s", e)
    return fresh


def run(fvg) -> list:
    found = []
    for sym in config.SYMBOLS:
        ctx = _ctx(fvg, sym)
        panels = chartstate.panels(sym)
        price = _num(ctx.get("last_price"))
        if price is None:
            for p in panels:
                price = _num(p.get("last_price")) or price
        obs = obstacles_from(ctx, panels, price)
        found += level_warnings(sym, price, obs)
        for (d, e, s, t, label, eid, tk) in _trades_for(sym):
            found += check_trade(sym, d, e, s, t, obs, label, eid, tk)
        prev = chartstate.previous_panels(sym)
        if prev and panels:
            found += diff_warnings(sym, prev, panels)
    for e in _board_entries(fvg):
        sym = e["symbol"]
        ctx = _ctx(fvg, sym)
        obs = obstacles_from(ctx, [], _num(ctx.get("last_price")))
        found += check_trade(sym, e.get("direction"), e.get("entry"), e.get("stop"), e.get("target"), obs,
                             f"engine entry #{e.get('id')} {e.get('cascade') or ''} {e.get('mt_tf') or ''} {e.get('mt_text') or ''}".strip(),
                             e.get("id"))
    return emit(found)


def run_if_due(fvg) -> list:
    if config.WATCH_SECONDS <= 0 or time.time() - _last["at"] < config.WATCH_SECONDS:
        return []
    _last["at"] = time.time()
    try:
        return run(fvg)
    except Exception as e:
        log.warning("watch failed: %s", e)
        return []
