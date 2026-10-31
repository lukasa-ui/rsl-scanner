# Einbauanleitung: RSL-Scanner-Update

## 1. Bestehende Daten sichern

Bevor Dateien in GitHub ersetzt werden: `portfolio.json` (Depot und Watchlist), `depot.txt`, `email_einstellungen.txt`, eigene Dateien in `listen/` und die `.streamlit`-Konfiguration sichern. **Die ZIP enthält aus Gründen der Projektvollständigkeit einen älteren Stand dieser Datendateien. Diese beim Aktualisieren eines bereits laufenden Projekts niemals über die neueren Dateien in GitHub kopieren.**

Die Streamlit-Secrets (z. B. `GITHUB_TOKEN` und `APP_PIN`) nicht in den Code oder das Repository schreiben.

## 2. Dateien aktualisieren

Im bestehenden GitHub-Repository `lukasa-ui/rsl-scanner` folgende Dateien aus der ZIP ersetzen:

- `app.py`
- `rsl_erweiterung.py`

Optional `README.md` und `INSTALLATION.md` aktualisieren. `rsl_kern.py`, `github_verbindung.py`, `wochenmail.py`, `requirements.txt` und die Indexlisten sind im Paket unverändert und müssen **nicht** ersetzt werden. Die neue App verwendet die vorhandenen Abhängigkeiten.

Alternativ das bereitgestellte **Update-ZIP** nutzen. Es enthält nur die zu ersetzenden Codedateien, Anleitungen und optionale Tests, aber keine Portfolio- und Konfigurationsdaten.

Commit erstellen. Auf Streamlit Community Cloud wird die App dann normalerweise durch den Repository-Commit neu bereitgestellt. Falls noch der alte Code erscheint, die App in Streamlit neu starten.

## 3. Funktionen überprüfen

1. Rangliste scannen. Die Spalten `RSL`, `Trendqualität`, `Sektor` und `vor 4 Wo.` prüfen. Die Trendqualitätszahl ist das signierte R², **nicht** die Efficiency Ratio.
2. In der Desktop-Rangliste eine Zeile auswählen und `+ Ins Depot` oder `+ Watchlist` klicken. Auf dem Handy erscheinen die Aktionen direkt in den Karten. Doppelte Einträge werden zurückgewiesen.
3. Den Reiter `Mein Depot` öffnen. Ein neu aufgenommener Titel hat einen aktiven Momentum-Stop, einen unveränderten RSL-Referenzwert und einen Kursreferenzwert.
4. Den Kurs- und RSL-Vergleich zum vorherigen Handelstag, die anzeigtbare Kursentwicklung seit Aufnahme und die Warnung beim Verlassen des grünen Bereichs prüfen.
5. Die Sektorverteilung betrachten. Für große Scanlisten `Weitere 20 Sektoren abrufen` verwenden.
6. Auf GitHub prüfen, ob `portfolio.json` genau die gewünschten Änderungen enthält. Die ursprünglichen Depotpositionen dürfen nicht verschwinden.
7. E-Mail-Tab und Excel-/CSV-Export wie bisher kurz prüfen.

## 4. Vorhandene Depotdaten

Die bestehende `portfolio.json` wird gelesen, ohne automatisch historische Aufnahmekurse zu erfinden oder alte Stops einzuschalten. Sektoren werden, sofern Yahoo sie liefert, zusammengefasst und höchstens einmal pro Aktualisierung in der vorhandenen JSON-Datei gespeichert. Bei neuen Positionen werden `aufnahme_kurs`, `rsl_wochen`, `referenz_rsl`, `sektor`, `stop_aktiv`, `stop_schwelle` und `stop_ausgeloest` hinterlegt.

Wenn `GITHUB_TOKEN` fehlt oder GitHub nicht erreichbar ist, werden Änderungen **nicht** vorgetäuscht. Ohne genügend Kursdaten erscheint ein Platzhalter statt einer erfundenen Kennzahl.

## 5. Verifikation und Grenzen

Das Paket wurde offline auf Python-Syntax, R²-, Portfolio-, Rendite- und Stop-Funktionen geprüft. Es wurde **nicht** mit echter Streamlit-Oberfläche und aktuellen Yahoo-/GitHub-Verbindungen im Produktivbetrieb ausgeführt. Nach dem GitHub-Commit den Browser-Test aus Schritt 3 durchführen.
