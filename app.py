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

st.set_page_config(page_title="RSL-Scanner", page_icon="📈", layout="centered")


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
    spalten = ["Rang", "Δ Rang", "Ticker", "RSL", "RSL vor 4 Wo.", "Name"] + (["Depot"] if "Depot" in df else [])
    tab = df[spalten + ["Rang %", "Veraltet"]].copy()
    tab["Name"] = [f"{n} ⚠️" if alt else n for n, alt in zip(tab["Name"], tab["Veraltet"])]
    top = tab["Rang %"] <= grenze
    tab = tab[spalten].rename(columns={"Δ Rang": "Δ", "RSL vor 4 Wo.": "vor 4 Wo."})

    rsl_fmt = lambda v: "–" if pd.isna(v) else k.de_zahl(v, 3)
    stil = (tab.style
            .format({"RSL": rsl_fmt, "vor 4 Wo.": rsl_fmt, "Δ": k.de_rang_delta})
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
                       "vor 4 Wo.": st.column_config.TextColumn(width=72),
                       "Name": st.column_config.TextColumn(width=230),
                       "Depot": st.column_config.TextColumn(width=90)})


def prozent(v) -> str:
    if v is None or pd.isna(v):
        return "–"
    return f'<strong style="color:{farbe(v)}">{"+" if v >= 0 else ""}{k.de_zahl(v, 1)} %</strong>'


def zeige_details(ticker: str, name: str, tageskurse: pd.Series, n: int, zeile=None):
    """Detailansicht: Kernzahlen, Wertentwicklung, Chart und Kennzahlen."""
    import altair as alt

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
tab_scan, tab_einzel, tab_mail, tab_hilfe = st.tabs(["Rangliste", "Aktie suchen", "E-Mail", "Hilfe"])
listen = k.eigene_listen()

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
            grenze = sp1.number_input("Grün markieren: beste … %", 1, 100, 30, 5,
                                      help="Depotwerte außerhalb dieser Grenze oder mit RSL unter 1 bekommen »Verkaufen«.")
            n = int(sp2.number_input("Wochen für die RSL", 5, 80, 26, 1))
            sp3, sp4 = st.columns(2)
            top = sp3.number_input("Nur die besten … zeigen (0 = alle)", 0, 2000, 0, 10)
            min_rsl = sp4.number_input("Nur RSL ab (0 = alle)", 0.0, 5.0, 0.0, 0.01, format="%.2f")
            if st.button("Kurse neu laden", help="Kurse werden eine Stunde zwischengespeichert."):
                lade_kurse.clear()
                st.toast("Beim nächsten Scan werden die Kurse neu geladen.")

        if st.button("Scan starten", type="primary", width="stretch"):
            with st.spinner("Stelle die Liste zusammen …"):
                namen, herkunft, fehler_quellen = k.sammle_universum(auswahl, listen, lade_index)
            for t, name in k.lese_tickertext(zusatz).items():
                namen.setdefault(t, name)
            depot_roh = k.lade_depot()
            isin_fehlend: list[str] = []
            depot = depot_roh
            if any(k.ISIN_MUSTER.match(t) for t in list(namen) + list(depot_roh)):
                with st.spinner("Suche die Yahoo-Ticker zu den ISINs …"):
                    namen, isin_fehlend = k.isins_aufloesen(namen, isin_zu_ticker)
                    depot, _ = k.isins_aufloesen(depot_roh, isin_zu_ticker)

            if not namen:
                st.session_state.pop("ergebnis", None)
                st.warning("Wähle oben eine Liste oder einen Index aus.")
            else:
                with st.spinner(f"Lade Kurse für {len(namen)} Werte …"):
                    kurse, fehler = lade_kurse(tuple(sorted(namen)))
                if kurse.empty:
                    st.session_state.pop("ergebnis", None)
                    if "rate" in fehler.lower() or "too many" in fehler.lower():
                        st.error("Yahoo blockiert gerade zu viele Anfragen. In 15–30 Minuten erneut scannen.")
                    else:
                        st.error("Yahoo hat keine Kurse geliefert. Später erneut scannen." +
                                 (f"\n\nDetails: {fehler}" if fehler else ""))
                else:
                    df, fehlend = k.screene(kurse, namen, n, "wochen")
                    fehlend += [t for t in namen if t not in kurse.columns]
                    fehlend += [f"{x} (ISIN bei Yahoo nicht gefunden)" for x in isin_fehlend]
                    st.session_state["ergebnis"] = {
                        "df": df, "kurse": kurse, "depot": depot, "fehlend": sorted(set(fehlend)), "n": n,
                        "herkunft": herkunft, "fehler_quellen": fehler_quellen,
                        "zeit": dt.datetime.now().strftime("%d.%m.%Y, %H:%M Uhr"),
                    }
                    st.session_state.pop("rangliste", None)
                    st.session_state.pop("zuletzt_geoeffnet", None)

    erg = st.session_state.get("ergebnis")
    if erg and not erg["df"].empty:
        df = k.depot_markieren(erg["df"], erg["depot"], grenze)
        anzeige = df[df["RSL"] >= min_rsl] if min_rsl > 0 else df
        if top:
            anzeige = anzeige.head(int(top))
        anzeige = anzeige.reset_index(drop=True)

        with st.container(key="karte_ergebnis"):
            im_top = int((df["Rang %"] <= grenze).sum())
            st.html(f'<div class="rsl-ergebnis"><h2>{im_top} von {len(df)} Werten in den besten {grenze} %.</h2>'
                    f'<p>Grün hinterlegt. Stand {erg["zeit"]}.</p></div>')

            # Depot als eine ruhige Zeile; Einzelheiten zum Aufklappen
            if erg["depot"]:
                ueb = k.depot_uebersicht(erg["df"], erg["depot"], grenze)
                verk = ueb[ueb["Signal"] == "Verkaufen"]
                halten = int((ueb["Signal"] == "Halten").sum())
                text = (f'<b class="v">Verkaufen: {html.escape(", ".join(verk["Ticker"]))}</b>. '
                        if len(verk) else '<b class="h">Alle Depotwerte halten.</b> ')
                text += f"{halten} von {len(ueb)} Positionen im grünen Bereich."
                st.html(f'<div class="rsl-depot{" alarm" if len(verk) else ""}"><span class="punkt"></span>'
                        f'<span>Depot: {text}</span></div>')
                with st.expander("Depot im Einzelnen"):
                    t2 = ueb[["Ticker", "Signal", "Rang", "RSL", "Δ Rang", "Name"]].copy()
                    st.dataframe(
                        t2.style.format({"Rang": lambda v: "–" if pd.isna(v) else int(v),
                                         "RSL": lambda v: "–" if pd.isna(v) else k.de_zahl(v, 3),
                                         "Δ Rang": lambda v: "–" if pd.isna(v) else k.de_rang_delta(v)}, na_rep="–")
                        .map(lambda v: f"font-weight:600;color:{GRUEN if v == 'Halten' else ROT}"
                             if v in ("Halten", "Verkaufen") else "", subset=["Signal"]),
                        hide_index=True, width="stretch")
                    st.caption(f"Halten heißt: unter den besten {grenze} % und RSL über 1. "
                               "Positionen trägst du in der Datei depot.txt auf GitHub ein.")

            ereignis = zeige_tabelle(anzeige, grenze, "rangliste")
            st.caption("Zeile antippen für Chart und Kennzahlen. Δ = Plätze seit letzter Woche.")

            ersatz = [q for q, _, _, ok in erg["herkunft"] if not ok]
            if ersatz or erg["fehler_quellen"]:
                st.warning("Nicht live abrufbar: " + ", ".join(ersatz + [q for q, _ in erg["fehler_quellen"]])
                           + ". Dafür wurde die hinterlegte Liste verwendet – Details unter »Mehr zu diesem Scan«.")

            zeilen = ereignis.selection.rows if ereignis is not None else []
            gewaehlt = anzeige.iloc[zeilen[0]]["Ticker"] if zeilen else None
            # Fenster nur öffnen, wenn gerade eine neue Zeile angetippt wurde (nicht bei jeder anderen Eingabe)
            if gewaehlt and st.session_state.get("zuletzt_geoeffnet") != gewaehlt:
                st.session_state["zuletzt_geoeffnet"] = gewaehlt
                zeile = erg["df"][erg["df"]["Ticker"] == gewaehlt].iloc[0]
                details_fenster(gewaehlt, zeile["Name"], erg["kurse"][gewaehlt], erg["n"], zeile)
            elif not gewaehlt:
                st.session_state.pop("zuletzt_geoeffnet", None)

            with st.expander("Mehr zu diesem Scan"):
                neu = k.neu_in_top(erg["df"], grenze)
                if not neu.empty:
                    st.markdown(f"**Neu in den besten {grenze} %** seit letzter Woche: "
                                + ", ".join(f"{r.Ticker} ({r.Rang})" for r in neu.itertuples()))
                if erg["fehlend"]:
                    st.markdown(f"**Ohne Kursdaten ({len(erg['fehlend'])}):** " + ", ".join(erg["fehlend"]))
                st.markdown("**Herkunft der Indexlisten:**\n" + "\n".join(
                    f"- {q}: {a} Werte, {h}" for q, a, h, _ in erg["herkunft"]) if erg["herkunft"] else
                    "**Herkunft:** nur eigene Listen.")
                for q, t in erg["fehler_quellen"]:
                    st.markdown(f"- {q}: nicht geladen ({t})")
                datum = dt.date.today().isoformat()
                d1, d2 = st.columns(2)
                d1.download_button("Excel herunterladen", k.als_excel(df), f"rsl_{datum}.xlsx", width="stretch")
                d2.download_button("CSV herunterladen", k.als_csv(df), f"rsl_{datum}.csv", "text/csv", width="stretch")

# ---------------- Aktie suchen
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
def geheimnis(name: str, standard=None):
    """Wert aus den Streamlit-Secrets (App-Einstellungen bei share.streamlit.io)."""
    try:
        return st.secrets.get(name, standard)
    except Exception:
        return standard


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
- **Depot:** Halten = unter den besten 30 % und RSL über 1, sonst Verkaufen
- **⚠️ hinter dem Namen:** seit über 10 Tagen kein neuer Kurs
- Kurs, Durchschnitt und Datum stehen in der Excel-Datei unter »Mehr zu diesem Scan«.

#### Dateien im GitHub-Projekt
- `depot.txt` – deine Positionen, ein Ticker oder eine ISIN pro Zeile, Name hinter `#`
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
