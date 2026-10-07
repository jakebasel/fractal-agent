"""Enrich the fvg-mcp ledger with what the live-session rules need, so tools/backtest.py can
test them. No model calls.

Adds per trade:
  news_min      signed minutes from entry to the nearest red-folder (high-importance) USD
                release on the same ET day (negative = before the release); None if none
  news_day      1 if a red-folder USD release falls on that ET day
  db_against_before_min   minutes since the last 5m Double Break AGAINST the trade's direction
                on the same symbol before entry (None = none in the last 6h)
  pair_db_against_before_min   same for the sister index (MNQ<->MES)
  db_against_after_ms     epoch ms of the first 5m DB against the trade after entry (<= 2h)
  v_candles     already in the ledger: 30s candles from the final tap to entry
  managed_r     R if the trade is closed at the opposing 5m DB (instructor's rule), replayed
                on fvg-mcp's archived tape with the same 2R + runner management; None if the
                tape for that day is not available

Inputs:
  --ledger  trade_history export (JSON, {"cols","rows"}) or the saved file
  --signals one JSON-lines file per symbol from fvg-mcp analysis/fetch_signals.py
            (Market Translator rows: received_at, tf, text/raw, direction, symbol)
  --calendar TradingView economic calendar JSON ({"result":[{date, title, importance}]})
  --tape    directory to cache archived_prices per (symbol, day); fetched via the agent's
            MCP client when missing (public, read-only)
Writes --out (enriched ledger with the same {"cols","rows"} shape plus the new columns).

  .venv/bin/python tools/backtest_enrich.py --ledger ledger.json --signals sigs_MNQ1.jsonl sigs_MES1.jsonl \
      --calendar calendar.json --tape tape_cache --out ledger_enriched.json
"""
import argparse
import bisect
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import config, scanner  # noqa: E402

PAIR = {"MNQ1!": "MES1!", "MES1!": "MNQ1!"}


def load_ledger(path):
    raw = Path(path).read_text()
    return json.loads(raw[raw.find("{"):])


def load_signals(paths):
    """{symbol: sorted [(ms, tf, signal, direction)]}"""
    out = {}
    for p in paths:
        for line in Path(p).read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            try:
                raw = json.loads(r.get("raw") or "{}")
            except ValueError:
                raw = {}
            sig = raw.get("signal") or ("DB" if "double break" in (r.get("text") or "").lower() else "M")
            tf = (r.get("tf") or raw.get("tf") or "").lower()
            d = (r.get("direction") or raw.get("direction") or "").upper()
            at = r.get("received_at") or ""
            try:
                ms = int(datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp() * 1000)
            except ValueError:
                continue
            out.setdefault(r.get("symbol"), []).append((ms, tf, sig, d))
    for k in out:
        out[k].sort()
    return out


def load_calendar(path):
    d = json.loads(Path(path).read_text())
    evs = d.get("result", d) if isinstance(d, dict) else d
    out = []
    for e in evs:
        if e.get("importance", 1) < 1:
            continue
        try:
            at = datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        out.append((at, e.get("title")))
    out.sort()
    return out


def db_against(sigs, direction, entry_ms, before_h=6.0, after_h=2.0):
    """(minutes since last opposing 5m DB before entry, ms of first opposing 5m DB after)"""
    against = "DOWN" if direction == "bull" else "UP"
    times = [s[0] for s in sigs]
    i = bisect.bisect_left(times, entry_ms)
    before = None
    for j in range(i - 1, -1, -1):
        ms, tf, sig, d = sigs[j]
        if entry_ms - ms > before_h * 3600_000:
            break
        if tf == "5m" and sig == "DB" and d == against:
            before = round((entry_ms - ms) / 60000, 1)
            break
    after = None
    for j in range(i, len(sigs)):
        ms, tf, sig, d = sigs[j]
        if ms - entry_ms > after_h * 3600_000:
            break
        if tf == "5m" and sig == "DB" and d == against:
            after = ms
            break
    return before, after


def news_for(cal, entry_dt):
    et = entry_dt.astimezone(config.ET)
    same_day = [(at, t) for at, t in cal if at.astimezone(config.ET).date() == et.date()]
    if not same_day:
        return None, 0
    nearest = min(same_day, key=lambda x: abs((entry_dt - x[0]).total_seconds()))
    return round((entry_dt - nearest[0]).total_seconds() / 60, 1), 1


class Tape:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self._fvg = None

    def get(self, symbol, day):
        f = self.folder / f"{symbol.replace('!', '')}_{day}.json"
        if f.exists():
            return json.loads(f.read_text())
        if self._fvg is None:
            from app.mcp_client import FVG
            self._fvg = FVG()
        try:
            ticks = self._fvg.archived_prices(symbol, day)
        except Exception as e:
            print(f"  tape {symbol} {day}: {e}", file=sys.stderr)
            ticks = []
        f.write_text(json.dumps(ticks))
        return ticks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--signals", nargs="+", required=True)
    ap.add_argument("--calendar", required=True)
    ap.add_argument("--tape", default=str(ROOT / "reports" / "tape_cache"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-tape", action="store_true", help="skip managed_r (no archive fetches)")
    a = ap.parse_args()

    led = load_ledger(a.ledger)
    cols = led["cols"]
    ci = {c: i for i, c in enumerate(cols)}
    sigs = load_signals(a.signals)
    cal = load_calendar(a.calendar)
    tape = None if a.no_tape else Tape(a.tape)
    print(f"signals: {{k: len(v) for k, v in sigs.items()}}  calendar: {len(cal)} red-folder events",
          file=sys.stderr)

    new_cols = ["news_min", "news_day", "db_against_before_min", "pair_db_against_before_min",
                "db_against_after_ms", "managed_r", "managed_outcome"]
    rows_out, n_tape = [], 0
    for r in led["rows"]:
        x = dict(zip(cols, r))
        add = {k: None for k in new_cols}
        if x["symbol"] in PAIR and x["entry_bar"]:
            entry_dt = datetime.fromtimestamp(x["entry_bar"] / 1000, tz=timezone.utc)
            add["news_min"], add["news_day"] = news_for(cal, entry_dt)
            b, aft = db_against(sigs.get(x["symbol"], []), x["dir"], x["entry_bar"])
            add["db_against_before_min"], add["db_against_after_ms"] = b, aft
            pb, _ = db_against(sigs.get(PAIR[x["symbol"]], []), x["dir"], x["entry_bar"])
            add["pair_db_against_before_min"] = pb
            if tape is not None and aft and x["entry"] and x["stop"] and x["target"] and x["r"] is not None:
                day = entry_dt.strftime("%Y-%m-%d")
                ticks = tape.get(x["symbol"], day)
                if entry_dt.hour >= 21:
                    ticks = ticks + tape.get(x["symbol"], (entry_dt + timedelta(days=1)).strftime("%Y-%m-%d"))
                if ticks:
                    mr, mo = scanner.replay([tuple(t) for t in ticks], x["dir"], x["entry"], x["stop"],
                                            x["target"], x["entry_bar"], kills=[aft])
                    add["managed_r"], add["managed_outcome"] = mr, mo
                    n_tape += 1
        rows_out.append(r + [add[k] for k in new_cols])
    out = {"cols": cols + new_cols, "rows": rows_out}
    Path(a.out).write_text(json.dumps(out))
    n = sum(1 for r in rows_out if r[ci["symbol"]] in PAIR)
    print(f"wrote {a.out}: {len(rows_out)} rows ({n} MNQ/MES), managed_r on {n_tape} trades", file=sys.stderr)


if __name__ == "__main__":
    main()
