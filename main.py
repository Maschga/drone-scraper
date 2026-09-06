from __future__ import annotations

import asyncio
import csv
import re
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.responses import FileResponse


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

INDEX_FILE = BASE_DIR / "index.html"
DATA_FILE = BASE_DIR / "data" / "prices.csv"

STORE_URL = "https://iflight-rc.eu"

TIMEZONE = ZoneInfo("Europe/Berlin")


PRODUCTS = [
    {
        "key": "eco",
        "name": "Nazgul DC5 O4 ECO V1.1 6S HD",
        "handle": "nazgul-dc5-o4-eco-v1-1-6s-hd",
        "variant_terms": [
            "elrs",
            "2.4",
        ],
    },
    {
        "key": "normal",
        "name": "Nazgul Evoque F5 V3 O4 GPS",
        "handle": "nazgul-evoque-f5-v3-o4-gps",
        "variant_terms": [
            "elrs",
            "2.4",
        ],
    },
]


CSV_FIELDS = [
    "timestamp",
    "key",
    "name",
    "variant",
    "price",
    "currency",
    "available",
    "url",
]


# ---------------------------------------------------------------------------
# Locks / Status
# ---------------------------------------------------------------------------

scrape_lock = asyncio.Lock()
file_lock = asyncio.Lock()


state = {
    "last_run": None,
    "last_success": None,
    "last_errors": {},
}


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    """
    Text vereinheitlichen, damit Varianten einfacher verglichen werden können.
    """
    return re.sub(
        r"\s+",
        " ",
        text.lower(),
    ).strip()


def shopify_price(raw_price) -> Decimal:
    """
    Shopify liefert Preise über /products/...js üblicherweise
    in der kleinsten Währungseinheit.

    Beispiel:
        49999 -> 499.99 EUR
    """

    if isinstance(raw_price, int):
        return Decimal(raw_price) / Decimal("100")

    if isinstance(raw_price, float):
        return Decimal(str(raw_price)) / Decimal("100")

    text = str(raw_price).strip()

    if re.fullmatch(r"-?\d+", text):
        return Decimal(text) / Decimal("100")

    return Decimal(
        text.replace(",", ".")
    )


def choose_variant(
    product: dict,
    required_terms: list[str],
) -> dict:
    """
    Sucht die passende ELRS-2.4-GHz-Variante.

    Da die aktuell angebotenen Varianten laut Shop bereits GPS enthalten,
    wird GPS nicht zusätzlich über den Variantennamen gefiltert.
    """

    variants = product.get(
        "variants",
        [],
    )

    matching = []

    for variant in variants:
        title = normalize(
            str(
                variant.get(
                    "title",
                    "",
                )
            )
        )

        if all(
            term.lower() in title
            for term in required_terms
        ):
            matching.append(
                variant
            )

    if not matching:
        available_titles = [
            str(
                variant.get(
                    "title",
                    "",
                )
            )
            for variant in variants
        ]

        raise RuntimeError(
            "Keine passende ELRS-2.4-GHz-Variante gefunden. "
            f"Gesucht: {required_terms}. "
            f"Vorhandene Varianten: {available_titles}"
        )

    # Wenn mehrere Varianten passen:
    # zuerst eine aktuell verfügbare auswählen.
    for variant in matching:
        if variant.get(
            "available",
            False,
        ):
            return variant

    # Falls momentan nichts lieferbar ist,
    # trotzdem den Preis der Variante speichern.
    return matching[0]


# ---------------------------------------------------------------------------
# Shopify
# ---------------------------------------------------------------------------

async def set_german_store_context(
    client: httpx.AsyncClient,
) -> None:
    """
    Versucht Shopify explizit auf Deutschland zu setzen.

    Der Cookie bleibt anschließend im httpx-Client erhalten.
    """

    response = await client.post(
        f"{STORE_URL}/localization",
        data={
            "form_type": "localization",
            "utf8": "✓",
            "_method": "put",
            "country_code": "DE",
            "return_to": "/",
        },
    )

    response.raise_for_status()


async def get_currency(
    client: httpx.AsyncClient,
) -> str:
    """
    Liest die aktuell vom Shop verwendete Währung aus dem Shopify-Warenkorb.
    """

    response = await client.get(
        f"{STORE_URL}/cart.js"
    )

    response.raise_for_status()

    data = response.json()

    return data.get(
        "currency",
        "EUR",
    )


async def fetch_product(
    client: httpx.AsyncClient,
    config: dict,
    currency: str,
) -> dict:
    """
    Holt die Shopify-Produktdaten und sucht die gewünschte Variante.
    """

    api_url = (
        f"{STORE_URL}/products/"
        f"{config['handle']}.js"
    )

    response = await client.get(
        api_url
    )

    response.raise_for_status()

    product = response.json()

    variant = choose_variant(
        product,
        config["variant_terms"],
    )

    price = shopify_price(
        variant["price"]
    )

    product_url = (
        f"{STORE_URL}/products/"
        f"{config['handle']}"
    )

    return {
        "key": config["key"],
        "name": config["name"],
        "variant": variant.get(
            "title",
            "",
        ),
        "price": f"{price:.2f}",
        "currency": currency,
        "available": bool(
            variant.get(
                "available",
                False,
            )
        ),
        "url": product_url,
    }


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def append_csv_rows(
    rows: list[dict],
) -> None:
    """
    Hängt neue Messwerte an data/prices.csv an.
    """

    DATA_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    new_file = not DATA_FILE.exists()

    with DATA_FILE.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=CSV_FIELDS,
        )

        if new_file:
            writer.writeheader()

        writer.writerows(
            rows
        )


def read_csv_rows() -> list[dict]:
    """
    Liest alle bisher gespeicherten Preiswerte.
    """

    if not DATA_FILE.exists():
        return []

    rows = []

    with DATA_FILE.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as file:

        reader = csv.DictReader(
            file
        )

        for row in reader:
            try:
                row["price"] = float(
                    row["price"]
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            row["available"] = (
                str(
                    row.get(
                        "available",
                        "",
                    )
                ).lower()
                == "true"
            )

            rows.append(
                row
            )

    return rows


# ---------------------------------------------------------------------------
# Preisabruf
# ---------------------------------------------------------------------------

async def collect_prices() -> dict:
    """
    Ruft beide Preise ab und schreibt sie in die CSV-Datei.

    Durch scrape_lock können nicht zwei Abrufe gleichzeitig laufen.
    """

    async with scrape_lock:

        timestamp = datetime.now(
            TIMEZONE
        ).isoformat(
            timespec="seconds"
        )

        collected = []
        errors = {}

        headers = {
            "User-Agent": (
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/140.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,"
                "application/xhtml+xml,"
                "application/json;q=0.9,"
                "*/*;q=0.8"
            ),
            "Accept-Language": (
                "de-DE,de;q=0.9,"
                "en-US;q=0.8,en;q=0.7"
            ),
        }

        timeout = httpx.Timeout(
            timeout=20.0,
            connect=10.0,
        )

        async with httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        ) as client:

            # ---------------------------------------------------------------
            # Deutschland / EUR setzen
            # ---------------------------------------------------------------

            try:
                await set_german_store_context(
                    client
                )

            except Exception as exc:
                # Nicht sofort abbrechen.
                # Der Shop könnte trotzdem bereits EUR verwenden.
                print(
                    "[WARNUNG] "
                    "Shopify-Lokalisierung konnte "
                    f"nicht gesetzt werden: {exc}"
                )

            # ---------------------------------------------------------------
            # Währung bestimmen
            # ---------------------------------------------------------------

            try:
                currency = await get_currency(
                    client
                )

            except Exception as exc:
                print(
                    "[WARNUNG] "
                    "Währung konnte nicht gelesen werden. "
                    f"Nutze EUR. Fehler: {exc}"
                )

                currency = "EUR"

            # ---------------------------------------------------------------
            # Produkte abrufen
            # ---------------------------------------------------------------

            for config in PRODUCTS:

                try:
                    result = await fetch_product(
                        client,
                        config,
                        currency,
                    )

                    result["timestamp"] = timestamp

                    collected.append(
                        result
                    )

                    print(
                        f"[{timestamp}] "
                        f"{result['name']} -> "
                        f"{result['price']} "
                        f"{result['currency']} "
                        f"({result['variant']})"
                    )

                except Exception as exc:
                    errors[
                        config["key"]
                    ] = str(exc)

                    print(
                        f"[FEHLER] "
                        f"{config['name']}: "
                        f"{exc}"
                    )

        # -------------------------------------------------------------------
        # Ergebnisse speichern
        # -------------------------------------------------------------------

        if collected:

            async with file_lock:
                append_csv_rows(
                    collected
                )

            state["last_success"] = (
                timestamp
            )

        state["last_run"] = timestamp
        state["last_errors"] = errors

        return {
            "timestamp": timestamp,
            "collected": collected,
            "errors": errors,
        }


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

scheduler = AsyncIOScheduler(
    timezone=TIMEZONE
)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    """
    Wird beim Starten/Beenden der FastAPI-Anwendung ausgeführt.
    """

    scheduler.add_job(
        collect_prices,
        trigger="interval",
        hours=1,
        id="nazgul-hourly",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    scheduler.start()

    print(
        "Starte Nazgul Price Tracker..."
    )

    print(
        "Erster Preisabruf..."
    )

    # Beim Start sofort einmal abrufen.
    await collect_prices()

    yield

    scheduler.shutdown(
        wait=False
    )


# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(
    title="iFlight Nazgul Price Tracker",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get(
    "/",
    include_in_schema=False,
)
async def index():
    """
    Liefert die externe index.html aus.
    """

    if not INDEX_FILE.exists():
        return {
            "error": (
                "index.html wurde nicht gefunden. "
                f"Erwartet unter: {INDEX_FILE}"
            )
        }

    return FileResponse(
        INDEX_FILE
    )


@app.get(
    "/api/prices"
)
async def api_prices():
    """
    Liefert alle historischen Preise als JSON.
    """

    async with file_lock:
        rows = read_csv_rows()

    return rows


@app.get(
    "/api/status"
)
async def api_status():
    """
    Statusinformationen für die Weboberfläche.
    """

    return {
        "last_run": state[
            "last_run"
        ],
        "last_success": state[
            "last_success"
        ],
        "last_errors": state[
            "last_errors"
        ],
        "products": [
            {
                "key": product[
                    "key"
                ],
                "name": product[
                    "name"
                ],
            }
            for product in PRODUCTS
        ],
    }


@app.post(
    "/api/collect"
)
async def api_collect():
    """
    Löst einen zusätzlichen manuellen Preisabruf aus.

    Wird vom Button in index.html verwendet.
    """

    return await collect_prices()


# ---------------------------------------------------------------------------
# Programmstart
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
