from __future__ import annotations

import asyncio
import csv
import re
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.responses import FileResponse


BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "index.html"
DATA_FILE = BASE_DIR / "data" / "prices.csv"

TIMEZONE = ZoneInfo("Europe/Berlin")
IFLIGHT_STORE_URL = "https://iflight-rc.eu"


PRODUCTS = [
    {
        "key": "iflight-nazgul-dc5",
        "name": "iFlight Nazgul DC5 O4 ECO V1.1 6S HD",
        "short_name": "Nazgul DC5 ECO",
        "shop": "iFlight Europe",
        "source": "iflight_shopify",
        "handle": "nazgul-dc5-o4-eco-v1-1-6s-hd",
        "variant_terms": ["elrs", "2.4"],
        "new_account_discount_percent": 5,
    },
    {
        "key": "iflight-nazgul-evoque",
        "name": "iFlight Nazgul Evoque F5 V3 O4 GPS",
        "short_name": "Nazgul Evoque F5 V3",
        "shop": "iFlight Europe",
        "source": "iflight_shopify",
        "handle": "nazgul-evoque-f5-v3-o4-gps",
        "variant_terms": ["elrs", "2.4"],
        "new_account_discount_percent": 5,
    },
    {
        "key": "geprc-vapor-d5-rotorama",
        "name": "GEPRC Vapor D5 O4 Pro - 6S ELRS mit GPS",
        "short_name": "GEPRC Vapor-D5",
        "shop": "Rotorama",
        "source": "rotorama_html",
        "url": (
            "https://www.rotorama.de/product/"
            "geprc-vapor-d5-o4-pro-elrs-2-4g"
        ),
        "variant": "6S ELRS 2.4G + GPS",
        "new_account_discount_percent": 0,
    },
    {
        "key": "geprc-vapor-d5",
        "name": "GEPRC Vapor-D5 HD DJI O4 Pro FPV Drohne ELRS 2.4G",
        "short_name": "GEPRC Vapor-D5",
        "shop": "FPV24",
        "source": "fpv24_html",
        "url": (
            "https://www.fpv24.com/de/geprc/"
            "geprc-vapor-d5-hd-dji-o4-pro-fpv-drohne-elrs-24g"
        ),
        "variant": "ELRS 2.4G",
        "new_account_discount_percent": 0,
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
    "shop_discounted",
]

LEGACY_KEY_MAP = {
    "eco": "iflight-nazgul-dc5",
    "normal": "iflight-nazgul-evoque",
}


scrape_lock = asyncio.Lock()
file_lock = asyncio.Lock()

state = {
    "last_run": None,
    "last_success": None,
    "last_errors": {},
}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def shopify_price(raw_price) -> Decimal:
    """
    Shopify /products/...js liefert Preise normalerweise in Cent.
    """
    if isinstance(raw_price, int):
        return Decimal(raw_price) / Decimal("100")

    if isinstance(raw_price, float):
        return Decimal(str(raw_price)) / Decimal("100")

    text = str(raw_price).strip()

    if re.fullmatch(r"-?\d+", text):
        return Decimal(text) / Decimal("100")

    return Decimal(text.replace(",", "."))


def parse_euro_price(raw_value: str) -> Decimal | None:
    """
    Erkennt z. B. 489,09 €, 539.90 EUR, 1.234,56 € oder 1,234.56.
    """
    text = (
        str(raw_value)
        .replace("\xa0", " ")
        .replace("EUR", " ")
        .replace("eur", " ")
        .replace("€", " ")
        .replace("â‚¬", " ")
        .strip()
    )

    matches = re.findall(
        r"(?<!\d)(\d{1,4}(?:[.\s]\d{3})*[,.]\d{2})(?!\d)",
        text,
    )

    for token in matches:
        token = token.replace(" ", "")

        if "," in token and "." in token:
            if token.rfind(",") > token.rfind("."):
                token = token.replace(".", "").replace(",", ".")
            else:
                token = token.replace(",", "")
        elif "," in token:
            token = token.replace(",", ".")

        try:
            value = Decimal(token)
        except InvalidOperation:
            continue

        if Decimal("50") <= value <= Decimal("5000"):
            return value

    return None


def choose_variant(product: dict, required_terms: list[str]) -> dict:
    variants = product.get("variants", [])
    matching = []

    for variant in variants:
        title = normalize(str(variant.get("title", "")))

        if all(term.lower() in title for term in required_terms):
            matching.append(variant)

    if not matching:
        available_titles = [
            str(variant.get("title", ""))
            for variant in variants
        ]
        raise RuntimeError(
            "Keine passende Variante gefunden. "
            f"Gesucht: {required_terms}. "
            f"Vorhandene Varianten: {available_titles}"
        )

    for variant in matching:
        if variant.get("available", False):
            return variant

    return matching[0]


async def set_iflight_german_context(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        f"{IFLIGHT_STORE_URL}/localization",
        data={
            "form_type": "localization",
            "utf8": "✓",
            "_method": "put",
            "country_code": "DE",
            "return_to": "/",
        },
    )
    response.raise_for_status()


async def get_iflight_currency(
    client: httpx.AsyncClient,
) -> str:
    response = await client.get(
        f"{IFLIGHT_STORE_URL}/cart.js"
    )
    response.raise_for_status()
    data = response.json()
    return data.get("currency", "EUR")


async def fetch_iflight_product(
    client: httpx.AsyncClient,
    config: dict,
    currency: str,
) -> dict:
    api_url = (
        f"{IFLIGHT_STORE_URL}/products/"
        f"{config['handle']}.js"
    )

    response = await client.get(api_url)
    response.raise_for_status()

    product = response.json()
    variant = choose_variant(
        product,
        config["variant_terms"],
    )

    price = shopify_price(variant["price"])

    compare_at_raw = variant.get("compare_at_price")
    compare_at_price = None

    if compare_at_raw not in (None, ""):
        try:
            compare_at_price = shopify_price(
                compare_at_raw
            )
        except (InvalidOperation, TypeError, ValueError):
            compare_at_price = None

    # Zusätzliche 5 % nur, wenn der Shoppreis nicht bereits reduziert ist.
    shop_discounted = bool(
        compare_at_price is not None
        and compare_at_price > price
    )

    product_url = (
        f"{IFLIGHT_STORE_URL}/products/"
        f"{config['handle']}"
    )

    return {
        "key": config["key"],
        "name": config["name"],
        "variant": variant.get("title", ""),
        "price": f"{price:.2f}",
        "currency": currency,
        "available": bool(
            variant.get("available", False)
        ),
        "url": product_url,
        "shop_discounted": shop_discounted,
    }


def extract_price_near_heading(
    soup: BeautifulSoup,
    *,
    limit: int = 120,
) -> Decimal | None:
    heading = soup.find("h1")

    if heading is None:
        return None

    for node in heading.find_all_next(
        string=True,
        limit=limit,
    ):
        text = " ".join(str(node).split())

        if not text:
            continue

        price = parse_euro_price(text)

        if price is not None:
            return price

    return None


def extract_fpv24_price(
    soup: BeautifulSoup,
    config: dict,
) -> Decimal:
    price = extract_price_near_heading(soup)

    if price is not None:
        return price

    selectors = [
        'meta[itemprop="price"]',
        'meta[property="product:price:amount"]',
        '[itemprop="price"]',
        '[data-price]',
        ".product--price",
        ".price--content",
        ".product-price",
        ".article-price",
        ".product-detail-price",
    ]

    for selector in selectors:
        for node in soup.select(selector):
            values = [
                node.get("content"),
                node.get("data-price"),
                node.get_text(" ", strip=True),
            ]

            for raw_value in values:
                if not raw_value:
                    continue

                price = parse_euro_price(raw_value)

                if price is not None:
                    return price

    page_text = soup.get_text(" ", strip=True)

    for product_name in (
        config.get("name", ""),
        config.get("short_name", ""),
    ):
        if not product_name:
            continue

        position = page_text.lower().find(
            product_name.lower()
        )

        if position == -1:
            continue

        price = parse_euro_price(
            page_text[position:position + 2500]
        )

        if price is not None:
            return price

    raise RuntimeError(
        "FPV24-Preis konnte nicht erkannt werden."
    )


def extract_fpv24_availability(
    soup: BeautifulSoup,
) -> bool:
    heading = soup.find("h1")

    if heading is not None:
        parts = [
            " ".join(str(node).split())
            for node in heading.find_all_next(
                string=True,
                limit=100,
            )
        ]
        local_text = normalize(
            " ".join(part for part in parts if part)
        )
    else:
        local_text = normalize(
            soup.get_text(" ", strip=True)[:5000]
        )

    unavailable_markers = [
        "vorbestellung",
        "vorbestellen",
        "wieder lieferbar",
        "nicht lieferbar",
        "nicht verfügbar",
        "nicht verfuegbar",
        "ausverkauft",
        "benachrichtigen",
    ]

    if any(
        marker in local_text
        for marker in unavailable_markers
    ):
        return False

    available_markers = [
        "sofort lieferbar",
        "auf lager",
        "lagernd",
        "sofort versandfertig",
        "in den warenkorb",
    ]

    return any(
        marker in local_text
        for marker in available_markers
    )


async def fetch_fpv24_product(
    client: httpx.AsyncClient,
    config: dict,
) -> dict:
    response = await client.get(
        config["url"],
        headers={
            "Referer": "https://www.fpv24.com/",
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": (
                "de-DE,de;q=0.9,en;q=0.7"
            ),
        },
    )
    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    price = extract_fpv24_price(
        soup,
        config,
    )

    available = extract_fpv24_availability(
        soup
    )

    return {
        "key": config["key"],
        "name": config["name"],
        "variant": config["variant"],
        "price": f"{price:.2f}",
        "currency": "EUR",
        "available": available,
        "url": config["url"],
        "shop_discounted": False,
    }


def extract_rotorama_price(
    soup: BeautifulSoup,
    config: dict,
) -> Decimal:
    price = extract_price_near_heading(
        soup,
        limit=100,
    )

    if price is not None:
        return price

    selectors = [
        'meta[itemprop="price"]',
        'meta[property="product:price:amount"]',
        '[itemprop="price"]',
        '[data-price]',
        ".price",
        ".product-price",
    ]

    for selector in selectors:
        for node in soup.select(selector):
            values = [
                node.get("content"),
                node.get("data-price"),
                node.get_text(" ", strip=True),
            ]

            for raw_value in values:
                if not raw_value:
                    continue

                price = parse_euro_price(raw_value)

                if price is not None:
                    return price

    page_text = soup.get_text(" ", strip=True)
    product_name = config.get("name", "")

    if product_name:
        position = page_text.lower().find(
            product_name.lower()
        )

        if position != -1:
            price = parse_euro_price(
                page_text[position:position + 2000]
            )

            if price is not None:
                return price

    raise RuntimeError(
        "Rotorama-Preis konnte nicht erkannt werden."
    )


def extract_rotorama_availability(
    soup: BeautifulSoup,
) -> bool:
    heading = soup.find("h1")

    if heading is not None:
        parts = [
            " ".join(str(node).split())
            for node in heading.find_all_next(
                string=True,
                limit=100,
            )
        ]
        local_text = normalize(
            " ".join(part for part in parts if part)
        )
    else:
        local_text = normalize(
            soup.get_text(" ", strip=True)[:5000]
        )

    unavailable_markers = [
        "auf dem weg",
        "verfügbarkeit überwachen",
        "verfuegbarkeit ueberwachen",
        "nicht auf lager",
        "nicht verfügbar",
        "nicht verfuegbar",
        "ausverkauft",
    ]

    if any(
        marker in local_text
        for marker in unavailable_markers
    ):
        return False

    available_markers = [
        "auf lager",
        "sofort verfügbar",
        "sofort verfuegbar",
        "lagernd",
        "vorrätig",
        "vorraetig",
        "in den warenkorb",
    ]

    return any(
        marker in local_text
        for marker in available_markers
    )


async def fetch_rotorama_product(
    client: httpx.AsyncClient,
    config: dict,
) -> dict:
    response = await client.get(
        config["url"],
        headers={
            "Referer": "https://www.rotorama.de/",
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": (
                "de-DE,de;q=0.9,en;q=0.7"
            ),
        },
    )
    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    price = extract_rotorama_price(
        soup,
        config,
    )

    available = extract_rotorama_availability(
        soup
    )

    return {
        "key": config["key"],
        "name": config["name"],
        "variant": config["variant"],
        "price": f"{price:.2f}",
        "currency": "EUR",
        "available": available,
        "url": config["url"],
        "shop_discounted": False,
    }


def ensure_csv_schema() -> None:
    """
    Migriert bestehende prices.csv-Dateien automatisch um neue Spalten.
    Alte Historie bleibt erhalten.
    """
    if not DATA_FILE.exists():
        return

    with DATA_FILE.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as file:
        reader = csv.DictReader(file)
        old_fields = reader.fieldnames or []

        if old_fields == CSV_FIELDS:
            return

        rows = list(reader)

    temp_file = DATA_FILE.with_name(
        f"{DATA_FILE.name}.tmp"
    )

    with temp_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=CSV_FIELDS,
            extrasaction="ignore",
        )
        writer.writeheader()

        for row in rows:
            row.setdefault(
                "shop_discounted",
                "false",
            )
            writer.writerow(
                {
                    field: row.get(field, "")
                    for field in CSV_FIELDS
                }
            )

    temp_file.replace(DATA_FILE)


def append_csv_rows(
    rows: list[dict],
) -> None:
    DATA_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ensure_csv_schema()
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

        writer.writerows(rows)


def read_csv_rows() -> list[dict]:
    if not DATA_FILE.exists():
        return []

    rows = []

    with DATA_FILE.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            try:
                row["price"] = float(
                    row["price"]
                )
            except (TypeError, ValueError):
                continue

            old_key = row.get("key", "")
            row["key"] = LEGACY_KEY_MAP.get(
                old_key,
                old_key,
            )

            row["available"] = (
                str(
                    row.get("available", "")
                ).lower()
                == "true"
            )

            row["shop_discounted"] = (
                str(
                    row.get(
                        "shop_discounted",
                        "",
                    )
                ).lower()
                == "true"
            )

            rows.append(row)

    return rows


async def collect_prices() -> dict:
    """
    Ruft alle Produkte ab und speichert den aktuellen Shoppreis.
    Bei iFlight wird separat gespeichert, ob der Shoppreis bereits
    rabattiert ist.
    """
    async with scrape_lock:
        timestamp = datetime.now(
            TIMEZONE
        ).isoformat(timespec="seconds")

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
                "text/html,application/xhtml+xml,"
                "application/json;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": (
                "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7"
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
            iflight_currency = "EUR"

            try:
                await set_iflight_german_context(
                    client
                )
            except Exception as exc:
                print(
                    "[WARNUNG] "
                    "iFlight-Lokalisierung konnte "
                    f"nicht gesetzt werden: {exc}"
                )

            try:
                iflight_currency = (
                    await get_iflight_currency(
                        client
                    )
                )
            except Exception as exc:
                print(
                    "[WARNUNG] "
                    "iFlight-Währung konnte nicht "
                    f"bestimmt werden: {exc}. Nutze EUR."
                )

            for config in PRODUCTS:
                try:
                    source = config["source"]

                    if source == "iflight_shopify":
                        result = await fetch_iflight_product(
                            client,
                            config,
                            iflight_currency,
                        )
                    elif source == "fpv24_html":
                        result = await fetch_fpv24_product(
                            client,
                            config,
                        )
                    elif source == "rotorama_html":
                        result = await fetch_rotorama_product(
                            client,
                            config,
                        )
                    else:
                        raise RuntimeError(
                            f"Unbekannte Quelle: {source}"
                        )

                    result["timestamp"] = timestamp
                    collected.append(result)

                    print(
                        f"[{timestamp}] "
                        f"{result['name']} -> "
                        f"{result['price']} "
                        f"{result['currency']} "
                        f"({result['variant']})"
                    )

                except Exception as exc:
                    errors[config["key"]] = str(exc)
                    print(
                        "[FEHLER] "
                        f"{config['name']}: {exc}"
                    )

        if collected:
            async with file_lock:
                append_csv_rows(collected)

            state["last_success"] = timestamp

        state["last_run"] = timestamp
        state["last_errors"] = errors

        return {
            "timestamp": timestamp,
            "collected": collected,
            "errors": errors,
        }


scheduler = AsyncIOScheduler(
    timezone=TIMEZONE
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        collect_prices,
        trigger="interval",
        hours=1,
        id="drone-scraper-hourly",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    scheduler.start()

    print("Starte drone-scraper...")
    print("Erster Preisabruf...")

    await collect_prices()

    yield

    scheduler.shutdown(wait=False)


app = FastAPI(
    title="drone-scraper",
    version="0.3.0",
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
async def index():
    if not INDEX_FILE.exists():
        return {
            "error": (
                "index.html wurde nicht gefunden. "
                f"Erwartet unter: {INDEX_FILE}"
            )
        }

    return FileResponse(INDEX_FILE)


@app.get("/api/prices")
async def api_prices():
    async with file_lock:
        return read_csv_rows()


@app.get("/api/status")
async def api_status():
    return {
        "last_run": state["last_run"],
        "last_success": state["last_success"],
        "last_errors": state["last_errors"],
        "products": [
            {
                "key": product["key"],
                "name": product["name"],
                "short_name": product["short_name"],
                "shop": product["shop"],
                "url": (
                    product["url"]
                    if "url" in product
                    else (
                        f"{IFLIGHT_STORE_URL}/products/"
                        f"{product['handle']}"
                    )
                ),
                "new_account_discount_percent": (
                    product.get(
                        "new_account_discount_percent",
                        0,
                    )
                ),
            }
            for product in PRODUCTS
        ],
    }


@app.post("/api/collect")
async def api_collect():
    return await collect_prices()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
