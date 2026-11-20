"""Frische Inhalte (Witze, Rätsel, Fakten, Wörter, Tipps, Slogans) über die OpenAI Responses API.

- Einmal pro Tag ein Aufruf, Ergebnis in data/ai/<datum>.json (gilt für alle Schüler:innen).
- Alles Erzeugte wandert zusätzlich in den wachsenden Pool data/content_ai.json,
  der mit den festen Listen aus content.py zusammengelegt wird.
- Ist die API nicht erreichbar (kein Key, offline, Fehler), wird None geliefert
  und die Zeitung nimmt Inhalte aus den Listen.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import httpx

from . import content
from .config import Config

API_URL = "https://api.openai.com/v1/responses"
LANGS = list(content.WORDS)  # Englisch, Französisch, Latein, Spanisch

_qa = {
    "type": "object",
    "properties": {
        "q": {"type": "string"},
        "a": {"type": "string"},
        "check": {"type": "string", "description": "Kurz: warum die Pointe/Lösung funktioniert"},
        "score": {"type": "integer", "description": "Ehrliche Bewertung 1–10"},
    },
    "required": ["q", "a", "check", "score"],
    "additionalProperties": False,
}
_word = {
    "type": "object",
    "properties": {"word": {"type": "string"}, "de": {"type": "string"}, "example": {"type": "string"}},
    "required": ["word", "de", "example"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {
        "jokes": {"type": "array", "items": _qa},
        "riddles": {"type": "array", "items": _qa},
        "facts": {"type": "array", "items": {"type": "string"}},
        "tips": {"type": "array", "items": {"type": "string"}},
        "slogans": {"type": "array", "items": {"type": "string"}},
        "words": {
            "type": "object",
            "properties": {lang: {"type": "array", "items": _word} for lang in LANGS},
            "required": LANGS,
            "additionalProperties": False,
        },
    },
    "required": ["jokes", "riddles", "facts", "tips", "slogans", "words"],
    "additionalProperties": False,
}

SYSTEM = """Du bist Redakteur:in einer witzigen Comic-Morgenzeitung für Schüler:innen
der Klassen 7–9 an einem Berliner Gymnasium. Alles auf Deutsch (außer die Fremdwörter).
Qualität vor Menge: lieber ein klassischer, wirklich guter Eintrag als ein neuer, schwacher.

Witze:
- Frage + Pointe, die Pointe beruht auf einem echten deutschen Wortspiel oder einer Doppeldeutigkeit.
- So gut müssen sie sein:
  „Was ist grün und klopft an die Tür?“ – „Ein Klopfsalat.“
  „Treffen sich zwei Magnete. Sagt der eine:“ – „Was soll ich heute bloß anziehen?“
  „Was macht ein Mathematiker im Garten?“ – „Wurzeln ziehen.“
- Schlecht (so NICHT): Pointen ohne Doppelsinn, bloße Beschreibungen, erzwungene Jahreszeit-Witze.
Rätsel:
- Eindeutige Lösung, die logisch zur Frage passt. Gern Denk-, Logik- oder kleine Mathe-Rätsel.
- Prüfe jede Lösung Schritt für Schritt im Feld „check“. Stimmt etwas nicht: anderes Rätsel nehmen.
Bewertung: Gib jedem Witz und Rätsel ehrlich 1–10 Punkte (10 = würde eine ganze Klasse zum Lachen/Grübeln bringen).
Fakten („Wusstest du?“):
- Überraschende, gut belegte Fakten aus Tierwelt, Weltall, Körper, Technik, Geschichte, Sprache.
- Ein Satz, mit „Wow“-Effekt. Keine Allgemeinplätze (z. B. „im Winter ist es kalt“).
Tipps: konkret, ein bis zwei kurze Sätze, motivierend statt belehrend.
Slogans: kurzer, witziger Zeitungs-Untertitel (max. 45 Zeichen).
Wörter: nützliches Wort der Fremdsprache auf Niveau Klasse 7–9 (nicht nur Anfänger-Grundwortschatz),
korrekte deutsche Übersetzung, kurzer korrekter Beispielsatz in der Fremdsprache. Latein: klassische Vokabeln.
Längen (es muss in kleine Comic-Kästen passen): Witz-Frage ≤ 110 Zeichen, Pointe ≤ 70;
Rätsel-Frage ≤ 160, Lösung ≤ 60; Fakt ≤ 170; Tipp ≤ 170.
Allgemein: kinderfreundlich, keine Politik, keine Gewalt, kein Spott über Religion, Herkunft, Aussehen, Gewicht.
Höchstens EIN Eintrag insgesamt darf zur Jahreszeit passen. Nichts aus „Schon vorhanden“ wiederholen.
"""


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _pool_file(cfg: Config) -> Path:
    return cfg.data_dir / "content_ai.json"


def _day_file(cfg: Config, day: dt.date) -> Path:
    return cfg.data_dir / "ai" / f"{day.isoformat()}.json"


def load_pool(cfg: Config) -> dict[str, Any]:
    f = _pool_file(cfg)
    if f.exists():
        try:
            return json.loads(f.read_text())
        except json.JSONDecodeError:
            pass
    return {"jokes": [], "riddles": [], "facts": [], "tips": [], "slogans": [], "words": {}}


def _merge_into_pool(cfg: Config, fresh: dict[str, Any]) -> None:
    pool = load_pool(cfg)
    static_seen = {_norm(q) for q, _ in content.JOKES + content.RIDDLES} | {_norm(x) for x in content.FACTS + content.TIPS + content.SLOGANS}

    def add(key: str, items: list, sig) -> None:
        seen = static_seen | {sig(x) for x in pool.setdefault(key, [])}
        for it in items:
            if sig(it) not in seen:
                pool[key].append(it)
                seen.add(sig(it))

    add("jokes", fresh.get("jokes", []), lambda x: _norm(x[0]))
    add("riddles", fresh.get("riddles", []), lambda x: _norm(x[0]))
    for k in ("facts", "tips", "slogans"):
        add(k, fresh.get(k, []), _norm)
    for lang, items in (fresh.get("words") or {}).items():
        existing = pool.setdefault("words", {}).setdefault(lang, [])
        seen = {_norm(w[0]) for w in existing} | {_norm(w[0]) for w in content.WORDS.get(lang, [])}
        for w in items:
            if _norm(w[0]) not in seen:
                existing.append(w)
                seen.add(_norm(w[0]))
    f = _pool_file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(pool, ensure_ascii=False, indent=1))


def _remove_known(cfg: Config, fresh: dict[str, Any]) -> dict[str, Any]:
    """Entfernt Einträge, die es schon gibt (feste Listen oder Pool)."""
    pool = load_pool(cfg)
    qa = {_norm(q) for q, _ in content.JOKES + content.RIDDLES}
    qa |= {_norm(x[0]) for x in pool.get("jokes", []) + pool.get("riddles", [])}
    flat = {_norm(x) for x in content.FACTS + content.TIPS + content.SLOGANS}
    flat |= {_norm(x) for k in ("facts", "tips", "slogans") for x in pool.get(k, [])}
    out = {
        "jokes": [x for x in fresh["jokes"] if _norm(x[0]) not in qa],
        "riddles": [x for x in fresh["riddles"] if _norm(x[0]) not in qa],
        **{k: [x for x in fresh[k] if _norm(x) not in flat] for k in ("facts", "tips", "slogans")},
        "words": {},
    }
    for lang, ws in fresh["words"].items():
        known = {_norm(w[0]) for w in content.WORDS.get(lang, [])} | {_norm(w[0]) for w in (pool.get("words") or {}).get(lang, [])}
        out["words"][lang] = [w for w in ws if _norm(w[0]) not in known]
    return out


def _avoid_list(cfg: Config, limit: int = 80) -> list[str]:
    pool = load_pool(cfg)
    items = [q for q, _ in content.JOKES + content.RIDDLES] + content.FACTS
    items += [x[0] for x in pool.get("jokes", []) + pool.get("riddles", [])] + pool.get("facts", [])
    words = [w[0] for ws in content.WORDS.values() for w in ws]
    words += [w[0] for ws in (pool.get("words") or {}).values() for w in ws]
    return items[-limit:] + [f"Wörter: {', '.join(words)}"]


def _normalize(raw: dict) -> dict[str, Any]:
    """API-Antwort -> dieselbe Form wie content.py (Tupel als Listen)."""
    clean = lambda s: " ".join(str(s).split())

    def best(items: list, keep: int, max_q: int, max_a: int, min_score: int = 7) -> list:
        ok = [x for x in items if x.get("q") and x.get("a") and int(x.get("score") or 0) >= min_score
              and len(x["q"]) <= max_q and len(x["a"]) <= max_a]
        ok.sort(key=lambda x: -int(x.get("score") or 0))
        return [[clean(x["q"]), clean(x["a"])] for x in ok[:keep]]

    return {
        "jokes": best(raw.get("jokes", []), 4, 130, 90),
        "riddles": best(raw.get("riddles", []), 3, 190, 80),
        "facts": [clean(x) for x in raw.get("facts", []) if x and len(x) <= 200],
        "tips": [clean(x) for x in raw.get("tips", []) if x and len(x) <= 200],
        "slogans": [clean(x) for x in raw.get("slogans", []) if x and len(x) <= 60],
        "words": {
            lang: [[clean(w["word"]), clean(w["de"]), clean(w["example"])] for w in ws if w.get("word")]
            for lang, ws in (raw.get("words") or {}).items()
        },
    }


def _output_text(resp: dict) -> str:
    if resp.get("output_text"):
        return resp["output_text"]
    for item in resp.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    return c.get("text", "")
                if c.get("type") == "refusal":
                    raise RuntimeError(f"Abgelehnt: {c.get('refusal')}")
    raise RuntimeError("Keine Textausgabe in der Antwort")


def _request(cfg: Config, day: dt.date, log=print) -> dict[str, Any]:
    """Probiert die Modelle aus OPENAI_MODEL (Komma-getrennt) der Reihe nach."""
    errors = []
    for model in [m.strip() for m in cfg.openai_model.split(",") if m.strip()]:
        try:
            return _request_model(cfg, day, model)
        except RuntimeError as exc:
            errors.append(f"{model}: {exc}")
            if "401" in str(exc):  # falscher Key – andere Modelle helfen nicht
                break
            log(f"   {model} nicht nutzbar, versuche nächstes Modell …")
    raise RuntimeError("; ".join(errors))


def _request_model(cfg: Config, day: dt.date, model: str) -> dict[str, Any]:
    avoid = "\n".join(f"- {x}" for x in _avoid_list(cfg))
    user = (
        f"Datum: {day.isoformat()} ({['Montag','Dienstag','Mittwoch','Donnerstag','Freitag','Samstag','Sonntag'][day.weekday()]}). "
        "\n\n"
        "Erzeuge: 8 Witze, 6 Rätsel, 4 Fakten, 2 Tipps, 3 Slogans und je 3 Wörter für "
        f"{', '.join(LANGS)}.\n\nSchon vorhanden (nicht wiederholen):\n{avoid}"
    )
    body = {
        "model": model,
        "input": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        "text": {"format": {"type": "json_schema", "name": "zeitung_inhalte", "strict": True, "schema": SCHEMA}},
    }
    try:
        r = httpx.post(API_URL, json=body, timeout=httpx.Timeout(300, connect=15),
                       headers={"Authorization": f"Bearer {cfg.openai_api_key}"})
    except httpx.HTTPError as exc:  # Timeout, offline, … -> nächstes Modell / Listen
        raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc
    if r.status_code != 200:
        msg = r.text[:300]
        try:
            msg = r.json().get("error", {}).get("message", msg)
        except ValueError:
            pass
        raise RuntimeError(f"HTTP {r.status_code}: {msg}")
    return _normalize(json.loads(_output_text(r.json())))


_memo: dict[dt.date, dict | None] = {}


def daily_content(cfg: Config, day: dt.date, log=print) -> dict[str, Any] | None:
    """Frische Inhalte für den Tag (aus Cache oder API). None = Listen benutzen."""
    if day in _memo:
        return _memo[day]
    f = _day_file(cfg, day)
    if f.exists():
        try:
            _memo[day] = json.loads(f.read_text())
            return _memo[day]
        except json.JSONDecodeError:
            pass
    if not cfg.ai_enabled:
        _memo[day] = None
        return None
    try:
        log(f"🤖 Hole frische Inhalte von OpenAI ({cfg.openai_model.split(',')[0].strip()}) …")
        fresh = _remove_known(cfg, _request(cfg, day, log))
    except Exception as exc:
        log(f"⚠️  OpenAI nicht verfügbar ({exc}) – nehme Inhalte aus den Listen")
        _memo[day] = None
        return None
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(fresh, ensure_ascii=False, indent=1))
    _merge_into_pool(cfg, fresh)
    n = sum(len(v) for k, v in fresh.items() if k != "words") + sum(len(v) for v in fresh["words"].values())
    log(f"   {n} neue Einträge, Pool: {_pool_file(cfg).name}")
    _memo[day] = fresh
    return fresh
