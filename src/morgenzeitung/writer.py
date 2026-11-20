"""Erzeugt die Texte der Zeitung aus dem Digest.

Regelbasiert (ohne KI). Später kann hier ein LLM-Writer angedockt werden,
der dieselbe `Story`-Struktur befüllt.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .digest import WEEKDAYS, Digest, german_date, short_date
from .variety import Variety

@dataclass
class Story:
    title: str
    date_line: str
    edition: str
    headline: str
    subline: str
    sound: str
    mascot_says: str
    alert_title: str = ""
    alert_lines: list[str] = field(default_factory=list)
    homework_title: str = "Hausaufgaben-Alarm"
    outro: str = ""


def write_story(d: Digest, title: str, v: Variety) -> Story:
    hi = f"{v.greeting}, {d.student}!"
    R, r = d.Rel, d.rel            # "Morgen"/"morgen", "Am Montag"/"am Montag", "Heute"/"heute"
    active = d.active_lessons
    n_lessons = len(active)
    cancelled = d.cancelled
    changes = d.changes
    hw_due = d.homework_today      # fällig am Zieltag
    no_school = d.no_school_event
    tests = d.tests_today          # Tests am Zieltag

    # --- Schlagzeile ---
    if no_school:
        headline = f"{R} kein normaler Unterricht!"
        subline = f"{no_school.title}. Check trotzdem, ob für dich etwas ansteht."
    elif tests:
        headline = f"{R}: {tests[0].title}!"
        subline = ("Heute Abend noch einmal kurz wiederholen, dann früh schlafen. Du schaffst das!"
                   if d.evening else "Tief durchatmen, du hast geübt. Viel Erfolg!")
    elif not d.lessons:
        headline = "Schulfreier Tag?!"
        subline = f"Im Dashboard steht {r} kein Unterricht. Genieß es – oder frag lieber nochmal nach!"
    elif len(cancelled) >= 2:
        headline = f"{R} fallen {len(cancelled)} Stunden aus!"
        subline = "Sensation im Stundenplan: mehr Zeit für Großes (oder Hausaufgaben)."
    elif len(cancelled) == 1:
        headline = f"{R} fällt {cancelled[0].subject} aus!"
        subline = f"Um {cancelled[0].start} Uhr bleibt der Raum leer. Plan B parat?"
    elif changes:
        headline = "Achtung, Planänderung!"
        subline = f"{R} {len(changes)} Änderung{'en' if len(changes) > 1 else ''} im Stundenplan – lies genau hin!"
    elif n_lessons >= 6:
        headline = f"{R} Marathon-Tag!"
        subline = f"{n_lessons} Blöcke von {d.school_start} bis {d.school_end} Uhr. Snacks einpacken!"
    elif n_lessons <= 2:
        headline = f"{R} kurzer Tag!"
        subline = f"Um {d.school_end} Uhr ist schon Schluss."
    else:
        headline = f"{R} startet {active[0].subject}!"
        subline = f"Von {d.school_start} bis {d.school_end} Uhr. Du schaffst das!"

    # --- Maskottchen ---
    if hw_due:
        fach = ", ".join(sorted({h.subject for h in hw_due}))
        says = (f"{hi} Für {r} noch {fach} – schon erledigt?" if d.evening
                else f"{hi} Hast du an {fach} gedacht?")
    elif d.upcoming_tests:
        t = d.upcoming_tests[0]
        says = f"{hi} {short_date(t.day)} ist {t.title} – {'heute schon' if d.evening else 'schon'} geübt?"
    elif d.school_start and not no_school:
        says = (f"{hi} {R} geht's um {d.school_start} los – Wecker gestellt?" if d.evening
                else f"{hi} Um {d.school_start} geht's los – nicht trödeln!")
    else:
        says = f"{hi} {R} wird entspannt."

    # --- Alarmbox ---
    alert_lines: list[str] = []
    for t in tests:
        alert_lines.append(f"{R.upper()}: {t.title}")
    for l in cancelled:
        alert_lines.append(f"{l.start} {l.subject}: fällt aus")
    for l in changes:
        alert_lines.append(f"{l.start} {l.subject}: {l.change_text}")
    for t in d.upcoming_tests:
        alert_lines.append(f"{short_date(t.day)}: {t.title}")

    hw_title = "Hausaufgaben-Alarm" if hw_due else "Hausaufgaben-Radar"

    total_min = sum(h.minutes for h in d.homework[:6])
    if total_min:
        outro = f"Geplanter Hausaufgaben-Aufwand: ca. {total_min} Minuten. Teile es dir gut ein!"
    elif d.evening:
        outro = "Tasche packen, Licht aus – bis morgen!"
    else:
        outro = "Bis morgen – deine Morgenzeitung."

    edition_label = (f"Abendausgabe für {WEEKDAYS[d.day.weekday()]}" if d.evening else "Morgenausgabe")
    return Story(
        title=title,
        date_line=german_date(d.day),
        edition=f"{edition_label} · KW {d.day.isocalendar()[1]}",
        headline=headline,
        subline=subline,
        sound=v.sound,
        mascot_says=says,
        alert_title=["Eilmeldung!", "Achtung!", "Breaking News!"][d.day.toordinal() % 3] if alert_lines else "",
        alert_lines=alert_lines[:6],
        homework_title=hw_title,
        outro=outro,
    )
