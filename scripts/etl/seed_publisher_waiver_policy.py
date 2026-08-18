"""Seed `publisher_waiver_policy` with hand-curated, cited rows.

Waivers are a country-tier rule, not per-journal data, so this is a
periodically-reviewed seed rather than something scraped per journal.
Verification level is marked honestly per row - some were fetched and
read directly this session, some rely on other sites' summaries because
the publisher's own page is JS-rendered or Cloudflare-blocked and
couldn't be fetched directly. Re-run/review this file's contents
periodically (policies change); `last_reviewed_at` records when.
"""
from __future__ import annotations

import datetime

from common import etl_run
from src.db.engine import session_scope
from src.db.models import PublisherWaiverPolicy

# Each entry's `notes` states exactly how it was verified, per the
# "authenticated from the original website, not hallucinated" requirement.
POLICIES = [
    {
        "publisher": "elsevier",
        "policy_type": "automatic_by_country",
        "full_waiver_income_groups": "low",
        "discount_pct": None,
        "discount_income_groups": "lower_middle",
        "policy_url": "https://www.elsevier.com/about/policies-and-standards/pricing",
        "notes": (
            "Fetched and read directly this session. Exact wording: 'During the "
            "publication process, we automatically notify authors who are entitled "
            "to free or discounted gold open access because they are in a lower- "
            "or middle-income country.' No separate downloadable waiver list - "
            "it's a country-income rule applied automatically at submission."
        ),
    },
    {
        "publisher": "wiley",
        "policy_type": "research4life_tier",
        "full_waiver_income_groups": "low",
        "discount_pct": None,
        "discount_income_groups": "lower_middle",
        "policy_url": "https://authorservices.wiley.com/open-research/open-access/for-authors/waivers-and-discounts.html",
        "notes": (
            "Wiley's own waivers-and-discounts page is a JS-rendered SPA shell and "
            "could not be fetched directly this session. Wording here is from an "
            "aggregated search summary, not independently read from Wiley's raw "
            "page text - flagged for manual confirmation before relying on exact "
            "percentages: 'Wiley's partnership with Research4Life enables "
            "institutions in low- and middle-income countries to receive automatic "
            "waivers and discounts on APCs.'"
        ),
    },
    {
        "publisher": "sage",
        "policy_type": "research4life_tier",
        "full_waiver_income_groups": "low",
        "discount_pct": 50.0,
        "discount_income_groups": "lower_middle",
        "policy_url": "https://www.sagepub.com/journals/information-for-authors/publishing-options/gold-open-access-article-processing-charge-waivers",
        "notes": (
            "Fetched and read directly this session (HTTP 200, real page text). "
            "Exact wording: 'Corresponding Authors affiliated with institutions in "
            "...Research4Life's Group A list...will automatically receive a full "
            "APC waiver. ...Group B list...will automatically receive a 50% "
            "discount...Eligibility is determined at the time of submission.'"
        ),
    },
    {
        "publisher": "springer",
        "policy_type": "custom_country_list",
        "full_waiver_income_groups": None,
        "discount_pct": None,
        "discount_income_groups": None,
        "policy_url": "https://www.springernature.com/gp/open-science/journals-books/journal-pricing-faqs",
        "notes": (
            "Fetched and read directly this session. Springer runs its own named "
            "72-country qualifying list (broader than Research4Life, e.g. includes "
            "India) for a fully-sponsored gold OA fund on eligible fully-OA "
            "journals - see ingest_springer_apc.py::fetch_waiver_qualifying_countries()."
        ),
    },
    {
        "publisher": "oup",
        "policy_type": "case_by_case",
        "full_waiver_income_groups": None,
        "discount_pct": None,
        "discount_income_groups": None,
        "policy_url": "https://academic.oup.com/pages/open-research/open-access/charges-licences-and-self-archiving/apc-waiver-policy",
        "notes": (
            "Page is Cloudflare-blocked to both plain requests and cloudscraper "
            "(tested live, both 403) - exact tiers NOT independently verified this "
            "session. Do not treat as confirmed; visit the URL directly before "
            "relying on this row."
        ),
    },
    {
        "publisher": "plos",
        "policy_type": "research4life_tier",
        "full_waiver_income_groups": "low",
        "discount_pct": None,
        "discount_income_groups": None,
        "policy_url": "https://plos.org/fees/",
        "notes": (
            "Page is Cloudflare-blocked to plain requests (tested live, 403) - "
            "wording here is from an aggregated search summary, not independently "
            "read from PLOS's raw page text: 'Free for authors based at "
            "institutions in a Research4Life Group A country without external "
            "funding.' Confirm at plos.org/fees before relying on this."
        ),
    },
]


def run():
    now = datetime.datetime.utcnow()
    with etl_run("publisher_waiver_policy_seed") as counters:
        with session_scope() as session:
            for entry in POLICIES:
                counters.fetched += 1
                row = session.query(PublisherWaiverPolicy).filter_by(publisher=entry["publisher"]).one_or_none()
                if row is None:
                    row = PublisherWaiverPolicy(publisher=entry["publisher"])
                    session.add(row)
                row.policy_type = entry["policy_type"]
                row.full_waiver_income_groups = entry["full_waiver_income_groups"]
                row.discount_pct = entry["discount_pct"]
                row.discount_income_groups = entry["discount_income_groups"]
                row.policy_url = entry["policy_url"]
                row.notes = entry["notes"]
                row.last_reviewed_at = now
                counters.upserted += 1


if __name__ == "__main__":
    run()
