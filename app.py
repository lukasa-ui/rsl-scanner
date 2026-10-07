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

# Indizes: name -> (Wikipedia-URL für die aktuelle Zusammensetzung oder None, Endung für Yahoo, Mindestanzahl)
# Bei None wird nur die hinterlegte Liste im Ordner "indizes" verwendet (Wikipedia ist dort veraltet).
# Bei einer URL wird Wikipedia gelesen; klappt das nicht, greift ebenfalls die hinterlegte Liste.
INDIZES = {
    "DAX": (None, ".DE", 0),
    "MDAX": (None, ".DE", 0),
    "SDAX": (None, ".DE", 0),
    "TecDAX": (None, ".DE", 0),
    "Euro Stoxx 50": (None, "", 0),
    "Dow Jones": ("https://en.wikipedia.org/wiki/List_of_Dow_Jones_Industrial_Average_companies", "", 25),
    "Nasdaq-100": ("https://en.wikipedia.org/wiki/Nasdaq-100", "", 90),
    "Global Challenges Index": (None, "", 0),
    "FTSE MIB": ("https://en.wikipedia.org/wiki/FTSE_MIB", ".MI", 35),
    "ATX": (None, ".VI", 0),
    "LuxX": (None, "", 0),
    "S&P 500": ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "", 400),
}
ALLE = "Planspiel Börse (alle Werte)"   # alle Indizes außer S&P 500 + alle eigenen Listen


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


def tickertabelle_aus_html(html: str, endung: str, minimum: int) -> dict[str, str]:
    gefunden = []
    for tab in pd.read_html(io.StringIO(html)):
        alle = " ".join(str(c).lower() for c in tab.columns)
        if "added" in alle or "removed" in alle:          # Tabelle der Indexänderungen überspringen
            continue
        namen = [_spaltenname(c) for c in tab.columns]
        daten = tab
        if _finde_spalte(namen, ("ticker", "symbol")) is None and len(tab):
            # Überschrift steckt manchmal in der ersten Datenzeile
            erste = [_spaltenname(v) for v in tab.iloc[0]]
            if _finde_spalte(erste, ("ticker", "symbol")) is not None:
                namen, daten = erste, tab.iloc[1:]
        gefunden.append(", ".join(namen[:5]))
        ti = _finde_spalte(namen, ("ticker", "symbol"))
        ni = _finde_spalte(namen, ("company", "security", "name", "unternehmen"))
        if ti is None or len(daten) < minimum:
            continue
        ergebnis = {}
        for _, zeile in daten.iterrows():
            t = re.sub(r"\[.*?\]", "", str(zeile.iloc[ti])).strip()
            if not t or t.lower() == "nan":
                continue
            t = t.split()[0].upper()
            if endung and "." not in t:
                t += endung
            elif not endung:
                t = t.replace(".", "-")          # Yahoo schreibt BRK-B statt BRK.B
            ergebnis[t] = str(zeile.iloc[ni]) if ni is not None else ""
        if len(ergebnis) >= minimum:
            return ergebnis
    raise RuntimeError("Keine passende Tabelle gefunden. Gefundene Tabellen: "
                       + " | ".join(gefunden[:8]))


def ersatzliste(name: str) -> Path:
    return ERSATZ_ORDNER / (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") + ".txt")


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def lade_index(name: str) -> tuple[dict[str, str], str]:
    """Aktuelle Zusammensetzung von Wikipedia; bei Problemen die mitgelieferte Ersatzliste.
    Gibt (Ticker->Name, Hinweis) zurück; Hinweis ist leer, wenn Wikipedia geklappt hat."""
    import requests

    url, endung, minimum = INDIZES[name]
    if url is None:
        datei = ersatzliste(name)
        if not datei.exists():
            raise RuntimeError(f"Liste {datei.name} fehlt im Ordner »indizes«.")
        return lese_tickertext(datei.read_text(encoding="utf-8")), ""
    try:
        antwort = requests.get(url, timeout=30, headers={
            "User-Agent": "RSL-Scanner/1.0 (private Aktien-App; github.com/lukasa-ui/rsl-scanner) "
                          "python-requests"})
        antwort.raise_for_status()
        return tickertabelle_aus_html(antwort.text, endung, minimum), ""
    except Exception as e:
        datei = ersatzliste(name)
        if datei.exists():
            text = datei.read_text(encoding="utf-8")
            stand = re.search(r"Stand ([0-9.]+)", text)
            return lese_tickertext(text), (
                f"{name}: aktuelle Zusammensetzung bei Wikipedia gerade nicht abrufbar. "
                f"Verwende hinterlegte Liste{' vom ' + stand.group(1) if stand else ''}.")
        raise RuntimeError(f"Zusammensetzung nicht abrufbar: {e}")


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
    optionen = list(listen) + list(INDIZES) + [ALLE]
    auswahl = st.multiselect(
        "Was soll gescannt werden?", optionen,
        default=optionen[:1] if listen else [],
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
                        neu, hinweis = lade_index(quelle)
                    if hinweis:
                        st.info(hinweis)
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

**Planspiel Börse (alle Werte)**  
Alle Indizes außer S&P 500 plus alle eigenen Listen – doppelte Werte zählen nur einmal.

**Indizes**  
DAX, MDAX, SDAX, TecDAX, Euro Stoxx 50, Global Challenges Index, ATX und LuxX kommen aus hinterlegten
Listen im Ordner `indizes` (Stand steht in der jeweiligen Datei). Nach einer Indexänderung die Datei auf GitHub
anpassen. Die DAX-Familie wird vierteljährlich überprüft (März, Juni, September, Dezember).
Dow Jones, Nasdaq-100, FTSE MIB und S&P 500 werden bei jedem Scan aktuell von Wikipedia gelesen;
klappt das nicht, wird die hinterlegte Liste verwendet.

**Kurse**
Kommen von Yahoo Finance und werden 1 Stunde zwischengespeichert. Meldet Yahoo »zu viele Anfragen«,
einfach 15–30 Minuten warten.
""")
