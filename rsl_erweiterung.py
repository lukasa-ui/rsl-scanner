
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
    """Lädt Depot und Watchlist aus portfolio.json auf GitHub."""
    try:
        inhalt, _ = github.lies_datei(PORTFOLIO_DATEI)
        if not inhalt:
            return neues_portfolio()

        daten = json.loads(inhalt)
        if not isinstance(daten, dict):
            return neues_portfolio()

        daten.setdefault("depot", {})
        daten.setdefault("watchlist", {})
        return daten

    except Exception:
        return neues_portfolio()


def portfolio_speichern(github, daten):
    """Speichert Depot und Watchlist dauerhaft auf GitHub."""
    github.schreibe_datei(
        PORTFOLIO_DATEI,
        json.dumps(daten, ensure_ascii=False, indent=2),
        "Depot und Watchlist aktualisiert"
    )


def depot_hinzufuegen(daten, ticker, name, rsl):
    """Fügt eine Position hinzu. Bei erneutem Hinzufügen gilt ein neuer Referenzwert."""
    if rsl is None or pd.isna(rsl):
        raise ValueError("Für diesen Titel liegt kein gültiger RSL-Wert vor.")

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
    daten["watchlist"][ticker] = {
        "name": str(name),
        "hinzugefuegt": datetime.now(timezone.utc).isoformat(),
    }


def depot_entfernen(daten, ticker):
    daten["depot"].pop(ticker, None)


def watchlist_entfernen(daten, ticker):
    daten["watchlist"].pop(ticker, None)


def trendqualitaet(kurse, wochen=26):
    """
    Signiertes R² einer linearen Regression auf logarithmierten Wochenkursen.
    Wertebereich -1 bis +1.
    Positiv = gleichmäßiger Aufwärtstrend.
    Negativ = gleichmäßiger Abwärtstrend.
    Nahe 0 = schwacher oder unruhiger Trend.
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

    except Exception:
        return None


def stop_status(position, aktueller_rsl):
    """Prüft den optionalen RSL-Momentum-Loss-Stop."""
    if not position.get("stop_aktiv", False):
        return "Aus"

    if aktueller_rsl is None or pd.isna(aktueller_rsl):
        return "Keine Daten"

    referenz = float(position.get("referenz_rsl", 0))
    schwelle = float(position.get("stop_schwelle", 0.75))

    if referenz <= 0:
        return "Keine Referenz"

    grenzwert = referenz * schwelle

    if position.get("stop_ausgeloest", False):
        return "Ausgelöst"

    if aktueller_rsl <= grenzwert:
        return "Ausgelöst"

    if aktueller_rsl <= grenzwert * 1.10:
        return "Nähert sich"

    return "Sicher"


def stop_einmalig_ausloesen(position, aktueller_rsl):
    """Speichert, dass der Stop für diese Position bereits ausgelöst wurde."""
    status = stop_status(position, aktueller_rsl)

    if status == "Ausgelöst":
        position["stop_ausgeloest"] = True

    return status
