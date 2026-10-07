"""Search over the full course material in knowledge/ (course transcripts, mini lessons, the
Reversal Set Up video, the SOP and strategy PDFs as text).

Plain BM25, no extra dependencies. For each setup we build a query from the signal, config,
retracement, session and what the vision model saw, and hand the top passages to DeepSeek
next to the rulebook, so it can quote the instructor rather than our summary.
"""
import math
import re
from collections import Counter
from pathlib import Path

from . import config

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"

_STOP = set("""a an the and or but if then so to of in on at by for with from up down is are was
were be been being it its this that these those there here you your we our they them i me my he
she his her as not no yes do does did just like right gonna going get got can could would should
will okay ok um uh guys yeah now again also very really actually pretty much well know see look
let lets one two""".split())

# trading phrases -> extra query words, so "DB" finds "double break" passages etc.
_EXPAND = {
    "db": "double break continuation retracement range",
    "2db": "double break both directions void conflict 2db",
    "m": "manipulation opposite direction first fair value gap",
    "2m": "manipulation first untouched fair value gap between two ms 70",
    "triangle": "triangle pattern manipulation double break",
    "reversal": "reversal zone reversal area closed above below higher time frame",
    "purple": "purple zone algorithmic drawn pushes",
    "blue": "blue zone new york",
    "ndog": "new day opening gap",
    "dsd": "dsd high low extension gas out",
    "asia": "asia session purple zone",
    "london": "london session obligation",
    "newyork": "new york open blue zone window",
    "deep": "deep retracement fair value gap double break leg",
    "shallow": "shallow retracement runaway",
    "runaway": "runaway retracement foothold",
    "divergence": "divergence stronger weaker pair",
    "spotlight": "spotlight confirmation dealing range",
}

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1 or t in ("m",)]


def _chunks(text: str, size: int = 900, overlap: int = 200):
    text = re.sub(r"\s+", " ", text).strip()
    # drop transcript filler loops ("Okay. Okay. Okay.")
    text = re.sub(r"(\b[\w' ,]{1,40}[.!?])(\s*\1){2,}", r"\1", text)
    i = 0
    while i < len(text):
        end = min(len(text), i + size)
        if end < len(text):
            dot = text.rfind(". ", i + size // 2, end)
            if dot > 0:
                end = dot + 1
        yield text[i:end].strip()
        if end >= len(text):
            break
        i = max(end - overlap, i + 1)


class Index:
    def __init__(self, root: Path = KNOWLEDGE_DIR):
        self.docs: list[tuple[str, str]] = []   # (source, passage)
        for p in sorted(root.rglob("*.txt")) + sorted(root.rglob("*.md")):
            src = str(p.relative_to(root))
            for c in _chunks(p.read_text(errors="ignore")):
                if len(c) > 120:
                    self.docs.append((src, c))
        self.tf = [Counter(_tokens(c)) for _, c in self.docs]
        self.len = [sum(t.values()) for t in self.tf]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 1
        df = Counter()
        for t in self.tf:
            df.update(t.keys())
        n = len(self.docs) or 1
        self.idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}

    def search(self, query: str, k: int = 6, k1: float = 1.4, b: float = 0.75):
        q = _tokens(query)
        scores = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            for w in q:
                f = tf.get(w)
                if f:
                    s += self.idf.get(w, 0) * f * (k1 + 1) / (f + k1 * (1 - b + b * self.len[i] / self.avg))
            if s > 0:
                scores.append((s, i))
        scores.sort(reverse=True)
        out, seen_src = [], Counter()
        for s, i in scores:
            src, text = self.docs[i]
            if seen_src[src] >= 2:      # spread results across sources
                continue
            seen_src[src] += 1
            out.append({"source": src, "score": round(s, 2), "text": text})
            if len(out) >= k:
                break
        return out


_index = None


def index() -> Index:
    global _index
    if _index is None:
        _index = Index()
    return _index


def query_for(context: dict) -> str:
    """Build a search query from what the setup is."""
    eng = context.get("engine", {})
    words = []
    for key in ("config", "retrace_quality", "session", "direction", "cascade"):
        v = eng.get(key)
        if v:
            words.append(str(v))
    sig = (eng.get("arming_signal") or {}).get("text") or ""
    words.append(sig)
    words += [str(s) for s in eng.get("signal_sequence") or []]
    if eng.get("two_m"):
        words.append("2m")
    read = context.get("chart_read") or {}
    for ch in read.get("charts", []) if isinstance(read, dict) else []:
        for z in ch.get("zones", []) or []:
            words.append(str(z.get("type", "")))
        if ch.get("reversal_zones"):
            words.append("reversal")
        if (ch.get("spotlight") or {}).get("confirmation") in ("bull", "bear"):
            words.append("spotlight")
        if ch.get("structure") == "consolidating":
            words.append("consolidation power of three")
    words.append("divergence")
    expanded = []
    for w in words:
        expanded.append(w)
        for tok in _tokens(w):
            if tok in _EXPAND:
                expanded.append(_EXPAND[tok])
    return " ".join(expanded)


def passages_for(context: dict, k: int | None = None) -> list[dict]:
    k = k or config.KNOWLEDGE_PASSAGES
    if k <= 0:
        return []
    return index().search(query_for(context), k=k)
