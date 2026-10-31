"""Privat gespeicherte Depots: OIDC-Identität => getrennte Datei in PRIVATEM Repository.

Keine Nutzerdaten aus dem öffentlichen Code-Repository lesen oder dorthin schreiben.
"""
import hashlib
import hmac
import json
from datetime import datetime

import pandas as pd


def benutzer_pfad(sub, schluessel, anbieter='google'):
    """Der Dateiname verrät weder E-Mail noch Google-ID."""
    if not isinstance(sub, str) or not sub.strip() or not isinstance(schluessel, str) or len(schluessel) < 32:
        raise ValueError('Eine gültige Nutzerkennung und ein starker privater Schlüssel sind erforderlich.')
    msg = f'{anbieter}:{sub}'.encode('utf-8')
    digest = hmac.new(schluessel.encode('utf-8'), msg, hashlib.sha256).hexdigest()
    return f'users/{digest}.json'


def portfolio_pruefen(daten):
    if not isinstance(daten, dict) or not isinstance(daten.get('depot'), dict) or not isinstance(daten.get('watchlist'), dict):
        raise ValueError("Ungültiges Portfolio: 'depot' und 'watchlist' müssen Objekte sein.")
    if len(daten['depot']) > 2000 or len(daten['watchlist']) > 5000:
        raise ValueError('Das Portfolio überschreitet die zulässige Größe.')
    for sammlung in ('depot', 'watchlist'):
        for ticker, pos in daten[sammlung].items():
            if not isinstance(ticker, str) or not 1 <= len(ticker) <= 50 or not isinstance(pos, dict):
                raise ValueError('Portfolio enthält ungültige Ticker oder Positionen.')
    return daten


def repo_privat_pruefen(github):
    """Fail closed: keine Depotdaten in ein öffentliches GitHub-Repository schreiben."""
    response = github._anfrage('GET', '')
    response.raise_for_status()
    metadata = response.json()
    if metadata.get('private') is not True:
        raise ValueError('Das Depot-Repository muss auf GitHub als PRIVAT eingerichtet sein.')
    return True


def portfolio_laden(github, pfad):
    inhalt, _ = github.lies_datei(pfad)
    if inhalt is None:
        return {'depot': {}, 'watchlist': {}}
    try:
        daten = json.loads(inhalt)
    except json.JSONDecodeError as exc:
        raise ValueError('Depotdatei ist beschädigt. Aus Sicherheitsgründen keine Überschreibung.') from exc
    return portfolio_pruefen(daten)


def portfolio_speichern(github, pfad, daten):
    portfolio_pruefen(daten)
    github.schreibe_datei(pfad, json.dumps(daten, ensure_ascii=False, indent=2), 'Privates Nutzerdepot aktualisiert')


def import_aus_json(datei_bytes):
    if len(datei_bytes) > 2_000_000:
        raise ValueError('Die Importdatei ist zu groß.')
    try:
        daten = json.loads(datei_bytes.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('Keine gültige UTF-8-JSON-Datei.') from exc
    return portfolio_pruefen(daten)


def schlusskurs_am_aufnahmetag(position, kurse):
    """Historischer TagesSCHLUSSkurs, nie als tatsächlicher Kaufpreis ausgeben.

    Fehlt die Tageskerze, nur den letzten vorherigen verfügbaren Tag verwenden.
    Rückgabe (Kurs, Tagesdatum) oder None.
    """
    stamp = position.get('hinzugefuegt')
    if not stamp:
        return None
    try:
        tag = datetime.fromisoformat(str(stamp).replace('Z', '+00:00')).date()
    except (ValueError, TypeError):
        return None
    serie = pd.to_numeric(pd.Series(kurse), errors='coerce').dropna()
    if serie.empty or not isinstance(serie.index, pd.DatetimeIndex):
        return None
    try:
        # Vergleich über reine Kalendertage vermeidet tz-naive / tz-aware Konflikte.
        zeilen = serie.loc[[i.date() <= tag for i in serie.index]]
    except (ValueError, AttributeError, TypeError):
        return None
    if zeilen.empty or float(zeilen.iloc[-1]) <= 0:
        return None
    return float(zeilen.iloc[-1]), zeilen.index[-1].date().isoformat()


def nach_rsl_sortieren(eintraege):
    """(ticker, daten, aktueller_rsl)-Einträge mit fehlendem RSL am Ende."""
    def key(e):
        try:
            x = float(e[2])
            if pd.notna(x):
                return (0, -x, e[0])
        except (ValueError, TypeError):
            pass
        return (1, 0, e[0])
    return sorted(eintraege, key=key)
