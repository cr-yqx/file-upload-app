import io
from urllib.parse import urlparse

import pytest

import app as app_module


def tiny_png_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"


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


def create_room(client, name="Machine Learning", slug="ml-room", passcode="pass1234"):
    return client.post(
        "/api/rooms",
        json={"name": name, "slug": slug, "passcode": passcode},
    )


def upload_png(client, slug="ml-room", filename="sample.png"):
    return client.post(
        f"/api/rooms/{slug}/upload",
        data={"file": (io.BytesIO(tiny_png_bytes()), filename)},
        content_type="multipart/form-data",
    )


def test_create_room_and_auth_flow(client, test_app):
    create_response = create_room(client)
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
    create_room(client, name="Image Room", slug="img-room", passcode="abcd1234")

    upload_response = upload_png(client, slug="img-room")

    assert upload_response.status_code == 200
    upload_payload = upload_response.get_json()
    assert upload_payload["success"] is True
    assert upload_payload["summary_job_id"] is None
    assert upload_payload["file"]["summary_status"] == "not_applicable"

    list_response = client.get("/api/rooms/img-room/files")
    assert list_response.status_code == 200
    list_payload = list_response.get_json()
    assert list_payload["viewer"]["has_profile"] is False
    assert list_payload["metrics"]["total_files"] == 1
    assert len(list_payload["files"]) == 1
    assert list_payload["files"][0]["original_name"] == "sample.png"
    assert list_payload["files"][0]["collab"]["comment_count"] == 0


def test_upload_pdf_creates_async_job(client):
    create_room(client, name="PDF Room", slug="pdf-room", passcode="abcd1234")

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
    create_room(client, name="Delete Room", slug="delete-room", passcode="abcd1234")

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


def test_profile_get_and_upsert_flow(client):
    create_room(client, name="Collab Room", slug="collab-room", passcode="abcd1234")

    get_before = client.get("/api/rooms/collab-room/profile")
    assert get_before.status_code == 200
    assert get_before.get_json()["viewer"]["has_profile"] is False

    invalid = client.post("/api/rooms/collab-room/profile", json={"nickname": "A"})
    assert invalid.status_code == 400

    upsert = client.post("/api/rooms/collab-room/profile", json={"nickname": "小王同学"})
    assert upsert.status_code == 200
    upsert_payload = upsert.get_json()
    assert upsert_payload["viewer"]["nickname"] == "小王同学"
    assert upsert_payload["viewer"]["viewer_token"] == "session-scoped"

    get_after = client.get("/api/rooms/collab-room/profile")
    assert get_after.status_code == 200
    after_payload = get_after.get_json()
    assert after_payload["viewer"]["has_profile"] is True
    assert after_payload["viewer"]["nickname"] == "小王同学"


def test_comment_requires_profile_and_can_list(client):
    create_room(client, name="Comment Room", slug="comment-room", passcode="abcd1234")
    upload_payload = upload_png(client, slug="comment-room", filename="notes.png").get_json()
    file_id = upload_payload["file_id"]

    no_profile_comment = client.post(
        f"/api/rooms/comment-room/files/{file_id}/comments",
        json={"content": "先看结论部分"},
    )
    assert no_profile_comment.status_code == 400

    client.post("/api/rooms/comment-room/profile", json={"nickname": "Alice"})

    empty_comment = client.post(
        f"/api/rooms/comment-room/files/{file_id}/comments",
        json={"content": "   "},
    )
    assert empty_comment.status_code == 400

    add_comment = client.post(
        f"/api/rooms/comment-room/files/{file_id}/comments",
        json={"content": "建议先看第 3 页方法论。"},
    )
    assert add_comment.status_code == 200
    assert add_comment.get_json()["comment"]["nickname"] == "Alice"

    list_comments = client.get(f"/api/rooms/comment-room/files/{file_id}/comments")
    assert list_comments.status_code == 200
    comments_payload = list_comments.get_json()
    assert len(comments_payload["comments"]) == 1
    assert comments_payload["comments"][0]["content"] == "建议先看第 3 页方法论。"


def test_star_and_read_are_idempotent_and_visible_in_files(client):
    create_room(client, name="Focus Room", slug="focus-room", passcode="abcd1234")
    upload_payload = upload_png(client, slug="focus-room", filename="focus.png").get_json()
    file_id = upload_payload["file_id"]

    star_without_profile = client.put(
        f"/api/rooms/focus-room/files/{file_id}/star",
        json={"starred": True},
    )
    assert star_without_profile.status_code == 400

    client.post("/api/rooms/focus-room/profile", json={"nickname": "Bob"})

    star_1 = client.put(f"/api/rooms/focus-room/files/{file_id}/star", json={"starred": True})
    assert star_1.status_code == 200
    star_2 = client.put(f"/api/rooms/focus-room/files/{file_id}/star", json={"starred": True})
    assert star_2.status_code == 200

    read_true = client.put(f"/api/rooms/focus-room/files/{file_id}/read", json={"read": True})
    assert read_true.status_code == 200
    read_false = client.put(f"/api/rooms/focus-room/files/{file_id}/read", json={"read": False})
    assert read_false.status_code == 200
    read_false_again = client.put(f"/api/rooms/focus-room/files/{file_id}/read", json={"read": False})
    assert read_false_again.status_code == 200

    listed = client.get("/api/rooms/focus-room/files")
    assert listed.status_code == 200
    listed_payload = listed.get_json()
    assert listed_payload["metrics"]["total_files"] == 1
    assert listed_payload["metrics"]["starred_files"] == 1
    assert listed_payload["metrics"]["unread_files"] == 1

    file_info = listed_payload["files"][0]
    assert file_info["collab"]["star_count"] == 1
    assert file_info["collab"]["starred_by_me"] is True
    assert file_info["collab"]["read_by_me"] is False
    assert file_info["collab"]["read_count"] == 0

    unstar_1 = client.put(f"/api/rooms/focus-room/files/{file_id}/star", json={"starred": False})
    assert unstar_1.status_code == 200
    unstar_2 = client.put(f"/api/rooms/focus-room/files/{file_id}/star", json={"starred": False})
    assert unstar_2.status_code == 200

    listed_after = client.get("/api/rooms/focus-room/files")
    after_payload = listed_after.get_json()
    assert after_payload["metrics"]["starred_files"] == 0
    assert after_payload["files"][0]["collab"]["star_count"] == 0
    assert after_payload["files"][0]["collab"]["starred_by_me"] is False


def test_legacy_endpoints_still_work(client):
    upload_response = client.post(
        "/upload",
        data={"file": (io.BytesIO(tiny_png_bytes()), "legacy.png")},
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
