"""
Vocabulary helpers for company names, domains, and categorical values.
"""

from __future__ import annotations

from collections import defaultdict
import re

import numpy as np


COMPANY_ADJECTIVES = [
    "Northstar", "BluePeak", "ClearPath", "Prime", "Signal", "Nimbus", "Trusted",
    "Apex", "Vector", "Summit", "Bright", "Adaptive", "Cobalt", "Granite",
]

COMPANY_NOUNS = [
    "Cloud", "Systems", "Analytics", "Works", "Platform", "Labs", "Metrics",
    "Solutions", "Logic", "Insights", "Stack", "Collective", "Flow", "Hub",
]

INDUSTRY_HINTS: dict[str, list[str]] = {
    "technology": ["Digital", "Data", "Scale", "Connect", "Automation"],
    "financial": ["Ledger", "Capital", "Trust", "Payments", "Risk"],
    "health": ["Care", "Clinical", "Health", "Patient", "Well"],
    "retail": ["Commerce", "Store", "Market", "Merch", "Demand"],
    "manufacturing": ["Factory", "Ops", "Supply", "Precision", "Forge"],
    "education": ["Learning", "Campus", "Scholar", "Academy", "Class"],
    "logistics": ["Freight", "Route", "Transit", "Carrier", "Fulfil"],
}

DEFAULT_TICKET_CATEGORIES = [
    "onboarding", "billing", "bug", "integration", "permissions", "reporting", "feature_request",
]

DEFAULT_CANCELLATION_REASONS = [
    "budget_constraints",
    "low_adoption",
    "switched_vendor",
    "merger_restructure",
    "payment_failure",
    "downsell_reassessment",
]

DEFAULT_INVOICE_STATUSES = ["paid", "partially_paid", "overdue", "void"]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "company"


def build_company_name(industry_name: str, company_suffixes: list[str], rng: np.random.Generator) -> str:
    adjective = str(rng.choice(COMPANY_ADJECTIVES))
    noun = str(rng.choice(COMPANY_NOUNS))
    hints = INDUSTRY_HINTS.get(industry_name.lower(), [industry_name.split()[0].title()])
    hint = str(rng.choice(hints))
    suffix = str(rng.choice(company_suffixes or ["Ltd"]))
    return f"{adjective} {hint} {noun} {suffix}"


def build_domain(company_name: str, domain_tlds: list[str], used_domains: set[str], rng: np.random.Generator) -> str:
    base = slugify(company_name)
    tld = str(rng.choice(domain_tlds or ["com"]))
    candidate = f"{base}.{tld}"
    counter = defaultdict(int)
    while candidate in used_domains:
        counter[base] += 1
        candidate = f"{base}-{counter[base]}.{tld}"
    used_domains.add(candidate)
    return candidate
