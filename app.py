"""
RSL-Scanner nach Robert A. Levy – Web-App (Streamlit)

Die Rechenlogik steckt in rsl_kern.py (gemeinsam mit der Freitags-E-Mail wochenmail.py).
Eigene Listen: Ordner »listen«, Depot: Datei »depot.txt«, Indexlisten: Ordner »indizes«.
Farben und Schrift: .streamlit/config.toml
"""

import datetime as dt
import html

import pandas as pd
import streamlit as st

import rsl_kern as k
import rsl_erweiterung as ext
import rsl_private_depot as priv

def geheimnis(name: str, standard=None):
    """Wert aus den Streamlit-Secrets (App-Einstellungen bei share.streamlit.io)."""
    try:
        return st.secrets.get(name, standard)
    except Exception:
        return standard

st.set_page_config(page_title="RSL-Scanner", page_icon="📈", layout="centered")

# Anmeldung und private Depotablage sind Pflicht. Kein unsicherer Rückfall auf
# das bisherige öffentliche portfolio.json, auch nicht bei Konfigurationsfehlern.
_AUTH = geheimnis("auth")
_PRIVAT_REPO = geheimnis("PORTFOLIO_GITHUB_REPO")
_PRIVAT_TOKEN = geheimnis("PORTFOLIO_GITHUB_TOKEN")
_USER_KEY = geheimnis("PORTFOLIO_USER_KEY")
if not _AUTH or not _PRIVAT_REPO or not _PRIVAT_TOKEN or not _USER_KEY:
    st.error("Private Anmeldung noch nicht eingerichtet. Google-OIDC sowie privates Depot-Repository "
             "und die vier Einträge in INSTALLATION_PRIVAT.md konfigurieren.")
    st.stop()
if not st.user.is_logged_in:
    st.title("RSL-Scanner")
    st.write("Melde dich an, um deine persönliche Rangliste und dein privates Depot zu öffnen.")
    if st.button("Mit Google anmelden", type="primary"):
        st.login("google")
    st.stop()
if not st.user.get("sub"):
    st.error("Der Google-Anbieter hat keine stabile Nutzerkennung geliefert. Anmeldung nicht möglich.")
    st.stop()
_EIGENES_DEPOT = priv.benutzer_pfad(st.user["sub"], _USER_KEY)



# ------------------------------------------------------------------ Zwischenspeicher

@st.cache_data(ttl=30 * 24 * 3600, show_spinner=False)
def isin_zu_ticker(isin: str):
    return k.isin_zu_ticker(isin)


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def lade_index(name: str):
    return k.lade_index(name)


@st.cache_data(ttl=3600, show_spinner=False)
def lade_kurse(ticker: tuple[str, ...]):
    return k.lade_kurse(ticker)


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def kennzahlen(ticker: str):
    return k.kennzahlen(ticker)


# ------------------------------------------------------------------ Gestaltung

GRUEN, ROT, GRAU = "#248A3D", "#D70015", "#6E6E73"
TOP_HG = "background-color: #E6F4EA"

st.html("""
<style>
  /* Systemschrift wie bei Apple (SF Pro auf iPhone/Mac), sonst Inter */
  html, body, .stApp, .stApp input, .stApp textarea, .stApp button, .stApp label, .stApp p, .stApp li,
  .stApp h1, .stApp h2, .stApp h3, .stApp h4, [data-baseweb] {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", Inter, "Helvetica Neue",
                 Arial, sans-serif !important;
    -webkit-font-smoothing: antialiased;
  }
  header[data-testid="stHeader"] { background: transparent; }
  [data-testid="stHeaderActionElements"], .stApp h1 a, .stApp h2 a, .stApp h3 a, .stApp h4 a { display: none !important; }
  .block-container { padding-top: 5.5rem; padding-bottom: 5rem; max-width: 980px; }
  .stApp p, .stApp li { font-variant-numeric: tabular-nums; }

  /* Kopf */
  .rsl-kopf { text-align: center; margin: 0 0 2.2rem 0; }
  .rsl-kopf h1 { font-size: clamp(2.4rem, 7vw, 3.6rem); font-weight: 700; letter-spacing: -0.025em;
                 line-height: 1.05; margin: 0; padding: 0; color: #1D1D1F; }
  .rsl-kopf p { font-size: clamp(1.05rem, 3.2vw, 1.35rem); color: #6E6E73; margin: 0.6rem 0 0 0;
                letter-spacing: -0.01em; }

  /* Reiter als iOS-Schalter (für ältere und neuere Streamlit-Versionen) */
  [role="tablist"], [data-baseweb="tab-list"] {
    justify-content: center; gap: 2px; background: #E8E8ED !important; border-radius: 980px; border: none !important;
    box-shadow: none !important; padding: 3px; width: fit-content !important; max-width: 100%;
    margin: 0 auto 1.8rem auto; overflow-x: auto; scrollbar-width: none; }
  [role="tablist"]::after, [role="tablist"]::before { display: none !important; }
  [data-baseweb="tab-highlight"], [data-baseweb="tab-border"], .react-aria-SelectionIndicator { display: none !important; }
  [data-testid="stTabs"] > div:first-child { border: none !important; box-shadow: none !important; }
  [role="tab"] { border-radius: 980px !important; padding: 0.4rem 1.1rem !important; height: auto !important;
                 color: #1D1D1F !important; background: transparent; border: none !important; margin: 0 !important;
                 white-space: nowrap; }
  [role="tab"] p { font-size: 0.95rem !important; font-weight: 500; color: #1D1D1F !important; }
  [role="tab"][aria-selected="true"] { background: #FFFFFF !important; box-shadow: 0 1px 4px rgba(0,0,0,0.14); }

  /* Karten */
  [class*="st-key-karte"] { background: #FFFFFF; border-radius: 22px; padding: 1.6rem 1.6rem 1.4rem 1.6rem;
                            box-shadow: 0 2px 14px rgba(0,0,0,0.05); margin-bottom: 1.2rem; }
  @media (max-width: 640px) { [class*="st-key-karte"] { padding: 1.1rem 0.9rem; border-radius: 18px; } }
  [class*="st-key-karte"] h4 { font-size: 1.35rem; font-weight: 600; letter-spacing: -0.015em; margin-top: 0; }

  /* Knöpfe: Pillenform */
  .stButton button, .stDownloadButton button { border-radius: 980px !important; padding: 0.55rem 1.4rem !important;
                                               font-weight: 500; }
  .stButton button[kind="primary"] { font-size: 1.05rem; padding: 0.75rem 1.4rem !important; }

  /* Eingabefelder und Aufklapper ruhiger */
  [data-testid="stExpander"] details { border: none !important; background: #F5F5F7; border-radius: 14px; }
  [data-testid="stDataFrame"] { border-radius: 14px; overflow: hidden; }
  [class*="st-key-rangliste_mobil"] { display: none; }
  [class*="st-key-mobile_aktie_"] { margin-bottom: .65rem; }
  /* Depotliste statt großer Karten: Details nur auf Wunsch aufklappen */
  [data-testid="stExpander"] details { margin-bottom: .35rem; border: 1px solid #E8E8ED !important; background: #FFFFFF !important; }
  [data-testid="stExpander"] summary { padding: .3rem .5rem; }
  [class*="st-key-karte_depot_"] { margin-bottom: .3rem; border-radius: 12px; padding: .5rem !important; }
  @media (max-width: 640px) {
    [class*="st-key-rangliste_mobil"] { display: block; }
    [class*="st-key-rangliste_desktop"] { display: none; }
    [class*="st-key-mobile_aktie_"] [data-testid="column"] { min-width: 0 !important; }
    [class*="st-key-mobile_aktie_"] .stButton button { padding: .5rem .4rem !important; font-size: .8rem; }
  }

  /* Ergebnis */
  .rsl-ergebnis h2 { font-size: clamp(1.5rem, 4.6vw, 2.1rem); font-weight: 700; letter-spacing: -0.02em;
                     line-height: 1.15; margin: 0 0 0.3rem 0; color: #1D1D1F; padding: 0; }
  .rsl-ergebnis p { color: #6E6E73; margin: 0 0 1rem 0; }
  .rsl-depot { display: flex; gap: 0.6rem; align-items: baseline; background: #F5F5F7; border-radius: 14px;
               padding: 0.75rem 1rem; margin: 0 0 1rem 0; }
  .rsl-depot .punkt { width: 0.6rem; height: 0.6rem; border-radius: 50%; background: #248A3D; flex: none;
                      transform: translateY(-0.05rem); }
  .rsl-depot.alarm .punkt { background: #D70015; }
  .rsl-depot b.v { color: #D70015; font-weight: 600; }
  .rsl-depot b.h { color: #248A3D; font-weight: 600; }

  /* Detailansicht */
  [role="dialog"] { background: #FFFFFF !important; border-radius: 22px !important; }
  .rsl-werte { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.3rem 1.2rem;
               margin: 0.4rem 0 1.2rem 0; }
  .rsl-werte div span { display: block; color: #6E6E73; font-size: 0.85rem; }
  .rsl-werte div strong { font-size: 1.9rem; font-weight: 700; letter-spacing: -0.02em;
                          font-variant-numeric: tabular-nums; }
  .rsl-werte div em { display: block; font-style: normal; font-size: 0.85rem; color: #6E6E73; }
  .rsl-entw { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 0.4rem;
              font-variant-numeric: tabular-nums; margin-bottom: 0.6rem; }
  .rsl-entw div { text-align: center; padding: 0.55rem 0; background: #F5F5F7; border-radius: 12px; }
  .rsl-entw span { display: block; font-size: 0.75rem; color: #6E6E73; }
  .rsl-entw strong { font-weight: 600; font-size: 1rem; }
  .rsl-status { list-style: none; padding: 0; margin: 0 0 0.6rem 0; }
  .rsl-status li { padding: 0.15rem 0; color: #1D1D1F; }
  .rsl-status li.offen { color: #6E6E73; }
  @media (max-width: 640px) {
    .block-container { padding: 3.2rem 0.7rem 2rem 0.7rem !important; }
    [data-testid="stHorizontalBlock"] { gap: 0.45rem !important; flex-wrap: wrap; }
    [data-testid="column"] { min-width: 100% !important; }
    [data-testid="stDataFrame"] { overflow-x: auto; }
    .rsl-kopf { margin-bottom: 1.2rem; }
    .rsl-entw { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .rsl-werte div strong { font-size: 1.4rem; }
    [role="tab"] { padding: 0.35rem 0.8rem !important; }
    [role="tab"] p { font-size: 0.9rem !important; }
  }
</style>
""")


def farbe(v, gut_ab=0.0):
    return GRUEN if v >= gut_ab else ROT


def zeige_tabelle(df: pd.DataFrame, grenze: float, schluessel: str):
    """Schlanke Rangliste: nur die Spalten, die man wirklich liest. Gibt die Zeilenauswahl zurück."""
    spalten = ["Rang", "Δ Rang", "Ticker", "RSL", "R²", "RSL vor 4 Wo.", "Sektor", "Name"] + (["Depot"] if "Depot" in df else [])
    tab = df.rename(columns={"Trendqualität": "R²"})[spalten + ["Rang %", "Veraltet"]].copy()
    tab["Name"] = [f"{n} ⚠️" if alt else n for n, alt in zip(tab["Name"], tab["Veraltet"])]
    top = tab["Rang %"] <= grenze
    tab = tab[spalten].rename(columns={"Δ Rang": "Δ", "RSL vor 4 Wo.": "vor 4 Wo."})

    rsl_fmt = lambda v: "–" if pd.isna(v) else k.de_zahl(v, 3)
    trend_fmt = lambda v: "–" if pd.isna(v) else k.de_zahl(float(v), 2)
    stil = (tab.style
            .format({"RSL": rsl_fmt, "R²": trend_fmt, "vor 4 Wo.": rsl_fmt, "Δ": k.de_rang_delta})
            .apply(lambda z: [TOP_HG if top.loc[z.name] else ""] * len(z), axis=1)
            .map(lambda v: "" if pd.isna(v) else f"color:{farbe(v, 1)};font-weight:600", subset=["RSL"])
            .map(lambda v: f"color:{GRAU}", subset=["vor 4 Wo."])
            .map(lambda v: "" if pd.isna(v) or v == 0 else f"color:{farbe(v)}", subset=["Δ"]))
    if "Depot" in tab:
        stil = stil.map(lambda v: f"font-weight:600;color:{GRUEN if 'Halten' in v else ROT}" if v else "",
                        subset=["Depot"])
    return st.dataframe(
        stil, hide_index=True, width="stretch", height=min(38 + 35 * len(tab), 640),
        on_select="rerun", selection_mode="single-row", key=schluessel,
        column_config={"Rang": st.column_config.NumberColumn(width=48),
                       "Δ": st.column_config.TextColumn(width=52),
                       "Ticker": st.column_config.TextColumn(width=92),
                       "RSL": st.column_config.TextColumn(width=58),
                       "R²": st.column_config.TextColumn(width=62),
                       "vor 4 Wo.": st.column_config.TextColumn(width=72),
                       "Sektor": st.column_config.TextColumn(width=145),
                       "Name": st.column_config.TextColumn(width=230),
                       "Depot": st.column_config.TextColumn(width=90)})


def prozent(v) -> str:
    if v is None or pd.isna(v):
        return "–"
    return f'<strong style="color:{farbe(v)}">{"+" if v >= 0 else ""}{k.de_zahl(v, 1)} %</strong>'


def zeige_details(ticker: str, name: str, tageskurse: pd.Series, n: int, zeile=None):
    """Detailansicht: Kernzahlen, Wertentwicklung, Chart und Kennzahlen."""
    import altair as alt

    if tageskurse.dropna().empty:
        st.info("Keine Kursdaten für die Detailansicht vorhanden.")
        return
    w = k.wochenschluesse(tageskurse)
    wert = k.rsl(w, n)
    st.subheader(name or ticker)
    st.caption(f"{ticker} · Kurs {k.de_zahl(w.iloc[-1], 2)} am {tageskurse.dropna().index[-1].strftime('%d.%m.%Y')}")
    if wert is None:
        st.warning("Für die RSL gibt es noch zu wenig Kurshistorie.")
        return

    vorher = None if zeile is None or pd.isna(zeile["RSL vor 4 Wo."]) else zeile["RSL vor 4 Wo."]
    rang_text, rang_zusatz = "–", ""
    if zeile is not None:
        rang_text = f"{int(zeile['Rang'])}"
        d = zeile["Δ Rang"]
        rang_zusatz = (f"Top {k.de_zahl(zeile['Rang %'], 0)} %, "
                       + ("neu" if pd.isna(d) else f'<span style="color:{farbe(d)}">{k.de_rang_delta(d)}</span>'
                          if d != 0 else "wie Vorwoche"))
    abstand = (wert - 1) * 100
    st.html(f"""
    <div class="rsl-werte">
      <div><span>RSL</span><strong style="color:{farbe(wert, 1)}">{k.de_zahl(wert, 3)}</strong>
           <em>{'vor 4 Wo. ' + k.de_zahl(vorher, 3) if vorher is not None else '&nbsp;'}</em></div>
      <div><span>Rang</span><strong>{rang_text}</strong><em>{rang_zusatz or '&nbsp;'}</em></div>
      <div><span>Abstand Ø</span><strong style="color:{farbe(abstand)}">{'+' if abstand >= 0 else ''}{k.de_zahl(abstand, 1)} %</strong>
           <em>{n} Wochen</em></div>
    </div>""")

    entw = k.wertentwicklung(tageskurse)
    st.html('<div class="rsl-entw">' + "".join(
        f"<div><span>{html.escape(z)}</span>{prozent(v)}</div>" for z, v in entw.items()) + "</div>")

    chart = pd.DataFrame({"Kurs": w, f"Ø {n} Wochen": w.rolling(n).mean()}).iloc[-78:]
    lang = chart.reset_index(names="Datum").melt("Datum", var_name="Linie", value_name="Wert").dropna()
    st.altair_chart(
        alt.Chart(lang).mark_line(strokeWidth=2).encode(
            x=alt.X("Datum:T", title=None, axis=alt.Axis(format="%m/%y", grid=False, tickCount=6)),
            y=alt.Y("Wert:Q", title=None, scale=alt.Scale(zero=False)),
            color=alt.Color("Linie:N", title=None, legend=alt.Legend(orient="bottom"),
                            scale=alt.Scale(range=["#1D1D1F", "#0071E3"])),
            strokeDash=alt.StrokeDash("Linie:N", legend=None, scale=alt.Scale(range=[[1, 0], [5, 3]])),
            tooltip=[alt.Tooltip("Datum:T", format="%d.%m.%Y"), "Linie:N", alt.Tooltip("Wert:Q", format=",.2f")],
        ).properties(height=240, background="#FFFFFF").configure_view(strokeWidth=0),
        width="stretch")

    with st.expander("Kennzahlen"):
        try:
            kz = kennzahlen(ticker)
        except Exception:
            kz = {}
        if not kz:
            st.write("Yahoo liefert gerade keine Kennzahlen. Später nochmal öffnen.")
        else:
            st.markdown("| | |\n|---|---|\n" + "\n".join(f"| {a} | {v} |" for a, v in kz.items() if a != "Name"))
            st.caption("Quelle: Yahoo Finance. Beträge in der Währung des Unternehmens bzw. der Börse.")


@st.dialog("Details", width="large")
def details_fenster(ticker, name, tageskurse, n, zeile):
    zeige_details(ticker, name, tageskurse, n, zeile)


# ------------------------------------------------------------------ Kopf

st.html("""<div class="rsl-kopf"><h1>RSL-Scanner</h1>
<p>Die stärksten Aktien der Woche. Nach Levy.</p></div>""")
an1, an2 = st.columns([5, 1])
an1.caption("Angemeldet: " + str(st.user.get("email", "Google-Konto")))
if an2.button("Abmelden", key="logout"):
    st.logout()
tab_scan, tab_depot, tab_einzel, tab_mail, tab_hilfe = st.tabs(
    ["Rangliste", "Mein Depot", "Aktie suchen", "E-Mail", "Hilfe"]
)
listen = k.eigene_listen()

# ---------------- Tagesvergleiche (unabhängig von der Erweiterungs-Version)

def _rsl_am_vorherigen_handelstag(kurse: pd.Series, wochen: int):
    """RSL mit den Kursen BIS zum vorletzten vorhandenen Handelstag.

    Diese kleine Berechnung liegt bewusst in app.py: Eine ältere, von
    Streamlit noch zwischengespeicherte rsl_erweiterung.py darf die ganze
    Oberfläche nicht durch einen fehlenden Funktionsnamen lahmlegen.
    """
    reihe = pd.Series(kurse).dropna()
    if len(reihe) < 2:
        return None
    return k.rsl(k.wochenschluesse(reihe.iloc[:-1]), int(wochen))


def _tagesveraenderung(kurse: pd.Series):
    """Veränderung zum letzten verfügbaren vorherigen Schlusskurs in Prozent."""
    reihe = pd.to_numeric(pd.Series(kurse), errors="coerce").dropna()
    if len(reihe) < 2 or reihe.iloc[-2] <= 0:
        return None
    return (float(reihe.iloc[-1]) / float(reihe.iloc[-2]) - 1) * 100


# ---------------- Persistenz, Sektoren, Aktionen

@st.cache_data(ttl=1800, show_spinner=False)
def _privat_repo_ist_sicher(token, projekt):
    import github_verbindung as ghv
    return priv.repo_privat_pruefen(ghv.GitHub(token, projekt))


@st.cache_data(ttl=45, show_spinner=False)
def _portfolio_lesen_cache(token, projekt, benutzer_pfad):
    import github_verbindung as ghv
    return priv.portfolio_laden(ghv.GitHub(token, projekt), benutzer_pfad)


def portfolio_lesen():
    try:
        _privat_repo_ist_sicher(_PRIVAT_TOKEN, _PRIVAT_REPO)
        return _portfolio_lesen_cache(_PRIVAT_TOKEN, _PRIVAT_REPO, _EIGENES_DEPOT)
    except Exception as exc:
        st.error(f"Privates Depot konnte nicht geladen werden. Keine Änderungen: {exc}")
        return None


def portfolio_schreiben(daten):
    try:
        _privat_repo_ist_sicher(_PRIVAT_TOKEN, _PRIVAT_REPO)
        import github_verbindung as ghv
        gh = ghv.GitHub(_PRIVAT_TOKEN, _PRIVAT_REPO)
        # Unabhängig vom Cache vor JEDEM Schreiben die Sichtbarkeit neu prüfen.
        priv.repo_privat_pruefen(gh)
        priv.portfolio_speichern(gh, _EIGENES_DEPOT, daten)
    except Exception as exc:
        st.error(f"Privates Depot konnte nicht gespeichert werden: {exc}")
        return False
    _portfolio_lesen_cache.clear()
    st.toast("Im privaten Depot gespeichert.")
    return True


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def sektor_von_yahoo(ticker: str) -> str:
    """24h-Cache: eine .info-Abfrage pro Ticker, kein Lookup für alle 500 Werte."""
    try:
        import yfinance as yf
        original = (yf.Ticker(ticker).info or {}).get("sector")
        return k.SEKTOREN.get(original, original) if original else "Unbekannt"
    except Exception:
        return "Unbekannt"


def aktie_aufnehmen(zeile, ziel):
    daten = portfolio_lesen()
    if daten is None:
        st.error("Privates Depot nicht verfügbar. Prüfe PORTFOLIO_GITHUB_TOKEN und das private Repository.")
        return
    ticker = str(zeile["Ticker"])
    try:
        if ziel == "depot":
            kurs = zeile.get("Kurs")
            import inspect
            name = zeile.get("Name", ticker)
            periode = int(st.session_state.get("ergebnis", {}).get("n", 26))
            sektor = zeile.get("Sektor")
            # Ältere Streamlit-Prozesse können noch die ursprüngliche Version
            # der Erweiterung geladen haben. Auch dann kein TypeError und
            # vor allem kein Überschreiben bestehender Depotpositionen.
            if "aufnahme_kurs" in inspect.signature(ext.depot_hinzufuegen).parameters:
                ext.depot_hinzufuegen(daten, ticker, name, zeile["RSL"],
                                      aufnahme_kurs=kurs, sektor=sektor,
                                      rsl_wochen=periode)
            else:
                if ticker in daten.get("depot", {}):
                    raise ValueError("Diese Aktie ist bereits im Depot.")
                ext.depot_hinzufuegen(daten, ticker, name, zeile["RSL"])
                pos = daten["depot"][ticker]
                pos["rsl_wochen"] = periode
                pos["aufnahme_kurs"] = float(kurs) if pd.notna(kurs) and float(kurs) > 0 else None
                pos["sektor"] = sektor if pd.notna(sektor) and sektor != "Unbekannt" else None
                pos["stop_aktiv"] = True
                pos["stop_schwelle"] = 0.75
                pos["stop_ausgeloest"] = False
        else:
            ext.watchlist_hinzufuegen(daten, ticker, zeile.get("Name", ticker))
    except (TypeError, ValueError) as exc:
        st.warning(str(exc))
        return
    if portfolio_schreiben(daten):
        st.rerun()


# ---------------- Rangliste
with tab_scan:
    with st.container(key="karte_scan"):
        erste = [l for l in listen if l == "Meine Liste"]
        weitere = [l for l in listen if l != "Meine Liste"]
        optionen = erste + [k.ALLE] + list(k.INDIZES) + weitere
        auswahl = st.multiselect("Was soll gescannt werden?", optionen, default=erste or optionen[:1])

        with st.expander("Einstellungen und weitere Ticker"):
            zusatz = st.text_area("Weitere Ticker oder ISINs", height=70,
                                  placeholder="z. B. SAP.DE ALV.DE oder DE0007164600")
            sp1, sp2 = st.columns(2)
            grenze = sp1.number_input("Grün markieren: beste … %", 1, 100, 30, 5, key="grenze_scan")
            n = int(sp2.number_input("Wochen für die RSL", 5, 80, 26, 1, key="rsl_wochen"))
            sp3, sp4 = st.columns(2)
            top = sp3.number_input("Nur die besten … zeigen (0 = alle)", 0, 2000, 0, 10)
            min_rsl = sp4.number_input("Nur RSL ab (0 = alle)", 0.0, 5.0, 0.0, 0.01, format="%.2f")
            if st.button("Kurse neu laden", help="Kurse werden eine Stunde zwischengespeichert."):
                lade_kurse.clear()
                st.toast("Beim nächsten Scan werden die Kurse neu geladen.")

        if st.button("Scan starten", type="primary", width="stretch"):
            with st.spinner("Stelle die Liste zusammen …"):
                namen, herkunft, fehler_quellen = k.sammle_universum(auswahl, listen, lade_index)
            for ticker, name in k.lese_tickertext(zusatz).items():
                namen.setdefault(ticker, name)
            # Keine gemeinsam im öffentlichen Code-Repository liegende Depotliste lesen.
            # Nur das aktuell angemeldete Konto darf Depotmarkierungen erzeugen.
            isin_fehlend = []
            depot = {}
            if any(k.ISIN_MUSTER.match(t) for t in namen):
                with st.spinner("Löse ISINs in Ticker auf …"):
                    namen, isin_fehlend = k.isins_aufloesen(namen, isin_zu_ticker)
            if not namen:
                st.session_state.pop("ergebnis", None)
                st.warning("Wähle eine Liste oder einen Index aus.")
            else:
                with st.spinner(f"Lade Kurse für {len(namen)} Werte …"):
                    kurse, fehler = lade_kurse(tuple(sorted(namen)))
                if kurse.empty:
                    st.session_state.pop("ergebnis", None)
                    st.error("Yahoo hat keine Kurse geliefert. " + (fehler or "Bitte später erneut versuchen."))
                else:
                    df, fehlend = k.screene(kurse, namen, n, "wochen")
                    if not df.empty:
                        trendwerte = {
                            ticker: ext.trendqualitaet(k.wochenschluesse(kurse[ticker].dropna()), wochen=n)
                            for ticker in df["Ticker"] if ticker in kurse.columns
                        }
                        df["Trendqualität"] = df["Ticker"].map(trendwerte)
                        # Yahoo-Metadaten werden getrennt und in kleinen Paketen geladen.
                        df["Sektor"] = "Unbekannt"
                    fehlend += [t for t in namen if t not in kurse.columns]
                    fehlend += [f"{x} (ISIN bei Yahoo nicht gefunden)" for x in isin_fehlend]
                    st.session_state["ergebnis"] = {
                        "df": df, "kurse": kurse, "depot": depot,
                        "fehlend": sorted(set(fehlend)), "n": n,
                        "herkunft": herkunft, "fehler_quellen": fehler_quellen,
                        "zeit": dt.datetime.now().strftime("%d.%m.%Y, %H:%M Uhr"),
                    }
                    # Erste sichtbare Werte gleich ausstatten; größere Indizes in Portionen nachladen.
                    st.session_state["scan_sektoren"] = {}
                    if not df.empty:
                        with st.spinner("Lade Sektoren der ersten fünf Aktien …"):
                            for ticker in df["Ticker"].head(5):
                                st.session_state["scan_sektoren"][ticker] = sektor_von_yahoo(ticker)
                    st.session_state["mobile_anzahl"] = 15
                    st.session_state.pop("rangliste", None)
                    st.session_state.pop("zuletzt_geoeffnet", None)

    erg = st.session_state.get("ergebnis")
    if erg is not None and not erg["df"].empty:
        df = erg["df"].copy()
        # Maximal 20 neue Yahoo-.info-Anfragen je Klick, um große Indizes nicht auszubremsen.
        bereits = st.session_state.setdefault("scan_sektoren", {})
        fehlende_sektoren = [t for t in df["Ticker"] if t not in bereits]
        if fehlende_sektoren:
            st.caption(f"Sektoren: {len(bereits)} von {len(df)} Titeln geprüft. "
                       "Yahoo-Sektoren können bei ETFs oder fehlenden Stammdaten unbekannt bleiben.")
            if st.button("Weitere 20 Sektoren abrufen", key="sektoren_weiter"):
                with st.spinner("Sektoren von Yahoo abrufen …"):
                    for ticker in fehlende_sektoren[:20]:
                        bereits[ticker] = sektor_von_yahoo(ticker)
                st.rerun()
        df["Sektor"] = df["Ticker"].map(bereits).fillna("Unbekannt")
        # Scanner und gespeichertes Depot getrennt, aber Signale anhand der aktuellen Liste.
        gespeichertes = portfolio_lesen()
        depot_ticker = {t: p.get("name", t) for t, p in gespeichertes["depot"].items()} if gespeichertes else {}
        
        df = k.depot_markieren(df, depot_ticker, grenze)
        anzeige = df[df["RSL"] >= min_rsl] if min_rsl else df
        if top:
            anzeige = anzeige.head(int(top))
        anzeige = anzeige.reset_index(drop=True)
        with st.container(key="karte_ergebnis"):
            im_top = int((df["Rang %"] <= grenze).sum())
            st.html(f'<div class="rsl-ergebnis"><h2>{im_top} von {len(df)} Werten in den besten {grenze} %.</h2>'
                    f'<p>Grün hinterlegt. Stand {erg["zeit"]}.</p></div>')
            with st.container(key="rangliste_desktop"):
                ereignis = zeige_tabelle(anzeige, grenze, "rangliste")
                st.caption("Zeile auswählen und ins private Depot übernehmen. R² (0 bis 1) misst die Güte "
                           "der Trendlinie über die eingestellten Wochen, nicht die Trendrichtung.")
                zeilen = ereignis.selection.rows if ereignis is not None else []
                if zeilen:
                    gewaehlte = anzeige.iloc[zeilen[0]]
                    ticker = gewaehlte["Ticker"]
                    st.markdown(f"**Ausgewählt: {html.escape(str(gewaehlte['Name']))} ({ticker})**")
                    ist_depot = bool(gespeichertes and ticker in gespeichertes["depot"])
                    ist_watchlist = bool(gespeichertes and ticker in gespeichertes["watchlist"])
                    a1, a2, a3 = st.columns([1, 1, 1])
                    if a1.button("＋ Ins Depot", disabled=ist_depot, key="scan_auswahl_depot", width="stretch"):
                        aktie_aufnehmen(gewaehlte, "depot")
                    if a2.button("＋ Watchlist", disabled=ist_depot or ist_watchlist,
                                 key="scan_auswahl_watch", width="stretch"):
                        aktie_aufnehmen(gewaehlte, "watchlist")
                    if a3.button("Chart & Details", key="scan_auswahl_details", width="stretch"):
                        details_fenster(ticker, gewaehlte["Name"], erg["kurse"][ticker], erg["n"], gewaehlte)
                else:
                    st.caption("Wähle eine Zeile, um Aktionen oder den Detailchart zu öffnen.")

            with st.container(key="rangliste_mobil"):
                st.caption("Mobile Rangliste mit direkter Depot- und Watchlist-Aktion")
                anzahl = int(st.session_state.get("mobile_anzahl", 15))
                for idx, z in anzeige.head(anzahl).iterrows():
                    ticker = str(z["Ticker"])
                    name = html.escape(str(z["Name"]))
                    r2 = z.get("Trendqualität")
                    r2_text = "–" if pd.isna(r2) else k.de_zahl(float(r2), 2)
                    with st.container(key=f"mobile_aktie_{idx}", border=True):
                        st.markdown(f"**#{int(z['Rang'])} · {name}**  \n"
                                    f"`{ticker}` · {z.get('Sektor', 'Unbekannt')}")
                        st.markdown(f"RSL **{k.de_zahl(z['RSL'], 3)}** · R²-Trendqualität **{r2_text}** · "
                                    f"vor 4 Wo. **{k.de_zahl(z['RSL vor 4 Wo.'], 3) if pd.notna(z['RSL vor 4 Wo.']) else '–'}**")
                        ist_depot = bool(gespeichertes and ticker in gespeichertes["depot"])
                        ist_watchlist = bool(gespeichertes and ticker in gespeichertes["watchlist"])
                        m1, m2 = st.columns(2)
                        if m1.button("Im Depot ✓" if ist_depot else "＋ Ins Depot", disabled=ist_depot,
                                     key=f"mobile_dep_{idx}", width="stretch"):
                            aktie_aufnehmen(z, "depot")
                        if m2.button("Auf Watchlist ✓" if ist_watchlist else "＋ Watchlist",
                                     disabled=ist_depot or ist_watchlist, key=f"mobile_watch_{idx}", width="stretch"):
                            aktie_aufnehmen(z, "watchlist")
                        if st.button("Chart & Details", key=f"mobile_detail_{idx}", width="stretch"):
                            details_fenster(ticker, z["Name"], erg["kurse"][ticker], erg["n"], z)
                if len(anzeige) > anzahl and st.button("Weitere 15 Werte anzeigen", key="mehr_mobile"):
                    st.session_state["mobile_anzahl"] = anzahl + 15
                    st.rerun()

            with st.expander("Mehr zu diesem Scan"):
                neu = k.neu_in_top(erg["df"], grenze)
                if not neu.empty:
                    st.markdown(f"**Neu in den besten {grenze} %**: "
                                + ", ".join(f"{r.Ticker} ({r.Rang})" for r in neu.itertuples()))
                if erg["fehlend"]:
                    st.markdown(f"**Ohne Kursdaten ({len(erg['fehlend'])}):** " + ", ".join(erg["fehlend"]))
                st.markdown("**Herkunft der Indexlisten:**\n" + "\n".join(
                    f"- {q}: {a} Werte, {h}" for q, a, h, _ in erg["herkunft"]) if erg["herkunft"] else
                    "**Herkunft:** nur eigene Listen.")
                for q, grund in erg["fehler_quellen"]:
                    st.markdown(f"- {q}: nicht geladen ({grund})")
                datum = dt.date.today().isoformat()
                d1, d2 = st.columns(2)
                d1.download_button("Excel herunterladen", k.als_excel(df), f"rsl_{datum}.xlsx", width="stretch")
                d2.download_button("CSV herunterladen", k.als_csv(df), f"rsl_{datum}.csv", "text/csv", width="stretch")

# ---------------- Aktie suchen

# ---------------- Mein Depot
with tab_depot:
    st.subheader("Mein Depot und meine Watchlist")
    st.caption("Dein Depot wird nur deinem Google-Konto zugeordnet und in einem privaten Repository "
               "gespeichert. Die Entwicklung seit Aufnahme bezieht sich auf einen hinterlegten "
               "Referenzkurs, nicht zwangsläufig auf deinen Kaufpreis.")
    portfolio = portfolio_lesen()
    if portfolio is not None:
        depot = portfolio["depot"]
        watchlist = portfolio["watchlist"]
        with st.expander("Bisheriges Depot einmalig importieren", expanded=False):
            st.caption("Nur im eingeloggten Konto: die vorhandene portfolio.json hier als Datei hochladen. "
                       "Ein Import ist nur möglich, solange Depot und Watchlist dieses Kontos leer sind.")
            datei = st.file_uploader("Portfolio-JSON auswählen", type=["json"], key="import_portfolio")
            if datei is not None:
                if depot or watchlist:
                    st.warning("Import gesperrt: Dieses Konto hat bereits Depot- oder Watchlist-Einträge.")
                else:
                    try:
                        importdaten = priv.import_aus_json(datei.getvalue())
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.caption(f"{len(importdaten['depot'])} Depotpositionen und "
                                   f"{len(importdaten['watchlist'])} Watchlist-Einträge erkannt.")
                        if st.button("Diese Daten in mein privates Depot importieren", key="import_confirm"):
                            if portfolio_schreiben(importdaten):
                                st.rerun()
        st.markdown("### Depot")
        if not depot:
            st.info("Noch keine Positionen im Depot. Aktien lassen sich direkt aus der Rangliste übernehmen.")
        else:
            # Ein einziger gebündelter, gecachter Kursabruf statt einer Anfrage je Karte.
            depot_ticker = tuple(sorted(depot))
            try:
                depot_kurse, depot_fehler = lade_kurse(depot_ticker)
            except Exception as exc:
                depot_kurse, depot_fehler = pd.DataFrame(), str(exc)
            if depot_kurse.empty:
                st.warning("Für das Depot wurden keine aktuellen Kurse geliefert. " + (depot_fehler or ""))
            kurs_daten = {}
            ausloesungen = []
            sektor_updates = []
            erg_depot = st.session_state.get("ergebnis")
            for ticker, pos in depot.items():
                if not pos.get("sektor"):
                    gefundener_sektor = sektor_von_yahoo(ticker)
                    if gefundener_sektor != "Unbekannt":
                        pos["sektor"] = gefundener_sektor
                        sektor_updates.append(ticker)
                s = (depot_kurse[ticker].dropna() if ticker in depot_kurse.columns
                     else pd.Series(dtype=float))
                if s.empty and erg_depot is not None and ticker in erg_depot["kurse"].columns:
                    s = erg_depot["kurse"][ticker].dropna()
                kurs_daten[ticker] = s
                periode = int(pos.get("rsl_wochen", 26))
                rsl_aktuell = k.rsl(k.wochenschluesse(s), periode) if not s.empty else None
                if pos.get("stop_aktiv", False) and not pos.get("stop_ausgeloest", False):
                    if ext.stop_einmalig_ausloesen(pos, rsl_aktuell) == "Ausgelöst":
                        ausloesungen.append(ticker)
            if ausloesungen or sektor_updates:
                if portfolio_schreiben(portfolio):
                    if ausloesungen:
                        st.warning("Momentum-Stop dauerhaft gespeichert: " + ", ".join(ausloesungen))
                elif ausloesungen:
                    st.error("Stop-Warnung erkannt, konnte aber nicht dauerhaft gespeichert werden.")

            # Einmal berechnen und ausschließlich nach AKTUELLEM RSL sortieren.
            positionen = []
            for ticker, position in depot.items():
                kursserie = kurs_daten[ticker]
                periode = int(position.get("rsl_wochen", 26))
                aktuell = k.rsl(k.wochenschluesse(kursserie), periode) if not kursserie.empty else None
                positionen.append((ticker, position, aktuell))
            positionen = priv.nach_rsl_sortieren(positionen)

            # Kompakte Gesamtübersicht: alle Titel und Kennzahlen auf einen Blick.
            uebersicht = []
            for rang, (ticker, position, aktuell) in enumerate(positionen, 1):
                kursserie = kurs_daten[ticker]
                tageswert = _tagesveraenderung(kursserie)
                seitwert = ext.rendite_seit_aufnahme(position, kursserie)
                uebersicht.append({
                    "#": rang,
                    "Aktie": position.get("name", ticker),
                    "Ticker": ticker,
                    "RSL": aktuell,
                    "Heute (%)": tageswert,
                    "Seit Aufnahme (%)": seitwert,
                    "Stop": ext.stop_status(position, aktuell),
                })
            st.caption("Nach aktuellem RSL absteigend. Details öffnen sich per Klick auf die Zeile darunter.")
            st.dataframe(pd.DataFrame(uebersicht), hide_index=True, width="stretch",
                         column_config={"RSL": st.column_config.NumberColumn(format="%.3f"),
                                        "Heute (%)": st.column_config.NumberColumn(format="%+.2f"),
                                        "Seit Aufnahme (%)": st.column_config.NumberColumn(format="%+.2f")})

            for rang, (ticker, position, aktuell) in enumerate(positionen, 1):
                kursserie = kurs_daten[ticker]
                periode = int(position.get("rsl_wochen", 26))
                vorher = _rsl_am_vorherigen_handelstag(kursserie, periode) if not kursserie.empty else None
                aenderung = _tagesveraenderung(kursserie)
                seit_aufnahme = ext.rendite_seit_aufnahme(position, kursserie)
                sektor = position.get("sektor") or sektor_von_yahoo(ticker)
                referenz = position.get("referenz_rsl")
                stop = ext.stop_status(position, aktuell)
                if erg_depot is not None and ticker in erg_depot["df"]["Ticker"].values:
                    zeile = erg_depot["df"].loc[erg_depot["df"]["Ticker"] == ticker].iloc[0]
                    rang_prozent = float(zeile["Rang %"])
                    ausserhalb = rang_prozent > grenze or float(zeile["RSL"]) < 1
                    ranghinweis = f"Top {k.de_zahl(rang_prozent, 1)} % im letzten Scan"
                else:
                    ausserhalb = False
                    ranghinweis = "Rangstatus nicht prüfbar: Titel im letzten Scan nicht enthalten"
                trendwert = ext.trendqualitaet(k.wochenschluesse(kursserie), periode) if not kursserie.empty else None
                kurs_text = "–" if kursserie.empty else k.de_zahl(float(kursserie.iloc[-1]), 2)
                rsl_text = "–" if aktuell is None else k.de_zahl(aktuell, 3)
                vorher_text = "–" if vorher is None else k.de_zahl(vorher, 3)
                referenz_text = "–" if referenz is None else k.de_zahl(float(referenz), 3)
                rendite_text = "–" if seit_aufnahme is None else f"{seit_aufnahme:+.2f} %".replace(".", ",")
                trend_text = "–" if trendwert is None else k.de_zahl(trendwert, 2)
                tag_text = "–" if aenderung is None else f"{aenderung:+.2f} %".replace(".", ",")
                hinweis = " ⚠" if stop in ("Ausgelöst", "Nähert sich") or ausserhalb else ""
                titel = (f"{rang}. {position.get('name', ticker)} ({ticker}) · "
                         f"RSL {rsl_text} · Seit {rendite_text}{hinweis}")
                with st.expander(titel, expanded=False):
                    st.caption(f"{ticker} · {sektor or 'Unbekannt'} · {ranghinweis}")
                    a, b, c = st.columns(3)
                    a.metric("Schlusskurs", kurs_text, tag_text if aenderung is not None else None,
                             delta_color="normal" if aenderung is not None else "off")
                    b.metric("RSL aktuell", rsl_text,
                             f"{aktuell - vorher:+.3f}" if aktuell is not None and vorher is not None else None)
                    c.metric("Seit Aufnahme", rendite_text)
                    st.caption(f"RSL Vortag: {vorher_text} · Referenz-RSL: {referenz_text} · "
                               f"R²: {trend_text} · Zeitraum: {periode} Wochen")
                    if ausserhalb:
                        st.warning(f"{ticker}: Außerhalb der grünen Top-{grenze}-%-Zone oder RSL unter 1.")
                    if stop == "Ausgelöst":
                        st.error("Momentum-Stop ausgelöst. Alarm bleibt bis zum manuellen Zurücksetzen gespeichert.")
                    elif stop == "Nähert sich":
                        st.warning("Der RSL nähert sich der Momentum-Stop-Schwelle.")
                    elif stop == "Keine Daten":
                        st.info("Momentum-Stop momentan nicht prüfbar: Kursdaten fehlen.")
                    elif stop == "Aus":
                        st.caption("Momentum-Stop deaktiviert.")
                    if st.toggle("Chart und Kennzahlen anzeigen", key=f"chart_{ticker}"):
                        if not kursserie.empty:
                            zeige_details(ticker, position.get("name", ticker), kursserie, periode)
                        else:
                            st.info("Für diesen Titel sind gerade keine Kursdaten verfügbar.")
                    if st.toggle("Stop, Referenzkurs und Position bearbeiten", key=f"details_{ticker}"):
                        aktiv_neu = st.checkbox("Momentum-Stop aktiv", value=position.get("stop_aktiv", False),
                                                key=f"stop_aktiv_{ticker}")
                        schwelle_neu = st.slider("Stop bei … % des Referenz-RSL", 50, 100,
                                                 value=int(float(position.get("stop_schwelle", .75)) * 100),
                                                 step=5, key=f"stop_schwelle_{ticker}")
                        st.caption("Alarmgrenze: Referenz-RSL × eingestellter Prozentsatz. "
                                   "Ein Stop ist eine Warnung, kein automatischer Verkauf.")
                        if st.button("Stop-Einstellungen speichern", key=f"save_stop_{ticker}"):
                            position["stop_aktiv"] = aktiv_neu
                            position["stop_schwelle"] = schwelle_neu / 100
                            if portfolio_schreiben(portfolio):
                                st.rerun()
                        if position.get("stop_ausgeloest", False):
                            if st.button("Stop-Alarm manuell zurücksetzen", key=f"reset_stop_{ticker}"):
                                position["stop_ausgeloest"] = False
                                if portfolio_schreiben(portfolio):
                                    st.rerun()
                        if position.get("aufnahme_kurs") is None:
                            st.info("Für diese ältere Position wurde damals kein Kurs gespeichert. "
                                    "Trage einen bekannten Kurs ein oder übernimm ausdrücklich einen historischen "
                                    "Schlusskurs als Näherung.")
                            kandidat = priv.schlusskurs_am_aufnahmetag(position, kursserie)
                            if kandidat:
                                preis, datum = kandidat
                                st.caption(f"Historischer Schlusskurs vom {datum}: {k.de_zahl(preis, 2)} "
                                           "(nicht zwingend der Kurs beim Hinzufügen).")
                                if st.button("Historischen Schlusskurs als Referenz übernehmen", key=f"hist_{ticker}"):
                                    position["aufnahme_kurs"] = preis
                                    position["aufnahme_kurs_quelle"] = f"Historischer Schlusskurs {datum}"
                                    if portfolio_schreiben(portfolio):
                                        st.rerun()
                            preis_manuell = st.number_input("Alternativ Referenzkurs eingeben", min_value=0.0,
                                                             value=0.0, step=0.01, format="%.2f",
                                                             key=f"manuell_kurs_{ticker}")
                            if st.button("Eigenen Referenzkurs speichern", key=f"save_kurs_{ticker}",
                                         disabled=preis_manuell <= 0):
                                position["aufnahme_kurs"] = float(preis_manuell)
                                position["aufnahme_kurs_quelle"] = "Manuell eingetragener Kurs"
                                if portfolio_schreiben(portfolio):
                                    st.rerun()
                        else:
                            st.caption("Kursreferenz: " + str(position.get("aufnahme_kurs_quelle", "Beim Hinzufügen gespeicherter Kurs")))
                        if st.button("Position entfernen", key=f"entferne_depot_{ticker}"):
                            ext.depot_entfernen(portfolio, ticker)
                            if portfolio_schreiben(portfolio):
                                st.rerun()

            st.markdown("### Sektorverteilung")
            sektoren = {}
            for ticker, pos in depot.items():
                sector = pos.get("sektor") or sektor_von_yahoo(ticker)
                sektoren.setdefault(sector, []).append(ticker)
            summe = len(depot)
            sektor_df = pd.DataFrame([
                {"Sektor": sector, "Positionen": len(ticker_liste),
                 "Anteil": round(len(ticker_liste) / summe * 100, 1),
                 "Aktien": ", ".join(ticker_liste)}
                for sector, ticker_liste in sektoren.items()
            ]).sort_values("Positionen", ascending=False)
            if not sektor_df.empty:
                import altair as alt
                chart = alt.Chart(sektor_df).mark_bar(cornerRadiusEnd=5).encode(
                    y=alt.Y("Sektor:N", sort="-x", title=None),
                    x=alt.X("Positionen:Q", title="Positionen", axis=alt.Axis(tickMinStep=1)),
                    color=alt.Color("Sektor:N", legend=None,
                                    scale=alt.Scale(range=["#0071E3", "#248A3D", "#D97706", "#A855F7",
                                                           "#DB2777", "#0891B2", "#7C3AED", "#DC2626",
                                                           "#65A30D", "#0D9488", "#F59E0B", "#6366F1"])),
                    tooltip=["Sektor:N", "Positionen:Q", alt.Tooltip("Anteil:Q", format=".1f"), "Aktien:N"],
                ).properties(height=max(130, len(sektor_df) * 43))
                st.altair_chart(chart, width="stretch")
                st.caption(f"{summe} Positionen in {len(sektoren)} Sektoren (einschließlich unbekannter Branchen).")
                st.dataframe(sektor_df, hide_index=True, width="stretch",
                             column_config={"Anteil": st.column_config.NumberColumn("Anteil (%)", format="%.1f")})
                if "Unbekannt" in sektoren:
                    st.caption("Für die unter 'Unbekannt' gelisteten Aktien liefert Yahoo derzeit keine Sektordaten.")

        st.divider()
        st.markdown("### Watchlist")
        if not watchlist:
            st.info("Deine Watchlist ist noch leer.")
        else:
            for ticker, position in list(watchlist.items()):
                with st.container(border=True):
                    a, b = st.columns([3, 1])
                    a.markdown(f"**{html.escape(position.get('name', ticker))}** · `{ticker}`")
                    if b.button("Entfernen", key=f"entferne_watch_{ticker}"):
                        ext.watchlist_entfernen(portfolio, ticker)
                        if portfolio_schreiben(portfolio):
                            st.rerun()
        with st.expander("Anderen Ticker zur Watchlist hinzufügen"):
            ticker_neu = st.text_input("Yahoo-Ticker / ISIN", key="portfolio_ticker_neu").strip().upper()
            if st.button("Zur Watchlist hinzufügen", key="portfolio_watch_hinzufuegen"):
                ticker_neu = isin_zu_ticker(ticker_neu) if k.ISIN_MUSTER.match(ticker_neu) else ticker_neu
                try:
                    ext.watchlist_hinzufuegen(portfolio, ticker_neu, ticker_neu)
                except ValueError as exc:
                    st.warning(str(exc))
                else:
                    if portfolio_schreiben(portfolio):
                        st.rerun()


with tab_einzel:
    with st.container(key="karte_suche"):
        suche = st.text_input("Name, ISIN, WKN oder Ticker", placeholder="z. B. Billerud, DE0007164600 oder SAP.DE")
        if suche:
            treffer = []
            try:
                import yfinance as yf
                treffer = [q for q in yf.Search(suche, max_results=10, news_count=0).quotes if q.get("symbol")]
            except Exception:
                pass
            if not treffer:
                treffer = [{"symbol": suche.strip().upper(), "shortname": "", "exchDisp": ""}]
            beschriftung = {q["symbol"]: f"{q['symbol']} – {q.get('longname') or q.get('shortname') or ''} "
                                         f"({q.get('exchDisp') or q.get('exchange') or '?'})" for q in treffer}
            symbol = st.selectbox("Treffer", list(beschriftung), format_func=beschriftung.get)
            kurse, fehler = lade_kurse((symbol,))
            if kurse.empty or symbol not in kurse.columns or kurse[symbol].dropna().empty:
                st.error("Für diesen Ticker liefert Yahoo keine Kurse." + (f" ({fehler})" if fehler else ""))
            else:
                name = beschriftung[symbol].split(" – ", 1)[-1].rsplit(" (", 1)[0].strip()
                zeige_details(symbol, name, kurse[symbol], 26)
                st.caption("Zeile für deine Liste oder dein Depot:")
                st.code(f"{symbol:<12}# {name}", language=None)

# ---------------- E-Mail


def naechster_freitag() -> str:
    heute = dt.date.today()
    tage = (4 - heute.weekday()) % 7
    if tage == 0 and dt.datetime.now().hour >= 13:
        tage = 7
    return (heute + dt.timedelta(days=tage)).strftime("%d.%m.")


STATUS_TEXT = {"queued": "wartet", "in_progress": "läuft gerade", "waiting": "wartet", "pending": "wartet"}
ERGEBNIS_TEXT = {"success": "✓ verschickt", "failure": "✗ Fehler", "cancelled": "abgebrochen", "skipped": "übersprungen"}

with tab_mail:
    import github_verbindung as ghv
    import wochenmail as wm

    token, pin = geheimnis("GITHUB_TOKEN"), geheimnis("APP_PIN")
    projekt = geheimnis("GITHUB_PROJEKT", "lukasa-ui/rsl-scanner")

    if not token or not pin:
        st.markdown(
            "Hier stellst du die Freitags-E-Mail ein: welche Listen drin sind und an welche Adresse sie geht. "
            "Dafür braucht die App einmalig einen Schlüssel zu deinem GitHub-Projekt und eine PIN, "
            "damit niemand sonst deine Einstellungen ändern kann.")
        st.markdown(
            "1. Bei GitHub einen Schlüssel erzeugen: **Settings → Developer settings → Personal access tokens → "
            "Fine-grained tokens → Generate new token**. Zugriff nur auf *rsl-scanner*, Berechtigungen "
            "*Actions, Contents, Secrets, Workflows* jeweils auf **Read and write**.\n"
            "2. Bei share.streamlit.io neben der App **⋮ → Settings → Secrets** öffnen und eintragen. "
            "Die PIN denkst du dir selbst aus (z. B. vier Ziffern) – sie schützt nur diesen Bereich:")
        st.code('GITHUB_TOKEN = "github_pat_…"\nAPP_PIN = "1234"', language="toml")
        st.markdown("3. Speichern – die App startet neu und dieser Bereich wird freigeschaltet.")
    elif not st.session_state.get("mail_frei"):
        st.write("Gib die App-PIN ein, die du bei Streamlit unter »Secrets« als APP_PIN festgelegt hast.")
        eingabe = st.text_input("App-PIN", type="password", key="pin_eingabe")
        if st.button("Entsperren"):
            if eingabe == str(pin):
                st.session_state["mail_frei"] = True
                st.rerun()
            else:
                st.error("Die PIN stimmt nicht.")
    else:
        gh = ghv.GitHub(token, projekt)
        stand = None
        try:
            if "mail_stand" not in st.session_state:
                with st.spinner("Lade die aktuellen Einstellungen von GitHub …"):
                    text, _ = gh.lies_datei("email_einstellungen.txt")
                    st.session_state["mail_stand"] = {
                        "cfg": wm.einstellungen_aus_text(text or ""),
                        "secrets": gh.vorhandene_secrets(),
                        "zeitplan": gh.zeitplan_vorhanden(),
                    }
            stand = st.session_state["mail_stand"]
        except Exception as e:
            st.error(f"GitHub ist nicht erreichbar: {e}")

    if token and pin and st.session_state.get("mail_frei") and stand is not None:
        cfg = stand["cfg"]
        zugang_ok = all(n in stand["secrets"] for n in ghv.SECRET_NAMEN)
        try:
            laeufe = gh.letzte_laeufe(5) if stand["zeitplan"] else []
        except Exception:
            laeufe = []
        letzter = laeufe[0] if laeufe else None
        laeuft = letzter is not None and letzter["status"] != "completed"
        test_ok = letzter is not None and letzter["ergebnis"] == "success"
        konto = (f" ({cfg['versand_adresse']} über {cfg['versand_server']})"
                 if cfg.get("versand_adresse") and cfg.get("versand_server") else "")

        haken = lambda ok: "✓" if ok else "○"
        st.html('<ul class="rsl-status">' + "".join(
            f'<li class="{"" if ok else "offen"}">{haken(ok)}&nbsp; {html.escape(t)}</li>'
            for ok, t in ((zugang_ok, "E-Mail-Zugang hinterlegt" + konto),
                          (stand["zeitplan"], "Zeitplan eingerichtet"),
                          (test_ok, "Letzte E-Mail erfolgreich verschickt"))) + "</ul>")

        if laeuft:
            st.info("Eine E-Mail wird gerade erstellt und verschickt. In 1–3 Minuten unten auf "
                    "»Status aktualisieren« tippen.")
        elif letzter is not None and letzter["ergebnis"] == "failure":
            gruende = st.session_state.setdefault("fehlergruende", {})
            if letzter["id"] not in gruende:
                try:
                    gruende[letzter["id"]] = gh.fehlergrund(letzter["id"])
                except Exception:
                    gruende[letzter["id"]] = ""
            grund = gruende[letzter["id"]] or "Der Grund ließ sich nicht auslesen – siehe Link unter »Letzte Läufe«."
            st.error(f"**Die letzte E-Mail ist nicht angekommen.** {grund}")
        elif test_ok and zugang_ok and stand["zeitplan"] and cfg.get("aktiv", "ja") != "nein":
            st.success(f"Alles eingerichtet. Die nächste E-Mail kommt am Freitag, {naechster_freitag()}, "
                       "gegen 13 Uhr.")
        elif zugang_ok and stand["zeitplan"]:
            st.info("Fast fertig: Sende unten eine Testmail, um zu prüfen, ob alles funktioniert.")

        # ---- Inhalt
        with st.container(key="karte_mail_inhalt"):
            st.markdown("#### Was soll in der E-Mail stehen?")
            mail_optionen = [l for l in listen if l == "Meine Liste"] + [k.ALLE] + list(k.INDIZES) + \
                            [l for l in listen if l != "Meine Liste"]
            gewaehlt = [n for gruppe in cfg["scan"] for n in gruppe if n in mail_optionen]
            mail_auswahl = st.multiselect("Ranglisten (jede wird ein eigener Abschnitt und ein eigenes Excel-Blatt)",
                                          mail_optionen, default=gewaehlt or ["Meine Liste"])
            m1, m2 = st.columns(2)
            mail_grenze = m1.number_input("Grün markieren: beste … %", 1, 100, int(cfg["top_prozent"]), 5, key="m_gr")
            mail_anzahl = m2.number_input("Werte im Text der Mail (0 = alle)", 0, 2000, int(cfg["anzahl"]), 10, key="m_an",
                                          help="Die vollständige Liste hängt immer als Excel-Datei an.")
            mail_aktiv = st.toggle("E-Mail jeden Freitag verschicken", value=cfg.get("aktiv", "ja") != "nein")
            if st.button("Inhalt speichern"):
                if not mail_auswahl:
                    st.error("Wähle mindestens eine Rangliste aus.")
                else:
                    neu = dict(cfg, scan=[[n] for n in mail_auswahl], top_prozent=float(mail_grenze),
                               anzahl=int(mail_anzahl), aktiv="ja" if mail_aktiv else "nein")
                    try:
                        gh.schreibe_datei("email_einstellungen.txt", wm.einstellungen_als_text(neu),
                                          "E-Mail-Inhalt geändert (aus der App)")
                        stand["cfg"] = neu
                        st.success("Gespeichert. Gilt ab der nächsten E-Mail.")
                    except Exception as e:
                        st.error(f"Speichern fehlgeschlagen: {e}")

        # ---- Versand
        with st.container(key="karte_mail_konto"):
            st.markdown("#### Über welches E-Mail-Konto wird verschickt?")
            if zugang_ok:
                st.caption("Zugangsdaten sind hinterlegt. Zum Ändern einfach neu eintragen und speichern.")
            anbieter = st.selectbox("Anbieter", list(ghv.ANBIETER))
            server, port, hinweis = ghv.ANBIETER[anbieter]
            if anbieter == "Anderer Anbieter":
                v1, v2 = st.columns([3, 1])
                server = v1.text_input("SMTP-Server", placeholder="z. B. smtp.example.de")
                port = int(v2.number_input("Port", 1, 65535, 587))
            st.caption(hinweis)
            adresse = st.text_input(f"Deine E-Mail-Adresse bei {anbieter if anbieter != 'Anderer Anbieter' else 'deinem Anbieter'}",
                                    placeholder="z. B. name@gmx.de")
            passwort = st.text_input(
                f"Passwort deines E-Mail-Kontos" + (" (App-Passwort)" if anbieter == "Gmail" else ""),
                type="password",
                help="Das Passwort, mit dem du dich bei deinem E-Mail-Anbieter anmeldest – nicht die App-PIN. "
                     "Es wird verschlüsselt bei GitHub gespeichert und ist danach nicht mehr lesbar.")
            empfaenger = st.text_input("Empfänger (leer = an dich selbst)",
                                       help="Mehrere Adressen mit Komma trennen.")
            if st.button("Zugangsdaten speichern"):
                if not (server and adresse and passwort):
                    st.error("Bitte Anbieter, E-Mail-Adresse und Passwort ausfüllen.")
                else:
                    try:
                        gh.setze_secrets({"SMTP_SERVER": server, "SMTP_PORT": str(port),
                                          "SMTP_BENUTZER": adresse.strip(), "SMTP_PASSWORT": passwort,
                                          "EMAIL_AN": empfaenger.strip() or adresse.strip()})
                        stand["secrets"] = gh.vorhandene_secrets()
                        # Adresse und Server (ohne Passwort) merken, damit oben angezeigt wird, was hinterlegt ist
                        neu = dict(stand["cfg"], versand_adresse=adresse.strip(), versand_server=server)
                        gh.schreibe_datei("email_einstellungen.txt", wm.einstellungen_als_text(neu),
                                          "E-Mail-Konto geändert (aus der App)")
                        stand["cfg"] = neu
                        st.success("Zugangsdaten verschlüsselt gespeichert. Jetzt unten eine Testmail senden.")
                    except Exception as e:
                        st.error(f"Speichern fehlgeschlagen: {e}")

        # ---- Zeitplan und Test
        with st.container(key="karte_mail_zeit"):
            st.markdown("#### Zeitplan und Test")
            if not stand["zeitplan"]:
                st.write("Der Zeitplan (freitags gegen 13 Uhr) ist noch nicht eingerichtet.")
                if st.button("Zeitplan einrichten"):
                    try:
                        gh.zeitplan_einrichten()
                        stand["zeitplan"] = True
                        st.success("Zeitplan eingerichtet. Nach etwa einer Minute kannst du eine Testmail senden.")
                    except Exception as e:
                        st.error(f"Einrichten fehlgeschlagen: {e}")
            else:
                st.write("Eingerichtet: jeden Freitag gegen 13 Uhr.")
            if st.button("Testmail jetzt senden", disabled=not (stand["zeitplan"] and zugang_ok)):
                try:
                    gh.jetzt_starten()
                    st.success("Gestartet. In 2–4 Minuten auf »Status aktualisieren« tippen – oben steht dann, "
                               "ob die E-Mail verschickt wurde.")
                except Exception as e:
                    st.error(str(e))
            if stand["zeitplan"]:
                if laeufe:
                    st.caption("Letzte Läufe:")
                    for l in laeufe:
                        zeit = pd.Timestamp(l["start"]).tz_convert("Europe/Berlin").strftime("%d.%m. %H:%M")
                        status = ERGEBNIS_TEXT.get(l["ergebnis"], STATUS_TEXT.get(l["status"], l["status"]))
                        art = "von Hand" if l["art"] == "workflow_dispatch" else "planmäßig"
                        st.markdown(f"- {zeit} Uhr, {art}: [{status}]({l['link']})")
                if st.button("Status aktualisieren"):
                    st.rerun()

# ---------------- Hilfe
with tab_hilfe, st.container(key="karte_hilfe"):
    st.markdown("""
#### So wird gerechnet
RSL = aktueller Kurs geteilt durch den Durchschnitt der letzten 26 Wochenschlusskurse.
Über 1 heißt: Der Kurs liegt über seinem Halbjahresdurchschnitt. Je höher, desto stärker.
Die laufende Woche zählt mit dem aktuellsten Kurs. Kurse sind um Dividenden und Splits bereinigt.

#### Die Rangliste lesen
- **Grün hinterlegt:** die besten 30 % (in den Einstellungen änderbar)
- **Δ:** Plätze gewonnen (▲) oder verloren (▼) seit letzter Woche, »neu« = letzte Woche noch keine RSL
- **vor 4 Wo.:** die RSL von vor vier Wochen – steigt oder sinkt die Stärke?
- **R²:** Güte der geraden Trendlinie durch die logarithmierten Wochenschlusskurse. Ein Wert von `0,89` entspricht 89 % erklärter Streuung (keine Erfolgswahrscheinlichkeit). R² liegt zwischen 0 und 1, unabhängig von der Trendrichtung. Standardzeitraum: 26 Wochen, in den Einstellungen änderbar.
- **Sektor:** Yahoo-Branche, soweit lieferbar, sonst »Unbekannt«. Bei großen Listen portionsweise abrufbar.
- **Depot:** Warnung, wenn Rang außerhalb der eingestellten grünen Zone oder RSL unter 1 liegt.
- **⚠️ hinter dem Namen:** seit über 10 Tagen kein neuer Kurs
- Kurs, Durchschnitt und Datum stehen in der Excel-Datei unter »Mehr zu diesem Scan«.

#### Dateien im GitHub-Projekt
- Private Depots liegen nach Google-Anmeldung in **getrennten Dateien in einem separaten privaten GitHub-Repository**. Das frühere öffentliche `portfolio.json` wird nicht mehr verwendet.
- `depot.txt` – Altdatei im öffentlichen Repository, wird aus Datenschutzgründen nicht mehr als Depotmarkierung gelesen.
- `listen/` – eigene Listen, z. B. `listen/beobachtung.txt` (erscheint dann in der Auswahl)
- `email_einstellungen.txt` – Inhalt der Freitags-E-Mail (am einfachsten im Reiter »E-Mail« ändern)
- `indizes/` – hinterlegte Indexlisten (DAX-Familie, Euro Stoxx 50, ATX, GCX, LuxX)

#### Woher die Indexlisten kommen
S&P 500 live von GitHub, Nasdaq-100 live von nasdaq.com, Dow Jones und FTSE MIB live von Wikipedia.
DAX, MDAX, SDAX, TecDAX, Euro Stoxx 50, ATX, Global Challenges Index und LuxX aus hinterlegten Listen –
die DAX-Familie wird im März, Juni, September und Dezember überprüft. **Planspiel Börse** umfasst alle
Indizes außer S&P 500 und alle eigenen Listen.

#### Ticker-Endungen bei Yahoo
`.DE` Xetra, `.PA` Paris, `.AS` Amsterdam, `.L` London, `.SW` Schweiz, `.ST` Stockholm, `.CO` Kopenhagen,
`.OL` Oslo, `.MC` Madrid, `.VI` Wien, `.MI` Mailand, `.T` Tokio, `.TO` Toronto, ohne Endung USA.
""")
    if listen:
        with st.expander("Inhalt meiner Listen"):
            for name, pfad in listen.items():
                eintraege = k.lese_tickertext(pfad.read_text(encoding="utf-8"))
                st.markdown(f"**{name}** ({len(eintraege)} Werte)")
                st.dataframe(pd.DataFrame({"Ticker": list(eintraege), "Name": list(eintraege.values())}),
                             hide_index=True, width="stretch")
