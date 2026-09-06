# iFlight Nazgul Price Tracker

Kleiner Preis-Tracker für iFlight Nazgul Drohnen mit FastAPI, CSV-Speicherung und Weboberfläche.

## Installation

`uv` installieren:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Projekt klonen:

```bash
git clone <REPOSITORY-URL>
cd nazgul-price-tracker
uv sync
```

Starten:

```bash
uv run python main.py
```

Danach:

```text
http://localhost:8000
```

Im Netzwerk:

```text
http://<IP-DES-RASPBERRY-PI>:8000
```

## systemd

Die Service-Datei liegt bereits im Repository:

```text
nazgul-tracker.service
```

Nach `/etc/systemd/system/` kopieren:

```bash
sudo cp nazgul-tracker.service /etc/systemd/system/
```

Dann:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nazgul-tracker
```

Status prüfen:

```bash
sudo systemctl status nazgul-tracker
```

Logs anzeigen:

```bash
journalctl -u nazgul-tracker -f
```

Nach Änderungen:

```bash
sudo systemctl restart nazgul-tracker
```

## Daten

Die Preise werden gespeichert unter:

```text
data/prices.csv
```
