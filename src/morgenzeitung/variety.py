"""Tägliche Abwechslung: Stil, Kopf, Maskottchen, Accessoires, Extra-Kästen.

Deterministisch pro (Tag, Schüler:in): derselbe Tag ergibt dieselbe Zeitung,
Geschwister bekommen am selben Tag eine andere Variante.
Listen werden reihum durchlaufen, damit sich nichts schnell wiederholt.
"""
from __future__ import annotations

import datetime as dt
import random
import zlib
from dataclasses import dataclass, field

from . import content
from .config import Config
from .digest import Digest

MASTHEADS = 4
HERO_PATTERNS = 4
BOX_KINDS = ["witz", "raetsel", "wort", "fakt", "tipp"]


@dataclass
class Box:
    kind: str
    title: str
    lines: list[str] = field(default_factory=list)
    answer: str = ""   # Rätsel-Lösung / Pointe
    extra: str = ""


@dataclass
class Variety:
    style: str
    masthead: int
    hero_pattern: int
    slogan: str
    mascot: str
    mascot_name: str
    accessories: list[str]
    greeting: str
    sound: str
    boxes: list[Box]
    countdown: str


def _cycle(pool: list, day: dt.date, salt: int, step: int = 1):
    return pool[(day.toordinal() * step + salt) % len(pool)]


def _languages(d: Digest) -> list[str]:
    subjects = {l.subject for ls in d.week.values() for l in ls}
    return [lang for lang in content.WORDS if any(lang in s for s in subjects)]


class Pools:
    """Feste Listen + KI-Pool (alles), plus frische KI-Inhalte des Tages (bevorzugt)."""

    def __init__(self, pool: dict | None = None, fresh: dict | None = None):
        pool = pool or {}
        t = lambda xs: [tuple(x) for x in xs]
        self.all = {
            "jokes": content.JOKES + t(pool.get("jokes", [])),
            "riddles": content.RIDDLES + t(pool.get("riddles", [])),
            "facts": content.FACTS + list(pool.get("facts", [])),
            "tips": content.TIPS + list(pool.get("tips", [])),
            "slogans": content.SLOGANS + list(pool.get("slogans", [])),
        }
        self.words = {lang: list(ws) + t((pool.get("words") or {}).get(lang, [])) for lang, ws in content.WORDS.items()}
        self.fresh = fresh or {}

    def pick(self, key: str, day: dt.date, salt: int, step: int = 1):
        fresh = self.fresh.get(key) or []
        if fresh:  # frische Inhalte von heute; Geschwister bekommen verschiedene
            item = fresh[salt % len(fresh)]
            return tuple(item) if isinstance(item, list) else item
        return _cycle(self.all[key], day, salt, step)

    def pick_word(self, lang: str, day: dt.date, salt: int):
        fresh = (self.fresh.get("words") or {}).get(lang) or []
        if fresh:
            return tuple(fresh[salt % len(fresh)])
        return _cycle(self.words[lang], day, salt, 1)

    @property
    def is_fresh(self) -> bool:
        return bool(self.fresh)


def _box(kind: str, d: Digest, salt: int, pools: Pools) -> Box:
    day = d.day
    if kind == "witz":
        q, a = pools.pick("jokes", day, salt, 7)
        return Box("witz", "Witz des Tages", [q], answer=a)
    if kind == "raetsel":
        q, a = pools.pick("riddles", day, salt, 5)
        return Box("raetsel", "Rätsel des Tages", [q], answer=a)
    if kind == "fakt":
        return Box("fakt", "Wusstest du?", [pools.pick("facts", day, salt, 3)])
    if kind == "tipp":
        return Box("tipp", "Profi-Tipp", [pools.pick("tips", day, salt, 1)])
    langs = _languages(d) or ["Englisch"]
    lang = _cycle(langs, day, salt)
    word, de, example = pools.pick_word(lang, day, salt)
    return Box("wort", f"Wort des Tages · {lang}", [word], answer=de, extra=example)


def _accessories(d: Digest) -> list[str]:
    acc: list[str] = []
    m, day = d.day.month, d.day.day
    if d.tests_today:
        acc.append("gradcap")
    elif m == 12 and day <= 26:
        acc.append("santa")
    if m in (11, 12, 1, 2):
        acc.append("scarf")
    if d.day.weekday() == 4 or d.no_school_event:
        acc.append("sunglasses")
    return acc


def _countdown(d: Digest) -> str:
    if d.day.month == 12 and d.day.day < 24:
        n = 24 - d.day.day
        return f"Noch {n} Tag{'e' if n > 1 else ''} bis Heiligabend"
    wd = d.day.weekday()
    if wd == 4:
        return "Letzter Schultag der Woche!"
    if wd < 4:
        return f"Noch {5 - wd} Schultage bis zum Wochenende"
    return ""


def pick_variety(d: Digest, cfg: Config, available_styles: list[str], forced_style: str | None = None,
                 pools: Pools | None = None) -> Variety:
    pools = pools or Pools()
    salt = zlib.crc32((cfg.profile or cfg.dashboard_email or "x").encode()) % 1000
    rng = random.Random(d.day.toordinal() * 1000 + salt)
    on = cfg.variety

    # Stil
    wanted = forced_style or cfg.comic_style
    if wanted != "auto":
        style = wanted
    else:
        pool = [s for s in cfg.comic_styles if s in available_styles] or available_styles
        style = _cycle(pool, d.day, salt)

    # Maskottchen
    keys = list(content.MASCOTS)
    if cfg.mascot in content.MASCOTS:
        mascot = cfg.mascot
    else:
        mascot = _cycle(keys, d.day, salt) if on else "owl"

    # Extra-Kästen: zwei verschiedene Arten pro Tag
    kinds = list(BOX_KINDS)
    if not _languages(d):
        kinds.remove("wort")
    if on:
        rng.shuffle(kinds)
        chosen = kinds[:2]
    else:
        chosen = ["witz", "tipp"]

    slogan = content.WEEKDAY_SLOGANS.get(d.day.weekday()) or pools.pick("slogans", d.day, salt)
    return Variety(
        style=style,
        masthead=(_cycle(list(range(1, MASTHEADS + 1)), d.day, salt, 3) if on else 1),
        hero_pattern=(_cycle(list(range(1, HERO_PATTERNS + 1)), d.day, salt + 1, 1) if on else 1),
        slogan=slogan,
        mascot=mascot,
        mascot_name=content.MASCOTS[mascot],
        accessories=_accessories(d) if on else [],
        greeting=(rng.choice(content.GREETINGS_EVENING if d.evening else content.GREETINGS) if on
                  else ("Hallo" if d.evening else "Guten Morgen")),
        sound=rng.choice(content.SOUNDS),
        boxes=[_box(k, d, salt, pools) for k in chosen],
        countdown=_countdown(d),
    )
