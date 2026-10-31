"""Depot, Watchlist, signierte R²-Trendqualität und RSL-Momentum-Stop."""

import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

PORTFOLIO_DATEI = "portfolio.json"


def neues_portfolio():
    return {"depot": {}, "watchlist": {}}


def portfolio_laden(github):
    """Lädt das Portfolio. API-, Berechtigungs- und JSON-Fehler bleiben sichtbar."""
    inhalt, _ = github.lies_datei(PORTFOLIO_DATEI)
    if inhalt is None or not inhalt.strip():
        return neues_portfolio()
    try:
        daten = json.loads(inhalt)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{PORTFOLIO_DATEI} enthält ungültiges JSON. Nichts wurde überschrieben.") from exc
    if not isinstance(daten, dict) or not isinstance(daten.get("depot", {}), dict) or not isinstance(daten.get("watchlist", {}), dict):
        raise ValueError(f"{PORTFOLIO_DATEI}: 'depot' und 'watchlist' müssen Objekte sein.")
    daten.setdefault("depot", {})
    daten.setdefault("watchlist", {})
    return daten


def portfolio_speichern(github, daten):
    if not isinstance(daten, dict):
        raise TypeError("Das Portfolio muss ein Dictionary sein.")
    daten.setdefault("depot", {})
    daten.setdefault("watchlist", {})
    github.schreibe_datei(PORTFOLIO_DATEI, json.dumps(daten, ensure_ascii=False, indent=2),
                          "Depot und Watchlist aktualisiert")


def _gueltiger_kurs(kurs):
    try:
        wert = float(kurs)
    except (TypeError, ValueError):
        return None
    return wert if math.isfinite(wert) and wert > 0 else None


def depot_hinzufuegen(daten, ticker, name, rsl, aufnahme_kurs=None, sektor=None, rsl_wochen=26):
    """Position mit dokumentiertem Referenzkurs und standardmäßig aktivem Stop aufnehmen."""
    ticker = str(ticker).strip().upper()
    if not ticker or rsl is None or not math.isfinite(float(rsl)) or float(rsl) <= 0:
        raise ValueError("Ticker und gültiger RSL sind erforderlich.")
    daten.setdefault("depot", {})
    daten.setdefault("watchlist", {})
    if ticker in daten["depot"]:
        raise ValueError("Diese Aktie ist bereits im Depot. Der Referenzwert bleibt unverändert.")
    daten["depot"][ticker] = {
        "name": str(name or ticker),
        "referenz_rsl": float(rsl),
        "rsl_wochen": int(rsl_wochen),
        "hinzugefuegt": datetime.now(timezone.utc).isoformat(),
        "aufnahme_kurs": _gueltiger_kurs(aufnahme_kurs),
        "sektor": sektor if sektor and sektor != "Unbekannt" else None,
        "stop_aktiv": True,
        "stop_schwelle": 0.75,
        "stop_ausgeloest": False,
    }
    daten["watchlist"].pop(ticker, None)


def watchlist_hinzufuegen(daten, ticker, name):
    ticker = str(ticker).strip().upper()
    if not ticker:
        raise ValueError("Der Ticker darf nicht leer sein.")
    daten.setdefault("depot", {})
    daten.setdefault("watchlist", {})
    if ticker in daten["depot"]:
        raise ValueError("Die Aktie befindet sich bereits im Depot.")
    if ticker in daten["watchlist"]:
        raise ValueError("Die Aktie befindet sich bereits auf der Watchlist.")
    daten["watchlist"][ticker] = {
        "name": str(name or ticker), "hinzugefuegt": datetime.now(timezone.utc).isoformat()
    }


def depot_entfernen(daten, ticker):
    daten.setdefault("depot", {}).pop(ticker, None)


def watchlist_entfernen(daten, ticker):
    daten.setdefault("watchlist", {}).pop(ticker, None)


def trendqualitaet(kurse, wochen=26):
    """Signiertes R² aus log(Wochenschlusskurs) gegen Zeit.

    Betrag = R² der Regression (0..1); Vorzeichen = Trendsteigung.
    Ein negatives Ergebnis ist damit KEIN gewöhnliches mathematisches R².
    """
    try:
        wochen = int(wochen)
        daten = pd.Series(kurse).dropna().astype(float).tail(wochen)
        if len(daten) < max(8, int(wochen * 0.6)) or not np.isfinite(daten).all() or (daten <= 0).any():
            return None
        y = np.log(daten.to_numpy())
        x = np.arange(len(y), dtype=float)
        steigung, abschnitt = np.polyfit(x, y, 1)
        gesamt = float(np.sum((y - np.mean(y)) ** 2))
        if gesamt <= 1e-22:
            return 0.0
        fehler = float(np.sum((y - (steigung * x + abschnitt)) ** 2))
        r2 = float(np.clip(1.0 - fehler / gesamt, 0.0, 1.0))
        return -r2 if steigung < 0 else r2
    except (TypeError, ValueError, FloatingPointError, np.linalg.LinAlgError):
        return None


def rsl_vorheriger_handelstag(kurse, wochen=26):
    """RSL bis zum vorletzten vorhandenen Tageskurs, keine Kursänderung als Ersatz."""
    import rsl_kern as k
    s = pd.Series(kurse).dropna()
    if len(s) < 2:
        return None
    return k.rsl(k.wochenschluesse(s.iloc[:-1]), int(wochen))


def tagesveraenderung(kurse):
    s = pd.Series(kurse).dropna().astype(float)
    if len(s) < 2 or float(s.iloc[-2]) <= 0:
        return None
    return (float(s.iloc[-1]) / float(s.iloc[-2]) - 1.0) * 100.0


def stop_status(position, aktueller_rsl):
    """Prüft Stop gegen ursprünglichen RSL, inklusive bereits gespeicherter Auslösung."""
    if not position.get("stop_aktiv", False):
        return "Aus"
    if position.get("stop_ausgeloest", False):
        return "Ausgelöst"
    if aktueller_rsl is None or pd.isna(aktueller_rsl):
        return "Keine Daten"
    try:
        referenz = float(position.get("referenz_rsl"))
        schwelle = float(position.get("stop_schwelle", 0.75))
        aktuell = float(aktueller_rsl)
    except (TypeError, ValueError):
        return "Keine Referenz"
    if not all(map(math.isfinite, [referenz, schwelle, aktuell])) or referenz <= 0 or not 0 < schwelle <= 1:
        return "Keine Referenz"
    grenzwert = referenz * schwelle
    if aktuell <= grenzwert:
        return "Ausgelöst"
    if aktuell <= grenzwert * 1.10:
        return "Nähert sich"
    return "Sicher"


def stop_einmalig_ausloesen(position, aktueller_rsl):
    """Setzt nur bei aktiviertem Stop den gespeicherten Alarm. Reset ausdrücklich manuell."""
    status = stop_status(position, aktueller_rsl)
    if position.get("stop_aktiv", False) and status == "Ausgelöst":
        position["stop_ausgeloest"] = True
    return status


def rendite_seit_aufnahme(position, kurse):
    """Entwicklung zum BEIM AUFNEHMEN gespeicherten Kurs. Keine echte Kaufkursrendite."""
    basis = _gueltiger_kurs(position.get("aufnahme_kurs"))
    s = pd.Series(kurse).dropna()
    if basis is None or s.empty:
        return None
    zuletzt = _gueltiger_kurs(s.iloc[-1])
    return None if zuletzt is None else (zuletzt / basis - 1) * 100
