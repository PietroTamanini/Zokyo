"""Constantes do admin global."""

SUBSCRIPTION_STATUSES = ("trialing", "active", "past_due", "suspended", "cancelled")

SUBSCRIPTION_STATUS_LABELS = {
    "trialing": "Trial",
    "active": "Ativa",
    "past_due": "Em atraso",
    "suspended": "Suspensa",
    "cancelled": "Cancelada",
}

SUBSCRIPTION_STATUS_BADGES = {
    "trialing": "b-blue",
    "active": "b-green",
    "past_due": "b-amber",
    "suspended": "b-red",
    "cancelled": "b-gray",
}

DNS_MODE_LABELS = {
    "manual": "Manual",
    "wildcard": "Wildcard",
    "cloudflare": "Cloudflare",
    "api": "Cloudflare",
}
