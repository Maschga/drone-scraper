# drone-scraper

Preis-Tracker für FPV-Drohnen mit FastAPI, stündlicher Erfassung,
CSV-Preisverlauf und responsiver Weboberfläche.

## Überwachte Modelle

- iFlight Nazgul DC5 O4 ECO V1.1 6S HD
- iFlight Nazgul Evoque F5 V3 O4 GPS
- GEPRC Vapor D5 O4 Pro - 6S ELRS mit GPS (Rotorama)
- GEPRC Vapor-D5 HD DJI O4 Pro ELRS 2.4G (FPV24)

Die frühere Vapor D6 wurde entfernt.

## Shops

Die iFlight-Nazgul-Produkte werden über die Shopify-Produkt-API von
iFlight Europe abgefragt.

Die beiden Vapor-D5-Angebote werden direkt von Rotorama und FPV24
aus den Produktseiten ausgelesen.

## iFlight-Neukundenrabatt

Für die beiden iFlight-Nazgul-Produkte ist ein
5-%-Neukundenrabatt konfiguriert.

Der Scraper speichert den aktuellen iFlight-Shoppreis und zusätzlich:

```text
shop_discounted
```

Dabei gilt sinngemäß:

```text
shop_discounted = compare_at_price > price
```

Wenn iFlight den Variantenpreis bereits reduziert hat, werden die
zusätzlichen 5 % nicht noch einmal abgezogen.

Nur wenn der Shoppreis nicht bereits reduziert ist:

```text
Neukundenpreis = Shoppreis × 0,95
```

## Bestehende CSV-Dateien

Ältere `data/prices.csv`-Dateien ohne `shop_discounted` werden beim
nächsten Schreiben automatisch auf das neue Schema migriert.

Die alten Keys `eco` und `normal` werden beim Lesen weiterhin auf
`iflight-nazgul-dc5` bzw. `iflight-nazgul-evoque` gemappt.

## Installation

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
uv run python main.py
```

Danach ist die Website unter `http://localhost:8000` erreichbar.

## API

```text
GET  /api/prices
GET  /api/status
POST /api/collect
```

## Daten

`data/prices.csv` enthält:

```text
timestamp
key
name
variant
price
currency
available
url
shop_discounted
```

## Automatische Erfassung

Beim Programmstart wird sofort ein Preisabruf ausgeführt.
Danach läuft der Abruf einmal pro Stunde.

## systemd

Die mitgelieferte Service-Datei erwartet:

```text
/home/pi/Documents/drone-scraper
```

Installation:

```bash
make install
```

Nach Code-Änderungen:

```bash
make reload
```
