"""
RSL-Scanner nach Robert A. Levy – Web-App (Streamlit)

RSL = aktueller Kurs / Durchschnitt der letzten 26 Wochenschlusskurse
(Anzahl Wochen in der App einstellbar). RSL > 1 = relative Stärke.

Kursdaten: Yahoo Finance über das Paket yfinance (dividenden-/split-bereinigt).
Eigene Aktienlisten liegen als .txt-Dateien im Ordner "listen" (ein Ticker pro Zeile,
Name als Kommentar hinter #).
"""

import datetime as dt
import io
import re
import time
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="RSL-Scanner", page_icon="📈", layout="wide")

LISTEN_ORDNER = Path(__file__).parent / "listen"

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


@st.cache_data(ttl=30 * 24 * 3600, show_spinner=False)
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


def isins_aufloesen(namen: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Ersetzt ISINs in {Ticker/ISIN: Name} durch Yahoo-Ticker. Gibt (neues dict, nicht gefundene) zurück."""
    ergebnis, nicht_gefunden = {}, []
    for schluessel, name in namen.items():
        if not ISIN_MUSTER.match(schluessel):
            ergebnis.setdefault(schluessel, name)
            continue
        try:
            ticker = isin_zu_ticker(schluessel)
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


ERSATZ_ORDNER = Path(__file__).parent / "indizes"


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


@st.cache_data(ttl=12 * 3600, show_spinner=False)
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

@st.cache_data(ttl=3600, show_spinner=False)
def lade_kurse(ticker: tuple[str, ...]) -> tuple[pd.DataFrame, str]:
    """Tägliche Schlusskurse der letzten 2 Jahre. Gibt (Kurse, Fehlermeldung) zurück."""
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
    zeilen, fehlend = [], []
    heute = pd.Timestamp(dt.date.today())
    for t in kurse.columns:
        s = kurse[t].dropna()
        reihe = wochenschluesse(s) if modus == "wochen" else s
        vor = 4 if modus == "wochen" else 20
        wert = rsl(reihe, n)
        if wert is None:
            fehlend.append(t)
            continue
        vorher = rsl(reihe.iloc[:-vor], n) if len(reihe) > vor else None
        stand = s.index[-1]
        zeilen.append({
            "Ticker": t,
            "Name": namen.get(t, ""),
            "RSL": wert,
            "RSL vor 4 Wo.": vorher,
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
    # Reihenfolge fürs Handy: Wichtiges zuerst
    vorne = ["Rang", "Ticker", "RSL", "RSL vor 4 Wo.", "Name"]
    df = df[vorne + [c for c in df.columns if c not in vorne]]
    return df, fehlend


def als_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig")


def als_excel(df: pd.DataFrame) -> bytes:
    puffer = io.BytesIO()
    df.to_excel(puffer, index=False, sheet_name="RSL")
    return puffer.getvalue()


def zeige_tabelle(df: pd.DataFrame):
    zahl = lambda v: "" if pd.isna(v) else f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    rsl_fmt = lambda v: "" if pd.isna(v) else f"{v:.3f}".replace(".", ",")
    ø_spalte = [c for c in df.columns if c.startswith("Ø")]
    stil = (df.style
            .format({"RSL": rsl_fmt, "RSL vor 4 Wo.": rsl_fmt, "Kurs": zahl,
                     **{c: zahl for c in ø_spalte},
                     "Rang %": lambda v: f"{v:.1f}".replace(".", ","),
                     "Stand": lambda d: d.strftime("%d.%m.%Y"),
                     "Veraltet": lambda b: "⚠️" if b else ""})
            .map(lambda v: "color:#1a7f37;font-weight:600" if v >= 1 else "color:#c62828;font-weight:600",
                 subset=["RSL"]))
    st.dataframe(stil, hide_index=True, width="stretch",
                 height=min(38 + 35 * len(df), 800))


# ------------------------------------------------------------------ Oberfläche

st.markdown("## 📈 RSL-Scanner nach Levy")

tab_scan, tab_einzel, tab_hilfe = st.tabs(["Scan", "Einzelwert / Suche", "Hilfe"])

# ---------------- Scan
with tab_scan:
    listen = eigene_listen()
    erste = [l for l in listen if l == "Meine Liste"]
    weitere = [l for l in listen if l != "Meine Liste"]
    optionen = erste + [ALLE] + list(INDIZES) + weitere
    auswahl = st.multiselect(
        "Was soll gescannt werden?", optionen,
        default=erste or optionen[:1],
        help="Eigene Listen (Ordner »listen«) und Indizes – mehrere kombinierbar.")
    zusatz = st.text_area(
        "Weitere Ticker (optional)", height=80,
        placeholder="z. B. SAP.DE ALV.DE AAPL oder ISINs wie DE0007164600 – auch ganze Listen")

    with st.expander("Einstellungen"):
        sp1, sp2 = st.columns(2)
        modus_text = sp1.radio("Berechnung", ["Wochen (Levy)", "Handelstage"], horizontal=True)
        modus = "wochen" if modus_text.startswith("Wochen") else "tage"
        if modus == "wochen":
            n = sp2.number_input("Anzahl Wochen", min_value=5, max_value=80, value=26, step=1)
        else:
            n = sp2.number_input("Anzahl Handelstage", min_value=20, max_value=400, value=130, step=5)
        sp3, sp4 = st.columns(2)
        top = sp3.number_input("Anzeigen: beste … Werte (0 = alle)", min_value=0, value=0, step=5)
        min_rsl = sp4.number_input("Nur RSL ab", min_value=0.0, value=0.0, step=0.01, format="%.2f",
                                   help="0 = kein Filter, z. B. 1,05")

    knopf1, knopf2 = st.columns([3, 2])
    starten = knopf1.button("🔍 Scan starten", type="primary", width="stretch")
    if knopf2.button("↻ Kurse neu abrufen", width="stretch",
                     help="Kurse werden 1 Stunde zwischengespeichert. Hiermit sofort neu laden."):
        lade_kurse.clear()
        st.toast("Zwischenspeicher geleert – beim nächsten Scan werden die Kurse neu geladen.")

    if starten:
        namen: dict[str, str] = {}
        herkunft_liste: list[tuple[str, int, str, bool]] = []
        quellen = list(auswahl)
        if ALLE in quellen:
            quellen.remove(ALLE)
            quellen += [i for i in list(INDIZES) + list(listen)
                        if i != "S&P 500" and i not in quellen]
        for quelle in quellen:
            try:
                if quelle in listen:
                    neu = lese_tickertext(listen[quelle].read_text(encoding="utf-8"))
                else:
                    with st.spinner(f"Lese Zusammensetzung {quelle} …"):
                        neu, herkunft, ok = lade_index(quelle)
                    herkunft_liste.append((quelle, len(neu), herkunft, ok))
                for t, name in neu.items():
                    namen.setdefault(t, name)
            except Exception as e:
                st.error(f"{quelle} konnte nicht geladen werden: {e}")
        for t, name in lese_tickertext(zusatz).items():
            namen.setdefault(t, name)

        isin_fehlend: list[str] = []
        if any(ISIN_MUSTER.match(t) for t in namen):
            with st.spinner("Suche Yahoo-Ticker zu den ISINs … (beim ersten Mal etwas länger)"):
                namen, isin_fehlend = isins_aufloesen(namen)

        if not namen:
            st.warning("Bitte eine Liste/einen Index auswählen oder Ticker eingeben.")
        else:
            with st.spinner(f"Lade Kurse für {len(namen)} Werte … (bei großen Indizes bis zu 1 Minute)"):
                kurse, fehler = lade_kurse(tuple(sorted(namen)))
            if kurse.empty:
                st.session_state.pop("ergebnis", None)
                if "rate" in fehler.lower() or "too many" in fehler.lower():
                    st.error("Yahoo hat die Anfrage vorübergehend gesperrt (zu viele Anfragen). "
                             "Bitte in 15–30 Minuten erneut versuchen.")
                else:
                    st.error("Keine Kursdaten erhalten. Ticker prüfen oder später erneut versuchen."
                             + (f"\n\nDetails: {fehler}" if fehler else ""))
            else:
                df, fehlend = screene(kurse, namen, int(n), modus)
                fehlend += [t for t in namen if t not in kurse.columns]
                fehlend += [f"{x} – bei Yahoo nicht gefunden" for x in isin_fehlend]
                st.session_state["ergebnis"] = {
                    "df": df, "fehlend": sorted(set(fehlend)), "n": int(n), "modus": modus,
                    "zeit": dt.datetime.now().strftime("%d.%m.%Y %H:%M"), "quellen": auswahl,
                    "herkunft": herkunft_liste,
                }

    erg = st.session_state.get("ergebnis")
    if erg and not erg["df"].empty:
        df = erg["df"]
        anzeige = df[df["RSL"] >= min_rsl] if min_rsl > 0 else df
        if top:
            anzeige = anzeige.head(int(top))
        einheit = "Wochen" if erg["modus"] == "wochen" else "Handelstage"
        st.markdown(f"#### Rangliste – RSL {erg['n']} {einheit}")
        st.markdown(f"**{len(df)}** Werte bewertet · **{int((df['RSL'] >= 1).sum())}** mit RSL über 1"
                    + (f" · angezeigt: {len(anzeige)}" if len(anzeige) != len(df) else ""))
        zeige_tabelle(anzeige)
        st.caption(f"Abgerufen: {erg['zeit']} · Kurse in Landeswährung der jeweiligen Börse · "
                   "⚠️ = seit über 10 Tagen kein neuer Kurs")
        for quelle, anzahl, herkunft, ok in erg.get("herkunft", []):
            if ok:
                st.caption(f"{quelle}: {anzahl} Werte – {herkunft}")
            else:
                st.warning(f"{quelle}: {anzahl} Werte – {herkunft}")
        if erg["fehlend"]:
            st.warning(f"Ohne ausreichende Kursdaten ({len(erg['fehlend'])}): " + ", ".join(erg["fehlend"])
                       + "\n\nTipp: im Reiter »Einzelwert / Suche« den richtigen Ticker suchen.")
        datum = dt.date.today().isoformat()
        d1, d2 = st.columns(2)
        d1.download_button("⬇️ Excel", als_excel(df), f"rsl_{datum}.xlsx", width="stretch")
        d2.download_button("⬇️ CSV", als_csv(df), f"rsl_{datum}.csv", "text/csv", width="stretch")

    if listen:
        with st.expander("Inhalt meiner Listen ansehen"):
            for name, pfad in listen.items():
                eintraege = lese_tickertext(pfad.read_text(encoding="utf-8"))
                st.markdown(f"**{name}** ({len(eintraege)} Werte)")
                st.dataframe(pd.DataFrame({"Ticker": list(eintraege), "Name": list(eintraege.values())}),
                             hide_index=True, width="stretch")

# ---------------- Einzelwert / Suche
with tab_einzel:
    st.write("Aktie über **Name, ISIN, WKN oder Ticker** suchen – zeigt den Yahoo-Ticker, die RSL "
             "und den Chart mit 26-Wochen-Durchschnitt.")
    suche = st.text_input("Suche", placeholder="z. B. Billerud, DE0007164600 oder SAP.DE")
    if suche:
        treffer = []
        try:
            import yfinance as yf
            treffer = [q for q in yf.Search(suche, max_results=10, news_count=0).quotes
                       if q.get("symbol")]
        except Exception:
            pass
        if not treffer:
            treffer = [{"symbol": suche.strip().upper(), "shortname": "", "exchDisp": ""}]
        beschriftung = {
            q["symbol"]: f"{q['symbol']} – {q.get('longname') or q.get('shortname') or ''} "
                         f"({q.get('exchDisp') or q.get('exchange') or '?'})"
            for q in treffer}
        symbol = st.selectbox("Treffer", list(beschriftung), format_func=beschriftung.get)
        wochen = st.number_input("Wochen für den Durchschnitt", 5, 80, 26, key="einzel_n")

        kurse, fehler = lade_kurse((symbol,))
        if kurse.empty or symbol not in kurse.columns or kurse[symbol].dropna().empty:
            st.error("Keine Kursdaten für diesen Ticker." + (f" ({fehler})" if fehler else ""))
        else:
            w = wochenschluesse(kurse[symbol])
            wert = rsl(w, int(wochen))
            if wert is None:
                st.warning("Zu wenig Kurshistorie für die RSL.")
            else:
                e1, e2, e3 = st.columns(3)
                e1.metric("RSL", f"{wert:.3f}".replace(".", ","))
                e2.metric("Kurs", f"{w.iloc[-1]:.2f}".replace(".", ","))
                e3.metric(f"Ø {wochen} Wochen", f"{w.iloc[-int(wochen):].mean():.2f}".replace(".", ","),
                          f"{(wert - 1) * 100:+.1f} % Abstand".replace(".", ","))
                chart = pd.DataFrame({"Wochenschluss": w,
                                      f"Ø {wochen} Wochen": w.rolling(int(wochen)).mean()}).iloc[-60:]
                st.line_chart(chart, height=300)
                name = beschriftung[symbol].split(" – ", 1)[-1].rsplit(" (", 1)[0]
                st.caption("Zeile für deine Liste (kopieren und in eine Datei im Ordner »listen« einfügen):")
                st.code(f"{symbol:<12}# {name}", language=None)

# ---------------- Hilfe
with tab_hilfe:
    st.markdown("""
**RSL nach Levy**
RSL = aktueller Kurs ÷ Durchschnitt der letzten 26 Wochenschlusskurse.
RSL über 1 = Kurs liegt über seinem Halbjahresdurchschnitt (relative Stärke). Je höher, desto stärker.
Die laufende Woche zählt mit dem aktuellsten Kurs als 26. Woche. Kurse sind um Dividenden und Splits bereinigt.

**RSL vor 4 Wochen**
Dieselbe Rechnung zum Stand von vor 4 Wochen – zeigt, ob die Stärke zu- oder abnimmt. Hat keinen Einfluss auf die Rangfolge.

**Ticker-Format (Yahoo)**
`.DE` Xetra · `.PA` Paris · `.AS` Amsterdam · `.L` London · `.SW` Schweiz · `.ST` Stockholm ·
`.CO` Kopenhagen · `.OL` Oslo · `.MC` Madrid · `.VI` Wien · `.T` Tokio · `.TO` Toronto · ohne Endung = USA.
Den richtigen Ticker findest du im Reiter »Einzelwert / Suche«.

**Eigene Listen dauerhaft speichern**
Listen sind Textdateien im Ordner `listen` deines GitHub-Projekts (ein Ticker **oder eine ISIN** pro Zeile,
Name hinter `#`). ISINs übersetzt die App selbst in Yahoo-Ticker.
Neue Liste: auf GitHub im Ordner `listen` → *Add file → Create new file* → z. B. `dividenden.txt`.
Nach dem Speichern erscheint sie nach kurzer Zeit hier in der Auswahl.

**Planspiel Börse**  
Alle Indizes außer S&P 500 plus alle eigenen Listen – doppelte Werte zählen nur einmal.

**Indizes – woher die Zusammensetzung kommt**  
- S&P 500: aktuell von GitHub (datasets/s-and-p-500-companies), sonst Wikipedia  
- Nasdaq-100: aktuell von nasdaq.com, sonst Wikipedia  
- Dow Jones, FTSE MIB: aktuell von Wikipedia  
- DAX, MDAX, SDAX, TecDAX, Euro Stoxx 50, ATX, Global Challenges Index, LuxX: hinterlegte Listen im Ordner
  `indizes` (Stand steht in der Datei). Die DAX-Familie wird im März, Juni, September und Dezember überprüft.  

Unter jeder Rangliste steht, woher die Zusammensetzung stammt. Ist eine Live-Quelle nicht erreichbar,
wird die hinterlegte Liste verwendet und ein gelber Hinweis angezeigt.

**Kurse**
Kommen von Yahoo Finance und werden 1 Stunde zwischengespeichert. Meldet Yahoo »zu viele Anfragen«,
einfach 15–30 Minuten warten.
""")
