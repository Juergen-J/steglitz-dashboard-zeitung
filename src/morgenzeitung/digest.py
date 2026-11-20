"""Macht aus den Rohdaten des Dashboards eine einheitliche Tages-Zusammenfassung."""
from __future__ import annotations

import datetime as dt
import html
import re
from dataclasses import dataclass, field
from typing import Any

WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]

NO_SCHOOL_RE = re.compile(r"kein(en)? (regulärer )?Unterricht|unterrichtsfrei|Studientag|Ferien|Feiertag", re.I)


def strip_html(s: Any) -> str:
    if s is None:
        return ""
    if isinstance(s, list):
        s = " ".join(str(x) for x in s if x)
    s = re.sub(r"<br\s*/?>|</p>|</div>", "\n", str(s))
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t ]+", " ", s)
    return re.sub(r"\s*\n\s*", "\n", s).strip()


def one_line(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def german_date(d: dt.date) -> str:
    return f"{WEEKDAYS[d.weekday()]}, {d.day}. {MONTHS[d.month - 1]} {d.year}"


def short_date(d: dt.date) -> str:
    return f"{WEEKDAYS[d.weekday()][:2]} {d.day}.{d.month}."


@dataclass
class Lesson:
    start: str          # "08:00"
    end: str
    subject: str
    teacher: str = ""
    room: str = ""
    room_old: str = ""
    teacher_old: str = ""
    cancelled: bool = False
    substitution: str = ""   # Vertretungstext
    changed: bool = False
    topic: str = ""          # Stundenthema
    homework_text: str = ""  # in dieser Stunde eingetragene Hausaufgabe
    lesson_key: str = ""
    period: int = 0

    @property
    def change_text(self) -> str:
        parts = []
        if self.room_old and self.room:
            parts.append(f"Raum {self.room_old} → {self.room}")
        if self.teacher_old:
            parts.append(f"Vertretung statt {self.teacher_old}")
        if self.substitution:
            parts.append(self.substitution)
        return " · ".join(parts) or ("Änderung" if self.changed else "")


@dataclass
class DayEvent:
    day: dt.date
    title: str
    kind: str  # "test" | "termin"
    no_school: bool = False


@dataclass
class Homework:
    due: dt.date
    subject: str
    text: str
    minutes: int = 0


@dataclass
class Message:
    date: dt.date | None
    sender: str
    text: str


@dataclass
class Digest:
    student: str
    day: dt.date
    issued: dt.date | None = None  # wann die Zeitung erscheint (Abendausgabe: Vortag)
    lessons: list[Lesson] = field(default_factory=list)
    week: dict[dt.date, list[Lesson]] = field(default_factory=dict)
    events: dict[dt.date, list[DayEvent]] = field(default_factory=dict)
    homework: list[Homework] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)  # für spätere Quellen

    @property
    def evening(self) -> bool:
        return bool(self.issued and self.issued < self.day)

    @property
    def rel(self) -> str:
        """'heute' / 'morgen' / 'am Montag' – aus Sicht des Erscheinungstags."""
        issued = self.issued or self.day
        delta = (self.day - issued).days
        if delta == 0:
            return "heute"
        if delta == 1:
            return "morgen"
        return f"am {WEEKDAYS[self.day.weekday()]}"

    @property
    def Rel(self) -> str:
        return self.rel[0].upper() + self.rel[1:]

    @property
    def pack_list(self) -> list[str]:
        """Was in die Schultasche gehört (Fächer ohne Ausfälle + Extras)."""
        items: list[str] = []
        for l in self.active_lessons:
            name = re.sub(r"\s*\(.*?\)\s*", " ", l.subject).strip()
            if name and name not in items:
                items.append(name)
        if any("sport" in x.lower() for x in items):
            items.append("Sportzeug")
        if any("schwimm" in x.lower() for x in items):
            items.append("Schwimmsachen")
        return items

    @property
    def day_events(self) -> list[DayEvent]:
        return self.events.get(self.day, [])

    @property
    def no_school_event(self) -> DayEvent | None:
        return next((e for e in self.day_events if e.no_school), None)

    @property
    def tests_today(self) -> list[DayEvent]:
        return [e for e in self.day_events if e.kind == "test"]

    @property
    def upcoming_tests(self) -> list[DayEvent]:
        """Tests in den nächsten 7 Tagen (ohne heute)."""
        end = self.day + dt.timedelta(days=7)
        return [e for d, evs in self.events.items() if self.day < d <= end for e in evs if e.kind == "test"]

    @property
    def cancelled(self) -> list[Lesson]:
        return [l for l in self.lessons if l.cancelled]

    @property
    def changes(self) -> list[Lesson]:
        return [l for l in self.lessons if l.change_text and not l.cancelled]

    @property
    def homework_today(self) -> list[Homework]:
        return [h for h in self.homework if h.due == self.day]

    @property
    def active_lessons(self) -> list[Lesson]:
        return [l for l in self.lessons if not l.cancelled]

    @property
    def school_start(self) -> str | None:
        ls = self.active_lessons
        return ls[0].start if ls else None

    @property
    def school_end(self) -> str | None:
        ls = self.active_lessons
        return ls[-1].end if ls else None


def _split_label(label: str) -> tuple[str, str]:
    # "<b>Mathematik</b> (Müller)" -> ("Mathematik", "Müller")
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", label)
    return (m.group(1).strip(), m.group(2).strip()) if m else (label, "")


def _parse_room(raum: Any, removed: Any) -> tuple[str, str]:
    if isinstance(raum, list):
        rooms = [str(r) for r in raum if r]
        if len(rooms) > 1:  # [alt, neu]
            return one_line(strip_html(rooms[-1])), one_line(strip_html(rooms[0]))
        raum = rooms[0] if rooms else ""
    raum = str(raum or "")
    old = ""
    m = re.search(r"<s>(.*?)</s>", raum)
    if m:
        old = strip_html(m.group(1))
        raum = raum[m.end():]
    if not old and removed:
        old = strip_html(removed)
    return one_line(strip_html(raum)), old


def _parse_lesson(e: dict) -> tuple[dt.date, Lesson]:
    start, end = e["start"], e.get("end") or ""
    day = dt.date.fromisoformat(start[:10])
    label_src = e.get("label_lehrer") or ""
    if "(" not in label_src:  # manchmal nur Kürzel – dann das volle Label nehmen
        label_src = e.get("label") or label_src
    subject, teacher = _split_label(one_line(strip_html(label_src)))
    _, teacher_long = _split_label(one_line(strip_html(e.get("label_lehrer_lang") or "")))
    room, room_old = _parse_room(e.get("raum"), e.get("raum_removed"))
    lehrer_removed = e.get("lehrer_removed") or []
    vtext = one_line(strip_html(e.get("vertretungs_text")))
    data = e.get("data") or {}
    cancelled = bool(e.get("entfall")) or "entfällt" in vtext.lower() or "fällt aus" in vtext.lower()
    return day, Lesson(
        start=start[11:16], end=end[11:16], subject=subject or "Unterricht",
        teacher=teacher_long or teacher, room=room, room_old=room_old,
        teacher_old=", ".join(strip_html(x) for x in lehrer_removed) if isinstance(lehrer_removed, list) else "",
        cancelled=cancelled, substitution=vtext,
        changed=bool(room_old or lehrer_removed or vtext),
        topic=one_line(re.sub(r"https?://\S+", "", strip_html(data.get("stundenthema_text")))).strip(" :–-"),
        homework_text=strip_html(data.get("hausaufgaben_text")),
        lesson_key=str(e.get("lesson_key") or ""),
        period=int(e.get("stunde") or 0),
    )


def _parse_day_events(e: dict, exclude: re.Pattern | None) -> list[DayEvent]:
    title = one_line(strip_html(e.get("title") or e.get("label")))
    if not title or (exclude and exclude.search(title)):
        return []
    start = dt.date.fromisoformat(e["start"][:10])
    end = dt.date.fromisoformat(e["end"][:10]) if len(e.get("end") or "") >= 10 else start + dt.timedelta(days=1)
    kind = "test" if "test" in (e.get("event_type") or "") else "termin"
    out, d = [], start
    while d < max(end, start + dt.timedelta(days=1)):
        out.append(DayEvent(day=d, title=title, kind=kind, no_school=bool(NO_SCHOOL_RE.search(title))))
        d += dt.timedelta(days=1)
    return out


def build_digest(raw: dict, day: dt.date, student: str, event_exclude: str = "",
                 hide_subjects: list[str] | None = None, issued: dt.date | None = None) -> Digest:
    d = Digest(student=student, day=day, issued=issued)
    exclude = re.compile(event_exclude, re.I) if event_exclude else None
    all_lessons: list[tuple[dt.date, Lesson]] = []
    seen_lessons, seen_events = set(), set()
    for wk in (raw.get("weeks") or {}).values():
        for e in (wk or {}).get("events", []):
            if len(e.get("start") or "") < 10:
                continue
            if e.get("lesson") and len(e["start"]) >= 16:
                eday, lesson = _parse_lesson(e)
                if hide_subjects and lesson.subject.lower() in hide_subjects:
                    continue
                key = (eday, lesson.start, lesson.lesson_key or lesson.subject)
                if key not in seen_lessons:
                    seen_lessons.add(key)
                    all_lessons.append((eday, lesson))
            else:
                for ev in _parse_day_events(e, exclude):
                    k = (ev.day, ev.title)
                    if k not in seen_events:
                        seen_events.add(k)
                        d.events.setdefault(ev.day, []).append(ev)

    all_lessons.sort(key=lambda x: (x[0], x[1].start))
    for eday, lesson in all_lessons:
        d.week.setdefault(eday, []).append(lesson)
    d.lessons = d.week.get(day, [])
    d.events = dict(sorted(d.events.items()))

    # --- Hausaufgaben ---
    hw_seen: set[tuple[str, str]] = set()

    def add_hw(due: dt.date, subject: str, text: str, minutes: int = 0, key: str = "") -> None:
        text = text.strip()
        sig = (key or subject, one_line(text).lower())
        if not text or sig in hw_seen or due < day:
            return
        hw_seen.add(sig)
        d.homework.append(Homework(due=due, subject=subject, text=text, minutes=minutes))

    for h in raw.get("homework") or []:
        try:
            due = dt.date.fromisoformat(h.get("datum", "")[:10])
        except ValueError:
            continue
        text = h.get("text")
        text = "\n".join(strip_html(t) for t in text) if isinstance(text, list) else strip_html(text)
        add_hw(due, strip_html(h.get("fach")), text, int(h.get("est_time") or 0), str(h.get("lesson_key") or ""))

    # In vergangenen Stunden aufgegeben -> fällig in der nächsten Stunde desselben Kurses
    for i, (eday, lesson) in enumerate(all_lessons):
        if not lesson.homework_text:
            continue
        if eday >= day:  # zukünftige Stunden stehen schon in homework.json
            add_hw(eday, lesson.subject, lesson.homework_text, key=lesson.lesson_key)
            continue
        nxt = next((ld for ld, l in all_lessons[i + 1:] if l.lesson_key == lesson.lesson_key and ld > eday), None)
        if nxt:
            add_hw(nxt, lesson.subject, lesson.homework_text, key=lesson.lesson_key)
    d.homework.sort(key=lambda h: (h.due, h.subject))

    # --- Nachrichten ---
    cutoff = day - dt.timedelta(days=7)
    for m in raw.get("messages") or []:
        try:
            mdate = dt.date.fromisoformat(m.get("date", "")[:10])
        except ValueError:
            mdate = None
        if mdate and mdate < cutoff:
            continue
        text = one_line(strip_html(m.get("html") or m.get("comment") or m.get("text") or ""))
        if not text:
            continue
        d.messages.append(Message(date=mdate, sender=strip_html(m.get("from")), text=text))
    d.messages = d.messages[:5]
    return d


def next_school_day(d: dt.date) -> dt.date:
    d += dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def prev_school_day(d: dt.date) -> dt.date:
    d -= dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def pick_target_day(now: dt.datetime, after_hour: int, edition: str = "abend") -> tuple[dt.date, dt.date]:
    """(Zieltag, Erscheinungstag).

    abend:  Zeitung für den nächsten Schultag (nach Mitternacht bis 4 Uhr zählt noch als Vorabend).
    morgen: Zeitung für heute; ab `after_hour` bzw. am Wochenende für den nächsten Schultag.
    """
    today = now.date()
    if edition == "abend":
        base = today - dt.timedelta(days=1) if now.hour < 4 else today
        return next_school_day(base), today
    if now.hour >= after_hour or today.weekday() >= 5:
        return next_school_day(today), today
    return today, today
