# drone-scraper

Preis-Tracker für FPV-Drohnen mit FastAPI, stündlicher Erfassung,
CSV-Preisverlauf und responsiver Weboberfläche.

Aktuell werden folgende Modelle überwacht:

- iFlight Nazgul DC5 O4 ECO V1.1 6S HD
- iFlight Nazgul Evoque F5 V3 O4 GPS
- GEPRC Vapor-D6 HD DJI O4 Pro ELRS 2.4G
- GEPRC Vapor-D5 HD DJI O4 Pro ELRS 2.4G

## Shops

Die iFlight-Nazgul-Produkte werden über die Shopify-Produkt-API von
iFlight Europe abgefragt.

Die beiden GEPRC-Vapor-Produkte werden direkt von FPV24 aus der
Produktseite ausgelesen.

## iFlight-Neukundenrabatt

Für die beiden iFlight-Nazgul-Produkte ist im Tracker ein
5-%-Neukundenrabatt konfiguriert.

Wichtig:

Der Scraper speichert in `data/prices.csv` immer den regulären
Shoppreis.

Der rabattierte Preis wird nur in der Weboberfläche berechnet:

```text
Neukundenpreis = regulärer Preis × 0,95
```

Dadurch bleiben die historischen Rohdaten unverändert.

Für die GEPRC-Vapor-Produkte wird kein solcher Rabatt berechnet.

## Installation

`uv` installieren:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Repository klonen:

```bash
git clone https://github.com/Maschga/drone-scraper.git
cd drone-scraper
```

Dependencies installieren:

```bash
uv sync
```

Anwendung starten:

```bash
uv run python main.py
```

Danach ist die Website erreichbar unter:

```text
http://localhost:8000
```

Im lokalen Netzwerk beispielsweise:

```text
http://<IP-DES-RASPBERRY-PI>:8000
```

## API

Alle gespeicherten Preise:

```text
GET /api/prices
```

Status, Produkte und Fehler:

```text
GET /api/status
```

Sofort einen neuen Preisabruf starten:

```text
POST /api/collect
```

## Automatische Erfassung

Die Preise werden beim Programmstart sofort einmal abgerufen.

Anschließend läuft der Abruf automatisch einmal pro Stunde.

## Daten

Die Preis-Historie liegt unter:

```text
data/prices.csv
```

Gespeichert werden:

```text
timestamp
key
name
variant
price
currency
available
url
```

`price` ist immer der reguläre Shoppreis.

## Alte Daten

Frühere Versionen des Projekts verwendeten für die beiden
Nazgul-Produkte die Keys:

```text
eco
normal
```

Diese alten Keys werden beim Lesen automatisch umgewandelt:

```text
eco    -> iflight-nazgul-dc5
normal -> iflight-nazgul-evoque
```

Eine vorhandene `data/prices.csv` muss deshalb nicht gelöscht oder
manuell migriert werden.

## systemd

Die neue Service-Datei heißt:

```text
drone-scraper.service
```

Falls noch der alte Service installiert ist:

```bash
sudo systemctl disable --now nazgul-tracker || true
sudo rm -f /etc/systemd/system/nazgul-tracker.service
sudo systemctl daemon-reload
```

Danach den neuen Service installieren:

```bash
make install
```

Status:

```bash
make status
```

Logs:

```bash
make logs
```

Nach Code-Änderungen:

```bash
make reload
```

## Raspberry-Pi-Pfad

Die mitgelieferte systemd-Datei erwartet das Projekt unter:

```text
/home/pi/Documents/drone-scraper
```

Falls dein Repository an einer anderen Stelle liegt, ändere in
`drone-scraper.service`:

```ini
WorkingDirectory=/home/pi/Documents/drone-scraper
```

## Website

Die Weboberfläche zeigt:

- den aktuellen Preis aller Drohnen
- den Shop
- die aktuelle Verfügbarkeit
- die gewählte Variante
- den letzten Messzeitpunkt
- den historischen Preisverlauf
- Zeiträume für 24 Stunden, 7 Tage, 30 Tage und den gesamten Verlauf
- Fehler des letzten Scraper-Laufs
- direkten Link zum jeweiligen Produkt

Bei den iFlight-Nazgul-Modellen werden zusätzlich angezeigt:

- regulärer Shoppreis
- berechneter Preis mit 5 % Neukundenrabatt

Der Rabatt kann für den Preis-Chart ein- oder ausgeschaltet werden.

## Neue Drohne hinzufügen

Weitere Produkte werden zentral in `PRODUCTS` in `main.py`
konfiguriert.

Die Weboberfläche erzeugt die Produktkarten automatisch aus der API,
sodass normalerweise keine weitere HTML-Karte von Hand ergänzt werden
muss.
