from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from docmark.main import app
from helpers import docx_bytes, pdf_bytes


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def upload_and_wait(
    client: TestClient,
    *,
    pdf_name: str = "题目.pdf",
    pdf_content: bytes | None = None,
    docx_name: str = "作业.docx",
    docx_content: bytes | None = None,
):
    response = client.post(
        "/api/jobs",
        files={
            "pdf": (pdf_name, pdf_content or pdf_bytes("7 + 8 = 16"), "application/pdf"),
            "docx": (
                docx_name,
                docx_content or docx_bytes(["作业：7 + 8 = 16。", "3 + 3 = 6。"]),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        },
    )
    assert response.status_code == 202, response.text
    job = response.json()
    for _ in range(80):
        current = client.get(f"/api/jobs/{job['id']}")
        assert current.status_code == 200
        if current.json()["status"] in {"completed", "failed"}:
            return current.json()
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_homepage_and_config(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert "上传文档" in page.text
    assert page.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in page.headers["content-security-policy"]

    config = client.get("/api/config").json()
    assert config["max_upload_mb"] >= 1
    assert config["allowed_extensions"] == ["docx", "pdf"]
    assert config["upload_requires"] == {"pdf": 1, "docx": 1}


def test_upload_pair_annotate_and_download_docx(client: TestClient) -> None:
    job = upload_and_wait(
        client,
        pdf_name="题目.pdf",
        docx_name="数学作业.docx",
        docx_content=docx_bytes(["作业：7 + 8 = 16。", "3 + 3 = 6。"]),
    )
    assert job["status"] == "completed", job
    assert job["issue_count"] == 1
    assert job["pdf_name"] == "题目.pdf"
    assert job["docx_name"] == "数学作业.docx"
    assert job["output_name"] == "数学作业_批注.docx"
    assert job["download_url"].endswith("/download")

    response = client.get(job["download_url"])
    assert response.status_code == 200
    assert response.content.startswith(b"PK")
    assert "filename*=utf-8''" in response.headers["content-disposition"].lower()


def test_rejects_missing_half_of_the_pair(client: TestClient) -> None:
    response = client.post(
        "/api/jobs",
        files={"pdf": ("题目.pdf", pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 400
    assert "同时上传" in response.json()["detail"]


def test_rejects_invalid_pdf_content(client: TestClient) -> None:
    response = client.post(
        "/api/jobs",
        files={
            "pdf": ("bad.pdf", b"not a pdf", "application/pdf"),
            "docx": ("作业.docx", docx_bytes(["1 + 1 = 2"]), "application/octet-stream"),
        },
    )
    assert response.status_code == 400


def test_rejects_wrong_extension_in_slot(client: TestClient) -> None:
    response = client.post(
        "/api/jobs",
        files={
            "pdf": ("其实是文档.docx", docx_bytes(["x"]), "application/octet-stream"),
            "docx": ("作业.docx", docx_bytes(["1 + 1 = 2"]), "application/octet-stream"),
        },
    )
    assert response.status_code == 415


def test_rejects_fake_docx(client: TestClient) -> None:
    response = client.post(
        "/api/jobs",
        files={
            "pdf": ("题目.pdf", pdf_bytes(), "application/pdf"),
            "docx": ("fake.docx", b"not a zip", "application/octet-stream"),
        },
    )
    assert response.status_code == 400


def test_unknown_job(client: TestClient) -> None:
    assert client.get("/api/jobs/" + "0" * 32).status_code == 404
    assert client.get("/api/jobs/not-a-job").status_code == 404
