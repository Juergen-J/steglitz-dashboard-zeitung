import datetime as dt

import pytest

from morgenzeitung.digest import _parse_room, _split_label, pick_target_day

from .conftest import WED


@pytest.mark.parametrize(
    "now, edition, expected",
    [
        ("2026-11-18 15:30", "abend", "2026-11-19"),   # Mittwochnachmittag -> Donnerstag
        ("2026-11-20 16:00", "abend", "2026-11-23"),   # Freitag -> Montag
        ("2026-11-21 11:00", "abend", "2026-11-23"),   # Samstag -> Montag
        ("2026-11-19 00:30", "abend", "2026-11-19"),   # nach Mitternacht zählt noch zum Vorabend
        ("2026-11-18 07:00", "morgen", "2026-11-18"),  # Morgenausgabe: heute
        ("2026-11-18 15:00", "morgen", "2026-11-19"),  # Morgenausgabe ab 14 Uhr: nächster Tag
        ("2026-11-22 09:00", "morgen", "2026-11-23"),  # Sonntag -> Montag
    ],
)
def test_pick_target_day(now, edition, expected):
    day, _ = pick_target_day(dt.datetime.fromisoformat(now), 14, edition)
    assert day.isoformat() == expected


def test_parse_room_with_strikethrough():
    assert _parse_room("<s>408</s> 407", "408") == ("407", "408")
    assert _parse_room(["115", "118"], None) == ("118", "115")
    assert _parse_room("301", None) == ("301", "")


def test_split_label():
    assert _split_label("Latein (Frau Dr. Beispiel)") == ("Latein", "Frau Dr. Beispiel")
    assert _split_label("Theater-AG") == ("Theater-AG", "")


def test_demo_digest_wednesday(demo_digest):
    d = demo_digest()
    assert len(d.lessons) == 5
    assert [l.subject for l in d.cancelled] == ["Chemie"]
    english = next(l for l in d.lessons if l.subject == "Englisch")
    assert "Raum 115 → 118" in english.change_text
    # Fachkonferenz wird gefiltert, Test am Freitag erscheint als Vorwarnung
    titles = [e.title for evs in d.events.values() for e in evs]
    assert not any("Fachkonferenz" in t for t in titles)
    assert [t.title for t in d.upcoming_tests] == ["LEK (Bio)"]
    assert {h.subject for h in d.homework_today} == {"Englisch", "Mathematik"}


def test_relative_wording_and_packlist(demo_digest):
    monday = dt.date(2026, 11, 23)
    d = demo_digest(monday, issued=dt.date(2026, 11, 20))
    assert d.evening and d.rel == "am Montag"
    assert "Sportzeug" in d.pack_list
    d = demo_digest(WED, issued=WED - dt.timedelta(days=1))
    assert d.rel == "morgen"
