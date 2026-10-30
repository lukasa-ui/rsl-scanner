"""Erweiterungen für Depot, Watchlist, Trendqualität und RSL-Momentum-Stop."""

import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

PORTFOLIO_DATEI = "portfolio.json"


def neues_portfolio():
    return {"depot": {}, "watchlist": {}}


def portfolio_laden(github):
    """Lädt Depot und Watchlist. Technische Fehler werden bewusst weitergegeben."""
    inhalt, _ = github.lies_datei(PORTFOLIO_DATEI)

    # Eine nicht vorhandene Datei bedeutet ein neues Portfolio.
    # GitHub-Verbindungs- und Berechtigungsfehler müssen dagegen sichtbar bleiben.
    if inhalt is None or not inhalt.strip():
        return neues_portfolio()

    try:
        daten = json.loads(inhalt)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{PORTFOLIO_DATEI} enthält kein gültiges JSON. "
            "Die Datei wurde nicht überschrieben."
        ) from exc

    if not isinstance(daten, dict):
        raise ValueError(f"{PORTFOLIO_DATEI} muss ein JSON-Objekt enthalten.")

    depot = daten.get("depot", {})
    watchlist = daten.get("watchlist", {})

    if not isinstance(depot, dict) or not isinstance(watchlist, dict):
        raise ValueError(
            f"{PORTFOLIO_DATEI}: 'depot' und 'watchlist' müssen Objekte sein. "
            "Die Datei wurde nicht überschrieben."
        )

    daten["depot"] = depot
    daten["watchlist"] = watchlist
    return daten


def portfolio_speichern(github, daten):
    """Speichert Depot und Watchlist dauerhaft auf GitHub."""
    if not isinstance(daten, dict):
        raise TypeError("Das Portfolio muss ein Dictionary sein.")

    daten.setdefault("depot", {})
    daten.setdefault("watchlist", {})

    github.schreibe_datei(
        PORTFOLIO_DATEI,
        json.dumps(daten, ensure_ascii=False, indent=2),
        "Depot und Watchlist aktualisiert",
    )


def depot_hinzufuegen(daten, ticker, name, rsl):
    """Fügt eine Position hinzu. Bei erneutem Hinzufügen gilt ein neuer Referenzwert."""
    if rsl is None or pd.isna(rsl):
        raise ValueError("Für diesen Titel liegt kein gültiger RSL-Wert vor.")

    ticker = str(ticker).strip().upper()
    if not ticker:
        raise ValueError("Der Ticker darf nicht leer sein.")

    daten.setdefault("depot", {})
    daten.setdefault("watchlist", {})
    daten["depot"][ticker] = {
        "name": str(name),
        "referenz_rsl": float(rsl),
        "hinzugefuegt": datetime.now(timezone.utc).isoformat(),
        "stop_aktiv": False,
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

    daten["watchlist"][ticker] = {
        "name": str(name),
        "hinzugefuegt": datetime.now(timezone.utc).isoformat(),
    }


def depot_entfernen(daten, ticker):
    daten.setdefault("depot", {}).pop(ticker, None)


def watchlist_entfernen(daten, ticker):
    daten.setdefault("watchlist", {}).pop(ticker, None)


def trendqualitaet(kurse, wochen=26):
    """
    Signiertes R² einer linearen Regression auf logarithmierten Wochenkursen.
    Positiv = gleichmäßiger Aufwärtstrend, negativ = gleichmäßiger Abwärtstrend.
    """
    try:
        daten = pd.Series(kurse).dropna().astype(float).tail(wochen)
        daten = daten[daten > 0]

        if len(daten) < max(8, int(wochen * 0.6)):
            return None

        y = np.log(daten.to_numpy())
        x = np.arange(len(y), dtype=float)
        steigung, abschnitt = np.polyfit(x, y, 1)
        prognose = steigung * x + abschnitt

        gesamt = np.sum((y - np.mean(y)) ** 2)
        fehler = np.sum((y - prognose) ** 2)

        if gesamt <= 0:
            return 0.0

        r2 = max(0.0, min(1.0, 1.0 - fehler / gesamt))
        return float(math.copysign(r2, steigung))

    except (TypeError, ValueError, FloatingPointError):
        return None


def stop_status(position, aktueller_rsl):
    """Prüft den optionalen RSL-Momentum-Loss-Stop."""
    if not position.get("stop_aktiv", False):
        return "Aus"

    if aktueller_rsl is None or pd.isna(aktueller_rsl):
        return "Keine Daten"

    try:
        referenz = float(position.get("referenz_rsl", 0))
        schwelle = float(position.get("stop_schwelle", 0.75))
    except (TypeError, ValueError):
        return "Keine Referenz"

    if not math.isfinite(referenz) or not math.isfinite(schwelle):
        return "Keine Referenz"
    if referenz <= 0 or not 0 < schwelle <= 1:
        return "Keine Referenz"

    if position.get("stop_ausgeloest", False):
        return "Ausgelöst"

    grenzwert = referenz * schwelle

    if float(aktueller_rsl) <= grenzwert:
        return "Ausgelöst"

    if float(aktueller_rsl) <= grenzwert * 1.10:
        return "Nähert sich"

    return "Sicher"


def stop_einmalig_ausloesen(position, aktueller_rsl):
    """Markiert den Stop dauerhaft als ausgelöst; Speichern übernimmt die App."""
    status = stop_status(position, aktueller_rsl)

    if status == "Ausgelöst":
        position["stop_ausgeloest"] = True

    return status
