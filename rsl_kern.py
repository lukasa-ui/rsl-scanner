"""
Rechenkern des RSL-Scanners (ohne Oberfläche) – wird von der App (app.py) und
der Freitags-E-Mail (wochenmail.py) gemeinsam genutzt, damit beide gleich rechnen.

RSL nach Levy = aktueller Kurs / Durchschnitt der letzten n Wochenschlusskurse (Standard 26).
"""

import datetime as dt
import io
import re
import time
from pathlib import Path

import pandas as pd

BASIS = Path(__file__).parent

LISTEN_ORDNER = BASIS / "listen"

WIKI = "https://en.wikipedia.org/wiki/"
GITHUB_SP500 = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
NASDAQ_API = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"

# Indizes in der Reihenfolge der Auswahlliste (nach Bedeutung/Beliebtheit).
# "quellen": Live-Quellen, die der Reihe nach probiert werden. Klappt keine, wird die hinterlegte Liste
# im Ordner "indizes" verwendet (und ein Hinweis angezeigt). Ohne Live-Quelle gilt nur die hinterlegte Liste.
INDIZES = {
    "S&P 500": {"quellen": [("csv", GITHUB_SP500), ("wiki", WIKI + "List_of_S%26P_500_companies")],
                "endung": "", "minimum": 450},
    "Nasdaq-100": {"quellen": [("nasdaq", NASDAQ_API), ("wiki", WIKI + "Nasdaq-100")],
                   "endung": "", "minimum": 90},
    "Dow Jones": {"quellen": [("wiki", WIKI + "List_of_Dow_Jones_Industrial_Average_companies")],
                  "endung": "", "minimum": 28},
    "DAX": {"quellen": [], "endung": ".DE", "minimum": 0},
    "Euro Stoxx 50": {"quellen": [], "endung": "", "minimum": 0},
    "MDAX": {"quellen": [], "endung": ".DE", "minimum": 0},
    "TecDAX": {"quellen": [], "endung": ".DE", "minimum": 0},
    "SDAX": {"quellen": [], "endung": ".DE", "minimum": 0},
    "FTSE MIB": {"quellen": [("wiki", WIKI + "FTSE_MIB")], "endung": ".MI", "minimum": 35},
    "ATX": {"quellen": [], "endung": ".VI", "minimum": 0},
    "Global Challenges Index": {"quellen": [], "endung": "", "minimum": 0},
    "LuxX": {"quellen": [], "endung": "", "minimum": 0},
}
QUELLEN_NAME = {"csv": "GitHub (datasets/s-and-p-500-companies)", "nasdaq": "nasdaq.com", "wiki": "Wikipedia"}
ALLE = "Planspiel Börse"   # alle Indizes außer S&P 500 + alle eigenen Listen


# ------------------------------------------------------------------ Listen & Ticker

def lese_tickertext(text: str) -> dict[str, str]:
    """Liest Ticker aus Text. Ein oder mehrere Ticker pro Zeile (getrennt durch Leerzeichen,
    Komma oder Semikolon); alles hinter # ist der Name/Kommentar. Ergebnis: {Ticker: Name}."""
    ergebnis: dict[str, str] = {}
    for zeile in text.splitlines():
        teil, _, kommentar = zeile.partition("#")
        ticker = [t.strip().upper() for t in re.split(r"[\s,;]+", teil) if t.strip()]
        for t in ticker:
            ergebnis.setdefault(t, kommentar.strip() if len(ticker) == 1 else "")
    return ergebnis


ISIN_MUSTER = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def isin_zu_ticker(isin: str) -> str | None:
    """Sucht den Yahoo-Ticker zu einer ISIN. Bei deutschen/luxemburgischen/irischen Papieren
    wird ein deutscher Handelsplatz bevorzugt. Fehler (z. B. Rate-Limit) werden nicht gespeichert."""
    import yfinance as yf

    quotes = yf.Search(isin, max_results=10, news_count=0).quotes
    symbole = [q["symbol"] for q in quotes if q.get("symbol")]
    if not symbole:
        return None
    if isin[:2] in ("DE", "LU", "IE", "AT"):
        for endung in (".DE", ".F", ".DU", ".SG", ".MU", ".BE", ".HM", ".HA"):
            for s in symbole:
                if s.endswith(endung):
                    return s
    return symbole[0]


def isins_aufloesen(namen: dict[str, str], aufloeser=None) -> tuple[dict[str, str], list[str]]:
    """Ersetzt ISINs in {Ticker/ISIN: Name} durch Yahoo-Ticker. Gibt (neues dict, nicht gefundene) zurück."""
    isin_zu_ticker_ = aufloeser or isin_zu_ticker
    ergebnis, nicht_gefunden = {}, []
    for schluessel, name in namen.items():
        if not ISIN_MUSTER.match(schluessel):
            ergebnis.setdefault(schluessel, name)
            continue
        try:
            ticker = isin_zu_ticker_(schluessel)
        except Exception:
            ticker = None
        if ticker:
            ergebnis.setdefault(ticker, f"{name} ({schluessel})" if name else schluessel)
        else:
            nicht_gefunden.append(f"{name} ({schluessel})" if name else schluessel)
    return ergebnis, nicht_gefunden


def eigene_listen() -> dict[str, Path]:
    if not LISTEN_ORDNER.exists():
        return {}
    listen = {}
    for p in sorted(LISTEN_ORDNER.glob("*.txt")):
        name = p.stem.replace("_", " ").strip()
        listen[name.title()] = p
    return listen


ERSATZ_ORDNER = BASIS / "indizes"


def _spaltenname(c) -> str:
    """Spaltenüberschrift vereinheitlichen: letzte Ebene, ohne Fußnoten [1], klein."""
    if isinstance(c, tuple):
        c = c[-1]
    return re.sub(r"\[.*?\]", "", str(c)).replace("\xa0", " ").strip().lower()


def _finde_spalte(namen: list[str], gesucht: tuple[str, ...]) -> int | None:
    for i, n in enumerate(namen):
        if n in gesucht or any(n.startswith(g) for g in gesucht):
            return i
    return None


def _ist_aenderungstabelle(tab: pd.DataFrame) -> bool:
    """Tabelle der Indexänderungen (Kopf »Added | Removed«) erkennen – nicht verwechseln mit
    einer normalen Spalte wie »Date added« in der S&P-500-Tabelle."""
    if not isinstance(tab.columns, pd.MultiIndex):
        return False
    oben = " ".join(str(c).lower() for c in tab.columns.get_level_values(0))
    return "added" in oben or "removed" in oben


def _yahoo_ticker(t: str, endung: str) -> str:
    t = re.sub(r"\[.*?\]", "", str(t)).strip().split()[0].upper()
    if endung and "." not in t:
        return t + endung
    if not endung:
        return t.replace(".", "-").replace("/", "-")      # Yahoo schreibt BRK-B statt BRK.B
    return t


def tickertabelle_aus_html(html: str, endung: str, minimum: int) -> dict[str, str]:
    gefunden = []
    for tab in pd.read_html(io.StringIO(html)):
        if _ist_aenderungstabelle(tab):
            continue
        namen = [_spaltenname(c) for c in tab.columns]
        daten = tab
        if _finde_spalte(namen, ("ticker", "symbol")) is None and len(tab):
            # Überschrift steckt manchmal in der ersten Datenzeile
            erste = [_spaltenname(v) for v in tab.iloc[0]]
            if _finde_spalte(erste, ("ticker", "symbol")) is not None:
                namen, daten = erste, tab.iloc[1:]
        gefunden.append(", ".join(namen[:4]))
        ti = _finde_spalte(namen, ("ticker", "symbol"))
        ni = _finde_spalte(namen, ("company", "security", "name", "unternehmen"))
        if ti is None or len(daten) < minimum:
            continue
        ergebnis = {}
        for _, zeile in daten.iterrows():
            roh = str(zeile.iloc[ti]).strip()
            if roh and roh.lower() != "nan":
                ergebnis[_yahoo_ticker(roh, endung)] = str(zeile.iloc[ni]) if ni is not None else ""
        if len(ergebnis) >= minimum:
            return ergebnis
    raise RuntimeError("keine passende Tabelle (gefunden: " + " | ".join(gefunden[:6]) + ")")


def tickertabelle_aus_csv(text: str, endung: str) -> dict[str, str]:
    tab = pd.read_csv(io.StringIO(text))
    namen = [_spaltenname(c) for c in tab.columns]
    ti = _finde_spalte(namen, ("symbol", "ticker"))
    ni = _finde_spalte(namen, ("security", "name", "company"))
    if ti is None:
        raise RuntimeError("CSV ohne Symbol-Spalte")
    return {_yahoo_ticker(z.iloc[ti], endung): (str(z.iloc[ni]) if ni is not None else "")
            for _, z in tab.iterrows() if str(z.iloc[ti]).strip() not in ("", "nan")}


def _symbolzeilen(obj):
    """Sucht in verschachteltem JSON die Liste von Einträgen mit »symbol«."""
    if isinstance(obj, list) and obj and isinstance(obj[0], dict) and "symbol" in obj[0]:
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            r = _symbolzeilen(v)
            if r:
                return r
    return None


def tickertabelle_aus_nasdaq(daten: dict, endung: str) -> dict[str, str]:
    zeilen = _symbolzeilen(daten) or []
    return {_yahoo_ticker(z["symbol"], endung): z.get("companyName") or z.get("name") or ""
            for z in zeilen if z.get("symbol")}


BROWSER_KOPF = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/128.0 Safari/537.36",
    "Accept": "text/html,application/json,text/csv;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


def hole_live(art: str, url: str, endung: str, minimum: int) -> dict[str, str]:
    import requests

    kopf = dict(BROWSER_KOPF)
    if art == "nasdaq":
        kopf.update({"Accept": "application/json, text/plain, */*",
                     "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"})
    antwort = requests.get(url, headers=kopf, timeout=30)
    antwort.raise_for_status()
    if art == "csv":
        ergebnis = tickertabelle_aus_csv(antwort.text, endung)
    elif art == "nasdaq":
        ergebnis = tickertabelle_aus_nasdaq(antwort.json(), endung)
    else:
        ergebnis = tickertabelle_aus_html(antwort.text, endung, minimum)
    if len(ergebnis) < minimum:
        raise RuntimeError(f"nur {len(ergebnis)} Werte erhalten")
    return ergebnis


def ersatzliste(name: str) -> Path:
    return ERSATZ_ORDNER / (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") + ".txt")


def lade_index(name: str) -> tuple[dict[str, str], str, bool]:
    """Gibt (Ticker->Name, Herkunft, ist_live) zurück. Probiert die Live-Quellen der Reihe nach,
    sonst die hinterlegte Liste."""
    cfg = INDIZES[name]
    fehler = []
    for art, url in cfg["quellen"]:
        try:
            return hole_live(art, url, cfg["endung"], cfg["minimum"]), \
                f"aktuell von {QUELLEN_NAME[art]}", True
        except Exception as e:
            fehler.append(f"{QUELLEN_NAME[art]}: {type(e).__name__} {str(e)[:120]}")
    datei = ersatzliste(name)
    if not datei.exists():
        raise RuntimeError("keine Quelle erreichbar – " + "; ".join(fehler))
    text = datei.read_text(encoding="utf-8")
    stand = re.search(r"Stand ([0-9.]+)", text)
    herkunft = f"hinterlegte Liste{' vom ' + stand.group(1) if stand else ''}"
    if fehler:
        herkunft += " – Live-Abruf fehlgeschlagen (" + "; ".join(fehler) + ")"
    return lese_tickertext(text), herkunft, not cfg["quellen"]


# ------------------------------------------------------------------ Kurse & RSL

def lade_kurse(ticker: tuple[str, ...], versuche: int = 1, pause: int = 60) -> tuple[pd.DataFrame, str]:
    """Tägliche Schlusskurse der letzten 2 Jahre. Gibt (Kurse, Fehlermeldung) zurück.
    Bei versuche > 1 wird nach einer Pause erneut probiert, wenn Yahoo nichts liefert."""
    for nr in range(versuche):
        kurse, fehler = _lade_kurse_einmal(ticker)
        if not kurse.empty:
            return kurse, fehler
        if nr + 1 < versuche:
            time.sleep(pause)
    return kurse, fehler


def _lade_kurse_einmal(ticker: tuple[str, ...]) -> tuple[pd.DataFrame, str]:
    import yfinance as yf

    teile, fehler = [], ""
    for i in range(0, len(ticker), 100):
        paket = list(ticker[i:i + 100])
        try:
            daten = yf.download(paket, period="2y", interval="1d", auto_adjust=True,
                                progress=False, threads=True)
        except Exception as e:                    # z. B. Rate-Limit
            fehler = str(e)
            continue
        if daten is None or daten.empty:
            continue
        close = daten["Close"]
        if isinstance(close, pd.Series):
            close = close.to_frame(name=paket[0])
        teile.append(close)
        if i + 100 < len(ticker):
            time.sleep(1)                         # Yahoo schonen
    if not teile:
        return pd.DataFrame(), fehler
    kurse = pd.concat(teile, axis=1)
    kurse = kurse.loc[:, ~kurse.columns.duplicated()]
    if getattr(kurse.index, "tz", None) is not None:
        kurse.index = kurse.index.tz_localize(None)
    return kurse, fehler


def wochenschluesse(s: pd.Series) -> pd.Series:
    """Schlusskurs jeder Woche (Freitag bzw. letzter Handelstag); die laufende Woche
    enthält den aktuellsten Kurs."""
    return s.dropna().resample("W-FRI").last().dropna()


def rsl(reihe: pd.Series, n: int) -> float | None:
    if len(reihe) < n:
        return None
    return float(reihe.iloc[-1] / reihe.iloc[-n:].mean())


def screene(kurse: pd.DataFrame, namen: dict[str, str], n: int, modus: str):
    """Rangliste nach RSL. Enthält auch die RSL von vor 4 Wochen und die Rangveränderung
    gegenüber der Vorwoche (Δ Rang > 0 = aufgestiegen)."""
    zeilen, fehlend = [], []
    heute = pd.Timestamp(dt.date.today())
    vor4 = 4 if modus == "wochen" else 20          # 4 Wochen zurück
    vor1 = 1 if modus == "wochen" else 5           # 1 Woche zurück
    for t in kurse.columns:
        s = kurse[t].dropna()
        if s.empty:
            fehlend.append(t)
            continue
        reihe = wochenschluesse(s) if modus == "wochen" else s
        wert = rsl(reihe, n)
        if wert is None:
            fehlend.append(t)
            continue
        stand = s.index[-1]
        zeilen.append({
            "Ticker": t,
            "Name": namen.get(t, ""),
            "RSL": wert,
            "RSL vor 4 Wo.": rsl(reihe.iloc[:-vor4], n) if len(reihe) > vor4 else None,
            "_rsl_vorwoche": rsl(reihe.iloc[:-vor1], n) if len(reihe) > vor1 else None,
            "Kurs": float(reihe.iloc[-1]),
            f"Ø {n} {'Wo.' if modus == 'wochen' else 'Tage'}": float(reihe.iloc[-n:].mean()),
            "Stand": stand.date(),
            "Veraltet": (heute - stand).days > 10,
        })
    df = pd.DataFrame(zeilen)
    if df.empty:
        return df, fehlend
    df = df.sort_values("RSL", ascending=False).reset_index(drop=True)
    df.insert(0, "Rang", range(1, len(df) + 1))
    df["Rang %"] = (df["Rang"] / len(df) * 100).round(1)
    vorwoche = df["_rsl_vorwoche"].rank(ascending=False, method="first")
    df["Rang Vorwoche"] = vorwoche.astype("Int64")
    df["Δ Rang"] = (df["Rang Vorwoche"] - df["Rang"]).astype("Int64")
    df["Rang % Vorwoche"] = (df["Rang Vorwoche"] / int(df["_rsl_vorwoche"].notna().sum() or 1) * 100).round(1)
    df = df.drop(columns="_rsl_vorwoche")
    vorne = ["Rang", "Δ Rang", "Ticker", "RSL", "RSL vor 4 Wo.", "Name"]
    df = df[vorne + [c for c in df.columns if c not in vorne]]
    return df, fehlend


# ------------------------------------------------------------------ Auswahl zusammenstellen

def sammle_universum(auswahl: list[str], listen: dict[str, Path], index_lader=None):
    """Sammelt die Ticker aller ausgewählten Listen/Indizes.
    Gibt (Ticker->Name, Herkunft [(Quelle, Anzahl, Text, ok)], Fehler [(Quelle, Text)]) zurück."""
    index_lader = index_lader or lade_index
    quellen = list(auswahl)
    if ALLE in quellen:
        quellen.remove(ALLE)
        quellen += [i for i in list(INDIZES) + list(listen) if i != "S&P 500" and i not in quellen]
    namen: dict[str, str] = {}
    herkunft, fehler = [], []
    for quelle in quellen:
        try:
            if quelle in listen:
                neu = lese_tickertext(listen[quelle].read_text(encoding="utf-8"))
            elif quelle in INDIZES:
                neu, text, ok = index_lader(quelle)
                herkunft.append((quelle, len(neu), text, ok))
            else:
                raise RuntimeError("unbekannte Liste bzw. unbekannter Index")
            for t, name in neu.items():
                namen.setdefault(t, name)
        except Exception as e:
            fehler.append((quelle, str(e)))
    return namen, herkunft, fehler


# ------------------------------------------------------------------ Depot

DEPOT_DATEI = BASIS / "depot.txt"


def lade_depot() -> dict[str, str]:
    """Depot-Positionen aus depot.txt (Ticker oder ISIN, Name hinter #)."""
    if not DEPOT_DATEI.exists():
        return {}
    return lese_tickertext(DEPOT_DATEI.read_text(encoding="utf-8"))


def depot_signal(rang_prozent: float, wert: float, grenze: float) -> str:
    return "Halten" if (rang_prozent <= grenze and wert >= 1) else "Verkaufen"


def depot_markieren(df: pd.DataFrame, depot: dict[str, str], grenze: float) -> pd.DataFrame:
    """Fügt eine Spalte »Depot« hinzu: Signal für Depotwerte, sonst leer."""
    if not depot or df.empty:
        return df
    df = df.copy()
    df["Depot"] = [
        depot_signal(rp, w, grenze) if t in depot else ""
        for t, rp, w in zip(df["Ticker"], df["Rang %"], df["RSL"])
    ]
    spalten = list(df.columns)
    spalten.insert(spalten.index("Name"), spalten.pop(spalten.index("Depot")))
    return df[spalten]


def depot_uebersicht(df: pd.DataFrame, depot: dict[str, str], grenze: float) -> pd.DataFrame:
    """Alle Depotwerte mit Rang, RSL und Signal – auch solche, die im Scan nicht vorkommen."""
    zeilen = []
    for t, name in depot.items():
        treffer = df[df["Ticker"] == t]
        if treffer.empty:
            zeilen.append({"Ticker": t, "Name": name, "Rang": None, "Rang %": None, "RSL": None,
                           "RSL vor 4 Wo.": None, "Δ Rang": None, "Signal": "nicht im Scan"})
        else:
            z = treffer.iloc[0]
            zeilen.append({"Ticker": t, "Name": name or z["Name"], "Rang": int(z["Rang"]),
                           "Rang %": z["Rang %"], "RSL": z["RSL"], "RSL vor 4 Wo.": z["RSL vor 4 Wo."],
                           "Δ Rang": z["Δ Rang"], "Signal": depot_signal(z["Rang %"], z["RSL"], grenze)})
    return pd.DataFrame(zeilen)


def neu_in_top(df: pd.DataFrame, grenze: float) -> pd.DataFrame:
    """Werte, die jetzt in den Top-x % sind, letzte Woche aber noch nicht."""
    if df.empty:
        return df
    jetzt = df["Rang %"] <= grenze
    vorher = df["Rang % Vorwoche"].fillna(101) <= grenze
    return df[jetzt & ~vorher]


# ------------------------------------------------------------------ Details zu einem Wert

def wertentwicklung(s: pd.Series) -> dict[str, float | None]:
    """Kursentwicklung in % über verschiedene Zeiträume (aus Tageskursen)."""
    s = s.dropna()
    if s.empty:
        return {}
    letzter = s.iloc[-1]
    ende = s.index[-1]

    def seit(tage=None, datum=None):
        stichtag = datum if datum is not None else ende - pd.Timedelta(days=tage)
        frueher = s[s.index <= stichtag]
        return None if frueher.empty else (letzter / frueher.iloc[-1] - 1) * 100

    return {"1 Woche": seit(7), "1 Monat": seit(30), "3 Monate": seit(91), "6 Monate": seit(182),
            "1 Jahr": seit(365), "seit 1.1.": seit(datum=pd.Timestamp(ende.year, 1, 1) - pd.Timedelta(days=1))}


SEKTOREN = {
    "Technology": "Technologie", "Healthcare": "Gesundheit", "Financial Services": "Finanzen",
    "Consumer Cyclical": "Zyklischer Konsum", "Consumer Defensive": "Basiskonsum", "Industrials": "Industrie",
    "Energy": "Energie", "Utilities": "Versorger", "Real Estate": "Immobilien",
    "Basic Materials": "Grundstoffe", "Communication Services": "Kommunikation",
}
LAENDER = {
    "Germany": "Deutschland", "United States": "USA", "United Kingdom": "Großbritannien", "France": "Frankreich",
    "Netherlands": "Niederlande", "Switzerland": "Schweiz", "Italy": "Italien", "Spain": "Spanien",
    "Austria": "Österreich", "Sweden": "Schweden", "Denmark": "Dänemark", "Norway": "Norwegen",
    "Finland": "Finnland", "Belgium": "Belgien", "Luxembourg": "Luxemburg", "Japan": "Japan",
    "Canada": "Kanada", "Ireland": "Irland", "China": "China", "Portugal": "Portugal",
}


def kennzahlen(ticker: str) -> dict[str, str]:
    """Wichtige Kennzahlen von Yahoo (soweit vorhanden), schon fürs Anzeigen formatiert."""
    import yfinance as yf

    info = yf.Ticker(ticker).info or {}
    w = info.get("currency") or info.get("financialCurrency") or ""

    def zahl(v, nk=2):
        return None if v in (None, "", "Infinity") else de_zahl(float(v), nk)

    def prozent(v, faktor=100):
        return None if v in (None, "") else de_zahl(float(v) * faktor, 1) + " %"

    def gross(v):
        if v in (None, ""):
            return None
        v = float(v)
        for grenze, einheit in ((1e12, "Bio."), (1e9, "Mrd."), (1e6, "Mio.")):
            if abs(v) >= grenze:
                return f"{de_zahl(v / grenze, 1)} {einheit} {w}".strip()
        return f"{de_zahl(v, 0)} {w}".strip()

    werte = {
        "Name": info.get("longName") or info.get("shortName"),
        "Art": {"EQUITY": "Aktie", "ETF": "ETF", "MUTUALFUND": "Fonds"}.get(info.get("quoteType"),
                                                                          info.get("quoteType")),
        "Sektor": SEKTOREN.get(info.get("sector"), info.get("sector")),
        "Branche": info.get("industry"),
        "Land": LAENDER.get(info.get("country"), info.get("country")),
        "Börse": info.get("fullExchangeName") or info.get("exchange"),
        "Währung": w or None,
        "Marktkapitalisierung": gross(info.get("marketCap")),
        "Fondsvolumen": gross(info.get("totalAssets")),
        "KGV": zahl(info.get("trailingPE"), 1),
        "KGV (erwartet)": zahl(info.get("forwardPE"), 1),
        "KBV": zahl(info.get("priceToBook"), 1),
        "Dividendenrendite": prozent(info.get("trailingAnnualDividendYield")),
        "Gewinnmarge": prozent(info.get("profitMargins")),
        "Umsatzwachstum": prozent(info.get("revenueGrowth")),
        "Eigenkapitalrendite": prozent(info.get("returnOnEquity")),
        "Beta": zahl(info.get("beta"), 2),
        "52-Wochen-Hoch": zahl(info.get("fiftyTwoWeekHigh")),
        "52-Wochen-Tief": zahl(info.get("fiftyTwoWeekLow")),
        "Kursziel Analysten": zahl(info.get("targetMeanPrice")),
        "Empfehlung Analysten": {"strong_buy": "Stark kaufen", "buy": "Kaufen", "hold": "Halten",
                                 "underperform": "Unterdurchschnittlich", "sell": "Verkaufen"}.get(
                                     info.get("recommendationKey")),
        "Laufende Kosten (TER)": de_zahl(float(info["netExpenseRatio"]), 2) + " %"
        if info.get("netExpenseRatio") not in (None, "") else None,
        "Webseite": info.get("website"),
    }
    return {k: v for k, v in werte.items() if v not in (None, "", "nan")}


# ------------------------------------------------------------------ Formatierung

def de_zahl(v: float, nk: int = 2) -> str:
    return f"{v:,.{nk}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def de_rang_delta(v) -> str:
    if v is None or pd.isna(v):
        return "neu"
    v = int(v)
    return f"▲ {v}" if v > 0 else (f"▼ {-v}" if v < 0 else "=")


def als_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig")


def als_excel(df: pd.DataFrame) -> bytes:
    puffer = io.BytesIO()
    df.to_excel(puffer, index=False, sheet_name="RSL")
    return puffer.getvalue()


