from email.message import EmailMessage

from morgenzeitung import ai_content
from morgenzeitung.mailcode import BODY_CODE_RE, CODE_RE, _body_text
from morgenzeitung.render import available_styles, render_html
from morgenzeitung.variety import Pools, pick_variety
from morgenzeitung.writer import write_story


def test_code_from_subject_and_body():
    msg = EmailMessage()
    msg["Subject"] = "Dein Anmeldecode lautet 306262"
    msg.set_content("Hallo!\n\nDein Anmeldecode lautet:\n\n306262\n\nDer Code ist für zehn Minuten gültig.")
    assert CODE_RE.search(msg["Subject"]).group(1) == "306262"
    assert BODY_CODE_RE.search(_body_text(msg)).group(1) == "306262"
    html = "<p>Dein Anmeldecode lautet:</p>\n<p style='font-size: 200%;'>123456</p>"
    assert BODY_CODE_RE.search(html).group(1) == "123456"


def test_ai_normalize_keeps_only_good_and_short_items():
    raw = {
        "jokes": [
            {"q": "Was macht ein Mathematiker im Garten?", "a": "Wurzeln ziehen.", "check": "", "score": 9},
            {"q": "Schwacher Witz?", "a": "Ja.", "check": "", "score": 4},
            {"q": "x" * 200, "a": "zu lang", "check": "", "score": 10},
        ],
        "riddles": [], "facts": ["Ein Fakt."], "tips": [], "slogans": [],
        "words": {"Englisch": [{"word": "brave", "de": "mutig", "example": "Be brave."}]},
    }
    out = ai_content._normalize(raw)
    assert out["jokes"] == [["Was macht ein Mathematiker im Garten?", "Wurzeln ziehen."]]
    assert out["words"]["Englisch"] == [["brave", "mutig", "Be brave."]]


def test_ai_disabled_without_key_falls_back(cfg, demo_digest):
    assert not cfg.ai_enabled
    assert ai_content.daily_content(cfg, demo_digest().day, log=lambda *_: None) is None


def test_variety_is_deterministic_per_day(cfg, demo_digest):
    d = demo_digest()
    a = pick_variety(d, cfg, available_styles(), None, Pools())
    b = pick_variety(d, cfg, available_styles(), None, Pools())
    assert (a.style, a.mascot, a.masthead, [x.kind for x in a.boxes]) == \
           (b.style, b.mascot, b.masthead, [x.kind for x in b.boxes])
    assert len(a.boxes) == 2


def test_render_html_contains_content(cfg, demo_digest):
    d = demo_digest()
    v = pick_variety(d, cfg, available_styles(), "classic", Pools())
    html = render_html(d, write_story(d, "Testzeitung", v), v)
    assert "Testzeitung" in html and "Chemie" in html
    assert "&#34;" not in html.split("</style>")[1]  # CSS darf nicht escaped werden
    assert "--accent" in html
