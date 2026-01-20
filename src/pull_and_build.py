import os
import json
import time
import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests


# -----------------------------
# Config (from GitHub Secrets)
# -----------------------------
SHOP = os.environ["SHOPIFY_SHOP"]  # e.g. goodsmith-store.myshopify.com
CLIENT_ID = os.environ["SHOPIFY_CLIENT_ID"]
CLIENT_SECRET = os.environ["SHOPIFY_CLIENT_SECRET"]
API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2026-01")
GOOGLE_KEY = os.environ["GOOGLE_GEOCODING_KEY"]

PUBLIC_PARTNERS_PATH = "partners.json"
PUBLIC_GEOCACHE_PATH = "geocache.json"


# -----------------------------
# Helpers
# -----------------------------
def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def safe_json_load(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def safe_json_write(path: str, data: Any) -> None:
    dirpath = os.path.dirname(path)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def parse_bool(val: Optional[str]) -> bool:
    if val is None:
        return False
    return str(val).strip().lower() in ("true", "1", "yes", "y", "on")


def parse_list(val: Optional[str]) -> List[str]:
    if not val:
        return []
    s = str(val).strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            arr = json.loads(s)
            if isinstance(arr, list):
                return [str(x) for x in arr if str(x).strip()]
        except Exception:
            pass
    return [s]


def shopify_admin_graphql_url() -> str:
    return f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json"


def get_shopify_access_token() -> str:
    url = f"https://{SHOP}/admin/oauth/access_token"
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials",
    }
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def shopify_graphql(token: str, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": token,
    }
    body = {"query": query, "variables": variables}

    for attempt in range(6):
        r = requests.post(shopify_admin_graphql_url(), headers=headers, json=body, timeout=60)
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(60, 2 ** attempt))
            continue
        r.raise_for_status()
        data = r.json()
        if data.get("errors"):
            raise RuntimeError(data["errors"])
        return data["data"]

    raise RuntimeError("Shopify GraphQL failed after retries")


def get_metafield_value(node: Dict[str, Any], alias: str) -> Optional[str]:
    mf = node.get(alias)
    return mf.get("value") if mf else None


def geocode_location(address: str) -> Optional[Tuple[float, float, str]]:
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": GOOGLE_KEY}

    for attempt in range(5):
        r = requests.get(url, params=params, timeout=30)
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(60, 2 ** attempt))
            continue

        r.raise_for_status()
        data = r.json()
        if data.get("status") == "OK" and data.get("results"):
            loc = data["results"][0]["geometry"]["location"]
            return float(loc["lat"]), float(loc["lng"]), data["results"][0]["formatted_address"]

        if data.get("status") in ("ZERO_RESULTS", "INVALID_REQUEST"):
            return None

    return None


# -----------------------------
# GraphQL Query
# -----------------------------
CUSTOMERS_QUERY = """
query CustomersForPartnerMap($cursor: String) {
  customers(first: 250, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        firstName
        lastName
        email
        phone

        mf_listung: metafield(namespace: "customer_fields", key: "listung") { value }
        mf_hufschuh: metafield(namespace: "customer_fields", key: "gs_hufschuh") { value }
        mf_klebebeschlag: metafield(namespace: "customer_fields", key: "gs_klebebeschlag") { value }

        mf_land: metafield(namespace: "customer_fields", key: "land_listung") { value }
        mf_stadt: metafield(namespace: "customer_fields", key: "stadt_listung") { value }
        mf_plz: metafield(namespace: "customer_fields", key: "plz_listug") { value }

        mf_anzeigename: metafield(namespace: "customer_fields", key: "anzeigename") { value }
        mf_preferred: metafield(namespace: "customer_fields", key: "bevorzugte_kontaktaufnahme_1") { value }
        mf_ausbildung: metafield(namespace: "customer_fields", key: "ausbildung") { value }
      }
    }
  }
}
"""


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    token = get_shopify_access_token()

    geocache: Dict[str, Any] = safe_json_load(PUBLIC_GEOCACHE_PATH, {})
    partners: List[Dict[str, Any]] = []

    cursor = None

    while True:
        data = shopify_graphql(token, CUSTOMERS_QUERY, {"cursor": cursor})
        customers = data["customers"]

        for edge in customers["edges"]:
            node = edge["node"]

            if not parse_bool(get_metafield_value(node, "mf_listung")):
                continue

            zip_code = (get_metafield_value(node, "mf_plz") or "").strip()
            city = (get_metafield_value(node, "mf_stadt") or "").strip()
            country = (get_metafield_value(node, "mf_land") or "").strip()

            if not zip_code or not city or not country:
                continue

            display_name = (
                (get_metafield_value(node, "mf_anzeigename") or "").strip()
                or f"{node.get('firstName','')} {node.get('lastName','')}".strip()
                or "Partner"
            )

            preferred = parse_list(get_metafield_value(node, "mf_preferred"))
            ausbildung = (get_metafield_value(node, "mf_ausbildung") or "").strip() or None

            cache_key = f"{zip_code}|{city}|{country}".lower()
            cached = geocache.get(cache_key)

            if cached:
                lat, lng = cached["lat"], cached["lng"]
            else:
                geo = geocode_location(f"{zip_code} {city}, {country}")
                if not geo:
                    continue
                lat, lng, formatted = geo
                geocache[cache_key] = {"lat": lat, "lng": lng, "formatted": formatted}
                time.sleep(0.02)

            partners.append({
                "partner_id": node["id"],
                "display_name": display_name,
                "zip": zip_code,
                "city": city,
                "country": country,
                "lat": lat,
                "lng": lng,
                "ausbildung": ausbildung,
                "services": {
                    "hufschuh": parse_bool(get_metafield_value(node, "mf_hufschuh")),
                    "klebebeschlag": parse_bool(get_metafield_value(node, "mf_klebebeschlag")),
                },
                "contact": {
                    "email": node.get("email"),
                    "phone": node.get("phone"),
                    "preferred": preferred,
                },
            })

        if customers["pageInfo"]["hasNextPage"]:
            cursor = customers["pageInfo"]["endCursor"]
            time.sleep(0.2)
        else:
            break

    safe_json_write(PUBLIC_PARTNERS_PATH, {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "partners": partners,
    })
    safe_json_write(PUBLIC_GEOCACHE_PATH, geocache)


if __name__ == "__main__":
    main()
