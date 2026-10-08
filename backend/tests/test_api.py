from __future__ import annotations

import json
import uuid

from tests.conftest import fake_llm, make_docx, make_pdf

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def upload(client, name="handbook.docx", data=None, collection=None):
    data = data if data is not None else make_docx("Employees accrue 21 days of PTO per year.")
    params = {"collection": collection} if collection else None
    return client.post("/api/documents", files={"file": (name, data, DOCX_TYPE)}, params=params)


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_health_ok(make_client):
    with make_client() as client:
        body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["llm"]["provider"] == "ollama"
    assert body["errors"] == []


def test_degraded_service_returns_503(make_client):
    with make_client(errors=["Database unavailable: refused"]) as client:
        health = client.get("/api/health").json()
        docs = client.get("/api/documents")
        chat = client.post("/api/chat/stream", json={"question": "hi"})
    assert health["status"] == "degraded" and health["database"] is False
    assert docs.status_code == 503 and "refused" in docs.json()["detail"]
    assert chat.status_code == 503


def test_upload_list_get_delete(make_client):
    with make_client() as client:
        res = upload(client)
        assert res.status_code == 201
        doc = res.json()
        assert doc["num_chunks"] >= 1 and doc["collection"] == "default"

        assert [d["id"] for d in client.get("/api/documents").json()] == [doc["id"]]
        assert client.get(f"/api/documents/{doc['id']}").status_code == 200
        assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
        assert client.delete(f"/api/documents/{doc['id']}").status_code == 404
        assert client.get("/api/documents").json() == []


def test_upload_errors(make_client):
    with make_client() as client:
        assert upload(client).status_code == 201
        dup = upload(client, name="copy.docx")
        assert dup.status_code == 409

        bad_type = client.post("/api/documents", files={"file": ("a.txt", b"hi", "text/plain")})
        assert bad_type.status_code == 400

        fake_pdf = client.post(
            "/api/documents", files={"file": ("a.pdf", b"nope", "application/pdf")}
        )
        assert fake_pdf.status_code == 400

        too_big = upload(client, name="big.pdf", data=b"%PDF-" + b"0" * (1024 * 1024 + 10))
        assert too_big.status_code == 413

        assert upload(client, collection="bad name!").status_code == 422


def test_get_unknown_document_404_and_invalid_id_422(make_client):
    with make_client() as client:
        assert client.get(f"/api/documents/{uuid.uuid4()}").status_code == 404
        assert client.get("/api/documents/not-a-uuid").status_code == 422


def test_chat_stream_sse(make_client):
    with make_client(llm=fake_llm("You get 21 days [1].")) as client:
        upload(client)
        res = client.post("/api/chat/stream", json={"question": "How much PTO do I get?"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(res.text)
    assert events[0][0] == "sources"
    assert events[0][1]["sources"][0]["filename"] == "handbook.docx"
    assert "".join(d["text"] for e, d in events if e == "token") == "You get 21 days [1]."
    assert events[-1] == ("done", {"cited": [1], "elapsed_ms": events[-1][1]["elapsed_ms"]})


def test_chat_validation(make_client):
    with make_client() as client:
        assert client.post("/api/chat/stream", json={"question": "   "}).status_code == 422
        assert client.post("/api/chat/stream", json={"question": "x" * 2001}).status_code == 422
        bad_history = {"question": "q", "history": [{"role": "system", "content": "x"}]}
        assert client.post("/api/chat/stream", json=bad_history).status_code == 422


def test_chat_non_streaming(make_client):
    with make_client(llm=fake_llm("Twenty-one days [1].")) as client:
        client.post(
            "/api/documents",
            files={"file": ("p.pdf", make_pdf("Employees get 21 days of PTO."), "application/pdf")},
        )
        body = client.post("/api/chat", json={"question": "PTO days?"}).json()
    assert body["answer"] == "Twenty-one days [1]."
    assert body["cited"] == [1]
    assert body["sources"][0]["page"] == 1
