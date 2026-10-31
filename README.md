# RSL-Scanner nach Robert A. Levy

Streamlit-App zum Screenen von Aktien anhand der relativen Stärke nach Levy.

**RSL = letzter verfügbarer Schlusskurs ÷ Durchschnitt der letzten n Wochenschlusskurse.** Standardmäßig n = 26. Der Rechenkern in `rsl_kern.py` bleibt für App und Freitags-E-Mail gemeinsam bestehen.

## Funktionen

- Rangliste mit RSL, Rangänderung, RSL vor vier Wochen, **Trendqualität (signiertes R²)** und Sektor.
- Trendqualität: Betrag entspricht R² einer linearen Regression über die logarithmierten Wochenschlusskurse. Das Vorzeichen kennzeichnet steigenden (+) oder fallenden (−) Trend. **Ein negatives Ergebnis ist kein gewöhnliches mathematisches R²**, sondern eine Vorzeichenkonvention. Beispielsweise `+89 %` = R² von 0,89 mit steigender Trendgeraden.
- Sektor aus Yahoo Finance `.info['sector']`, übersetzt in die bestehenden deutschen Kategorien. Fehlende Sektoren bleiben `Unbekannt`. Um Yahoo nicht zu überlasten, lädt ein Scan zuerst fünf Sektoren, weitere jeweils in 20er-Paketen auf Knopfdruck. Die Werte werden zwischengespeichert.
- Aus der Rangliste per Auswahl (Desktop) oder direkt aus Karten (Handy) in Depot beziehungsweise Watchlist übernehmen.
- Depot-Karten mit Schlusskurs, Tagesveränderung, aktuellem RSL, RSL des vorherigen Handelstags, Referenz-RSL, Sektor, Chart und Kennzahlen.
- Entwicklung seit Aufnahme wird nur aus **beim Hinzufügen gespeichertem Referenzkurs** berechnet. Für alte Positionen ohne Referenzkurs wird keine vermeintliche Rendite erfunden.
- Neuer Depot-Eintrag hat standardmäßig einen aktiven RSL-Momentum-Stop (75 % des ursprünglichen RSL). Alarm wird in `portfolio.json` gespeichert und muss manuell zurückgesetzt werden. Es erfolgt **kein automatischer Kauf oder Verkauf**.
- Warnung für Positionen außerhalb des grünen Rangbereichs, sofern der Titel im letzten Scan enthalten ist.
- Sektorverteilung mit Balkengrafik, Positionszahlen, Prozentanteilen und zugehörigen Tickern.
- Bestehende E-Mail-Einstellungen, Indexlisten, ISIN-Auflösung und Exporte bleiben erhalten.

## Einrichtung

Bitte `INSTALLATION.md` lesen. Vorhandene **`portfolio.json`, `depot.txt`, `email_einstellungen.txt`, `listen/` und `.streamlit`-Secrets nicht blind überschreiben**: Sie enthalten möglicherweise neuere persönliche Daten und Einstellungen.

Zum Starten: `pip install -r requirements.txt` und `streamlit run app.py`. Für GitHub-Synchronisierung benötigt die Streamlit-App `GITHUB_TOKEN` mit Berechtigung `Contents: Read and write`, optional `GITHUB_PROJEKT` (Standard `lukasa-ui/rsl-scanner`).

## Offline-Prüfung

`python -m pytest -q tests/test_rsl_erweiterung.py` (erfordert zusätzlich `pytest`). Die Tests brauchen keinen Yahoo- oder GitHub-Zugang. Die App kann mit `PYTHONPATH=. python tests/smoke_fake_streamlit.py` grob ohne echte Streamlit-Laufzeit durchlaufen werden; dies **ersetzt keinen Live-Test im Browser**.

Kursdaten und Sektoren stammen von Yahoo Finance. Bei Verzögerungen, API-Limits oder fehlenden Daten werden keine künstlichen Zahlen eingesetzt.
