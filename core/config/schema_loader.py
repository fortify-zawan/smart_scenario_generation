"""Loads schema.yml and exposes structured views used by LLM prompts and the validation engine."""
import os
from functools import lru_cache

import yaml

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.yml")


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(_SCHEMA_PATH) as f:
        return yaml.safe_load(f)


# ── Entity-specific accessors ─────────────────────────────────────────────────

def transaction_attributes() -> dict:
    """Returns {canonical_name: {type, description, aliases}} for transaction attributes."""
    return _load().get("transaction_attributes", {})


def user_attributes() -> dict:
    """Returns {canonical_name: {type, description, aliases}} for user attributes."""
    return _load().get("user_attributes", {})


def recipient_attributes() -> dict:
    """Returns {canonical_name: {type, description, aliases}} for recipient attributes."""
    return _load().get("recipient_attributes", {})


# ── Attribute lookups ─────────────────────────────────────────────────────────

def all_attributes() -> dict:
    """Returns a merged dict of {canonical_name: {type, description, aliases, entity}} across all entity types."""
    schema = _load()
    merged = {}
    for section, entity_name in [
        ("transaction_attributes", "transaction"),
        ("user_attributes", "user"),
        ("recipient_attributes", "recipient"),
    ]:
        for name, meta in schema.get(section, {}).items():
            merged[name] = {**meta, "entity": entity_name}
    return merged


def entity_of(attr_name: str) -> str:
    """Return which entity ('transaction', 'user', 'recipient') owns the given canonical attribute name.

    Also resolves aliases. Returns 'transaction' as the default if not found.
    """
    schema = _load()
    attr_lower = attr_name.strip().lower()
    for section, entity_name in [
        ("transaction_attributes", "transaction"),
        ("user_attributes", "user"),
        ("recipient_attributes", "recipient"),
    ]:
        attrs = schema.get(section, {})
        if attr_lower in attrs:
            return entity_name
        for meta in attrs.values():
            if attr_lower in [a.lower() for a in meta.get("aliases", [])]:
                return entity_name
    return "transaction"  # default fallback


def canonical_name(raw: str) -> str:
    """
    Resolve a raw attribute name (possibly an alias) to its canonical name.
    Returns the raw name unchanged if no match is found.
    """
    attrs = all_attributes()
    raw_lower = raw.strip().lower()
    # Direct match
    if raw_lower in attrs:
        return raw_lower
    # Alias match
    for canonical, meta in attrs.items():
        if raw_lower in [a.lower() for a in meta.get("aliases", [])]:
            return canonical
    return raw  # unknown — return as-is


def get_by_type(attr_type: str) -> list[str]:
    """Return all canonical attribute names of a given type (numeric, categorical, datetime, boolean)."""
    return [name for name, meta in all_attributes().items() if meta.get("type") == attr_type]


def get_allowed_values(attr_name: str) -> list | None:
    """Return the allowed_values list for a given canonical attribute, or None if not defined."""
    meta = all_attributes().get(attr_name)
    if meta is None:
        return None
    return meta.get("allowed_values")


# ── Aggregation lookups ───────────────────────────────────────────────────────

def supported_aggregations() -> dict:
    """Returns {aggregation_name: {applies_to, description}} from schema."""
    return _load().get("aggregations", {})


def aggregation_names() -> list[str]:
    return list(supported_aggregations().keys())


# ── Country value normalization ───────────────────────────────────────────────

# Fields that store country values and need ISO → full-name normalization for rule evaluation
_COUNTRY_FIELDS = {
    "origin_country_code",
    "destination_country_code",
    "user_origin_country_code",
    "recipient_destination_country_code",
    # backward compat aliases still present in older session data
    "send_country_code",
    "receive_country_code",
    "signup_send_country_code",
}

# ISO 3166-1 alpha-2 → full name for countries commonly referenced in AML rules
_ISO_TO_NAME: dict[str, str] = {
    "AF": "Afghanistan", "AL": "Albania", "AO": "Angola", "AM": "Armenia",
    "AZ": "Azerbaijan", "BS": "Bahamas", "BH": "Bahrain", "BD": "Bangladesh",
    "BY": "Belarus", "BZ": "Belize", "BO": "Bolivia", "BA": "Bosnia and Herzegovina",
    "MM": "Myanmar", "KH": "Cambodia", "CM": "Cameroon", "CN": "China",
    "CO": "Colombia", "CD": "Congo", "CG": "Republic of Congo", "CR": "Costa Rica",
    "CU": "Cuba", "DO": "Dominican Republic", "EC": "Ecuador", "EG": "Egypt",
    "SV": "El Salvador", "ER": "Eritrea", "ET": "Ethiopia",
    "GN": "Guinea", "GW": "Guinea-Bissau", "GY": "Guyana", "HT": "Haiti",
    "HN": "Honduras", "IQ": "Iraq", "IR": "Iran", "JM": "Jamaica",
    "KZ": "Kazakhstan", "KG": "Kyrgyzstan", "LA": "Laos", "LB": "Lebanon",
    "LR": "Liberia", "LY": "Libya", "MK": "North Macedonia", "ML": "Mali",
    "MR": "Mauritania", "MX": "Mexico", "MD": "Moldova", "MN": "Mongolia",
    "MA": "Morocco", "MZ": "Mozambique", "NP": "Nepal", "NI": "Nicaragua",
    "NE": "Niger", "NG": "Nigeria", "KP": "North Korea", "OM": "Oman",
    "PK": "Pakistan", "PA": "Panama", "PY": "Paraguay", "PH": "Philippines",
    "PS": "Palestine", "QA": "Qatar", "RU": "Russia", "RW": "Rwanda",
    "SA": "Saudi Arabia", "SN": "Senegal", "SL": "Sierra Leone", "SO": "Somalia",
    "SS": "South Sudan", "SD": "Sudan", "SR": "Suriname", "SY": "Syria",
    "TJ": "Tajikistan", "TZ": "Tanzania", "TH": "Thailand", "TG": "Togo",
    "TT": "Trinidad and Tobago", "TN": "Tunisia", "TR": "Turkey",
    "TM": "Turkmenistan", "UG": "Uganda", "UA": "Ukraine",
    "AE": "United Arab Emirates", "UZ": "Uzbekistan", "VE": "Venezuela",
    "VN": "Vietnam", "YE": "Yemen", "ZM": "Zambia", "ZW": "Zimbabwe",
    # Common non-flagged countries
    "US": "United States", "GB": "United Kingdom", "DE": "Germany",
    "FR": "France", "IT": "Italy", "ES": "Spain", "NL": "Netherlands",
    "CA": "Canada", "AU": "Australia", "IN": "India", "JP": "Japan",
    "SG": "Singapore", "ZA": "South Africa",
}


def normalize_country_values(attrs: dict, high_risk_countries: list[str] | None = None) -> dict:
    """
    For country-type fields, map ISO 2-letter codes to full country names.
    Uses high_risk_countries (from the rule) as the preferred source of exact casing,
    falling back to the built-in mapping table.
    """
    # Build a lookup that prefers exact strings from the rule
    iso_map = dict(_ISO_TO_NAME)
    for name in (high_risk_countries or []):
        for iso, default_name in _ISO_TO_NAME.items():
            if default_name.lower() == name.lower():
                iso_map[iso] = name  # use exact casing from the rule

    result = {}
    for k, v in attrs.items():
        if k in _COUNTRY_FIELDS and isinstance(v, str) and len(v) == 2 and v.upper() in iso_map:
            result[k] = iso_map[v.upper()]
        else:
            result[k] = v
    return result


# ── Prompt formatting ─────────────────────────────────────────────────────────

def format_attributes_for_prompt(
    show_aliases: bool = True,
    allowed_attrs: set[str] | None = None,
) -> str:
    """
    Returns a compact attribute reference table for injecting into LLM prompts.
    Groups by entity type and shows canonical name, type, and common aliases.
    Set show_aliases=False for generation prompts where aliases cause key confusion.
    Pass allowed_attrs to restrict the table to only those canonical names.
    """
    schema = _load()
    lines = ["CANONICAL ATTRIBUTE SCHEMA (use ONLY these exact names as JSON keys — do not use aliases or invent others):"]

    for section, label in [
        ("transaction_attributes", "Transaction (transactions table)"),
        ("user_attributes", "User (users table)"),
        ("recipient_attributes", "Recipient (recipients table)"),
    ]:
        attrs = schema.get(section, {})
        if allowed_attrs is not None:
            attrs = {k: v for k, v in attrs.items() if k in allowed_attrs}
        if not attrs:
            continue
        lines.append(f"\n{label} attributes:")
        for name, meta in attrs.items():
            if show_aliases:
                aliases = ", ".join(meta.get("aliases", [])[:3])
                alias_str = f" (also known as: {aliases})" if aliases else ""
            else:
                alias_str = ""
            allowed = meta.get("allowed_values")
            if allowed:
                value_str = f" ALLOWED VALUES (use ONLY these): {' | '.join(str(v) for v in allowed)}"
            else:
                value_str = f" — {meta['description']}"
            lines.append(f"  {name} [{meta['type']}]{alias_str}{value_str}")

    return "\n".join(lines)


def format_aggregations_for_prompt() -> str:
    """Returns a compact aggregation reference for injecting into LLM prompts."""
    aggs = supported_aggregations()
    lines = ["SUPPORTED AGGREGATIONS (use ONLY these — do not use average_per_day, std_dev, etc.):"]
    for name, meta in aggs.items():
        desc = str(meta.get("description", "")).replace("\n", " ").strip()
        lines.append(f"  {name} [{meta['applies_to']}] — {desc}")
    return "\n".join(lines)
