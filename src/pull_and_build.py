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

# Metafields (namespace fixed)
NS = "customer_fields"

MF_KEYS = {
    "listung": ("customer_fields", "listung"),
    "gs_hufschuh": ("customer_fields", "gs_hufschuh"),
    "gs_klebebeschlag": ("customer_fields", "gs_klebebeschlag"),
    "land_listung": ("customer_fields", "land_listung"),
    "stadt_listung": ("customer_fields", "stadt_listung"),
    "plz_listug": ("customer_fields", "plz_listug"),  # IMPORTANT: key is plz_listug (as in your Shopify)
    "anzeigename": ("customer_fields", "anzeigename"),
    "bevorzugte_kontaktaufnahme_1": ("customer_fields", "bevorzugte_kontaktaufnahme_1"),
    "ausbildung": ("customer_fields", "ausbildung"),  # NEW
}


# -----------------------------
# Helpers
# -----------------------------
def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def safe_json_load(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


def safe_json_write(path: str, data: Any) -> None:
    # FIX: if path is in repo root, dirname is "" -> os.makedirs("") would crash
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
    v = str(val).strip().lower()
    return v in ("true", "1", "yes", "y", "on")


def parse_list(val: Optional[str]) -> List[str]:
    """
    Shopify list metafields often come back as a JSON string, e.g. '["Mail","Telefon"]'.
    Sometimes it can be a single string.
    """
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
    # fallback: treat as single value
    return [s] if s else []


def shopify_admin_graphql_url() -> str:
    return f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json"


def get_shopify_access_token() -> str:
    """
    Client Credentials Grant per Shopify docs.
    """
    url = f"https://{SHOP}/admin/oauth/access_token"
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials",
    }
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"No access_token in response: {data}")
    return token


def shopify_graphql(token: str, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": token,
    }
    body = {"query": query, "variables": variables}

    # basic retry for 429/5xx
    for attempt in range(6):
        r = requests.post(shopify_admin_graphql_url(), headers=headers, json=body, timeout=60)
        if r.status_code in (429, 500, 502, 503, 504):
            wait = min(60, 2 ** attempt)
            print(f"Shopify GraphQL retry {attempt+1}/6 (status {r.status_code}) waiting {wait}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        data = r.json()
        if "errors" in data and data["errors"]:
            raise RuntimeError(f"GraphQL errors: {data['errors']}")
        return data["data"]
    raise RuntimeError("Shopify GraphQL failed after retries")


def get_metafield_value(node: Dict[str, Any], alias: str) -> Optional[str]:
    mf = node.get(alias)
    if not mf:
        return None
    return mf.get("value")


def geocode_location(address: str) -> Optional[Tuple[float, float, str]]:
    """
    Google Geocoding API.
    Returns (lat, lng, formatted_address) or None.
    """
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": GOOGLE_KEY}
    for attempt in range(5):
        r = requests.get(url, params=params, timeout=30)
        if r.status_code in (429, 500, 502, 503, 504):
            wait = min(60, 2 ** attempt)
            print(f"Geocoding retry {attempt+1}/5 (status {r.status_code}) waiting {wait}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        if status == "OK" and data.get("results"):
            res0 = data["results"][0]
            loc = res0["geometry"]["location"]
            lat = float(loc["lat"])
            lng = float(loc["lng"])
            fmt = str(res0.get("formatted_address") or "")
            return lat, lng, fmt
        if status in ("ZERO_RESULTS", "INVALID_REQUEST"):
            return None
        # OVER_QUERY_LIMIT or unknown -> retry with backoff
        wait = min(60, 2 ** attempt)
        print(f"Geocoding status={status}, retry {attempt+1}/5 waiting {wait}s")
        time.sleep(wait)
    return None


# -----------------------------
# Main build
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


def main() -> None:
    token = get_shopify_access_token()
    print("Got Shopify access token.")

    geocache: Dict[str, Any] = safe_json_load(PUBLIC_GEOCACHE_PATH, {})
    if not isinstance(geocache, dict):
        geocache = {}

    partners: List[Dict[str, Any]] = []
    cursor = None
    total_customers = 0
    listed_candidates = 0
    geocoded_new = 0
    skipped_missing_location = 0
    skipped_geocode_fail = 0

    while True:
        data = shopify_graphql(token, CUSTOMERS_QUERY, {"cursor": cursor})
        customers = data["customers"]
        edges = customers["edges"]
        total_customers += len(edges)

        for edge in edges:
            node = edge["node"]

            listung_val = get_metafield_value(node, "mf_listung")
            if not parse_bool(listung_val):
                continue

            listed_candidates += 1

            zip_code = (get_metafield_value(node, "mf_plz") or "").strip()
            city = (get_metafield_value(node, "mf_stadt") or "").strip()
            country = (get_metafield_value(node, "mf_land") or "").strip()

            if not zip_code or not city or not country:
                skipped_missing_location += 1
                continue

            # display name
            anzeigename = (get_metafield_value(node, "mf_anzeigename") or "").strip()
            first = (node.get("firstName") or "").strip()
            last = (node.get("lastName") or "").strip()
            fallback_name = (first + " " + last).strip()
            display_name = anzeigename or fallback_name or "Partner"

            preferred = parse_list(get_metafield_value(node, "mf_preferred"))

            # NEW: ausbildung
            ausbildung = (get_metafield_value(node, "mf_ausbildung") or "").strip()
            if not ausbildung:
                ausbildung = None

            # services
            hufschuh = parse_bool(get_metafield_value(node, "mf_hufschuh"))
            klebebeschlag = parse_bool(get_metafield_value(node, "mf_klebebeschlag"))

            # geocode (PLZ/Ort/Land)
            cache_key = f"{zip_code}|{city}|{country}".lower()
            cached = geocache.get(cache_key)

            lat = lng = None
            if isinstance(cached, dict) and "lat" in cached and "lng" in cached:
                lat = float(cached["lat"])
                lng = float(cached["lng"])
            else:
                query_addr = f"{zip_code} {city}, {country}"
                res = geocode_location(query_addr)
                if not res:
                    skipped_geocode_fail += 1
                    continue
                lat, lng, formatted = res
                geocache[cache_key] = {"lat": lat, "lng": lng, "formatted": formatted}
                geocoded_new += 1
                # small delay to be gentle with API quotas
                time.sleep(0.02)

            partner = {
                "partner_id": node["id"],  # Shopify GID
                "display_name": display_name,
                "zip": zip_code,
                "city": city,
                "country": country,  # your fixed label (Germany, Austria, ...)
                "lat": lat,
                "lng": lng,
                "ausbildung": ausbildung,  # NEW
                "services": {
                    "hufschuh": hufschuh,
                    "klebebeschlag": klebebeschlag,
                },
                "contact": {
                    "email": node.get("email"),
                    "phone": node.get("phone"),
                    "preferred": preferred,
                },
            }
            partners.append(partner)

        page_info = customers["pageInfo"]
        if page_info["hasNextPage"]:
            cursor = page_info["endCursor"]
            # short pause to reduce risk of rate limiting
            time.sleep(0.2)
        else:
            break

    out = {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "partners": partners,
    }

    safe_json_write(PUBLIC_PARTNERS_PATH, out)
    safe_json_write(PUBLIC_GEOCACHE_PATH, geocache)

    print("----- Summary -----")
    print(f"Total customers scanned: {total_customers}")
    print(f"Listing enabled candidates: {listed_candidates}")
    print(f"Partners written: {len(partners)}")
    print(f"New geocodes performed: {geocoded_new}")
    print(f"Skipped (missing zip/city/country): {skipped_missing_location}")
    print(f"Skipped (geocoding failed): {skipped_geocode_fail}")


if __name__ == "__main__":
    main()
