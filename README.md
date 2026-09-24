# drone-scraper

EU-Preis-Tracker für:

- iFlight Nazgul DC5 ECO O4 Pro
- iFlight Nazgul Evoque F5 V3 O4 Pro
- GEPRC Vapor D5 O4 Pro

## Deine Konfiguration

Der Tracker ist jetzt ausdrücklich auf folgende Regeln eingestellt:

- **immer ELRS 2.4 GHz**
- **Nazgul DC5 / Evoque: immer mit GPS**
- **Vapor D5: GPS und ohne GPS werden getrennt**
- beim Vapor wird eine Variante **ohne GPS** nicht mit einer GPS-Variante
  in derselben Preislinie vermischt

Dadurch wird nicht mehr versehentlich ein günstigerer Preis einer
schlechter passenden Konfiguration als Vergleichspreis dargestellt.

## Aufgenommene Shops / Varianten

### iFlight Europe

- Nazgul DC5 ECO O4 Pro — ELRS 2.4 GHz + GPS
- Nazgul Evoque F5 V3 O4 Pro — ELRS 2.4 GHz + GPS

Die Shopify-Auswahl sucht explizit nach `elrs`, `2.4` **und** `gps`.

### FPV24

- Vapor D5 O4 Pro — ELRS 2.4 GHz + GPS

Die aktuell geführte FPV24-Produktseite nennt ein integriertes
GEP-M10-GPS.

### Rotorama

- Nazgul Evoque F5 V3 O4 Pro — ELRS 2.4 GHz + GPS
- Vapor D5 O4 Pro — ELRS 2.4 GHz + GPS

Der Rotorama DC5 ECO ELRS ohne GPS wird bewusst nicht in die
Wunschkonfiguration aufgenommen, weil bei iFlight-Modellen GPS Pflicht
ist.

### RCTech.de

- Nazgul DC5 ECO O4 Pro — ELRS 2.4 GHz + GPS
- Vapor D5 O4 Pro — ELRS 2.4 GHz + GPS

Für die betrachteten Drohnen gilt innerhalb Deutschlands die
Versandkostenfreiheit ab 99 EUR.

### HobbyDrone.cz

- Nazgul DC5 ECO O4 Pro — ELRS 2.4 GHz + GPS
- Vapor D5 O4 Pro — ELRS 2.4 GHz **ohne GPS**
- Vapor D5 O4 Pro — ELRS 2.4 GHz **mit GPS**

HobbyDrone ist damit besonders interessant für den Vapor-Vergleich,
weil beide Ausstattungen als eigene Produktseiten geführt werden.

Ein Evoque F5 V3 O4 Pro ELRS 2.4 GHz ist dort gelistet, aber nicht als
klar passende GPS-Konfiguration; er wird deshalb nicht als
Wunschkonfiguration getrackt.

## GPS-Trennung

In `PRODUCTS` besitzt jedes Angebot:

```text
family
receiver
gps
```

Beispiel:

```text
family   = vapor-d5
receiver = ELRS 2.4 GHz
gps      = false
```

oder:

```text
family   = vapor-d5
receiver = ELRS 2.4 GHz
gps      = true
```

Die Weboberfläche erzeugt daraus getrennte Bereiche:

```text
GEPRC Vapor D5 · ohne GPS · ELRS 2.4 GHz
GEPRC Vapor D5 · mit GPS  · ELRS 2.4 GHz
```

Auch die Chart-Linien bleiben getrennt.

## iFlight 5-%-Neukundenrabatt

Der zusätzliche 5-%-Rabatt wird nur angewendet, wenn der aktuelle
Shopify-Variantenpreis **nicht bereits reduziert** ist.

```text
shop_discounted = compare_at_price > price
```

Wenn `shop_discounted = true`, wird kein weiterer 5-%-Rabatt
eingerechnet.

## Versand Deutschland

Aktuell verwendete Regeln:

- **FPV24:** unter 100 EUR = 6,90 EUR; unter 150 EUR = 5,90 EUR;
  ab 150 EUR = 3,90 EUR
- **Rotorama:** GLS Deutschland = 5,49 EUR
- **RCTech.de:** Versandkostenfrei innerhalb Deutschlands ab 99 EUR
- **iFlight Europe:** konkreter Betrag / Gratisgrenze im Checkout
- **HobbyDrone.cz:** EU-Hauszustellung ab 4,90 EUR; exakter Preis
  abhängig von Zielland/Bestellung und daher im Checkout

Bei dynamischem Versand wird kein erfundener Betrag in den
Gesamtpreis gerechnet.

## CSV

`data/prices.csv` enthält:

```text
timestamp
key
family
name
variant
receiver
gps
price
currency
available
url
shop_discounted
shipping_cost
shipping_note
```

Ältere CSV-Dateien werden beim nächsten Schreiben automatisch
auf das neue Schema migriert.

## Installation

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
uv run python main.py
```

Danach:

```text
http://localhost:8000
```

## API

```text
GET  /api/prices
GET  /api/status
POST /api/collect
```

## Quellen / Produktseiten

- iFlight DC5:
  https://iflight-rc.eu/products/nazgul-dc5-o4-eco-v1-1-6s-hd
- iFlight Evoque:
  https://iflight-rc.eu/products/nazgul-evoque-f5-v3-o4-gps
- FPV24 Vapor:
  https://www.fpv24.com/de/geprc/geprc-vapor-d5-hd-dji-o4-pro-fpv-drohne-elrs-24g
- Rotorama Evoque:
  https://www.rotorama.de/product/iflight-nazgul-evoque-f5-v3-o4-pro-6s-elrs-s-gps
- Rotorama Vapor:
  https://www.rotorama.de/product/geprc-vapor-d5-o4-pro-elrs-2-4g
- RCTech DC5:
  https://www.rctech.de/iflight-nazgul-dc5-eco-v11-o4-pro-bnf-elrs-24ghz-gps-fpv-drone
- RCTech Vapor:
  https://www.rctech.de/?a=7717&lang=eng
- HobbyDrone DC5 GPS:
  https://www.hobbydrone.cz/de/fpv-drone-iflight-nazgul-dc5-eco-v1-1-o4-pro-bnf-elrs-2-4ghz-gps/
- HobbyDrone Vapor ohne GPS:
  https://www.hobbydrone.cz/de/fpv-drone-geprc-vapor-d5-o4-pro-elrs-2-4ghz/
- HobbyDrone Vapor GPS:
  https://www.hobbydrone.cz/de/fpv-drone-geprc-vapor-d5-o4-pro-elrs-2-4ghz-gps/
- HobbyDrone Versand:
  https://www.hobbydrone.cz/de/versand-und-zahlungen/
- RCTech Versandhinweis:
  https://www.rctech.de/wir-ueber-uns
