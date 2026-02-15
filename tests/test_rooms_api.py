import io
from urllib.parse import urlparse

import pytest

import app as app_module


@pytest.fixture()
def test_app(tmp_path, monkeypatch):
    database_path = tmp_path / "test.db"
    upload_path = tmp_path / "uploads"

    flask_app = app_module.create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "UPLOAD_FOLDER": str(upload_path),
            "SECRET_KEY": "test-secret",
            "DEFAULT_ROOM_PASSCODE": "demo1234",
        }
    )

    monkeypatch.setattr(app_module, "enqueue_summary_job", lambda _job: "rq-test-id")

    with flask_app.app_context():
        app_module.db.drop_all()
        app_module.db.create_all()
        app_module.ensure_default_room()

    return flask_app


@pytest.fixture()
def client(test_app):
    return test_app.test_client()


def test_create_room_and_auth_flow(client, test_app):
    create_response = client.post(
        "/api/rooms",
        json={"name": "Machine Learning", "slug": "ml-room", "passcode": "pass1234"},
    )
    assert create_response.status_code == 200
    create_payload = create_response.get_json()
    assert create_payload["success"] is True
    assert create_payload["room"]["slug"] == "ml-room"

    with test_app.test_client() as second_client:
        wrong_auth = second_client.post("/api/rooms/ml-room/auth", json={"passcode": "wrong"})
        assert wrong_auth.status_code == 401

        correct_auth = second_client.post("/api/rooms/ml-room/auth", json={"passcode": "pass1234"})
        assert correct_auth.status_code == 200
        assert correct_auth.get_json()["success"] is True


def test_upload_image_and_list_files(client):
    client.post("/api/rooms", json={"name": "Image Room", "slug": "img-room", "passcode": "abcd1234"})

    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    upload_response = client.post(
        "/api/rooms/img-room/upload",
        data={"file": (io.BytesIO(png_bytes), "sample.png")},
        content_type="multipart/form-data",
    )

    assert upload_response.status_code == 200
    upload_payload = upload_response.get_json()
    assert upload_payload["success"] is True
    assert upload_payload["summary_job_id"] is None
    assert upload_payload["file"]["summary_status"] == "not_applicable"

    list_response = client.get("/api/rooms/img-room/files")
    assert list_response.status_code == 200
    list_payload = list_response.get_json()
    assert len(list_payload["files"]) == 1
    assert list_payload["files"][0]["original_name"] == "sample.png"


def test_upload_pdf_creates_async_job(client):
    client.post("/api/rooms", json={"name": "PDF Room", "slug": "pdf-room", "passcode": "abcd1234"})

    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    upload_response = client.post(
        "/api/rooms/pdf-room/upload",
        data={"file": (io.BytesIO(pdf_bytes), "lecture.pdf")},
        content_type="multipart/form-data",
    )

    assert upload_response.status_code == 200
    upload_payload = upload_response.get_json()
    assert upload_payload["summary_job_id"] is not None

    job_id = upload_payload["summary_job_id"]
    job_response = client.get(f"/api/rooms/pdf-room/jobs/{job_id}")
    assert job_response.status_code == 200
    job_payload = job_response.get_json()
    assert job_payload["job"]["status"] == "queued"


def test_delete_file_removes_metadata_and_asset(client):
    client.post("/api/rooms", json={"name": "Delete Room", "slug": "delete-room", "passcode": "abcd1234"})

    jpg_bytes = b"\xff\xd8\xff\xdb\x00C\x00"
    upload_response = client.post(
        "/api/rooms/delete-room/upload",
        data={"file": (io.BytesIO(jpg_bytes), "to-delete.jpg")},
        content_type="multipart/form-data",
    )

    upload_payload = upload_response.get_json()
    file_id = upload_payload["file_id"]

    delete_response = client.delete(f"/api/rooms/delete-room/files/{file_id}")
    assert delete_response.status_code == 200

    list_response = client.get("/api/rooms/delete-room/files")
    assert list_response.status_code == 200
    assert list_response.get_json()["files"] == []

    file_url = upload_payload["file"]["url"]
    file_path = urlparse(file_url).path
    check_deleted_response = client.get(file_path)
    assert check_deleted_response.status_code == 404


def test_legacy_endpoints_still_work(client):
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"

    upload_response = client.post(
        "/upload",
        data={"file": (io.BytesIO(png_bytes), "legacy.png")},
        content_type="multipart/form-data",
    )
    assert upload_response.status_code == 200
    payload = upload_response.get_json()
    assert payload["deprecated"] is True

    list_response = client.get("/api/files")
    assert list_response.status_code == 200
    list_payload = list_response.get_json()
    assert list_payload["deprecated"] is True
    assert len(list_payload["files"]) >= 1
