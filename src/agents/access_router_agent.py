"""
Find a legal way to read a paywalled paper.

Roughly half the papers a researcher needs sit behind a subscription they do not
have. A free, legal copy very often exists anyway — deposited by the author in a
repository, or posted as a preprint — but nothing in the usual workflow tells
them so. This module runs that search as an explicit cascade and reports what it
tried at each step.

Order, cheapest and most legitimate first:

  1. OpenAlex          — publisher-of-record OA status and repository copies
  2. Unpaywall         — 50,000+ sources indexed for legal free copies
  3. arXiv             — preprint, when the title matches closely
  4. Your institution  — OpenURL resolver link, if you configured one
  5. Who else has it   — institutions publishing in that journal, for a co-author ask
  6. Ask the author    — a ready-to-send request email
  7. Interlibrary loan — the last legal resort

Shadow libraries are deliberately absent. Beyond the legal problem, any
institution that caught the app recommending one would block it outright.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from typing import Optional
from urllib.parse import quote_plus

import requests

OPENALEX = "https://api.openalex.org"
UNPAYWALL = "https://api.unpaywall.org/v2"
ARXIV = "http://export.arxiv.org/api/query"

# Both APIs ask for a contact address and give a better rate limit with one.
CONTACT = os.environ.get("OPENALEX_MAILTO", "research@example.com")

_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)

TIMEOUT = 15


def extract_doi(text: str) -> str:
    """Pull a DOI out of a raw string, URL, or citation."""
    match = _DOI_RE.search((text or "").strip())
    return match.group(0).rstrip(".,;)") if match else ""


def _step(number: int, name: str, status: str, detail: str = "", url: str = "") -> dict:
    """One rung of the access ladder, always reported even when it fails."""
    return {"step": number, "name": name, "status": status, "detail": detail, "url": url}


def _openalex_work(doi: str, title: str) -> Optional[dict]:
    """Fetch the work by DOI, falling back to a title search."""
    try:
        if doi:
            resp = requests.get(f"{OPENALEX}/works/doi:{doi}",
                                params={"mailto": CONTACT}, timeout=TIMEOUT)
            if resp.status_code == 200:
                return resp.json()

        if title:
            resp = requests.get(f"{OPENALEX}/works", params={
                "filter": f"title.search:{title[:200]}",
                "per-page": 1,
                "mailto": CONTACT,
            }, timeout=TIMEOUT)
            if resp.status_code == 200:
                results = resp.json().get("results") or []
                return results[0] if results else None
    except Exception:
        pass
    return None


def _unpaywall(doi: str) -> Optional[dict]:
    try:
        resp = requests.get(f"{UNPAYWALL}/{doi}",
                            params={"email": CONTACT}, timeout=TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def _titles_match(a: str, b: str) -> bool:
    """Guard against arXiv returning a loosely related preprint."""
    def norm(s: str) -> set:
        return set(re.findall(r"[a-z0-9]+", (s or "").lower()))

    left, right = norm(a), norm(b)
    if not left or not right:
        return False
    overlap = len(left & right) / max(len(left), len(right))
    return overlap >= 0.75


def _arxiv(title: str) -> Optional[dict]:
    """Look for a preprint whose title matches closely enough to be the same paper."""
    if not title:
        return None
    try:
        resp = requests.get(ARXIV, params={
            "search_query": f'ti:"{title[:120]}"',
            "max_results": 1,
        }, timeout=TIMEOUT)
        if resp.status_code != 200:
            return None

        ns = {"a": "http://www.w3.org/2005/Atom"}
        entry = ET.fromstring(resp.text).find("a:entry", ns)
        if entry is None:
            return None

        found_title = (entry.findtext("a:title", "", ns) or "").strip()
        if not _titles_match(title, found_title):
            return None

        pdf = next((link.get("href") for link in entry.findall("a:link", ns)
                    if link.get("title") == "pdf"), "")
        return {"title": found_title,
                "url": pdf or entry.findtext("a:id", "", ns)}
    except Exception:
        return None


def _institutions_publishing_in(source_id: str, limit: int = 8) -> list:
    """Institutions that publish in this journal — likely to hold a subscription.

    This is a proxy, not a subscription record: no open dataset lists which
    institution licenses which journal. Publishing there regularly is decent
    evidence of access, and gives the user somewhere to direct a co-author ask.
    """
    if not source_id:
        return []
    try:
        resp = requests.get(f"{OPENALEX}/works", params={
            "filter": f"primary_location.source.id:{source_id}",
            "group_by": "authorships.institutions.lineage",
            "mailto": CONTACT,
        }, timeout=TIMEOUT)
        if resp.status_code != 200:
            return []
        groups = resp.json().get("group_by") or []
        return [{"name": g.get("key_display_name", ""), "works": g.get("count", 0)}
                for g in groups[:limit] if g.get("key_display_name")]
    except Exception:
        return []


def _corresponding_author(work: dict) -> dict:
    """Best guess at who to email, preferring the marked corresponding author."""
    authorships = work.get("authorships") or []
    if not authorships:
        return {}

    chosen = next((a for a in authorships if a.get("is_corresponding")), authorships[0])
    author = chosen.get("author") or {}
    institutions = chosen.get("institutions") or []
    return {
        "name": author.get("display_name", ""),
        "institution": institutions[0].get("display_name", "") if institutions else "",
    }


def _author_request_email(work: dict, title: str) -> dict:
    """A request email the user can send as-is.

    Authors may share their own manuscript with individuals, and most are glad
    to. It is the most reliable step in this whole cascade.
    """
    author = _corresponding_author(work)
    surname = (author.get("name") or "").split()[-1] if author.get("name") else ""
    greeting = f"Dear Dr. {surname}," if surname else "Dear Author,"

    body = (
        f"{greeting}\n\n"
        f"I am researching this area and would like to read your paper, "
        f"\"{title}\". My institution does not hold a subscription to the "
        f"journal, so I cannot access the full text.\n\n"
        f"Would you be willing to share a copy of the accepted manuscript? "
        f"I would be grateful, and happy to cite it appropriately.\n\n"
        f"Thank you for your time.\n\n"
        f"Best regards,\n[Your name]\n[Your institution]"
    )
    return {
        "author_name": author.get("name", ""),
        "author_institution": author.get("institution", ""),
        "subject": f"Request for a copy of your paper: {title[:80]}",
        "body": body,
    }


def _resolver_links(institution: dict, doi: str, title: str) -> dict:
    """Build institution access links from a user-supplied resolver config.

    No open API maps an institution to its subscriptions, so the user supplies
    their library's OpenURL resolver base or EZproxy prefix once. Their
    librarian or library website has both.
    """
    if not institution:
        return {}

    links = {}
    resolver = (institution.get("resolver_url") or "").strip()
    ezproxy = (institution.get("ezproxy_prefix") or "").strip()

    if resolver:
        joiner = "&" if "?" in resolver else "?"
        if doi:
            links["openurl"] = f"{resolver}{joiner}id=doi:{quote_plus(doi)}"
        elif title:
            links["openurl"] = f"{resolver}{joiner}title={quote_plus(title[:150])}"

    if ezproxy and doi:
        links["ezproxy"] = f"{ezproxy.rstrip('/')}/login?url=https://doi.org/{doi}"

    return links


def resolve_access(query: str, institution: Optional[dict] = None) -> dict:
    """Run the full access cascade for one paper.

    Args:
        query: a DOI, a DOI URL, or a paper title.
        institution: optional `{"name", "resolver_url", "ezproxy_prefix"}`
            describing the user's library link resolver.

    Returns a record carrying every step attempted, so a failure is legible
    rather than a blank "not found".
    """
    query = (query or "").strip()
    if not query:
        return {"error": "Enter a DOI or paper title."}

    doi = extract_doi(query)
    title_query = "" if doi else query

    steps: list = []
    best: Optional[dict] = None

    # ── Step 1: OpenAlex ────────────────────────────────────────────────────
    work = _openalex_work(doi, title_query) or {}
    if not work:
        steps.append(_step(1, "OpenAlex record", "not_found",
                           "No matching record. Check the DOI or try the exact title."))
        return {
            "query": query, "doi": doi, "title": title_query,
            "steps": steps, "best": None,
            "advice": "Without a matched record the remaining steps cannot run.",
        }

    title = work.get("title") or work.get("display_name") or title_query
    doi = doi or extract_doi(work.get("doi") or "")
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    oa = work.get("open_access") or {}

    steps.append(_step(1, "OpenAlex record", "found",
                       f"{title[:90]} ({work.get('publication_year', 'n.d.')})"))

    if oa.get("is_oa") and oa.get("oa_url"):
        best_loc = work.get("best_oa_location") or {}
        version = best_loc.get("version") or "unknown version"
        steps.append(_step(2, "Open-access copy via OpenAlex", "found",
                           f"{oa.get('oa_status', 'oa')} · {version}",
                           best_loc.get("pdf_url") or oa["oa_url"]))
        best = {
            "url": best_loc.get("pdf_url") or oa["oa_url"],
            "kind": "pdf" if best_loc.get("pdf_url") else "landing",
            "source": "OpenAlex",
            "version": version,
            "license": best_loc.get("license") or "not stated",
        }
    else:
        steps.append(_step(2, "Open-access copy via OpenAlex", "not_found",
                           "Publisher record shows no open version."))

    # ── Step 2: Unpaywall ───────────────────────────────────────────────────
    if doi:
        unpaywall = _unpaywall(doi)
        if unpaywall and unpaywall.get("is_oa"):
            loc = unpaywall.get("best_oa_location") or {}
            url = loc.get("url_for_pdf") or loc.get("url")
            steps.append(_step(3, "Unpaywall", "found",
                               f"{unpaywall.get('oa_status', 'oa')} · "
                               f"{loc.get('host_type', 'repository')} · "
                               f"{len(unpaywall.get('oa_locations') or [])} location(s)",
                               url or ""))
            # Prefer a direct PDF over a landing page even if OpenAlex answered first.
            if url and (best is None or (loc.get("url_for_pdf") and best["kind"] != "pdf")):
                best = {
                    "url": url,
                    "kind": "pdf" if loc.get("url_for_pdf") else "landing",
                    "source": "Unpaywall",
                    "version": loc.get("version") or "unknown version",
                    "license": loc.get("license") or "not stated",
                }
        elif unpaywall:
            steps.append(_step(3, "Unpaywall", "not_found",
                               "No legal free copy indexed across 50,000+ sources."))
        else:
            steps.append(_step(3, "Unpaywall", "skipped", "Lookup failed or timed out."))
    else:
        steps.append(_step(3, "Unpaywall", "skipped", "Needs a DOI."))

    # ── Step 3: arXiv preprint ──────────────────────────────────────────────
    if best is None:
        preprint = _arxiv(title)
        if preprint:
            steps.append(_step(4, "arXiv preprint", "found",
                               "Preprint — may differ from the published version.",
                               preprint["url"]))
            best = {"url": preprint["url"], "kind": "pdf", "source": "arXiv",
                    "version": "preprint", "license": "arXiv licence"}
        else:
            steps.append(_step(4, "arXiv preprint", "not_found",
                               "No preprint with a matching title."))
    else:
        steps.append(_step(4, "arXiv preprint", "skipped",
                           "A copy was already found above."))

    # ── Step 4: institutional resolver ──────────────────────────────────────
    links = _resolver_links(institution or {}, doi, title)
    if links:
        steps.append(_step(5, (institution or {}).get("name") or "Your institution",
                           "found", "Open through your library's subscription.",
                           links.get("openurl") or links.get("ezproxy", "")))
    else:
        steps.append(_step(5, "Your institution", "skipped",
                           "Add your library's OpenURL resolver to check subscriptions."))

    # ── Step 5: who else has access ─────────────────────────────────────────
    institutions = _institutions_publishing_in(source.get("id", ""))
    if institutions:
        steps.append(_step(6, "Institutions publishing in this journal", "found",
                           f"{len(institutions)} institutions — a contact at any of "
                           "them likely has access."))
    else:
        steps.append(_step(6, "Institutions publishing in this journal", "not_found",
                           "Could not determine publishing institutions."))

    # ── Step 6: ask the author ──────────────────────────────────────────────
    email = _author_request_email(work, title)
    steps.append(_step(7, "Request from the author", "found",
                       f"Email drafted for {email.get('author_name') or 'the author'}."))

    # ── Step 7: interlibrary loan ───────────────────────────────────────────
    steps.append(_step(8, "Interlibrary loan", "found",
                       "Your library can order a copy from another library, usually "
                       "free to you and delivered within a few days."))

    return {
        "query": query,
        "doi": doi,
        "title": title,
        "journal": source.get("display_name", ""),
        "year": work.get("publication_year"),
        "is_retracted": bool(work.get("is_retracted")),
        "is_oa": bool(oa.get("is_oa")),
        "oa_status": oa.get("oa_status", "closed"),
        "cited_by": work.get("cited_by_count", 0),
        "steps": steps,
        "best": best,
        "institution_links": links,
        "institutions_with_access": institutions,
        "author_request": email,
    }
