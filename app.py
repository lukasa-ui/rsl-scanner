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

GRUEN, ROT, GRAU = "#0F6B4F", "#B3261E", "#6B7A75"
TOP_HG = "background-color: #DDEFE6"

st.html("""
<style>
  .block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 940px; }
  [data-testid="stMarkdownContainer"] p, .rsl-zahl { font-variant-numeric: tabular-nums; }
  .rsl-kopf h1 { font-size: 1.9rem; margin: 0; padding: 0; letter-spacing: -0.01em; }
  .rsl-kopf p { color: #6B7A75; margin: 0.1rem 0 0 0; }
  .rsl-zeile { color: #1C2724; margin: 0; }
  .rsl-zeile b { font-weight: 600; }
  .rsl-depot { border-left: 3px solid #0F6B4F; padding: 0.3rem 0 0.3rem 0.8rem; margin: 0; }
  .rsl-depot.alarm { border-left-color: #B3261E; }
  .rsl-depot b.v { color: #B3261E; }
  .rsl-depot b.h { color: #0F6B4F; }
  .rsl-werte { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.2rem 1.2rem;
               margin: 0.6rem 0 1rem 0; }
  .rsl-werte div span { display: block; color: #6B7A75; font-size: 0.85rem; }
  .rsl-werte div strong { font-size: 1.55rem; font-weight: 600; font-variant-numeric: tabular-nums; }
  .rsl-werte div em { display: block; font-style: normal; font-size: 0.85rem; }
  .rsl-entw { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 0.2rem;
              font-variant-numeric: tabular-nums; margin-bottom: 0.4rem; }
  .rsl-entw div { text-align: center; padding: 0.35rem 0; background: #F1F5F3; border-radius: 4px; }
  .rsl-entw span { display: block; font-size: 0.75rem; color: #6B7A75; }
  .rsl-entw strong { font-weight: 600; font-size: 0.95rem; }
  @media (max-width: 640px) {
    .rsl-entw { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .rsl-werte div strong { font-size: 1.3rem; }
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
      <div><span>Abstand zum Ø</span><strong style="color:{farbe(abstand)}">{'+' if abstand >= 0 else ''}{k.de_zahl(abstand, 1)} %</strong>
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
                            scale=alt.Scale(range=["#1C2724", "#0F6B4F"])),
            strokeDash=alt.StrokeDash("Linie:N", legend=None, scale=alt.Scale(range=[[1, 0], [5, 3]])),
            tooltip=[alt.Tooltip("Datum:T", format="%d.%m.%Y"), "Linie:N", alt.Tooltip("Wert:Q", format=",.2f")],
        ).properties(height=240),
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

st.html(f"""<div class="rsl-kopf"><h1>RSL-Scanner</h1>
<p>Relative Stärke nach Levy für dein Planspiel Börse</p></div>""")
tab_scan, tab_einzel, tab_hilfe = st.tabs(["Rangliste", "Aktie suchen", "Hilfe"])
listen = k.eigene_listen()

# ---------------- Rangliste
with tab_scan:
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

        st.html(f'<p class="rsl-zeile"><b>{len(df)}</b> Werte bewertet, <b>{int((df["Rang %"] <= grenze).sum())}</b> '
                f'davon in den besten {grenze} % (grün). Stand {erg["zeit"]}.</p>')

        # Depot als eine ruhige Zeile; Einzelheiten zum Aufklappen
        if erg["depot"]:
            ueb = k.depot_uebersicht(erg["df"], erg["depot"], grenze)
            verk = ueb[ueb["Signal"] == "Verkaufen"]
            halten = int((ueb["Signal"] == "Halten").sum())
            text = (f'<b class="v">Verkaufen: {html.escape(", ".join(verk["Ticker"]))}</b>. '
                    if len(verk) else '<b class="h">Alle Depotwerte halten.</b> ')
            text += f"{halten} von {len(ueb)} Positionen im grünen Bereich."
            st.html(f'<div class="rsl-depot{" alarm" if len(verk) else ""}">Depot: {text}</div>')
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

# ---------------- Hilfe
with tab_hilfe:
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
- `email_einstellungen.txt` – welche Listen die Freitags-E-Mail enthält
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
