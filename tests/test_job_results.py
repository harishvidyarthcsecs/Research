"""Regression coverage for the SSE-to-result handoff."""
from app import app
from src.jobs import JOBS


def test_terminal_sse_closes_before_completed_result_is_fetched():
    payload = {
        "summary": {"papers_analyzed": 1},
        "recommendations": [{"title": "Validate the handoff"}],
    }
    job = JOBS.create("SSE handoff regression")
    job.status = "running"
    job.emit("start", topic=job.topic, stages=[])
    job.finish("done", result=payload)

    with app.test_client() as client:
        stream_response = client.get(f"/research/events/{job.id}", buffered=True)
        result_response = client.get(f"/research/result/{job.id}")
        report_response = client.get(f"/report/{job.id}.md")

    stream_body = stream_response.get_data(as_text=True)
    assert stream_response.status_code == 200
    assert "Connection" not in stream_response.headers
    assert stream_body.count("event: end") == 1
    assert stream_body.rstrip().endswith('"status": "done", "error": null}')

    assert result_response.status_code == 200
    assert result_response.get_json() == payload
    assert report_response.status_code == 200
    assert report_response.mimetype == "text/markdown"
