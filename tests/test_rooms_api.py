import io
import json
import zipfile
from datetime import datetime
from urllib.parse import urlparse

import pytest

import app as app_module


def tiny_png_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"


def tiny_docx_bytes() -> bytes:
    content_types = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">
  <Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>
  <Default Extension=\"xml\" ContentType=\"application/xml\"/>
  <Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>
</Types>
"""
    rels = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
  <Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/>
</Relationships>
"""
    document_xml = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">
  <w:body>
    <w:p><w:r><w:t>Hello DOCX</w:t></w:r></w:p>
    <w:p><w:r><w:t>Second paragraph</w:t></w:r></w:p>
  </w:body>
</w:document>
"""
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
    return mem.getvalue()


def tiny_doc_bytes() -> bytes:
    return b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1minimal-doc"


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
            "PASSWORD_HASH_METHOD": "pbkdf2:sha256:1",
            "PASSWORD_HASH_FALLBACK_METHOD": "pbkdf2:sha256:1",
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


def upload_docx(client, slug="ml-room", filename="sample.docx"):
    return client.post(
        f"/api/rooms/{slug}/upload",
        data={"file": (io.BytesIO(tiny_docx_bytes()), filename)},
        content_type="multipart/form-data",
    )


def upload_doc(client, slug="ml-room", filename="sample.doc"):
    return client.post(
        f"/api/rooms/{slug}/upload",
        data={"file": (io.BytesIO(tiny_doc_bytes()), filename)},
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


def test_word_upload_and_word_filter(client):
    create_room(client, name="Word Room", slug="word-room", passcode="abcd1234")
    set_profile(client, "word-room", "Wendy")

    docx_upload = upload_docx(client, slug="word-room", filename="spec.docx")
    doc_upload = upload_doc(client, slug="word-room", filename="legacy.doc")
    png_upload = upload_png(client, slug="word-room", filename="image.png")

    assert docx_upload.status_code == 200
    assert doc_upload.status_code == 200
    assert png_upload.status_code == 200

    docx_payload = docx_upload.get_json()
    doc_payload = doc_upload.get_json()
    assert docx_payload["summary_job_id"] is not None
    assert docx_payload["file"]["summary_status"] == "pending"
    docx_job = client.get(f"/api/rooms/word-room/jobs/{docx_payload['summary_job_id']}")
    assert docx_job.status_code == 200
    assert docx_job.get_json()["job"]["status"] == "queued"

    assert doc_payload["summary_job_id"] is None
    assert doc_payload["file"]["summary_status"] == "not_applicable"
    assert "docx" in (doc_payload["file"]["summary_error"] or "").lower()

    word_only = client.get("/api/rooms/word-room/files?file_type=word")
    assert word_only.status_code == 200
    word_files = word_only.get_json()["files"]
    assert len(word_files) == 2
    assert {item["type"] for item in word_files} == {"doc", "docx"}


def test_docx_summary_execution_path(client, test_app, monkeypatch):
    create_room(client, name="Docx Summary Room", slug="docx-summary-room", passcode="abcd1234")
    set_profile(client, "docx-summary-room", "Wendy")

    upload_response = upload_docx(client, slug="docx-summary-room", filename="summary.docx")
    assert upload_response.status_code == 200
    payload = upload_response.get_json()
    job_id = payload["summary_job_id"]
    assert job_id is not None

    fake_summary = {
        "one_line_summary": "docx summary ok",
        "key_points": ["p1", "p2", "p3"],
        "keywords": ["k1", "k2", "k3", "k4", "k5"],
        "suggested_actions": ["a1", "a2", "a3"],
    }
    monkeypatch.setattr(app_module, "generate_ai_summary", lambda _text: fake_summary)
    monkeypatch.setattr(app_module, "app", test_app)
    test_app.config["SUMMARY_MIN_TEXT_CHARS"] = 1

    app_module.process_pdf_summary(job_id)

    with test_app.app_context():
        summary_job = app_module.db.session.get(app_module.SummaryJob, job_id)
        assert summary_job is not None
        assert summary_job.status == "done"
        assert summary_job.file is not None
        assert summary_job.file.summary_status == "done"
        assert summary_job.file.summary_json["one_line_summary"] == "docx summary ok"


def test_upload_preserves_original_filename(client, test_app):
    create_room(client, name="Filename Room", slug="filename-room", passcode="abcd1234")
    set_profile(client, "filename-room", "NameTester")

    source_name = "中文 空格 (v1) #final ✨.png"
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

    long_name = f"{'名' * 300}.png"
    upload_response = upload_png(client, slug="long-name-room", filename=long_name)
    assert upload_response.status_code == 200
    payload = upload_response.get_json()
    assert payload["file"]["original_name"] == long_name

    with test_app.app_context():
        record = app_module.FileRecord.query.filter_by(room_id=payload["room"]["id"]).first()
        assert record is not None
        assert record.original_name_full == long_name


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
        json={"content": "please check page 2"},
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
        json={"content": "add one more action"},
    )
    assert add_comment_2.status_code == 200

    incremental_pull = client.get(f"/api/rooms/comment-room/files/{file_id}/comments?after_id={cursor_id}")
    assert incremental_pull.status_code == 200
    incremental_payload = incremental_pull.get_json()
    assert len(incremental_payload["comments"]) == 1
    assert incremental_payload["comments"][0]["content"] == "add one more action"


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
    client.post(f"/api/rooms/meeting-room/files/{file_id}/comments", json={"content": "first comment"})

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


def test_owner_binding_recovers_for_legacy_unbound_room(client, test_app):
    create_room(client, name="Legacy Owner Room", slug="legacy-owner-room", passcode="abcd1234")
    set_profile(client, "legacy-owner-room", "Owner")

    with test_app.app_context():
        room = app_module.Room.query.filter_by(slug="legacy-owner-room").first()
        assert room is not None
        room.owner_viewer_token = None
        app_module.db.session.commit()

    profile = client.get("/api/rooms/legacy-owner-room/profile")
    assert profile.status_code == 200
    profile_payload = profile.get_json()
    assert profile_payload["discussion"]["owner_bound"] is True
    assert profile_payload["discussion"]["is_owner"] is True

    owner_end = client.post("/api/rooms/legacy-owner-room/discussion/end")
    assert owner_end.status_code == 200
    assert owner_end.get_json()["discussion"]["status"] in {"running", "done"}


def test_owner_binding_recovers_when_creator_session_token_rotates(client, test_app):
    create_room(client, name="Owner Recover Room", slug="owner-recover-room", passcode="abcd1234")
    set_profile(client, "owner-recover-room", "Owner")

    with test_app.app_context():
        room = app_module.Room.query.filter_by(slug="owner-recover-room").first()
        assert room is not None
        room.created_by_ip = "127.0.0.1"
        room.owner_viewer_token = "legacy-owner-token"
        app_module.db.session.commit()

    with client.session_transaction() as session_data:
        session_data[app_module.room_session_key("owner-recover-room")] = True
        session_data[app_module.room_viewer_token_session_key("owner-recover-room")] = "new-owner-token"

    profile = client.get("/api/rooms/owner-recover-room/profile")
    assert profile.status_code == 200
    payload = profile.get_json()
    assert payload["discussion"]["owner_bound"] is True
    assert payload["discussion"]["is_owner"] is True

    with test_app.app_context():
        room = app_module.Room.query.filter_by(slug="owner-recover-room").first()
        assert room is not None
        assert room.owner_viewer_token == "new-owner-token"

    owner_end = client.post("/api/rooms/owner-recover-room/discussion/end")
    assert owner_end.status_code == 200
    assert owner_end.get_json()["discussion"]["status"] in {"running", "done"}


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
            "quote_text": "Important\ufffd paragraph",
            "quote_prefix": "prefix",
            "quote_suffix": "suffix",
            "quote_start": 10,
            "quote_end": 28,
            "content": "please review this section first",
        },
    )
    assert create_thread.status_code == 200
    thread_payload = create_thread.get_json()
    thread_id = thread_payload["thread"]["id"]
    first_comment_id = thread_payload["comment"]["id"]
    assert thread_payload["thread"]["message_count"] == 1
    assert thread_payload["thread"]["source_type"] == "pdf"
    assert "\ufffd" not in thread_payload["thread"]["quote_text"]
    assert thread_payload["thread"]["quote_text"] == "Important paragraph"

    listed = client.get(f"/api/rooms/line-room/files/{file_id}/line-threads?page=1")
    assert listed.status_code == 200
    listed_payload = listed.get_json()
    assert len(listed_payload["threads"]) == 1
    assert listed_payload["threads"][0]["id"] == thread_id
    assert "\ufffd" not in listed_payload["threads"][0]["quote_text"]

    reply = client.post(
        f"/api/rooms/line-room/line-threads/{thread_id}/messages",
        json={"content": "adding one more point"},
    )
    assert reply.status_code == 200

    edited = client.patch(
        f"/api/rooms/line-room/line-comments/{first_comment_id}",
        json={"content": "please prioritize this section"},
    )
    assert edited.status_code == 200
    assert edited.get_json()["comment"]["content"] == "please prioritize this section"

    with test_app.test_client() as second_client:
        second_client.post("/api/rooms/line-room/auth", json={"passcode": "abcd1234"})
        second_client.post("/api/rooms/line-room/profile", json={"nickname": "Guest"})
        forbidden_edit = second_client.patch(
            f"/api/rooms/line-room/line-comments/{first_comment_id}",
            json={"content": "forbidden edit"},
        )
        assert forbidden_edit.status_code == 403

        forbidden_delete = second_client.delete(f"/api/rooms/line-room/line-comments/{first_comment_id}")
        assert forbidden_delete.status_code == 403

    deleted = client.delete(f"/api/rooms/line-room/line-comments/{first_comment_id}")
    assert deleted.status_code == 200
    assert deleted.get_json()["comment"]["is_deleted"] is True


def test_docx_line_thread_and_doc_downgrade(client):
    create_room(client, name="Word Line Room", slug="word-line-room", passcode="abcd1234")
    set_profile(client, "word-line-room", "Owner")

    docx_upload_payload = upload_docx(client, slug="word-line-room", filename="note.docx").get_json()
    docx_file_id = docx_upload_payload["file_id"]

    create_docx_thread = client.post(
        f"/api/rooms/word-line-room/files/{docx_file_id}/line-threads",
        json={
            "source_type": "docx",
            "anchor_scope": "segment",
            "page_number": 1,
            "segment_key": "segment-1",
            "segment_start": 0,
            "segment_end": 5,
            "quote_text": "Hello",
            "quote_prefix": "",
            "quote_suffix": "",
            "quote_start": 0,
            "quote_end": 5,
            "content": "docx scoped comment",
        },
    )
    assert create_docx_thread.status_code == 200
    docx_thread_payload = create_docx_thread.get_json()
    assert docx_thread_payload["thread"]["source_type"] == "docx"
    assert docx_thread_payload["thread"]["anchor_scope"] == "segment"
    assert docx_thread_payload["thread"]["segment_key"] == "segment-1"

    list_docx_threads = client.get(
        f"/api/rooms/word-line-room/files/{docx_file_id}/line-threads?segment_key=segment-1"
    )
    assert list_docx_threads.status_code == 200
    assert len(list_docx_threads.get_json()["threads"]) == 1

    doc_upload_payload = upload_doc(client, slug="word-line-room", filename="legacy.doc").get_json()
    doc_file_id = doc_upload_payload["file_id"]

    create_doc_thread = client.post(
        f"/api/rooms/word-line-room/files/{doc_file_id}/line-threads",
        json={
            "page_number": 1,
            "quote_text": "Legacy",
            "content": "should fail",
        },
    )
    assert create_doc_thread.status_code == 400
    assert ".doc" in create_doc_thread.get_json()["message"]

    full_comment_on_doc = client.post(
        f"/api/rooms/word-line-room/files/{doc_file_id}/comments",
        json={"content": "full comment still allowed"},
    )
    assert full_comment_on_doc.status_code == 200


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
            "content": "line comment content",
        },
    )
    assert add_thread.status_code == 200

    add_full_comment = client.post(
        f"/api/rooms/summary-room/files/{file_id}/comments",
        json={"content": "full comment content"},
    )
    assert add_full_comment.status_code == 200

    with client.application.app_context():
        room = app_module.Room.query.filter_by(slug="summary-room").first()
        assert room is not None
        summary_json = app_module.build_discussion_summary_json(room)

    owners = summary_json.get("by_commented_owner") or []
    assert owners

    found_line_feedback = False
    for owner_group in owners:
        for file_item in owner_group.get("files", []):
            assert "full_comments" in file_item
            assert "line_comments" in file_item
            assert "action_board" in file_item
            assert "processing" in file_item["action_board"]
            assert "follow_up" in file_item["action_board"]

            full_comments = file_item.get("full_comments") or []
            assert full_comments
            assert full_comments[0]["comment_content"] == "full comment content"

            line_feedback = file_item.get("line_feedback") or []
            if line_feedback:
                found_line_feedback = True
                first_feedback = line_feedback[0]
                assert first_feedback["page_number"] == 1
                comments = first_feedback.get("comments") or []
                assert comments
                assert comments[0]["comment_content"] == "line comment content"
                line_comments = file_item.get("line_comments") or []
                assert line_comments
                assert line_comments[0]["comments"][0]["comment_content"] == "line comment content"
                break
        if found_line_feedback:
            break

    assert found_line_feedback is True


def test_discussion_summary_endpoint_normalizes_legacy_action_board_and_dedupes_claims(client, test_app):
    create_room(client, name="Legacy Summary Room", slug="legacy-summary-room", passcode="abcd1234")
    set_profile(client, "legacy-summary-room", "Owner")
    upload_payload = upload_pdf(client, slug="legacy-summary-room", filename="legacy-summary.pdf").get_json()

    with test_app.app_context():
        room = app_module.Room.query.filter_by(slug="legacy-summary-room").first()
        assert room is not None
        file_record = app_module.FileRecord.query.filter_by(id=upload_payload["file_id"]).first()
        assert file_record is not None
        file_name = app_module.get_file_original_name(file_record)

        legacy_payload = {
            "meeting_overview": {"room_name": room.name},
            "by_commented_owner": [
                {
                    "owner_nickname": "Owner",
                    "owner_summary": "legacy format payload",
                    "files": [
                        {
                            "file_id": file_record.id,
                            "file_name": file_name,
                            "comment_details": [
                                {
                                    "commenter_nickname": "A",
                                    "comment_content": "full legacy content",
                                    "created_at": datetime.utcnow().isoformat() + "Z",
                                }
                            ],
                            "line_feedback": [
                                {
                                    "thread_id": 1,
                                    "source_type": "pdf",
                                    "page_number": 1,
                                    "quote_text": "legacy\ufffd quote",
                                    "comments": [
                                        {
                                            "commenter_nickname": "B",
                                            "comment_content": "line legacy content",
                                            "created_at": datetime.utcnow().isoformat() + "Z",
                                        }
                                    ],
                                }
                            ],
                            "action_board": {"processing": [], "follow_up": []},
                        }
                    ],
                    "claimable_actions": [
                        f"处理《{file_name}》第1页引用：legacy quote",
                        f"跟进《{file_name}》全文评论：full legacy content",
                        f"跟进《{file_name}》全文评论：full legacy content",
                        "额外待确认：会后统一术语口径",
                    ],
                    "action_board": {"processing": [], "follow_up": []},
                }
            ],
            "cross_actions": [],
        }

        room.discussion_ended_at = datetime.utcnow()
        room.discussion_status = app_module.DISCUSSION_STATUS_DONE
        room.discussion_summary_version = 1
        summary = app_module.RoomDiscussionSummary(
            room_id=room.id,
            version=1,
            status=app_module.DISCUSSION_STATUS_DONE,
            summary_json=legacy_payload,
            summary_text=json.dumps(legacy_payload, ensure_ascii=False),
        )
        app_module.db.session.add(summary)
        app_module.db.session.commit()

    summary_response = client.get("/api/rooms/legacy-summary-room/discussion/summary")
    assert summary_response.status_code == 200
    payload = summary_response.get_json()
    normalized = payload["summary"]["summary_json"]
    owner_group = normalized["by_commented_owner"][0]
    file_item = owner_group["files"][0]

    assert file_item["action_board"]["processing"]
    assert file_item["action_board"]["follow_up"]
    assert owner_group["processing_details"]
    assert owner_group["follow_up_details"]
    assert owner_group["action_board"]["processing"] == owner_group["processing_details"]
    assert owner_group["action_board"]["follow_up"] == owner_group["follow_up_details"]
    assert any("full legacy content" in item for item in owner_group["processing_details"])
    assert any("line legacy content" in item for item in owner_group["processing_details"])
    assert all("\ufffd" not in item for item in owner_group["processing_details"])
    assert all("\ufffd" not in item for item in owner_group["follow_up_details"])
    assert file_item["comment_details"] == file_item["full_comments"]
    assert file_item["line_feedback"] == file_item["line_comments"]
    assert owner_group["claimable_actions"] == ["额外待确认：会后统一术语口径"]


def test_discussion_summary_endpoint_removes_fully_mapped_claimable_actions(client, test_app):
    create_room(client, name="Legacy Summary Room 2", slug="legacy-summary-room-2", passcode="abcd1234")
    set_profile(client, "legacy-summary-room-2", "Owner")
    upload_payload = upload_pdf(client, slug="legacy-summary-room-2", filename="legacy-summary-2.pdf").get_json()

    with test_app.app_context():
        room = app_module.Room.query.filter_by(slug="legacy-summary-room-2").first()
        assert room is not None
        file_record = app_module.FileRecord.query.filter_by(id=upload_payload["file_id"]).first()
        assert file_record is not None
        file_name = app_module.get_file_original_name(file_record)

        legacy_payload = {
            "meeting_overview": {"room_name": room.name},
            "by_commented_owner": [
                {
                    "owner_nickname": "Owner",
                    "files": [
                        {
                            "file_id": file_record.id,
                            "file_name": file_name,
                            "comment_details": [],
                            "line_feedback": [],
                            "action_board": {"processing": [], "follow_up": []},
                        }
                    ],
                    "claimable_actions": [
                        f"处理《{file_name}》：补充结构化结论与负责人。",
                        f"跟进《{file_name}》：暂无全文评论，建议会后补充。",
                    ],
                    "action_board": {"processing": [], "follow_up": []},
                }
            ],
            "cross_actions": [],
        }

        room.discussion_ended_at = datetime.utcnow()
        room.discussion_status = app_module.DISCUSSION_STATUS_DONE
        room.discussion_summary_version = 1
        summary = app_module.RoomDiscussionSummary(
            room_id=room.id,
            version=1,
            status=app_module.DISCUSSION_STATUS_DONE,
            summary_json=legacy_payload,
            summary_text=json.dumps(legacy_payload, ensure_ascii=False),
        )
        app_module.db.session.add(summary)
        app_module.db.session.commit()

    summary_response = client.get("/api/rooms/legacy-summary-room-2/discussion/summary")
    assert summary_response.status_code == 200
    payload = summary_response.get_json()
    normalized = payload["summary"]["summary_json"]
    owner_group = normalized["by_commented_owner"][0]
    assert owner_group["processing_details"]
    assert owner_group["follow_up_details"]
    assert owner_group["claimable_actions"] == []


def test_discussion_summary_follow_up_only_contains_owner_comments_to_others_and_not_truncated(client, test_app):
    create_room(client, name="Flow Room", slug="flow-room", passcode="abcd1234")
    set_profile(client, "flow-room", "Alice")
    alice_upload = upload_pdf(client, slug="flow-room", filename="alice.pdf")
    assert alice_upload.status_code == 200
    alice_file_id = alice_upload.get_json()["file_id"]

    with test_app.test_client() as bob_client:
        auth = bob_client.post("/api/rooms/flow-room/auth", json={"passcode": "abcd1234"})
        assert auth.status_code == 200
        set_profile_response = set_profile(bob_client, "flow-room", "Bob")
        assert set_profile_response.status_code == 200
        bob_upload = upload_pdf(bob_client, slug="flow-room", filename="bob.pdf")
        assert bob_upload.status_code == 200
        bob_file_id = bob_upload.get_json()["file_id"]

        bob_comment = bob_client.post(
            f"/api/rooms/flow-room/files/{alice_file_id}/comments",
            json={"content": "Bob对Alice的完整点评内容，不应该出现在Alice的跟进区。"},
        )
        assert bob_comment.status_code == 200

    long_quote = "这是Alice针对Bob文件的完整划线引用文本，长度足够用于验证系统不会再做截断处理。"
    long_line_comment = "Alice在线上点评Bob文件，这条划线评论必须完整保留，不允许省略号。"
    long_full_comment = "Alice给Bob的全文评论也必须完整保留，并且只能出现在Alice的跟进区域。"

    alice_line_thread = client.post(
        f"/api/rooms/flow-room/files/{bob_file_id}/line-threads",
        json={
            "page_number": 1,
            "quote_text": long_quote,
            "quote_prefix": "",
            "quote_suffix": "",
            "quote_start": 10,
            "quote_end": 10 + len(long_quote),
            "content": long_line_comment,
        },
    )
    assert alice_line_thread.status_code == 200

    alice_full_comment = client.post(
        f"/api/rooms/flow-room/files/{bob_file_id}/comments",
        json={"content": long_full_comment},
    )
    assert alice_full_comment.status_code == 200

    with test_app.app_context():
        room = app_module.Room.query.filter_by(slug="flow-room").first()
        assert room is not None
        summary_json = app_module.build_discussion_summary_json(room)
        normalized = app_module.normalize_discussion_summary_payload(summary_json)

    owner_groups = normalized.get("by_commented_owner") or []
    owner_map = {group.get("owner_nickname"): group for group in owner_groups}
    assert "Alice" in owner_map
    assert "Bob" in owner_map

    alice_group = owner_map["Alice"]
    bob_group = owner_map["Bob"]

    assert any("Bob对Alice的完整点评内容" in item for item in alice_group.get("processing_details", []))
    assert any(long_full_comment in item for item in alice_group.get("follow_up_details", []))
    assert any(long_line_comment in item for item in alice_group.get("follow_up_details", []))
    assert any(long_quote in item for item in alice_group.get("follow_up_details", []))
    assert all("Bob对Alice的完整点评内容" not in item for item in alice_group.get("follow_up_details", []))
    assert any("Alice给Bob的全文评论" in item for item in bob_group.get("processing_details", []))


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

