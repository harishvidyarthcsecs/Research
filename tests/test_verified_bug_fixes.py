import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app as webapp
from src.agents.literature_builder_agent import LiteratureBuilderAgent
from src.agents.narrative_verifier import (
    UnsupportedSentenceError,
    split_sentences,
    verify_paragraph,
)
from src.agents.reference_validator import ReferenceValidator
from src.blueprints import journals
from src.models.data_models import Claim, ClaimCluster, EvidenceRow, PaperMetadata


def test_custom_citation_results_are_json_serializable(monkeypatch):
    paper = PaperMetadata(
        title="Serializable paper", authors=["A. Author"], year=2025,
        venue="Journal", abstract="Abstract",
    )

    class FakeSystem:
        async def research(self, _topic):
            return SimpleNamespace(papers=[paper])

    class FakeFormatter:
        async def process(self, papers):
            return [{"original_paper": papers[0], "bibitem_key": "Au25"}]

        def get_citation_stats(self, _citations):
            return {"total": 1}

    monkeypatch.setattr(webapp, "get_system", lambda: FakeSystem())
    monkeypatch.setattr(webapp, "CustomCitationFormatter", FakeFormatter)

    result = webapp.run_citation_generation("serialization")

    assert isinstance(result["citations"][0]["original_paper"], dict)
    json.dumps(result)


def test_retired_debug_route_returns_404():
    response = webapp.app.test_client().get("/debug")
    assert response.status_code == 404


def test_server_defaults_are_private_and_debug_is_opt_in(monkeypatch):
    for name in ("HOST", "PORT", "FLASK_DEBUG"):
        monkeypatch.delenv(name, raising=False)
    assert webapp._server_options() == {
        "debug": False, "host": "127.0.0.1", "port": 5050, "threaded": True,
    }

    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("FLASK_DEBUG", "1")
    assert webapp._server_options()["host"] == "0.0.0.0"
    assert webapp._server_options()["debug"] is True


def test_admin_endpoints_fail_closed_and_accept_valid_header(monkeypatch):
    client = webapp.app.test_client()
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    for endpoint in ("/api/admin/coverage", "/api/admin/etl/status"):
        assert client.get(endpoint).status_code == 403
    assert client.post(
        "/api/admin/etl/run/doaj", data="source=doaj", content_type="text/plain"
    ).status_code == 403

    wrapped = journals._require_admin(lambda: "ok")
    monkeypatch.setenv("ADMIN_TOKEN", "correct-token")
    with webapp.app.test_request_context(
        method="POST", data="source=doaj", content_type="text/plain",
        headers={"X-Admin-Token": "wrong-token"},
    ):
        assert wrapped()[1] == 403
    with webapp.app.test_request_context(
        method="POST", data="source=doaj", content_type="text/plain",
        headers={"X-Admin-Token": "correct-token"},
    ):
        assert wrapped() == "ok"


_JSON_POST_ENDPOINTS = (
    "/research",
    "/research/start",
    "/validate-references",
    "/reformat-references",
    "/generate-literature",
    "/generate-literature/start",
    "/generate-custom-citations",
    "/humanize",
    "/export/json",
    "/export/pdf",
    "/export/docx",
    "/check-plagiarism",
    "/recommend-journals",
    "/screen-abstracts",
    "/generate-checklist",
    "/write-grant",
    "/get-citation-network",
    "/resolve-access",
    "/run-benchmark",
)


@pytest.mark.parametrize("endpoint", _JSON_POST_ENDPOINTS)
@pytest.mark.parametrize("body", (b"{", b"[]"))
def test_json_post_endpoints_reject_malformed_or_non_object_input(endpoint, body):
    response = webapp.app.test_client().post(
        endpoint, data=body, content_type="application/json"
    )
    assert response.status_code == 400
    assert response.get_json()["error"] in {"Invalid JSON object", "Invalid request data"}


def test_input_limits_and_unexpected_errors_are_generic(monkeypatch):
    client = webapp.app.test_client()

    oversized = client.post(
        "/humanize", data=b"x" * (5 * 1024 * 1024 + 1),
        content_type="application/json",
    )
    assert oversized.status_code == 413

    too_long = client.post("/humanize", json={"text": "x" * 200_001})
    assert too_long.status_code == 400
    assert client.post(
        "/resolve-access", json={"query": "10.1/example", "institution": []}
    ).status_code == 400
    assert client.post(
        "/generate-checklist", json={"abstract": ["wrong type"]}
    ).status_code == 400

    class BrokenChecker:
        def check(self, _text):
            raise RuntimeError("private backend detail")

    monkeypatch.setattr(webapp, "PlagiarismCheckerAgent", BrokenChecker)
    failed = client.post("/check-plagiarism", json={"text": "word " * 30})
    assert failed.status_code == 500
    assert failed.get_json() == {"error": "Internal server error"}
    assert b"private backend detail" not in failed.data


def test_export_topic_cannot_control_temp_path_and_file_is_deleted(monkeypatch):
    created_paths = []
    real_mkstemp = webapp.tempfile.mkstemp

    def recording_mkstemp(*args, **kwargs):
        fd, path = real_mkstemp(*args, **kwargs)
        created_paths.append(path)
        return fd, path

    monkeypatch.setattr(webapp.tempfile, "mkstemp", recording_mkstemp)
    response = webapp.app.test_client().post(
        "/export/pdf", json={"topic": "../../private/report"}
    )

    assert response.status_code == 200
    disposition = response.headers["Content-Disposition"]
    assert "private_report" in disposition
    assert "../" not in disposition
    assert created_paths and all(not os.path.exists(path) for path in created_paths)


def test_server_header_does_not_disclose_versions():
    response = webapp.app.test_client().get("/debug")
    assert response.headers["Server"] == "ResearchAgent"
    assert "Werkzeug" not in response.headers["Server"]
    assert "Python" not in response.headers["Server"]


@pytest.mark.asyncio
async def test_crossref_doi_is_url_encoded(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"message": {"title": ["Found"]}}

    class Requests:
        @staticmethod
        def get(url, **_kwargs):
            captured["url"] = url
            return Response()

    import src.agents.reference_validator as validator_module
    monkeypatch.setattr(validator_module, "requests", Requests)

    verification = {"checks_performed": [], "issues_found": []}
    await ReferenceValidator()._search_by_doi("10.1000/a b?x=1", verification)
    assert captured["url"] == "https://api.crossref.org/works/10.1000/a%20b%3Fx%3D1"


@pytest.mark.asyncio
async def test_no_evidence_fallback_drops_unknown_citations(monkeypatch):
    paper = PaperMetadata(
        title="No author paper", authors=[], year=2025, venue="Journal",
        abstract="A sufficiently long abstract. " * 10,
    )
    claim = Claim(statement="A claim", paper_id=paper.id)
    cluster = ClaimCluster(
        cluster_id="cluster", theme="Theme", research_objective="Objective",
        claims=[claim], papers=[paper],
    )
    agent = LiteratureBuilderAgent(mode="rules")
    monkeypatch.setattr(
        agent, "_build_cluster_paragraph",
        AsyncMock(return_value=("Unsupported claim \\cite{Unknown25}.", ["Unknown25"], [claim.id])),
    )

    text, citations, _claim_ids, sentences = await agent._build_cluster_paragraph_from_table(
        cluster, "rules", rows_by_paper={}, rows_by_key={}
    )

    assert "\\cite{Unknown" not in text
    assert citations == []
    assert sentences == []


def _evidence_rows():
    row = EvidenceRow(
        id="row-1", paper_id="paper-1", bibitem_key="Known25",
        verbatim_evidence="Evidence", confidence=1.0,
    )
    return {row.bibitem_key: row}


def test_newlines_and_bullets_are_separate_citation_gate_units():
    rows = _evidence_rows()
    paragraph = "Supported result \\cite{Known25}.\n- Unsupported bullet without a cite"

    assert len(split_sentences(paragraph)) == 2
    with pytest.raises(UnsupportedSentenceError):
        verify_paragraph(paragraph, rows)


def test_common_abbreviations_do_not_split_valid_sentences():
    rows = _evidence_rows()
    paragraph = (
        "Smith et al. compare Fig. 2, e.g. the corrected model, i.e. the final "
        "variant, vs. baseline \\cite{Known25}. A second result is supported "
        "\\cite{Known25}."
    )

    sentences = split_sentences(paragraph)
    assert len(sentences) == 2
    assert all(sentence.verified for sentence in verify_paragraph(paragraph, rows))
