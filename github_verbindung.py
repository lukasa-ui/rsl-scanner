"""
Verbindung der App zum eigenen GitHub-Projekt.

Unterstützt:
- Dateien lesen und schreiben
- GitHub Actions Secrets verschlüsselt setzen
- den Wochenmail-Workflow einrichten, starten und überwachen
"""

import base64
import io
import re
import zipfile

import requests

API = "https://api.github.com"
WORKFLOW_PFAD = ".github/workflows/wochenmail.yml"
WORKFLOW_DATEI = "wochenmail.yml"
SECRET_NAMEN = ["SMTP_SERVER", "SMTP_PORT", "SMTP_BENUTZER", "SMTP_PASSWORT", "EMAIL_AN"]

WORKFLOW_YML = """name: RSL-Wochenmail

on:
  schedule:
    # Freitags 12:50 Uhr deutscher Zeit: Sommer- und Winterzeit in UTC abbilden.
    - cron: "50 10 * * 5"
    - cron: "50 11 * * 5"
  workflow_dispatch:

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

ANBIETER = {
    "GMX": (
        "mail.gmx.net",
        587,
        "Bei GMX vorher den POP3/IMAP-Zugriff in den E-Mail-Einstellungen erlauben.",
    ),
    "WEB.DE": (
        "smtp.web.de",
        587,
        "Bei WEB.DE vorher den POP3/IMAP-Zugriff in den E-Mail-Einstellungen erlauben.",
    ),
    "Gmail": (
        "smtp.gmail.com",
        465,
        "Bei Gmail ein App-Passwort verwenden. Dafür muss die Bestätigung in zwei Schritten aktiv sein.",
    ),
    "T-Online": (
        "securesmtp.t-online.de",
        465,
        "Bei T-Online das E-Mail-Passwort aus dem Kundencenter verwenden.",
    ),
    "Anderer Anbieter": (
        "",
        587,
        "Server und Port findest du in den SMTP-Einstellungen deines Anbieters.",
    ),
}


class GitHubFehler(RuntimeError):
    """Fehler bei GitHub API oder Berechtigungen."""


class GitHub:
    def __init__(self, token: str, projekt: str, zweig: str = "main", sitzung=None):
        self.projekt = projekt.strip("/")
        self.zweig = zweig
        self.http = sitzung or requests.Session()
        self.kopf = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _anfrage(self, art: str, pfad: str, **kw):
        try:
            antwort = self.http.request(
                art,
                f"{API}/repos/{self.projekt}{pfad}",
                headers=self.kopf,
                timeout=30,
                **kw,
            )
        except requests.RequestException as exc:
            raise GitHubFehler(f"GitHub ist nicht erreichbar: {exc}") from exc

        if antwort.status_code == 401:
            raise GitHubFehler("Der GitHub-Schlüssel ist ungültig oder abgelaufen.")
        if antwort.status_code == 403:
            raise GitHubFehler(
                "Dem GitHub-Schlüssel fehlt eine Berechtigung. Prüfe Contents, "
                "Secrets, Workflows und Actions sowie den Zugriff auf das Repository."
            )
        return antwort

    def pruefen(self) -> str:
        """Prüft Schlüssel und Repository-Zugriff."""
        a = self._anfrage("GET", "")
        if a.status_code == 404:
            raise GitHubFehler(
                f"Repository '{self.projekt}' nicht gefunden oder kein Zugriff darauf."
            )
        a.raise_for_status()
        return a.json().get("full_name", self.projekt)

    def lies_datei(self, pfad: str) -> tuple[str | None, str | None]:
        """Gibt (Inhalt, SHA) zurück. Bei fehlender Datei (None, None)."""
        a = self._anfrage(
            "GET",
            f"/contents/{pfad}",
            params={"ref": self.zweig},
        )
        if a.status_code == 404:
            # 404 kann auch ein fehlender Repository-Zugriff sein.
            self.pruefen()
            return None, None

        a.raise_for_status()
        daten = a.json()
        if daten.get("type") != "file":
            raise GitHubFehler(f"{pfad} ist keine normale Datei.")

        kodiert = daten.get("content", "")
        if not kodiert and daten.get("encoding") == "base64":
            raise GitHubFehler(f"GitHub hat für {pfad} keinen Dateiinhalt geliefert.")

        try:
            inhalt = base64.b64decode(kodiert).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise GitHubFehler(f"Datei {pfad} konnte nicht dekodiert werden.") from exc

        return inhalt, daten.get("sha")

    def schreibe_datei(self, pfad: str, inhalt: str, nachricht: str):
        _, sha = self.lies_datei(pfad)
        nutzlast = {
            "message": nachricht,
            "branch": self.zweig,
            "content": base64.b64encode(inhalt.encode("utf-8")).decode("ascii"),
        }
        if sha:
            nutzlast["sha"] = sha

        a = self._anfrage("PUT", f"/contents/{pfad}", json=nutzlast)
        if a.status_code not in (200, 201):
            raise GitHubFehler(
                f"Speichern von {pfad} fehlgeschlagen ({a.status_code}): {a.text[:300]}"
            )

    def setze_secrets(self, werte: dict[str, str]):
        """Setzt GitHub Actions Secrets. Die Werte sind danach nicht auslesbar."""
        try:
            from nacl import encoding, public
        except ImportError as exc:
            raise GitHubFehler(
                "PyNaCl fehlt. Ergänze 'pynacl' in requirements.txt und installiere es."
            ) from exc

        a = self._anfrage("GET", "/actions/secrets/public-key")
        a.raise_for_status()
        schluessel = a.json()
        box = public.SealedBox(
            public.PublicKey(
                schluessel["key"].encode("utf-8"),
                encoding.Base64Encoder(),
            )
        )

        for name, wert in werte.items():
            if not re.fullmatch(r"[A-Z0-9_]+", name):
                raise ValueError(f"Ungültiger Secret-Name: {name}")

            verschluesselt = base64.b64encode(
                box.encrypt(str(wert).encode("utf-8"))
            ).decode("utf-8")

            b = self._anfrage(
                "PUT",
                f"/actions/secrets/{name}",
                json={
                    "encrypted_value": verschluesselt,
                    "key_id": schluessel["key_id"],
                },
            )
            if b.status_code not in (201, 204):
                raise GitHubFehler(
                    f"Secret {name} konnte nicht gespeichert werden "
                    f"({b.status_code}): {b.text[:200]}"
                )

    def vorhandene_secrets(self) -> dict[str, str]:
        """Liefert Secret-Namen und Änderungszeitpunkte, niemals Secret-Werte."""
        a = self._anfrage(
            "GET",
            "/actions/secrets",
            params={"per_page": 100},
        )
        a.raise_for_status()
        return {
            secret["name"]: secret.get("updated_at", "")
            for secret in a.json().get("secrets", [])
        }

    def zeitplan_vorhanden(self) -> bool:
        inhalt, _ = self.lies_datei(WORKFLOW_PFAD)
        return inhalt is not None

    def zeitplan_einrichten(self):
        self.schreibe_datei(
            WORKFLOW_PFAD,
            WORKFLOW_YML,
            "Zeitplan für die Freitags-E-Mail (aus der App)",
        )

    def jetzt_starten(self):
        a = self._anfrage(
            "POST",
            f"/actions/workflows/{WORKFLOW_DATEI}/dispatches",
            json={"ref": self.zweig},
        )
        if a.status_code == 404:
            raise GitHubFehler(
                "Der Zeitplan ist noch nicht eingerichtet oder GitHub kennt ihn "
                "noch nicht. Warte nach dem Einrichten kurz."
            )
        if a.status_code != 204:
            raise GitHubFehler(
                f"Start fehlgeschlagen ({a.status_code}): {a.text[:300]}"
            )

    def letzte_laeufe(self, anzahl: int = 3) -> list[dict]:
        a = self._anfrage(
            "GET",
            f"/actions/workflows/{WORKFLOW_DATEI}/runs",
            params={"per_page": anzahl},
        )
        if a.status_code == 404:
            return []
        a.raise_for_status()
        return [
            {
                "id": lauf.get("id"),
                "status": lauf.get("status"),
                "ergebnis": lauf.get("conclusion"),
                "start": lauf.get("created_at"),
                "art": lauf.get("event"),
                "link": lauf.get("html_url"),
            }
            for lauf in a.json().get("workflow_runs", [])
        ]

    def fehlergrund(self, lauf_id) -> str:
        """Liest GitHub-Action-Logs (ZIP) und sucht nach einer FEHLER-Zeile."""
        a = self._anfrage("GET", f"/actions/runs/{lauf_id}/jobs")
        a.raise_for_status()
        jobs = a.json().get("jobs", [])
        if not jobs:
            return ""

        log_antwort = self._anfrage(
            "GET",
            f"/actions/jobs/{jobs[0]['id']}/logs",
        )
        if log_antwort.status_code != 200:
            return ""

        inhalt = log_antwort.content
        textdateien = []

        try:
            with zipfile.ZipFile(io.BytesIO(inhalt)) as archiv:
                for name in archiv.namelist():
                    if name.lower().endswith((".txt", ".log")):
                        textdateien.append(
                            archiv.read(name).decode("utf-8", errors="replace")
                        )
        except (zipfile.BadZipFile, OSError):
            # Falls GitHub ausnahmsweise direkt Text zurückgibt.
            textdateien = [log_antwort.text]

        zeilen = []
        for datei in textdateien:
            zeilen.extend(datei.splitlines())

        bereinigt = [re.sub(r"^\S+Z\s", "", zeile) for zeile in zeilen]
        treffer = [
            zeile.split("FEHLER:", 1)[1].strip()
            for zeile in bereinigt
            if "FEHLER:" in zeile
        ]
        if treffer:
            return treffer[-1][:500]

        nutzbar = [
            zeile.strip()
            for zeile in bereinigt
            if zeile.strip()
            and not zeile.startswith("##[")
            and "Process completed with exit code" not in zeile
        ]
        return nutzbar[-1][:500] if nutzbar else ""
