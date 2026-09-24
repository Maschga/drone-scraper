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


# ---------------------------------------------------------------------------
# Produktkonfiguration
# ---------------------------------------------------------------------------
#
# Grundregel:
# - ausschließlich ELRS 2.4 GHz
# - iFlight Nazgul: nur GPS-Angebote
# - GEPRC Vapor D5: GPS und ohne GPS werden getrennt geführt
#
# So werden unterschiedliche Ausstattungen nicht mehr in einer Preislinie
# vermischt.
# ---------------------------------------------------------------------------

PRODUCTS = [
    # -----------------------------------------------------------------------
    # iFlight Europe – gewünschte GPS-Konfiguration
    # -----------------------------------------------------------------------
    {
        "key": "iflight-dc5-gps",
        "family": "nazgul-dc5",
        "name": "iFlight Nazgul DC5 ECO V1.1 O4 Pro ELRS 2.4GHz + GPS",
        "short_name": "Nazgul DC5 ECO",
        "shop": "iFlight Europe",
        "source": "iflight_shopify",
        "handle": "nazgul-dc5-o4-eco-v1-1-6s-hd",
        "variant_terms": ["elrs", "2.4", "gps"],
        "receiver": "ELRS 2.4 GHz",
        "gps": True,
        "new_account_discount_percent": 5,
        "shipping_mode": "checkout",
        "shipping_label": "Versandpreis/Gratisgrenze im iFlight-Checkout",
    },
    {
        "key": "iflight-evoque-gps",
        "family": "nazgul-evoque",
        "name": "iFlight Nazgul Evoque F5 V3 O4 Pro ELRS 2.4GHz + GPS",
        "short_name": "Nazgul Evoque F5 V3",
        "shop": "iFlight Europe",
        "source": "iflight_shopify",
        "handle": "nazgul-evoque-f5-v3-o4-gps",
        "variant_terms": ["elrs", "2.4", "gps"],
        "receiver": "ELRS 2.4 GHz",
        "gps": True,
        "new_account_discount_percent": 5,
        "shipping_mode": "checkout",
        "shipping_label": "Versandpreis/Gratisgrenze im iFlight-Checkout",
    },

    # -----------------------------------------------------------------------
    # FPV24 – Vapor D5, Produktseite ist die GPS-Version
    # -----------------------------------------------------------------------
    {
        "key": "fpv24-vapor-d5-gps",
        "family": "vapor-d5",
        "name": "GEPRC Vapor-D5 O4 Pro ELRS 2.4GHz + GPS",
        "short_name": "GEPRC Vapor-D5",
        "shop": "FPV24",
        "source": "html",
        "url": (
            "https://www.fpv24.com/de/geprc/"
            "geprc-vapor-d5-hd-dji-o4-pro-fpv-drohne-elrs-24g"
        ),
        "referer": "https://www.fpv24.com/",
        "receiver": "ELRS 2.4 GHz",
        "gps": True,
        "new_account_discount_percent": 0,
        "shipping_mode": "fpv24_de",
        "shipping_label": "DHL/DPD Deutschland",
    },

    # -----------------------------------------------------------------------
    # Rotorama
    # DC5 ohne GPS wird bewusst nicht aufgenommen, da bei iFlight GPS Pflicht.
    # -----------------------------------------------------------------------
    {
        "key": "rotorama-evoque-gps",
        "family": "nazgul-evoque",
        "name": "iFlight Nazgul Evoque F5 V3 O4 Pro 6S ELRS + GPS",
        "short_name": "Nazgul Evoque F5 V3",
        "shop": "Rotorama",
        "source": "html",
        "url": (
            "https://www.rotorama.de/product/"
            "iflight-nazgul-evoque-f5-v3-o4-pro-6s-elrs-s-gps"
        ),
        "referer": "https://www.rotorama.de/",
        "receiver": "ELRS 2.4 GHz",
        "gps": True,
        "new_account_discount_percent": 0,
        "shipping_mode": "fixed",
        "shipping_cost": "5.49",
        "shipping_label": "GLS Deutschland",
    },
    {
        "key": "rotorama-vapor-d5-gps",
        "family": "vapor-d5",
        "name": "GEPRC Vapor D5 O4 Pro 6S ELRS + GPS",
        "short_name": "GEPRC Vapor-D5",
        "shop": "Rotorama",
        "source": "html",
        "url": (
            "https://www.rotorama.de/product/"
            "geprc-vapor-d5-o4-pro-elrs-2-4g"
        ),
        "referer": "https://www.rotorama.de/",
        "receiver": "ELRS 2.4 GHz",
        "gps": True,
        "new_account_discount_percent": 0,
        "shipping_mode": "fixed",
        "shipping_cost": "5.49",
        "shipping_label": "GLS Deutschland",
    },

    # -----------------------------------------------------------------------
    # RCTech.de
    # Versand innerhalb Deutschlands ab 99 EUR kostenlos.
    # -----------------------------------------------------------------------
    {
        "key": "rctech-dc5-gps",
        "family": "nazgul-dc5",
        "name": "iFlight Nazgul DC5 ECO V1.1 O4 Pro ELRS 2.4GHz + GPS",
        "short_name": "Nazgul DC5 ECO",
        "shop": "RCTech.de",
        "source": "html",
        "url": (
            "https://www.rctech.de/"
            "iflight-nazgul-dc5-eco-v11-o4-pro-bnf-elrs-24ghz-gps-fpv-drone"
        ),
        "referer": "https://www.rctech.de/",
        "receiver": "ELRS 2.4 GHz",
        "gps": True,
        "new_account_discount_percent": 0,
        "shipping_mode": "fixed",
        "shipping_cost": "0.00",
        "shipping_label": "Versandkostenfrei ab 99 EUR (DE)",
    },
    {
        "key": "rctech-vapor-d5-gps",
        "family": "vapor-d5",
        "name": "GEPRC Vapor-D5 O4 Pro ELRS 2.4GHz + GPS",
        "short_name": "GEPRC Vapor-D5",
        "shop": "RCTech.de",
        "source": "html",
        "url": "https://www.rctech.de/?a=7717&lang=eng",
        "referer": "https://www.rctech.de/",
        "receiver": "ELRS 2.4 GHz",
        "gps": True,
        "new_account_discount_percent": 0,
        "shipping_mode": "fixed",
        "shipping_cost": "0.00",
        "shipping_label": "Versandkostenfrei ab 99 EUR (DE)",
    },

    # -----------------------------------------------------------------------
    # HobbyDrone.cz
    # DC5 nur als gewünschte GPS-Version.
    # Vapor D5 bewusst in beiden GPS-Ausführungen getrennt.
    # -----------------------------------------------------------------------
    {
        "key": "hobbydrone-dc5-gps",
        "family": "nazgul-dc5",
        "name": "iFlight Nazgul DC5 ECO V1.1 O4 Pro ELRS 2.4GHz + GPS",
        "short_name": "Nazgul DC5 ECO",
        "shop": "HobbyDrone.cz",
        "source": "html",
        "url": (
            "https://www.hobbydrone.cz/de/"
            "fpv-drone-iflight-nazgul-dc5-eco-v1-1-o4-pro-bnf-elrs-2-4ghz-gps/"
        ),
        "referer": "https://www.hobbydrone.cz/de/",
        "receiver": "ELRS 2.4 GHz",
        "gps": True,
        "new_account_discount_percent": 0,
        "shipping_mode": "checkout",
        "shipping_label": "EU-Hauszustellung ab 4,90 EUR; exakt im Checkout",
    },
    {
        "key": "hobbydrone-vapor-d5-nogps",
        "family": "vapor-d5",
        "name": "GEPRC Vapor-D5 O4 Pro ELRS 2.4GHz ohne GPS",
        "short_name": "GEPRC Vapor-D5",
        "shop": "HobbyDrone.cz",
        "source": "html",
        "url": (
            "https://www.hobbydrone.cz/de/"
            "fpv-drone-geprc-vapor-d5-o4-pro-elrs-2-4ghz/"
        ),
        "referer": "https://www.hobbydrone.cz/de/",
        "receiver": "ELRS 2.4 GHz",
        "gps": False,
        "new_account_discount_percent": 0,
        "shipping_mode": "checkout",
        "shipping_label": "EU-Hauszustellung ab 4,90 EUR; exakt im Checkout",
    },
    {
        "key": "hobbydrone-vapor-d5-gps",
        "family": "vapor-d5",
        "name": "GEPRC Vapor-D5 O4 Pro ELRS 2.4GHz + GPS",
        "short_name": "GEPRC Vapor-D5",
        "shop": "HobbyDrone.cz",
        "source": "html",
        "url": (
            "https://www.hobbydrone.cz/de/"
            "fpv-drone-geprc-vapor-d5-o4-pro-elrs-2-4ghz-gps/"
        ),
        "referer": "https://www.hobbydrone.cz/de/",
        "receiver": "ELRS 2.4 GHz",
        "gps": True,
        "new_account_discount_percent": 0,
        "shipping_mode": "checkout",
        "shipping_label": "EU-Hauszustellung ab 4,90 EUR; exakt im Checkout",
    },
]


CSV_FIELDS = [
    "timestamp",
    "key",
    "family",
    "name",
    "variant",
    "receiver",
    "gps",
    "price",
    "currency",
    "available",
    "url",
    "shop_discounted",
    "shipping_cost",
    "shipping_note",
]


# Historische Keys auf die heute passende Variante abbilden.
LEGACY_KEY_MAP = {
    "eco": "iflight-dc5-gps",
    "normal": "iflight-evoque-gps",
    "iflight-nazgul-dc5": "iflight-dc5-gps",
    "iflight-nazgul-evoque": "iflight-evoque-gps",
    "geprc-vapor-d5": "fpv24-vapor-d5-gps",
    "geprc-vapor-d5-rotorama": "rotorama-vapor-d5-gps",
}


PRODUCT_BY_KEY = {
    product["key"]: product
    for product in PRODUCTS
}


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
    return re.sub(
        r"\s+",
        " ",
        text.lower(),
    ).strip()


def shopify_price(raw_price) -> Decimal:
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


def parse_euro_price(
    raw_value: str,
) -> Decimal | None:
    """
    Erkennt z.B. 489,09 EUR, 539.90 EUR oder 1.234,56 EUR.
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
        r"(?<!\d)"
        r"(\d{1,4}(?:[.\s]\d{3})*[,.]\d{2})"
        r"(?!\d)",
        text,
    )

    for token in matches:
        token = token.replace(" ", "")

        if "," in token and "." in token:
            if token.rfind(",") > token.rfind("."):
                token = (
                    token
                    .replace(".", "")
                    .replace(",", ".")
                )
            else:
                token = token.replace(",", "")
        elif "," in token:
            token = token.replace(",", ".")

        try:
            value = Decimal(token)
        except InvalidOperation:
            continue

        if (
            Decimal("50")
            <= value
            <= Decimal("5000")
        ):
            return value

    return None


def choose_variant(
    product: dict,
    required_terms: list[str],
) -> dict:
    """
    Sucht exakt die konfigurierte Shopify-Variante.
    Bei iFlight enthalten required_terms auch "gps", damit nie
    versehentlich die günstigere Nicht-GPS-Version im Vergleich landet.
    """
    variants = product.get("variants", [])
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
            matching.append(variant)

    if not matching:
        titles = [
            str(
                variant.get(
                    "title",
                    "",
                )
            )
            for variant in variants
        ]

        raise RuntimeError(
            "Keine passende Variante gefunden. "
            f"Gesucht: {required_terms}. "
            f"Vorhandene Varianten: {titles}"
        )

    for variant in matching:
        if variant.get("available", False):
            return variant

    return matching[0]


def shipping_for_product(
    config: dict,
    price: Decimal,
) -> tuple[Decimal | None, str]:
    mode = config.get(
        "shipping_mode",
        "checkout",
    )

    if mode == "fixed":
        return (
            Decimal(
                str(
                    config["shipping_cost"]
                )
            ),
            str(
                config.get(
                    "shipping_label",
                    "Versand",
                )
            ),
        )

    if mode == "fpv24_de":
        if price < Decimal("100"):
            cost = Decimal("6.90")
        elif price < Decimal("150"):
            cost = Decimal("5.90")
        else:
            cost = Decimal("3.90")

        return (
            cost,
            str(
                config.get(
                    "shipping_label",
                    "Versand Deutschland",
                )
            ),
        )

    return (
        None,
        str(
            config.get(
                "shipping_label",
                "Versand im Checkout",
            )
        ),
    )


def base_result(
    config: dict,
    *,
    variant: str,
    price: Decimal,
    currency: str,
    available: bool,
    url: str,
    shop_discounted: bool = False,
) -> dict:
    shipping_cost, shipping_note = (
        shipping_for_product(
            config,
            price,
        )
    )

    return {
        "key": config["key"],
        "family": config["family"],
        "name": config["name"],
        "variant": variant,
        "receiver": config["receiver"],
        "gps": bool(config["gps"]),
        "price": f"{price:.2f}",
        "currency": currency,
        "available": available,
        "url": url,
        "shop_discounted": shop_discounted,
        "shipping_cost": (
            f"{shipping_cost:.2f}"
            if shipping_cost is not None
            else ""
        ),
        "shipping_note": shipping_note,
    }


# ---------------------------------------------------------------------------
# iFlight / Shopify
# ---------------------------------------------------------------------------

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

    return response.json().get(
        "currency",
        "EUR",
    )


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

    price = shopify_price(
        variant["price"]
    )

    compare_at_raw = variant.get(
        "compare_at_price"
    )

    compare_at_price = None

    if compare_at_raw not in (
        None,
        "",
    ):
        try:
            compare_at_price = (
                shopify_price(
                    compare_at_raw
                )
            )
        except (
            InvalidOperation,
            TypeError,
            ValueError,
        ):
            compare_at_price = None

    # 5-%-Neukundenrabatt darf nur zusätzlich gerechnet werden,
    # wenn iFlight nicht bereits selbst rabattiert.
    shop_discounted = bool(
        compare_at_price is not None
        and compare_at_price > price
    )

    product_url = (
        f"{IFLIGHT_STORE_URL}/products/"
        f"{config['handle']}"
    )

    return base_result(
        config,
        variant=str(
            variant.get(
                "title",
                "",
            )
        ),
        price=price,
        currency=currency,
        available=bool(
            variant.get(
                "available",
                False,
            )
        ),
        url=product_url,
        shop_discounted=shop_discounted,
    )


# ---------------------------------------------------------------------------
# HTML-Shops: FPV24 / Rotorama / RCTech / HobbyDrone
# ---------------------------------------------------------------------------

def extract_price_near_heading(
    soup: BeautifulSoup,
    *,
    limit: int = 140,
) -> Decimal | None:
    heading = soup.find("h1")

    if heading is None:
        return None

    for node in heading.find_all_next(
        string=True,
        limit=limit,
    ):
        text = " ".join(
            str(node).split()
        )

        if not text:
            continue

        price = parse_euro_price(text)

        if price is not None:
            return price

    return None


def extract_html_price(
    soup: BeautifulSoup,
    config: dict,
) -> Decimal:
    price = extract_price_near_heading(
        soup
    )

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
        ".price",
    ]

    for selector in selectors:
        for node in soup.select(selector):
            for raw_value in (
                node.get("content"),
                node.get("data-price"),
                node.get_text(
                    " ",
                    strip=True,
                ),
            ):
                if not raw_value:
                    continue

                price = parse_euro_price(
                    raw_value
                )

                if price is not None:
                    return price

    page_text = soup.get_text(
        " ",
        strip=True,
    )

    position = (
        page_text
        .lower()
        .find(
            config["short_name"]
            .lower()
        )
    )

    if position != -1:
        price = parse_euro_price(
            page_text[
                position:
                position + 2800
            ]
        )

        if price is not None:
            return price

    raise RuntimeError(
        "Preis konnte nicht erkannt werden."
    )


def extract_html_availability(
    soup: BeautifulSoup,
) -> bool:
    heading = soup.find("h1")

    if heading is not None:
        parts = []

        for node in heading.find_all_next(
            string=True,
            limit=160,
        ):
            text = " ".join(
                str(node).split()
            )

            if text:
                parts.append(text)

        local_text = normalize(
            " ".join(parts)
        )
    else:
        local_text = normalize(
            soup.get_text(
                " ",
                strip=True,
            )[:7000]
        )

    # Immer zuerst negative Marker prüfen.
    unavailable_markers = [
        "auf dem weg",
        "verfügbarkeit überwachen",
        "verfuegbarkeit ueberwachen",
        "artikel vergriffen",
        "momentan nicht verfügbar",
        "momentan nicht verfuegbar",
        "derzeit nicht verfügbar",
        "derzeit nicht verfuegbar",
        "ausverkauft",
        "vorbestellung",
        "vorbestellen",
        "wieder lieferbar",
        "nicht lieferbar",
        "nicht auf lager",
        "nicht verfügbar",
        "nicht verfuegbar",
        "benachrichtigen, wenn verfügbar",
        "benachrichtigen, wenn verfuegbar",
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
        "sofort lieferbar",
        "lagernd",
        "vorrätig",
        "vorraetig",
        "in den warenkorb",
    ]

    return any(
        marker in local_text
        for marker in available_markers
    )


async def fetch_html_product(
    client: httpx.AsyncClient,
    config: dict,
) -> dict:
    response = await client.get(
        config["url"],
        headers={
            "Referer": config.get(
                "referer",
                config["url"],
            ),
            "Accept": (
                "text/html,"
                "application/xhtml+xml,"
                "application/xml;q=0.9,"
                "*/*;q=0.8"
            ),
            "Accept-Language": (
                "de-DE,de;q=0.9,"
                "en;q=0.7"
            ),
        },
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    price = extract_html_price(
        soup,
        config,
    )

    available = (
        extract_html_availability(
            soup
        )
    )

    variant = (
        f"{config['receiver']} · "
        f"{'GPS' if config['gps'] else 'ohne GPS'}"
    )

    return base_result(
        config,
        variant=variant,
        price=price,
        currency="EUR",
        available=available,
        url=config["url"],
    )


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def ensure_csv_schema() -> None:
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
            old_key = row.get(
                "key",
                "",
            )

            mapped_key = (
                LEGACY_KEY_MAP.get(
                    old_key,
                    old_key,
                )
            )

            config = PRODUCT_BY_KEY.get(
                mapped_key,
                {},
            )

            row["key"] = mapped_key
            row.setdefault(
                "family",
                config.get(
                    "family",
                    "",
                ),
            )
            row.setdefault(
                "receiver",
                config.get(
                    "receiver",
                    "",
                ),
            )
            row.setdefault(
                "gps",
                str(
                    bool(
                        config.get(
                            "gps",
                            False,
                        )
                    )
                ).lower(),
            )
            row.setdefault(
                "shop_discounted",
                "false",
            )
            row.setdefault(
                "shipping_cost",
                "",
            )
            row.setdefault(
                "shipping_note",
                "",
            )

            writer.writerow(
                {
                    field: row.get(
                        field,
                        "",
                    )
                    for field in CSV_FIELDS
                }
            )

    temp_file.replace(
        DATA_FILE
    )


def append_csv_rows(
    rows: list[dict],
) -> None:
    DATA_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ensure_csv_schema()

    new_file = (
        not DATA_FILE.exists()
    )

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
            except (
                TypeError,
                ValueError,
            ):
                continue

            old_key = row.get(
                "key",
                "",
            )

            row["key"] = (
                LEGACY_KEY_MAP.get(
                    old_key,
                    old_key,
                )
            )

            config = PRODUCT_BY_KEY.get(
                row["key"],
                {},
            )

            row["family"] = (
                row.get("family")
                or config.get(
                    "family",
                    "",
                )
            )

            row["receiver"] = (
                row.get("receiver")
                or config.get(
                    "receiver",
                    "",
                )
            )

            gps_raw = row.get(
                "gps",
                "",
            )

            if gps_raw == "":
                row["gps"] = bool(
                    config.get(
                        "gps",
                        False,
                    )
                )
            else:
                row["gps"] = (
                    str(gps_raw)
                    .lower()
                    == "true"
                )

            row["available"] = (
                str(
                    row.get(
                        "available",
                        "",
                    )
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

            shipping_raw = row.get(
                "shipping_cost",
                "",
            )

            try:
                row["shipping_cost"] = (
                    float(shipping_raw)
                    if shipping_raw
                    not in (None, "")
                    else None
                )
            except (
                TypeError,
                ValueError,
            ):
                row["shipping_cost"] = None

            row["shipping_note"] = str(
                row.get(
                    "shipping_note",
                    "",
                )
            )

            rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Preisabruf
# ---------------------------------------------------------------------------

async def collect_prices() -> dict:
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
                    f"bestimmt werden: {exc}. "
                    "Nutze EUR."
                )

            for config in PRODUCTS:
                try:
                    if (
                        config["source"]
                        == "iflight_shopify"
                    ):
                        result = (
                            await fetch_iflight_product(
                                client,
                                config,
                                iflight_currency,
                            )
                        )

                    elif (
                        config["source"]
                        == "html"
                    ):
                        result = (
                            await fetch_html_product(
                                client,
                                config,
                            )
                        )

                    else:
                        raise RuntimeError(
                            "Unbekannte Quelle: "
                            f"{config['source']}"
                        )

                    result["timestamp"] = (
                        timestamp
                    )

                    collected.append(
                        result
                    )

                    print(
                        f"[{timestamp}] "
                        f"{result['name']} "
                        f"@ {config['shop']} -> "
                        f"{result['price']} "
                        f"{result['currency']}"
                    )

                except Exception as exc:
                    errors[
                        config["key"]
                    ] = str(exc)

                    print(
                        "[FEHLER] "
                        f"{config['name']} "
                        f"@ {config['shop']}: "
                        f"{exc}"
                    )

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


scheduler = AsyncIOScheduler(
    timezone=TIMEZONE
)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
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

    scheduler.shutdown(
        wait=False
    )


app = FastAPI(
    title="drone-scraper",
    version="0.5.0",
    lifespan=lifespan,
)


@app.get(
    "/",
    include_in_schema=False,
)
async def index():
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


@app.get("/api/prices")
async def api_prices():
    async with file_lock:
        return read_csv_rows()


@app.get("/api/status")
async def api_status():
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
                "key": product["key"],
                "family": product["family"],
                "name": product["name"],
                "short_name": product[
                    "short_name"
                ],
                "shop": product["shop"],
                "receiver": product[
                    "receiver"
                ],
                "gps": product["gps"],
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
                "shipping_mode": product.get(
                    "shipping_mode",
                    "checkout",
                ),
                "shipping_label": product.get(
                    "shipping_label",
                    "",
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
