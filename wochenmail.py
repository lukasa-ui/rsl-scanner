"""
Freitags-E-Mail des RSL-Scanners.

Läuft automatisch freitags gegen 13 Uhr über GitHub Actions (.github/workflows/wochenmail.yml) oder von Hand:
    python wochenmail.py

Einstellungen: email_einstellungen.txt (welche Listen/Indizes, wie viele Werte …)
Zugangsdaten für den Versand kommen aus Umgebungsvariablen (bei GitHub: »Secrets«):
    SMTP_SERVER, SMTP_PORT, SMTP_BENUTZER, SMTP_PASSWORT, EMAIL_AN   (optional EMAIL_VON)
Fehlen sie, wird nur eine Vorschau »wochenmail_vorschau.html« gespeichert.
"""

import datetime as dt
import html
import io
import re
import os
import smtplib
import sys
from email.message import EmailMessage

import pandas as pd

import rsl_kern as k

EINSTELLUNGEN = k.BASIS / "email_einstellungen.txt"
GRUEN, ROT, GRAU = "#0F6B4F", "#B3261E", "#6B7A75"
TOP_HG = "#DDEFE6"


# ------------------------------------------------------------------ Einstellungen

STANDARD = {"scan": [], "top_prozent": 30.0, "anzahl": 30, "wochen": 26,
            "app_link": "https://rsl-lukas.streamlit.app", "aktiv": "ja"}


def einstellungen_aus_text(text: str) -> dict:
    cfg = dict(STANDARD, scan=[])
    for zeile in text.splitlines():
        zeile = zeile.split("#", 1)[0].strip()
        if "=" not in zeile:
            continue
        schluessel, wert = (t.strip() for t in zeile.split("=", 1))
        schluessel = schluessel.lower()
        if schluessel == "scan":
            cfg["scan"].append([t.strip() for t in wert.split(",") if t.strip()])
        elif schluessel == "top_prozent":
            cfg[schluessel] = float(wert.replace(",", "."))
        elif schluessel in ("anzahl", "wochen"):
            cfg[schluessel] = int(wert)
        else:
            cfg[schluessel] = wert
    return cfg


def einstellungen_als_text(cfg: dict) -> str:
    """Schreibt die Einstellungen im Format von email_einstellungen.txt (z. B. aus der App heraus)."""
    zeilen = [
        "# Einstellungen für die Freitags-E-Mail (am einfachsten in der App unter »E-Mail« ändern)",
        "# Jede Zeile »scan = …« wird eine eigene Rangliste in der E-Mail und ein eigenes Blatt in der Excel-Datei.",
        "# Mehrere Namen in EINER Zeile mit Komma trennen = eine gemeinsame Rangliste.",
        "",
    ]
    zeilen += [f"scan = {', '.join(gruppe)}" for gruppe in cfg["scan"]]
    zeilen += [
        "",
        "# Grün markiert werden die besten … Prozent (gleichzeitig Grenze für »Verkaufen« im Depot)",
        f"top_prozent = {k.de_zahl(cfg['top_prozent'], 0)}",
        "# So viele Werte stehen pro Rangliste im Text der E-Mail (0 = alle). Die vollständige Liste hängt immer als Excel an.",
        f"anzahl = {int(cfg['anzahl'])}",
        f"wochen = {int(cfg['wochen'])}",
        f"app_link = {cfg.get('app_link', '')}",
        "# E-Mail an/aus: ja oder nein",
        f"aktiv = {cfg.get('aktiv', 'ja')}",
        "",
    ]
    return "\n".join(zeilen)


def lies_einstellungen() -> dict:
    text = EINSTELLUNGEN.read_text(encoding="utf-8") if EINSTELLUNGEN.exists() else ""
    cfg = einstellungen_aus_text(text)
    if not cfg["scan"]:
        cfg["scan"] = [[k.ALLE]]
    return cfg


# ------------------------------------------------------------------ Berechnung

def berechne(cfg: dict) -> dict:
    listen = k.eigene_listen()
    abschnitte = []
    alle_namen: dict[str, str] = {}
    for auswahl in cfg["scan"]:
        namen, herkunft, fehler = k.sammle_universum(auswahl, listen)
        namen, isin_fehlend = k.isins_aufloesen(namen)
        abschnitte.append({"titel": " + ".join(auswahl), "namen": namen, "herkunft": herkunft,
                           "fehler": fehler, "isin_fehlend": isin_fehlend})
        for t, n in namen.items():
            alle_namen.setdefault(t, n)
    depot, _ = k.isins_aufloesen(k.lade_depot())
    for t, n in depot.items():
        alle_namen.setdefault(t, n)

    # Alle Kurse in einem Abruf (schont Yahoo); bei Sperre bis zu 3 Versuche mit Pause
    kurse, kursfehler = k.lade_kurse(tuple(sorted(alle_namen)), versuche=3, pause=120)
    if kurse.empty:
        raise RuntimeError(f"Keine Kursdaten von Yahoo erhalten. {kursfehler}")

    for a in abschnitte:
        spalten = [t for t in a["namen"] if t in kurse.columns]
        df, fehlend = k.screene(kurse[spalten], a["namen"], cfg["wochen"], "wochen")
        a["df"] = k.depot_markieren(df, depot, cfg["top_prozent"])
        a["fehlend"] = sorted(set(fehlend + [t for t in a["namen"] if t not in kurse.columns]))
    return {"abschnitte": abschnitte, "depot": depot}


# ------------------------------------------------------------------ E-Mail-Inhalt

def _name(n) -> str:
    """Name ohne angehängte ISIN in Klammern."""
    return re.sub(r"\s*\([A-Z]{2}[A-Z0-9]{9}[0-9]\)$", "", str(n))


def _rsl(v) -> str:
    return "–" if v is None or pd.isna(v) else k.de_zahl(v, 3)


def _delta_html(v) -> str:
    text = k.de_rang_delta(v)
    farbe = GRUEN if text.startswith("▲") else ROT if text.startswith("▼") else GRAU
    return f'<span style="color:{farbe}">{text}</span>'


def _tabelle(df: pd.DataFrame, grenze: float) -> str:
    zellen = 'style="padding:4px 6px;border-bottom:1px solid #eee;'
    kopf = ("<tr>" + "".join(
        f'<th style="padding:4px 6px;text-align:{a};border-bottom:2px solid #ccc;font-size:12px;color:#444">{t}</th>'
        for t, a in (("Rang", "right"), ("Δ", "right"), ("Ticker", "left"), ("Name", "left"),
                     ("RSL", "right"), ("vor 4 Wo.", "right"))) + "</tr>")
    zeilen = []
    for _, r in df.iterrows():
        hg = f"background:{TOP_HG};" if r["Rang %"] <= grenze else ""
        rsl_farbe = GRUEN if r["RSL"] >= 1 else ROT
        depot = r.get("Depot", "") or ""
        name = html.escape(_name(r["Name"])[:38]) + (f' <b style="color:{GRUEN if "Halten" in depot else ROT}">'
                                                   f'{html.escape(depot)}</b>' if depot else "")
        zeilen.append(
            f"<tr>"
            f'<td {zellen}{hg}text-align:right">{r["Rang"]}</td>'
            f'<td {zellen}{hg}text-align:right;white-space:nowrap">{_delta_html(r["Δ Rang"])}</td>'
            f'<td {zellen}{hg}white-space:nowrap"><b>{html.escape(r["Ticker"])}</b></td>'
            f'<td {zellen}{hg}">{name}</td>'
            f'<td {zellen}{hg}text-align:right;color:{rsl_farbe};font-weight:bold">{_rsl(r["RSL"])}</td>'
            f'<td {zellen}{hg}text-align:right;color:{GRAU}">{_rsl(r["RSL vor 4 Wo."])}</td>'
            f"</tr>")
    return ('<table style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px;width:100%">'
            + kopf + "".join(zeilen) + "</table>")


def baue_html(cfg: dict, daten: dict) -> str:
    grenze = cfg["top_prozent"]
    heute = dt.date.today().strftime("%d.%m.%Y")
    teile = [f'<div style="font-family:Arial,sans-serif;max-width:720px;color:#222">',
             f'<h2 style="margin-bottom:4px">📈 RSL-Wochenbericht vom {heute}</h2>',
             f'<p style="color:{GRAU};margin-top:0">RSL nach Levy, {cfg["wochen"]} Wochen · '
             f'grün hinterlegt = beste {k.de_zahl(grenze, 0)} % · Δ = Plätze seit letzter Woche</p>']

    # Depot (bewertet in der ersten Rangliste)
    if daten["depot"] and daten["abschnitte"]:
        ref = daten["abschnitte"][0]
        ueb = k.depot_uebersicht(ref["df"], daten["depot"], grenze)
        verkaufen = ueb[ueb["Signal"] == "Verkaufen"]
        teile.append(f'<h3>💼 Mein Depot <span style="font-weight:normal;color:{GRAU};font-size:13px">'
                     f'(bewertet in: {html.escape(ref["titel"])})</span></h3>')
        if not verkaufen.empty:
            teile.append(f'<p style="color:{ROT};font-weight:bold">Verkaufssignal: '
                         + ", ".join(f'{html.escape(t)} ({html.escape(_name(n)[:30])})'
                                     for t, n in zip(verkaufen["Ticker"], verkaufen["Name"])) + "</p>")
        else:
            teile.append(f'<p style="color:{GRUEN};font-weight:bold">Kein Verkaufssignal – alle Depotwerte halten.</p>')
        zeilen = "".join(
            f'<tr><td style="padding:3px 6px"><b>{html.escape(r.Ticker)}</b></td>'
            f'<td style="padding:3px 6px">{html.escape(_name(r.Name)[:34])}</td>'
            f'<td style="padding:3px 6px;text-align:right">{"–" if pd.isna(r.Rang) else int(r.Rang)}</td>'
            f'<td style="padding:3px 6px;text-align:right">{_rsl(r.RSL)}</td>'
            f'<td style="padding:3px 6px;font-weight:bold;color:'
            f'{GRUEN if r.Signal == "Halten" else ROT if r.Signal == "Verkaufen" else GRAU}">{r.Signal}</td></tr>'
            for r in ueb.itertuples())
        teile.append('<table style="border-collapse:collapse;font-size:13px">'
                     '<tr style="color:#444;font-size:12px"><th align="left">Ticker</th><th align="left">Name</th>'
                     '<th>Rang</th><th>RSL</th><th align="left">Signal</th></tr>' + zeilen + "</table>")

    for a in daten["abschnitte"]:
        df = a["df"]
        teile.append(f'<h3 style="margin-top:28px;border-top:1px solid #ddd;padding-top:12px">'
                     f'{html.escape(a["titel"])}</h3>')
        if df.empty:
            teile.append("<p>Keine Werte mit Kursdaten.</p>")
            continue
        im_top = int((df["Rang %"] <= grenze).sum())
        teile.append(f'<p style="color:{GRAU};margin-top:0">{len(df)} Werte · {im_top} in den besten '
                     f'{k.de_zahl(grenze, 0)} % · {int((df["RSL"] >= 1).sum())} mit RSL über 1</p>')
        neu = k.neu_in_top(df, grenze)
        if not neu.empty:
            rest = len(neu) - 15
            teile.append(f'<p>🚀 <b>Neu in den besten {k.de_zahl(grenze, 0)} % ({len(neu)}):</b> '
                         + ", ".join(f'{html.escape(r.Ticker)} ({html.escape(_name(r.Name)[:25])}, Rang {r.Rang})'
                                     for r in neu.head(15).itertuples())
                         + (f" und {rest} weitere (siehe App)" if rest > 0 else "") + "</p>")
        teile.append(_tabelle(df if cfg["anzahl"] <= 0 else df.head(cfg["anzahl"]), grenze))
        hinweise = [f"{q}: {h.split(' (')[0]}" for q, _, h, ok in a["herkunft"] if not ok]
        hinweise += [f"{q}: {t}" for q, t in a["fehler"]]
        if a["fehlend"] or a["isin_fehlend"]:
            hinweise.append(f"Ohne Kursdaten: {len(a['fehlend']) + len(a['isin_fehlend'])} Werte")
        if hinweise:
            teile.append(f'<p style="color:{GRAU};font-size:12px">' + "<br>".join(html.escape(h) for h in hinweise)
                         + "</p>")

    if cfg.get("app_link"):
        teile.append(f'<p style="margin-top:24px"><a href="{html.escape(cfg["app_link"])}">'
                     f'➜ Zur App (Charts, Kennzahlen, alle Werte)</a></p>')
    teile.append(f'<p style="color:{GRAU};font-size:11px">Vollständige Ranglisten als Excel im Anhang. '
                 f'Einstellungen: Datei email_einstellungen.txt im GitHub-Projekt. Kurse: Yahoo Finance.</p></div>')
    return "".join(teile)


def baue_excel(daten: dict) -> bytes:
    puffer = io.BytesIO()
    with pd.ExcelWriter(puffer) as writer:
        for a in daten["abschnitte"]:
            name = "".join(c for c in a["titel"] if c not in ':\\/?*[]')[:31] or "RSL"
            a["df"].to_excel(writer, sheet_name=name, index=False)
    return puffer.getvalue()


# ------------------------------------------------------------------ Versand

def sende(betreff: str, html_text: str, anhang: bytes | None = None):
    server = os.environ.get("SMTP_SERVER", "").strip()
    an = os.environ.get("EMAIL_AN", "").strip()
    if not server or not an:
        datei = k.BASIS / "wochenmail_vorschau.html"
        datei.write_text(html_text, encoding="utf-8")
        print(f"Keine Zugangsdaten (SMTP_SERVER/EMAIL_AN) – nur Vorschau gespeichert: {datei}")
        return
    port = int(os.environ.get("SMTP_PORT", "587") or 587)
    benutzer = os.environ.get("SMTP_BENUTZER", "").strip()
    passwort = os.environ.get("SMTP_PASSWORT", "")
    msg = EmailMessage()
    msg["Subject"] = betreff
    msg["From"] = os.environ.get("EMAIL_VON", "").strip() or benutzer
    msg["To"] = an
    msg.set_content("Dein RSL-Wochenbericht – bitte in einem E-Mail-Programm mit HTML-Ansicht öffnen.")
    msg.add_alternative(html_text, subtype="html")
    if anhang:
        msg.add_attachment(anhang, maintype="application",
                           subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           filename=f"rsl_{dt.date.today().isoformat()}.xlsx")
    if port == 465:
        with smtplib.SMTP_SSL(server, port, timeout=60) as smtp:
            smtp.login(benutzer, passwort)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(server, port, timeout=60) as smtp:
            smtp.starttls()
            smtp.login(benutzer, passwort)
            smtp.send_message(msg)
    print(f"E-Mail an {an} verschickt.")


def richtige_uhrzeit() -> bool:
    """Der Zeitplan hat zwei Zeilen (Sommer- und Winterzeit), weil GitHub nur in UTC rechnet.
    Es läuft nur die Zeile, die gerade 12:50 Uhr deutscher Zeit entspricht. Von Hand gestartet: immer."""
    plan = os.environ.get("ZEITPLAN", "").strip()
    if not plan:
        return True
    from zoneinfo import ZoneInfo
    sommerzeit = dt.datetime.now(ZoneInfo("Europe/Berlin")).utcoffset() == dt.timedelta(hours=2)
    return plan.startswith("50 10") if sommerzeit else plan.startswith("50 11")


def main():
    if not richtige_uhrzeit():
        print("Diese Zeitplan-Zeile ist in der aktuellen Jahreszeit nicht zuständig – übersprungen.")
        return
    cfg = lies_einstellungen()
    if cfg.get("aktiv", "ja").strip().lower() in ("nein", "no", "aus", "0"):
        print("E-Mail ist in email_einstellungen.txt ausgeschaltet (aktiv = nein).")
        return
    heute = dt.date.today().strftime("%d.%m.%Y")
    try:
        daten = berechne(cfg)
    except Exception as e:
        sende(f"RSL-Wochenbericht {heute}: Fehler",
              f"<p>Der Wochenbericht konnte nicht erstellt werden:</p><pre>{html.escape(str(e))}</pre>"
              f"<p>Meist sperrt Yahoo vorübergehend. Der Bericht lässt sich auf GitHub unter "
              f"»Actions → RSL-Wochenmail → Run workflow« erneut starten.</p>")
        raise
    erster = daten["abschnitte"][0]["df"] if daten["abschnitte"] else pd.DataFrame()
    verkaufen = 0
    if daten["depot"] and not erster.empty:
        ueb = k.depot_uebersicht(erster, daten["depot"], cfg["top_prozent"])
        verkaufen = int((ueb["Signal"] == "Verkaufen").sum())
    betreff = f"RSL-Wochenbericht {heute}" + (f" – {verkaufen} Verkaufssignal(e) im Depot" if verkaufen else "")
    sende(betreff, baue_html(cfg, daten), baue_excel(daten))


if __name__ == "__main__":
    try:
        main()
    except Exception as fehler:
        print(f"FEHLER: {fehler}", file=sys.stderr)
        sys.exit(1)
