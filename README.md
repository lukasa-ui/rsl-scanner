# RSL-Scanner nach Levy

Web-App zum Screenen von Aktien nach der Relativen Stärke nach Levy (RSL).

- **RSL** = aktueller Kurs ÷ Durchschnitt der letzten 26 Wochenschlusskurse (einstellbar)
- Scannt eigene Listen (Ordner `listen`), DAX, MDAX, S&P 500, Nasdaq-100 oder frei eingegebene Ticker
- Suche nach Name/ISIN → Yahoo-Ticker, RSL und Chart
- Export als Excel/CSV

**Eigene Liste anlegen:** im Ordner `listen` eine `.txt`-Datei anlegen, ein Ticker pro Zeile, Name hinter `#`:

```
SAP.DE      # SAP
BILL.ST     # Billerud
```

Kursdaten: Yahoo Finance (über `yfinance`).
