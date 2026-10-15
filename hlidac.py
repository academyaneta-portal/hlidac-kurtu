#!/usr/bin/env python3
"""Hlídač volných kurtů – hala Sprint a Tenis Paradise (Brno).

Hlídá odpolední termíny (výchozí: po–pá, 15:00–18:00) a pošle e-mail / SMS,
když se objeví nově uvolněná hodina. Stav posledního běhu drží v state.json.

Konfigurace přes proměnné prostředí (viz README.md).
"""
import datetime as dt
import html
import http.cookiejar
import json
import os
import re
import smtplib
import sys
import urllib.parse
import urllib.request
from email.mime.text import MIMEText
from html.parser import HTMLParser
from pathlib import Path

WINDOW_FROM = os.environ.get("WINDOW_FROM", "15:00")
WINDOW_TO = os.environ.get("WINDOW_TO", "18:00")
WEEKDAYS = {int(d) for d in os.environ.get("WEEKDAYS", "0,1,2,3,4").split(",")}  # 0 = pondělí
DAYS_AHEAD = int(os.environ.get("DAYS_AHEAD", "14"))
STATE_FILE = Path(os.environ.get("STATE_FILE", Path(__file__).with_name("state.json")))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128 Safari/537.36"

SPRINT_URL = "https://memberzone.cz/sprint_tenis/Sportoviste.aspx?ID_Sportoviste=1&NAZEV=Tenis%20hala"
PARADISE_BASE = "https://jdemenato.cz/reservation/tenis-paradise/reservationcalendaroverview"
LINKS = {"Sprint": "https://memberzone.cz/sprint_tenis/", "Paradise": PARADISE_BASE}

CZ_DAYS = ["po", "út", "st", "čt", "pá", "so", "ne"]


def hm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def fmt(mins):
    return f"{mins // 60}:{mins % 60:02d}"


def opener():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def get(op, url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "cs"})
    with op.open(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


# ---------- Sprint (memberzone.cz) ----------
# Stránka ukazuje 7 dní dopředu; každá karta = začátek volné hodiny + seznam volných kurtů.

def fetch_sprint():
    page = get(opener(), SPRINT_URL)
    slots = []
    for card in re.finditer(r'data-identifi="kurty".*?</p>', page, re.S):
        c = card.group(0)
        names = re.search(r'id="\w+_hfKurtyName"[^>]*value="([^"]*)"', c)
        when = re.search(r'id="\w+_hfDatumCas"[^>]*value="([^"]*)"', c)
        length = re.search(r'id="\w+_hfDelka"[^>]*value="(\d+)"', c)
        if not (names and when):
            continue
        d = dt.datetime.strptime(re.sub(r"\s+", "", when.group(1)), "%d.%m.%Y%H:%M:%S")
        dur = int(length.group(1)) if length else 60
        for court in html.unescape(names.group(1)).split(","):
            court = re.sub(r"\s+", " ", court).replace("Tenis hala ", "kurt ").strip()
            slots.append(("Sprint", d.date().isoformat(), d.hour * 60 + d.minute, dur, court))
    return slots


# ---------- Tenis Paradise (jdemenato.cz) ----------
# Den po dni; buňky timetableFree mají třídu timeNNN (minuty od půlnoci), půlhodinové kroky.

class ParadiseGrid(HTMLParser):
    def __init__(self):
        super().__init__()
        self.courts, self.free = [], []  # free: (col, start_min)
        self._in_court = False
        self._row, self._col, self._pending = -1, 0, {}  # pending: col -> rows still covered
        self._in_body = False

    def handle_starttag(self, tag, a):
        a = dict(a)
        cls = a.get("class") or ""
        if tag == "th" and "serviceTop" in cls:
            self._in_court = True
        elif tag == "tbody":
            self._in_body = True
        elif tag == "tr" and self._in_body:
            self._row += 1
            self._col = 0
            self._pending = {c: n - 1 for c, n in self._pending.items() if n > 1}
        elif tag == "td" and self._in_body:
            while self._col in self._pending:
                self._col += 1
            span = int(a.get("rowspan") or 1)
            if span > 1:
                self._pending[self._col] = span
            m = re.search(r"\btime(\d+)\b", cls)
            if "timetableFree" in cls and m:
                self.free.append((self._col, int(m.group(1))))
            self._col += 1

    def handle_data(self, data):
        if self._in_court and data.strip():
            self.courts.append(data.strip())
            self._in_court = False


def fetch_paradise(days):
    op = opener()
    get(op, PARADISE_BASE)  # založí session
    slots = []
    for day in days:
        page = get(op, f"{PARADISE_BASE}.navigation.daynavigationbar:selectdayinternal/{day.isoformat()}")
        p = ParadiseGrid()
        p.feed(page)
        halves = {}
        for col, start in p.free:
            court = p.courts[col] if col < len(p.courts) else f"kurt {col + 1}"
            halves.setdefault(court, set()).add(start)
        for court, starts in halves.items():
            name = court.replace("Umělý povrch", "kurt")
            for s in sorted(starts):
                if s + 30 in starts:  # aspoň celá hodina volno
                    slots.append(("Paradise", day.isoformat(), s, 60, name))
    return slots


# ---------- logika ----------

def in_window(slot):
    _, day, start, dur, _ = slot
    d = dt.date.fromisoformat(day)
    return d.weekday() in WEEKDAYS and start >= hm(WINDOW_FROM) and start + dur <= hm(WINDOW_TO)


def key(slot):
    hall, day, start, dur, court = slot
    return f"{hall}|{day}|{fmt(start)}|{court}"


def describe(slots):
    lines, by = [], {}
    for hall, day, start, dur, court in slots:
        by.setdefault((hall, day, start, dur), []).append(court)
    last_hall = None
    for (hall, day, start, dur), courts in sorted(by.items()):
        if hall != last_hall:
            lines.append(f"\n{hall.upper()} – {LINKS[hall]}")
            last_hall = hall
        d = dt.date.fromisoformat(day)
        lines.append(f"  {CZ_DAYS[d.weekday()]} {d.day}.{d.month}. {fmt(start)}–{fmt(start + dur)}  ({', '.join(sorted(courts))})")
    return "\n".join(lines).strip()


def short(slots):
    by = {}
    for hall, day, start, dur, court in slots:
        by.setdefault((hall, day, start), 0)
        by[(hall, day, start)] += 1
    parts = []
    for (hall, day, start), n in sorted(by.items()):
        d = dt.date.fromisoformat(day)
        parts.append(f"{hall[:3]} {CZ_DAYS[d.weekday()]}{d.day}.{d.month}. {fmt(start)}" + (f" {n}k" if n > 1 else ""))
    return "Volny kurt: " + "; ".join(parts)


def send_email(subject, body):
    to = os.environ.get("EMAIL_TO")
    user, pw = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD")
    if not (to and user and pw):
        return False
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtp.gmail.com"), 465, timeout=30) as s:
        s.login(user, pw)
        s.sendmail(user, [a.strip() for a in to.split(",")], msg.as_string())
    return True


def send_sms(text):
    """SMS přes Twilio (TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM, SMS_TO)."""
    sid, token = os.environ.get("TWILIO_SID"), os.environ.get("TWILIO_TOKEN")
    frm, to = os.environ.get("TWILIO_FROM"), os.environ.get("SMS_TO")
    if not (sid and token and frm and to):
        return False
    data = urllib.parse.urlencode({"From": frm, "To": to, "Body": text[:600]}).encode()
    req = urllib.request.Request(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", data=data)
    import base64
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode())
    urllib.request.urlopen(req, timeout=30).read()
    return True


def send_push(title, text, click=None):
    """Bezplatná push notifikace přes ntfy.sh (NTFY_TOPIC) – aplikace ntfy v mobilu."""
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return False
    msg = {"topic": topic, "title": title, "message": text[:3900], "priority": 4, "tags": ["tennis"]}
    if click:
        msg["click"] = click
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(msg).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()
    return True


def main():
    dry = "--dry-run" in sys.argv
    today = dt.date.today()
    days = [today + dt.timedelta(n) for n in range(DAYS_AHEAD) if (today + dt.timedelta(n)).weekday() in WEEKDAYS]

    now_min = dt.datetime.now().hour * 60 + dt.datetime.now().minute
    current, errors = [], []
    for name, fn in (("Sprint", fetch_sprint), ("Paradise", lambda: fetch_paradise(days))):
        try:
            current += fn()
        except Exception as e:  # jedna hala nesmí shodit druhou
            errors.append(f"{name}: {e}")
    current = [s for s in current if in_window(s) and not (s[1] == today.isoformat() and s[2] <= now_min)]

    first_run = not STATE_FILE.exists()
    prev = set(json.loads(STATE_FILE.read_text())["free"]) if not first_run else set()
    # hala, která selhala, si nechá starý stav (aby se po výpadku neposílaly "nové" termíny)
    failed = {e.split(":")[0] for e in errors}
    keep = {k for k in prev if k.split("|")[0] in failed}
    now_keys = {key(s) for s in current} | keep
    new = [s for s in current if key(s) not in prev]

    print(f"{dt.datetime.now():%Y-%m-%d %H:%M} volných: {len(current)}, nových: {len(new)}" + (f", chyby: {errors}" if errors else ""))
    if new:
        print(describe(new))

    if new and not dry:
        title = ("Aktuálně volné kurty" if first_run else "Uvolnil se kurt!") + f" ({WINDOW_FROM}–{WINDOW_TO}, po–pá)"
        body = describe(new) + "\n\nRychle rezervuj – kdo dřív přijde…"
        send_email(title, body)
        halls = {s[0] for s in new}
        send_push(title, describe(new), LINKS[halls.pop()] if len(halls) == 1 else None)
        if not first_run:
            send_sms(short(new))

    if not dry:
        STATE_FILE.write_text(json.dumps({"checked": dt.datetime.now().isoformat(timespec="seconds"),
                                          "free": sorted(now_keys), "errors": errors}, ensure_ascii=False, indent=1))
    return 1 if len(errors) == 2 else 0


if __name__ == "__main__":
    sys.exit(main())
