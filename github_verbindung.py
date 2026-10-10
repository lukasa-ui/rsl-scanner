"""
Verbindung der App zum eigenen GitHub-Projekt.

Damit lassen sich die E-Mail-Einstellungen direkt in der App ändern:
- email_einstellungen.txt lesen und speichern
- E-Mail-Zugangsdaten verschlüsselt als GitHub-»Secrets« ablegen (nur schreibbar, nie lesbar)
- den Freitags-Zeitplan (.github/workflows/wochenmail.yml) anlegen
- die E-Mail sofort von Hand starten und den Status der letzten Läufe abfragen

Benötigt einen »Fine-grained personal access token« mit Zugriff auf genau dieses Projekt und den Rechten
Contents, Secrets, Workflows und Actions (jeweils Read and write).
"""

import base64

import requests

API = "https://api.github.com"
WORKFLOW_PFAD = ".github/workflows/wochenmail.yml"
WORKFLOW_DATEI = "wochenmail.yml"
SECRET_NAMEN = ["SMTP_SERVER", "SMTP_PORT", "SMTP_BENUTZER", "SMTP_PASSWORT", "EMAIL_AN"]

WORKFLOW_YML = """name: RSL-Wochenmail

on:
  schedule:
    # Freitags gegen 13 Uhr deutscher Zeit. GitHub rechnet in UTC, daher zwei Zeilen:
    - cron: "50 10 * * 5"   # 12:50 Uhr Sommerzeit
    - cron: "50 11 * * 5"   # 12:50 Uhr Winterzeit
  workflow_dispatch:        # Start von Hand (auch über die App: »Testmail jetzt senden«)

jobs:
  wochenmail:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Pakete installieren
        run: pip install yfinance curl_cffi pandas lxml requests openpyxl
      - name: Bericht erstellen und versenden
        env:
          ZEITPLAN: ${{ github.event.schedule }}
          SMTP_SERVER: ${{ secrets.SMTP_SERVER }}
          SMTP_PORT: ${{ secrets.SMTP_PORT }}
          SMTP_BENUTZER: ${{ secrets.SMTP_BENUTZER }}
          SMTP_PASSWORT: ${{ secrets.SMTP_PASSWORT }}
          EMAIL_AN: ${{ secrets.EMAIL_AN }}
        run: python wochenmail.py
"""

# Bekannte Anbieter: Server, Port und ein Hinweis, was beim Anbieter vorher einzuschalten ist
ANBIETER = {
    "GMX": ("mail.gmx.net", 587,
            "Bei GMX vorher einschalten: E-Mail → Einstellungen → POP3/IMAP Abruf → »POP3 und IMAP Zugriff erlauben«."),
    "WEB.DE": ("smtp.web.de", 587,
               "Bei WEB.DE vorher einschalten: E-Mail → Einstellungen → POP3/IMAP Abruf → Zugriff erlauben."),
    "Gmail": ("smtp.gmail.com", 465,
              "Bei Gmail funktioniert nur ein App-Passwort: Google-Konto → Sicherheit → Bestätigung in zwei Schritten "
              "einschalten → App-Passwörter → neues Passwort erstellen und hier eintragen."),
    "T-Online": ("securesmtp.t-online.de", 465,
                 "Bei T-Online das eigene E-Mail-Passwort aus dem Kundencenter verwenden (nicht das Login-Passwort)."),
    "Anderer Anbieter": ("", 587, "Server und Port findest du in der Hilfe deines Anbieters unter »SMTP«."),
}


class GitHubFehler(RuntimeError):
    pass


class GitHub:
    def __init__(self, token: str, projekt: str, zweig: str = "main", sitzung=None):
        self.projekt = projekt
        self.zweig = zweig
        self.http = sitzung or requests.Session()
        self.kopf = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"}

    # -------------------------------------------------------------- Grundfunktionen
    def _anfrage(self, art: str, pfad: str, **kw):
        antwort = self.http.request(art, f"{API}/repos/{self.projekt}{pfad}", headers=self.kopf, timeout=30, **kw)
        if antwort.status_code == 401:
            raise GitHubFehler("Der GitHub-Schlüssel ist ungültig oder abgelaufen.")
        if antwort.status_code == 403:
            raise GitHubFehler("Dem GitHub-Schlüssel fehlt eine Berechtigung (Contents, Secrets, Workflows oder "
                               "Actions jeweils auf »Read and write« stellen).")
        return antwort

    def pruefen(self) -> str:
        """Prüft Schlüssel und Projekt. Gibt den Projektnamen zurück."""
        a = self._anfrage("GET", "")
        if a.status_code == 404:
            raise GitHubFehler(f"Projekt »{self.projekt}« nicht gefunden oder der Schlüssel hat keinen Zugriff darauf.")
        a.raise_for_status()
        return a.json().get("full_name", self.projekt)

    # -------------------------------------------------------------- Dateien
    def lies_datei(self, pfad: str) -> tuple[str | None, str | None]:
        """Gibt (Inhalt, sha) zurück – (None, None), wenn die Datei nicht existiert."""
        a = self._anfrage("GET", f"/contents/{pfad}", params={"ref": self.zweig})
        if a.status_code == 404:
            return None, None
        a.raise_for_status()
        daten = a.json()
        return base64.b64decode(daten["content"]).decode("utf-8"), daten["sha"]

    def schreibe_datei(self, pfad: str, inhalt: str, nachricht: str):
        _, sha = self.lies_datei(pfad)
        nutzlast = {"message": nachricht, "branch": self.zweig,
                    "content": base64.b64encode(inhalt.encode("utf-8")).decode("ascii")}
        if sha:
            nutzlast["sha"] = sha
        a = self._anfrage("PUT", f"/contents/{pfad}", json=nutzlast)
        if a.status_code not in (200, 201):
            raise GitHubFehler(f"Speichern von {pfad} fehlgeschlagen ({a.status_code}): {a.text[:200]}")

    # -------------------------------------------------------------- Secrets
    def setze_secrets(self, werte: dict[str, str]):
        from nacl import encoding, public

        a = self._anfrage("GET", "/actions/secrets/public-key")
        a.raise_for_status()
        schluessel = a.json()
        box = public.SealedBox(public.PublicKey(schluessel["key"].encode("utf-8"), encoding.Base64Encoder()))
        for name, wert in werte.items():
            verschluesselt = base64.b64encode(box.encrypt(str(wert).encode("utf-8"))).decode("utf-8")
            b = self._anfrage("PUT", f"/actions/secrets/{name}",
                              json={"encrypted_value": verschluesselt, "key_id": schluessel["key_id"]})
            if b.status_code not in (201, 204):
                raise GitHubFehler(f"Secret {name} konnte nicht gespeichert werden ({b.status_code}).")

    def vorhandene_secrets(self) -> dict[str, str]:
        """Name -> Zeitpunkt der letzten Änderung (die Werte selbst sind nicht lesbar)."""
        a = self._anfrage("GET", "/actions/secrets", params={"per_page": 100})
        a.raise_for_status()
        return {s["name"]: s.get("updated_at", "") for s in a.json().get("secrets", [])}

    # -------------------------------------------------------------- Zeitplan und Läufe
    def zeitplan_vorhanden(self) -> bool:
        inhalt, _ = self.lies_datei(WORKFLOW_PFAD)
        return inhalt is not None

    def zeitplan_einrichten(self):
        self.schreibe_datei(WORKFLOW_PFAD, WORKFLOW_YML, "Zeitplan für die Freitags-E-Mail (aus der App)")

    def jetzt_starten(self):
        a = self._anfrage("POST", f"/actions/workflows/{WORKFLOW_DATEI}/dispatches", json={"ref": self.zweig})
        if a.status_code == 404:
            raise GitHubFehler("Der Zeitplan ist noch nicht eingerichtet (oder GitHub kennt ihn noch nicht – "
                               "nach dem Einrichten eine Minute warten).")
        if a.status_code != 204:
            raise GitHubFehler(f"Start fehlgeschlagen ({a.status_code}): {a.text[:200]}")

    def letzte_laeufe(self, anzahl: int = 3) -> list[dict]:
        a = self._anfrage("GET", f"/actions/workflows/{WORKFLOW_DATEI}/runs", params={"per_page": anzahl})
        if a.status_code == 404:
            return []
        a.raise_for_status()
        return [{"status": r.get("status"), "ergebnis": r.get("conclusion"), "start": r.get("created_at"),
                 "art": r.get("event"), "link": r.get("html_url")} for r in a.json().get("workflow_runs", [])]
