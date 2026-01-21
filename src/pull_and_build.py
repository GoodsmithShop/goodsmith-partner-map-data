# -----------------------------
# Activity classification config
# -----------------------------
DAYS_12M = 365
DAYS_6M = 180

# NEW thresholds per your spec
THRESH_REGULAR_6M = 3          # >= 3 orders in last 6 months => "Regelmäßig aktiv"
THRESH_REGULAR_12M = 6         # OR >= 6 orders in last 12 months => "Regelmäßig aktiv"
THRESH_HIGH_12M = 10           # >= 10 orders in last 12 months => "Sehr aktiv" (if recent)
RECENT_DAYS = 60               # last order within 60 days


def classify_activity(orders_6m: int, orders_12m: int, last_order_days: Optional[int]) -> Optional[str]:
    if orders_12m <= 0 and last_order_days is None:
        return None

    # "Sehr aktiv" = high demand (volume + recency)
    if orders_12m >= THRESH_HIGH_12M and last_order_days is not None and last_order_days <= RECENT_DAYS:
        return "Sehr aktiv"

    # "Regelmäßig aktiv" = medium volume
    if orders_6m >= THRESH_REGULAR_6M or orders_12m >= THRESH_REGULAR_12M:
        return "Regelmäßig aktiv"

    # Still useful signal: recent order
    if last_order_days is not None and last_order_days <= RECENT_DAYS:
        return "Kürzlich aktiv"

    if orders_12m > 0:
        return "Aktiv"

    return None
