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
            "DISCUSSION_ASYNC": False,
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


def set_profile(client, slug, nickname):
    return client.post(f"/api/rooms/{slug}/profile", json={"nickname": nickname})


def upload_png(client, slug="ml-room", filename="sample.png"):
    return client.post(
        f"/api/rooms/{slug}/upload",
        data={"file": (io.BytesIO(tiny_png_bytes()), filename)},
        content_type="multipart/form-data",
    )


def upload_pdf(client, slug="ml-room", filename="sample.pdf"):
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    return client.post(
        f"/api/rooms/{slug}/upload",
        data={"file": (io.BytesIO(pdf_bytes), filename)},
        content_type="multipart/form-data",
    )


def test_create_room_and_auth_flow(client, test_app):
    create_response = create_room(client)
    assert create_response.status_code == 200
    payload = create_response.get_json()
    assert payload["success"] is True
    assert payload["room"]["slug"] == "ml-room"
    assert payload["discussion"]["status"] == "idle"

    profile = client.get("/api/rooms/ml-room/profile")
    assert profile.status_code == 200
    assert profile.get_json()["viewer"]["is_owner"] is True

    with test_app.test_client() as second_client:
        wrong_auth = second_client.post("/api/rooms/ml-room/auth", json={"passcode": "wrong"})
        assert wrong_auth.status_code == 401

        correct_auth = second_client.post("/api/rooms/ml-room/auth", json={"passcode": "pass1234"})
        assert correct_auth.status_code == 200
        assert correct_auth.get_json()["success"] is True


def test_upload_requires_profile_then_success(client):
    create_room(client, name="Image Room", slug="img-room", passcode="abcd1234")

    no_profile_upload = upload_png(client, slug="img-room")
    assert no_profile_upload.status_code == 400

    set_profile(client, "img-room", "Alice")

    upload_response = upload_png(client, slug="img-room")
    assert upload_response.status_code == 200
    upload_payload = upload_response.get_json()
    assert upload_payload["file"]["uploader_nickname"] == "Alice"
    assert upload_payload["file"]["summary_status"] == "not_applicable"
    assert upload_payload["file"]["url"].startswith("/uploads/img-room/")
    parsed_abs = urlparse(upload_payload["file"]["absolute_url"])
    assert parsed_abs.scheme in {"http", "https"}
    assert parsed_abs.netloc
    assert parsed_abs.path == upload_payload["file"]["url"]

    list_response = client.get("/api/rooms/img-room/files")
    assert list_response.status_code == 200
    list_payload = list_response.get_json()
    assert list_payload["viewer"]["has_profile"] is True
    assert list_payload["files"][0]["uploader_nickname"] == "Alice"
    assert list_payload["files"][0]["url"].startswith("/uploads/img-room/")
    parsed_list_abs = urlparse(list_payload["files"][0]["absolute_url"])
    assert parsed_list_abs.path == list_payload["files"][0]["url"]

    uploader_token = list_payload["files"][0]["uploader_viewer_token"]
    filtered = client.get(f"/api/rooms/img-room/files?uploader_token={uploader_token}")
    assert filtered.status_code == 200
    assert len(filtered.get_json()["files"]) == 1


def test_upload_pdf_creates_async_job(client):
    create_room(client, name="PDF Room", slug="pdf-room", passcode="abcd1234")
    set_profile(client, "pdf-room", "Bob")

    upload_response = upload_pdf(client, slug="pdf-room", filename="lecture.pdf")

    assert upload_response.status_code == 200
    upload_payload = upload_response.get_json()
    assert upload_payload["summary_job_id"] is not None
    assert upload_payload["file"]["uploader_nickname"] == "Bob"

    job_id = upload_payload["summary_job_id"]
    job_response = client.get(f"/api/rooms/pdf-room/jobs/{job_id}")
    assert job_response.status_code == 200
    assert job_response.get_json()["job"]["status"] == "queued"


def test_upload_preserves_original_filename(client, test_app):
    create_room(client, name="Filename Room", slug="filename-room", passcode="abcd1234")
    set_profile(client, "filename-room", "NameTester")

    source_name = "中文 空格 (v1) #final ✅.png"
    upload_response = upload_png(client, slug="filename-room", filename=source_name)
    assert upload_response.status_code == 200
    payload = upload_response.get_json()
    assert payload["file"]["original_name"] == source_name

    with test_app.app_context():
        record = app_module.FileRecord.query.filter_by(room_id=payload["room"]["id"]).first()
        assert record is not None
        assert record.original_name_full == source_name


def test_upload_preserves_very_long_filename(client, test_app):
    create_room(client, name="Long Name Room", slug="long-name-room", passcode="abcd1234")
    set_profile(client, "long-name-room", "LongTester")

    long_name = f"{'超' * 300}.png"
    upload_response = upload_png(client, slug="long-name-room", filename=long_name)
    assert upload_response.status_code == 200
    payload = upload_response.get_json()
    assert payload["file"]["original_name"] == long_name

    with test_app.app_context():
        record = app_module.FileRecord.query.filter_by(room_id=payload["room"]["id"]).first()
        assert record is not None
        assert record.original_name_full == long_name
        assert len(record.original_name) <= 255


def test_presence_and_collaborators(client):
    create_room(client, name="Presence Room", slug="presence-room", passcode="abcd1234")
    set_profile(client, "presence-room", "Carol")

    presence = client.post("/api/rooms/presence-room/presence")
    assert presence.status_code == 200

    collaborators = client.get("/api/rooms/presence-room/collaborators")
    assert collaborators.status_code == 200
    payload = collaborators.get_json()
    assert len(payload["collaborators"]) >= 1
    assert payload["collaborators"][0]["nickname"] in {"Carol", "匿名协作者"}


def test_comment_incremental_cursor(client):
    create_room(client, name="Comment Room", slug="comment-room", passcode="abcd1234")
    set_profile(client, "comment-room", "Dora")
    upload_payload = upload_png(client, slug="comment-room", filename="notes.png").get_json()
    file_id = upload_payload["file_id"]

    add_comment_1 = client.post(
        f"/api/rooms/comment-room/files/{file_id}/comments",
        json={"content": "先看第 2 页结论。"},
    )
    assert add_comment_1.status_code == 200

    first_pull = client.get(f"/api/rooms/comment-room/files/{file_id}/comments")
    assert first_pull.status_code == 200
    first_payload = first_pull.get_json()
    assert len(first_payload["comments"]) == 1
    cursor_id = first_payload["cursor"]["after_id"]

    empty_pull = client.get(f"/api/rooms/comment-room/files/{file_id}/comments?after_id={cursor_id}")
    assert empty_pull.status_code == 200
    assert empty_pull.get_json()["comments"] == []

    add_comment_2 = client.post(
        f"/api/rooms/comment-room/files/{file_id}/comments",
        json={"content": "补充一个行动建议。"},
    )
    assert add_comment_2.status_code == 200

    incremental_pull = client.get(f"/api/rooms/comment-room/files/{file_id}/comments?after_id={cursor_id}")
    assert incremental_pull.status_code == 200
    incremental_payload = incremental_pull.get_json()
    assert len(incremental_payload["comments"]) == 1
    assert incremental_payload["comments"][0]["content"] == "补充一个行动建议。"


def test_star_read_and_metrics(client):
    create_room(client, name="Focus Room", slug="focus-room", passcode="abcd1234")
    set_profile(client, "focus-room", "Eve")
    upload_payload = upload_png(client, slug="focus-room", filename="focus.png").get_json()
    file_id = upload_payload["file_id"]

    star_1 = client.put(f"/api/rooms/focus-room/files/{file_id}/star", json={"starred": True})
    assert star_1.status_code == 200
    star_2 = client.put(f"/api/rooms/focus-room/files/{file_id}/star", json={"starred": True})
    assert star_2.status_code == 200

    read_true = client.put(f"/api/rooms/focus-room/files/{file_id}/read", json={"read": True})
    assert read_true.status_code == 200
    read_false = client.put(f"/api/rooms/focus-room/files/{file_id}/read", json={"read": False})
    assert read_false.status_code == 200

    listed = client.get("/api/rooms/focus-room/files")
    payload = listed.get_json()
    assert payload["metrics"]["total_files"] == 1
    assert payload["metrics"]["starred_files"] == 1
    assert payload["metrics"]["unread_files"] == 1


def test_discussion_end_owner_only_and_summary(client, test_app):
    create_room(client, name="Meeting Room", slug="meeting-room", passcode="abcd1234")
    set_profile(client, "meeting-room", "Owner")
    upload_payload = upload_png(client, slug="meeting-room", filename="meeting.png").get_json()
    file_id = upload_payload["file_id"]
    client.post(f"/api/rooms/meeting-room/files/{file_id}/comments", json={"content": "第一条评论"})

    with test_app.test_client() as second_client:
        second_client.post("/api/rooms/meeting-room/auth", json={"passcode": "abcd1234"})
        second_client.post("/api/rooms/meeting-room/profile", json={"nickname": "Guest"})
        forbidden = second_client.post("/api/rooms/meeting-room/discussion/end")
        assert forbidden.status_code == 403

    owner_end = client.post("/api/rooms/meeting-room/discussion/end")
    assert owner_end.status_code == 200
    assert owner_end.get_json()["discussion"]["status"] in {"running", "done"}

    summary = client.get("/api/rooms/meeting-room/discussion/summary")
    assert summary.status_code == 200
    summary_payload = summary.get_json()
    assert summary_payload["discussion"]["status"] in {"done", "running", "failed"}
    if summary_payload["summary"]:
        assert "meeting_overview" in summary_payload["summary"]["summary_json"]
        assert "by_commented_owner" in summary_payload["summary"]["summary_json"]


def test_delete_file_removes_metadata_and_asset(client):
    create_room(client, name="Delete Room", slug="delete-room", passcode="abcd1234")
    set_profile(client, "delete-room", "Frank")

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


def test_pdf_line_thread_crud_and_author_permissions(client, test_app):
    create_room(client, name="Line Room", slug="line-room", passcode="abcd1234")
    set_profile(client, "line-room", "Owner")
    upload_payload = upload_pdf(client, slug="line-room", filename="paper.pdf").get_json()
    file_id = upload_payload["file_id"]

    create_thread = client.post(
        f"/api/rooms/line-room/files/{file_id}/line-threads",
        json={
            "page_number": 1,
            "quote_text": "Important paragraph",
            "quote_prefix": "prefix",
            "quote_suffix": "suffix",
            "quote_start": 10,
            "quote_end": 28,
            "content": "请先看这一段。",
        },
    )
    assert create_thread.status_code == 200
    thread_payload = create_thread.get_json()
    thread_id = thread_payload["thread"]["id"]
    first_comment_id = thread_payload["comment"]["id"]
    assert thread_payload["thread"]["message_count"] == 1

    listed = client.get(f"/api/rooms/line-room/files/{file_id}/line-threads?page=1")
    assert listed.status_code == 200
    listed_payload = listed.get_json()
    assert len(listed_payload["threads"]) == 1
    assert listed_payload["threads"][0]["id"] == thread_id

    reply = client.post(
        f"/api/rooms/line-room/line-threads/{thread_id}/messages",
        json={"content": "我补充一个问题。"},
    )
    assert reply.status_code == 200

    edited = client.patch(
        f"/api/rooms/line-room/line-comments/{first_comment_id}",
        json={"content": "请重点阅读这一段。"},
    )
    assert edited.status_code == 200
    assert edited.get_json()["comment"]["content"] == "请重点阅读这一段。"

    with test_app.test_client() as second_client:
        second_client.post("/api/rooms/line-room/auth", json={"passcode": "abcd1234"})
        second_client.post("/api/rooms/line-room/profile", json={"nickname": "Guest"})
        forbidden_edit = second_client.patch(
            f"/api/rooms/line-room/line-comments/{first_comment_id}",
            json={"content": "越权编辑"},
        )
        assert forbidden_edit.status_code == 403

        forbidden_delete = second_client.delete(f"/api/rooms/line-room/line-comments/{first_comment_id}")
        assert forbidden_delete.status_code == 403

    deleted = client.delete(f"/api/rooms/line-room/line-comments/{first_comment_id}")
    assert deleted.status_code == 200
    assert deleted.get_json()["comment"]["is_deleted"] is True


def test_discussion_summary_contains_line_feedback(client):
    create_room(client, name="Summary Room", slug="summary-room", passcode="abcd1234")
    set_profile(client, "summary-room", "Owner")
    upload_payload = upload_pdf(client, slug="summary-room", filename="summary.pdf").get_json()
    file_id = upload_payload["file_id"]

    add_thread = client.post(
        f"/api/rooms/summary-room/files/{file_id}/line-threads",
        json={
            "page_number": 1,
            "quote_text": "Original quote",
            "quote_prefix": "A",
            "quote_suffix": "B",
            "quote_start": 3,
            "quote_end": 16,
            "content": "原文评论内容",
        },
    )
    assert add_thread.status_code == 200

    with client.application.app_context():
        room = app_module.Room.query.filter_by(slug="summary-room").first()
        assert room is not None
        summary_json = app_module.build_discussion_summary_json(room)

    owners = summary_json.get("by_commented_owner") or []
    assert owners

    found_line_feedback = False
    for owner_group in owners:
        for file_item in owner_group.get("files", []):
            line_feedback = file_item.get("line_feedback") or []
            if line_feedback:
                found_line_feedback = True
                first_feedback = line_feedback[0]
                assert first_feedback["page_number"] == 1
                comments = first_feedback.get("comments") or []
                assert comments
                assert comments[0]["comment_content"] == "原文评论内容"
                break
        if found_line_feedback:
            break

    assert found_line_feedback is True


def test_legacy_endpoints_still_work(client):
    upload_response = client.post(
        "/upload",
        data={"file": (io.BytesIO(tiny_png_bytes()), "legacy.png")},
        content_type="multipart/form-data",
    )
    assert upload_response.status_code == 200
    payload = upload_response.get_json()
    assert payload["deprecated"] is True
    assert payload["file"]["url"].startswith("http")
    assert payload["file"]["absolute_url"] == payload["file"]["url"]

    list_response = client.get("/api/files")
    assert list_response.status_code == 200
    list_payload = list_response.get_json()
    assert list_payload["deprecated"] is True
    assert len(list_payload["files"]) >= 1
