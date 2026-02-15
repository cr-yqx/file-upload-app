import json
import os
import re
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from flask import (
    Flask,
    abort,
    current_app,
    has_request_context,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from openai import OpenAI
from pypdf import PdfReader
from sqlalchemy import or_
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


db = SQLAlchemy()

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "pdf"}
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
MIME_TYPES = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}

SUMMARY_STATUS_PENDING = "pending"
SUMMARY_STATUS_RUNNING = "running"
SUMMARY_STATUS_DONE = "done"
SUMMARY_STATUS_FAILED = "failed"
SUMMARY_STATUS_NOT_APPLICABLE = "not_applicable"

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_DONE = "done"
JOB_STATUS_FAILED = "failed"


class Room(db.Model):
    __tablename__ = "rooms"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    passcode_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by_ip = db.Column(db.String(64), nullable=True)

    files = db.relationship(
        "FileRecord",
        back_populates="room",
        cascade="all, delete-orphan",
        order_by=lambda: FileRecord.created_at.desc(),
    )


class FileRecord(db.Model):
    __tablename__ = "files"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    size_bytes = db.Column(db.BigInteger, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    uploader_ip = db.Column(db.String(64), nullable=True)
    summary_status = db.Column(db.String(32), nullable=False, default=SUMMARY_STATUS_NOT_APPLICABLE)
    summary_text = db.Column(db.Text, nullable=True)
    summary_json = db.Column(db.JSON, nullable=True)
    summary_error = db.Column(db.Text, nullable=True)

    room = db.relationship("Room", back_populates="files")
    jobs = db.relationship(
        "SummaryJob",
        back_populates="file",
        cascade="all, delete-orphan",
        order_by=lambda: SummaryJob.id.desc(),
    )


class SummaryJob(db.Model):
    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    job_type = db.Column(db.String(50), nullable=False, default="pdf_summary")
    status = db.Column(db.String(32), nullable=False, default=JOB_STATUS_QUEUED)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    error = db.Column(db.Text, nullable=True)
    rq_job_id = db.Column(db.String(64), nullable=True)

    file = db.relationship("FileRecord", back_populates="jobs")


class AccessLog(db.Model):
    __tablename__ = "access_logs"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    action = db.Column(db.String(80), nullable=False)
    file_id = db.Column(db.Integer, db.ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    client_ip = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


db.Index("idx_files_room_created_at", FileRecord.room_id, FileRecord.created_at)
db.Index("idx_jobs_file_id", SummaryJob.file_id)


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    # SQLAlchemy defaults "postgresql://" to psycopg2.
    # Force psycopg3 driver since this project uses psycopg[binary].
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)

    return url


def create_app(test_config: Optional[Dict[str, Any]] = None) -> Flask:
    app = Flask(__name__)

    database_url = normalize_database_url(os.getenv("DATABASE_URL", "sqlite:///app.db"))
    upload_folder = os.getenv("UPLOAD_FOLDER", "uploads")
    engine_options: Dict[str, Any] = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        engine_options["connect_args"] = {"check_same_thread": False}

    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "change-me-in-production"),
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS=engine_options,
        UPLOAD_FOLDER=upload_folder,
        MAX_CONTENT_LENGTH=int(os.getenv("MAX_FILE_SIZE", str(10 * 1024 * 1024))),
        OPENAI_API_KEY=os.getenv("OPENAI_API_KEY", ""),
        OPENAI_MODEL=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        OPENAI_BASE_URL=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        SUMMARY_MAX_TEXT_CHARS=int(os.getenv("SUMMARY_MAX_TEXT_CHARS", "20000")),
        SUMMARY_MIN_TEXT_CHARS=int(os.getenv("SUMMARY_MIN_TEXT_CHARS", "80")),
        SUMMARY_MAX_ATTEMPTS=int(os.getenv("SUMMARY_MAX_ATTEMPTS", "2")),
        SUMMARY_RETRY_DELAY_SECONDS=int(os.getenv("SUMMARY_RETRY_DELAY_SECONDS", "3")),
        DEFAULT_ROOM_SLUG=os.getenv("DEFAULT_ROOM_SLUG", "demo"),
        DEFAULT_ROOM_NAME=os.getenv("DEFAULT_ROOM_NAME", "Demo Room"),
        DEFAULT_ROOM_PASSCODE=os.getenv("DEFAULT_ROOM_PASSCODE", "demo1234"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    register_error_handlers(app)
    register_routes(app)

    with app.app_context():
        os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
        db.create_all()
        ensure_default_room()

    return app


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(413)
    def file_too_large(_error: Exception):
        return jsonify({"success": False, "message": "File too large."}), 413


def register_routes(app: Flask) -> None:
    @app.get("/health")
    def health() -> Any:
        return jsonify(
            {
                "success": True,
                "status": "ok",
                "time": datetime.utcnow().isoformat() + "Z",
                "counts": {
                    "rooms": Room.query.count(),
                    "files": FileRecord.query.count(),
                    "jobs": SummaryJob.query.count(),
                },
            }
        )

    @app.get("/")
    def room_entry_page() -> Any:
        return render_template("room_entry.html", default_room_slug=current_app.config["DEFAULT_ROOM_SLUG"])

    @app.get("/r/<room_slug>")
    def room_page(room_slug: str) -> Any:
        room = Room.query.filter_by(slug=room_slug).first()
        if room is None:
            abort(404)

        return render_template(
            "room.html",
            room=room,
            authorized=is_room_authorized(room_slug),
            is_deprecated=request.args.get("deprecated") == "1",
        )

    @app.post("/api/rooms")
    def create_room_api() -> Any:
        data = request.get_json(silent=True) or {}

        room_name = (data.get("name") or "").strip()
        requested_slug = (data.get("slug") or "").strip()
        passcode = (data.get("passcode") or "").strip()

        if not room_name:
            return jsonify({"success": False, "message": "Room name is required."}), 400

        if len(passcode) < 4:
            return jsonify({"success": False, "message": "Passcode must be at least 4 characters."}), 400

        if requested_slug:
            room_slug = slugify(requested_slug)
            if Room.query.filter_by(slug=room_slug).first() is not None:
                return jsonify({"success": False, "message": "Room slug already exists."}), 409
        else:
            room_slug = make_unique_slug(room_name)

        room = Room(
            name=room_name,
            slug=room_slug,
            passcode_hash=generate_password_hash(passcode),
            created_by_ip=get_client_ip(),
        )
        db.session.add(room)
        db.session.commit()

        mark_room_authorized(room.slug)
        write_access_log(room_id=room.id, action="create_room")

        share_url = request.host_url.rstrip("/") + url_for("room_page", room_slug=room.slug)

        return jsonify(
            {
                "success": True,
                "room": serialize_room(room),
                "share_url": share_url,
            }
        )

    @app.post("/api/rooms/<room_slug>/auth")
    def auth_room_api(room_slug: str) -> Any:
        room = Room.query.filter_by(slug=room_slug).first()
        if room is None:
            return jsonify({"success": False, "message": "Room not found."}), 404

        data = request.get_json(silent=True) or {}
        passcode = (data.get("passcode") or "").strip()

        if not check_password_hash(room.passcode_hash, passcode):
            return jsonify({"success": False, "message": "Invalid passcode."}), 401

        mark_room_authorized(room.slug)
        write_access_log(room_id=room.id, action="auth_room")

        return jsonify({"success": True, "room": serialize_room(room)})

    @app.post("/api/rooms/<room_slug>/upload")
    def upload_to_room_api(room_slug: str) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        return handle_file_upload(room=room, deprecated=False, bypass_auth=False)

    @app.get("/api/rooms/<room_slug>/files")
    def list_room_files_api(room_slug: str) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        room_files = (
            FileRecord.query.filter_by(room_id=room.id)
            .order_by(FileRecord.created_at.desc(), FileRecord.id.desc())
            .all()
        )

        return jsonify(
            {
                "success": True,
                "room": serialize_room(room),
                "files": [serialize_file(file_record) for file_record in room_files],
            }
        )

    @app.get("/api/rooms/<room_slug>/jobs/<int:job_id>")
    def get_job_status_api(room_slug: str, job_id: int) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        summary_job = (
            SummaryJob.query.join(FileRecord, SummaryJob.file_id == FileRecord.id)
            .filter(SummaryJob.id == job_id, FileRecord.room_id == room.id)
            .first()
        )

        if summary_job is None:
            return jsonify({"success": False, "message": "Job not found."}), 404

        return jsonify(
            {
                "success": True,
                "job": serialize_job(summary_job),
                "file": serialize_file(summary_job.file),
            }
        )

    @app.delete("/api/rooms/<room_slug>/files/<int:file_id>")
    def delete_room_file_api(room_slug: str, file_id: int) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        file_record = FileRecord.query.filter_by(id=file_id, room_id=room.id).first()
        if file_record is None:
            return jsonify({"success": False, "message": "File not found."}), 404

        file_path = get_stored_file_path(room.slug, file_record.stored_name)
        if os.path.exists(file_path):
            os.remove(file_path)

        db.session.delete(file_record)
        db.session.commit()

        write_access_log(room_id=room.id, action="delete_file", file_id=file_id)

        return jsonify({"success": True, "message": "File deleted."})

    @app.get("/uploads/<room_slug>/<stored_name>")
    def uploaded_file(room_slug: str, stored_name: str) -> Any:
        room = Room.query.filter_by(slug=room_slug).first()
        if room is None:
            abort(404)

        if not is_room_authorized(room_slug):
            return jsonify({"success": False, "message": "Room auth required."}), 401

        folder = get_room_upload_folder(room_slug, ensure=False)
        if not os.path.exists(os.path.join(folder, stored_name)):
            abort(404)

        extension = get_extension(stored_name)
        mimetype = MIME_TYPES.get(extension)
        return send_from_directory(folder, stored_name, mimetype=mimetype)

    # Legacy compatibility routes.
    @app.get("/files")
    def legacy_files_page() -> Any:
        default_room = ensure_default_room()
        mark_room_authorized(default_room.slug)
        return redirect(url_for("room_page", room_slug=default_room.slug, deprecated=1))

    @app.get("/api/files")
    def legacy_list_files() -> Any:
        default_room = ensure_default_room()

        room_files = (
            FileRecord.query.filter_by(room_id=default_room.id)
            .order_by(FileRecord.created_at.desc(), FileRecord.id.desc())
            .all()
        )

        payload = {
            "success": True,
            "deprecated": True,
            "deprecation_message": "Use GET /api/rooms/<room_slug>/files instead.",
            "files": [serialize_file(file_record, legacy=True) for file_record in room_files],
        }
        return jsonify(payload)

    @app.delete("/api/files/<filename>")
    def legacy_delete_file(filename: str) -> Any:
        default_room = ensure_default_room()

        file_record = (
            FileRecord.query.filter(
                FileRecord.room_id == default_room.id,
                or_(
                    FileRecord.stored_name == filename,
                    FileRecord.original_name == filename,
                ),
            )
            .order_by(FileRecord.id.desc())
            .first()
        )

        if file_record is None:
            return jsonify({"success": False, "deprecated": True, "message": "File not found."}), 404

        file_path = get_stored_file_path(default_room.slug, file_record.stored_name)
        if os.path.exists(file_path):
            os.remove(file_path)

        db.session.delete(file_record)
        db.session.commit()

        write_access_log(room_id=default_room.id, action="legacy_delete_file", file_id=file_record.id)

        return jsonify(
            {
                "success": True,
                "deprecated": True,
                "deprecation_message": "Use DELETE /api/rooms/<room_slug>/files/<file_id>.",
                "message": "File deleted.",
            }
        )

    @app.post("/upload")
    def legacy_upload_file() -> Any:
        default_room = ensure_default_room()
        return handle_file_upload(room=default_room, deprecated=True, bypass_auth=True)

    @app.get("/uploads/<filename>")
    def legacy_uploaded_file(filename: str) -> Any:
        default_room = ensure_default_room()

        demo_path = get_stored_file_path(default_room.slug, filename)
        legacy_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)

        if os.path.exists(demo_path):
            extension = get_extension(filename)
            mimetype = MIME_TYPES.get(extension)
            return send_from_directory(get_room_upload_folder(default_room.slug, ensure=False), filename, mimetype=mimetype)

        if os.path.exists(legacy_path):
            extension = get_extension(filename)
            mimetype = MIME_TYPES.get(extension)
            return send_file(legacy_path, mimetype=mimetype)

        abort(404)


def get_room_for_api(room_slug: str, require_auth: bool = True):
    room = Room.query.filter_by(slug=room_slug).first()
    if room is None:
        return None, (jsonify({"success": False, "message": "Room not found."}), 404)

    if require_auth and not is_room_authorized(room_slug):
        return None, (jsonify({"success": False, "message": "Room auth required."}), 401)

    return room, None


def allowed_file(filename: str) -> bool:
    return "." in filename and get_extension(filename) in ALLOWED_EXTENSIONS


def get_extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def get_client_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.remote_addr or "unknown"


def room_session_key(room_slug: str) -> str:
    return f"room_auth::{room_slug}"


def is_room_authorized(room_slug: str) -> bool:
    return bool(session.get(room_session_key(room_slug)))


def mark_room_authorized(room_slug: str) -> None:
    session[room_session_key(room_slug)] = True
    session.modified = True


def slugify(value: str) -> str:
    lowered = value.lower().strip()
    slug = re.sub(r"[^a-z0-9-]+", "-", lowered)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "room"


def make_unique_slug(seed: str) -> str:
    base_slug = slugify(seed)
    candidate = base_slug

    while Room.query.filter_by(slug=candidate).first() is not None:
        candidate = f"{base_slug}-{uuid.uuid4().hex[:6]}"

    return candidate


def get_room_upload_folder(room_slug: str, ensure: bool = True) -> str:
    room_folder = os.path.join(current_app.config["UPLOAD_FOLDER"], room_slug)
    if ensure:
        os.makedirs(room_folder, exist_ok=True)
    return room_folder


def get_stored_file_path(room_slug: str, stored_name: str) -> str:
    return os.path.join(get_room_upload_folder(room_slug, ensure=True), stored_name)


def build_room_file_url(room_slug: str, stored_name: str) -> str:
    return request.host_url.rstrip("/") + url_for("uploaded_file", room_slug=room_slug, stored_name=stored_name)


def build_legacy_file_url(stored_name: str) -> str:
    return request.host_url.rstrip("/") + f"/uploads/{stored_name}"


def serialize_room(room: Room) -> Dict[str, Any]:
    return {
        "id": room.id,
        "slug": room.slug,
        "name": room.name,
        "created_at": room.created_at.isoformat() + "Z",
    }


def serialize_job(summary_job: SummaryJob) -> Dict[str, Any]:
    return {
        "id": summary_job.id,
        "file_id": summary_job.file_id,
        "job_type": summary_job.job_type,
        "status": summary_job.status,
        "attempts": summary_job.attempts,
        "started_at": summary_job.started_at.isoformat() + "Z" if summary_job.started_at else None,
        "finished_at": summary_job.finished_at.isoformat() + "Z" if summary_job.finished_at else None,
        "error": summary_job.error,
    }


def serialize_file(file_record: FileRecord, legacy: bool = False) -> Dict[str, Any]:
    extension = get_extension(file_record.stored_name)
    file_type = "image" if extension in IMAGE_EXTENSIONS else "pdf"
    latest_job_id = file_record.jobs[0].id if file_record.jobs else None

    payload = {
        "id": file_record.id,
        "room_slug": file_record.room.slug,
        "filename": file_record.stored_name,
        "stored_name": file_record.stored_name,
        "original_name": file_record.original_name,
        "mime_type": file_record.mime_type,
        "size": file_record.size_bytes,
        "size_mb": round(file_record.size_bytes / (1024 * 1024), 2),
        "modified": file_record.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "type": file_type,
        "url": build_room_file_url(file_record.room.slug, file_record.stored_name),
        "summary_status": file_record.summary_status,
        "summary_text": file_record.summary_text,
        "summary_json": file_record.summary_json,
        "summary_error": file_record.summary_error,
        "summary_job_id": latest_job_id,
    }

    if legacy:
        payload["url"] = build_legacy_file_url(file_record.stored_name)

    return payload


def ensure_default_room() -> Room:
    default_room_slug = current_app.config["DEFAULT_ROOM_SLUG"]
    default_room = Room.query.filter_by(slug=default_room_slug).first()

    if default_room is None:
        default_room = Room(
            slug=default_room_slug,
            name=current_app.config["DEFAULT_ROOM_NAME"],
            passcode_hash=generate_password_hash(current_app.config["DEFAULT_ROOM_PASSCODE"]),
            created_by_ip="system",
        )
        db.session.add(default_room)
        db.session.commit()

    return default_room


def write_access_log(room_id: int, action: str, file_id: Optional[int] = None) -> None:
    try:
        if has_request_context():
            client_ip = get_client_ip()
            user_agent = request.headers.get("User-Agent")
        else:
            client_ip = "system"
            user_agent = None

        access_log = AccessLog(
            room_id=room_id,
            action=action,
            file_id=file_id,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        db.session.add(access_log)
        db.session.commit()
    except Exception:
        db.session.rollback()


def handle_file_upload(room: Room, deprecated: bool, bypass_auth: bool) -> Any:
    if not bypass_auth and not is_room_authorized(room.slug):
        return jsonify({"success": False, "message": "Room auth required."}), 401

    if "file" not in request.files:
        return jsonify({"success": False, "message": "No file selected."}), 400

    uploaded_file = request.files["file"]

    if uploaded_file.filename == "":
        return jsonify({"success": False, "message": "No file selected."}), 400

    if not allowed_file(uploaded_file.filename):
        return jsonify({"success": False, "message": "Unsupported file type."}), 400

    extension = get_extension(uploaded_file.filename)
    safe_original_name = secure_filename(uploaded_file.filename) or f"file-{uuid.uuid4().hex}.{extension}"
    stored_name = f"{uuid.uuid4().hex}.{extension}"

    room_folder = get_room_upload_folder(room.slug, ensure=True)
    file_path = os.path.join(room_folder, stored_name)
    uploaded_file.save(file_path)

    file_size = os.path.getsize(file_path)
    mime_type = MIME_TYPES.get(extension, uploaded_file.mimetype or "application/octet-stream")
    summary_status = SUMMARY_STATUS_PENDING if extension == "pdf" else SUMMARY_STATUS_NOT_APPLICABLE

    file_record = FileRecord(
        room_id=room.id,
        original_name=safe_original_name,
        stored_name=stored_name,
        mime_type=mime_type,
        size_bytes=file_size,
        uploader_ip=get_client_ip(),
        summary_status=summary_status,
    )
    db.session.add(file_record)
    db.session.commit()

    summary_job = None
    if extension == "pdf":
        summary_job = SummaryJob(
            file_id=file_record.id,
            job_type="pdf_summary",
            status=JOB_STATUS_QUEUED,
            attempts=0,
        )
        db.session.add(summary_job)
        db.session.commit()

        try:
            enqueue_summary_job(summary_job)
        except Exception as exc:
            summary_job.status = JOB_STATUS_FAILED
            summary_job.error = f"Summary worker unavailable: {exc}"
            summary_job.finished_at = datetime.utcnow()
            file_record.summary_status = SUMMARY_STATUS_FAILED
            file_record.summary_error = "Summary worker unavailable. Please retry later."
            db.session.commit()

    write_access_log(room_id=room.id, action="upload_file", file_id=file_record.id)

    payload = {
        "success": True,
        "message": "File uploaded successfully.",
        "room": serialize_room(room),
        "file_id": file_record.id,
        "summary_job_id": summary_job.id if summary_job else None,
        "file": serialize_file(file_record, legacy=deprecated),
    }

    if deprecated:
        payload.update(
            {
                "deprecated": True,
                "deprecation_message": "Use POST /api/rooms/<room_slug>/upload instead.",
                "filename": file_record.stored_name,
                "size": file_record.size_bytes,
                "url": build_legacy_file_url(file_record.stored_name),
            }
        )

    return jsonify(payload)


def enqueue_summary_job(summary_job: SummaryJob) -> str:
    local_job_id = f"local-{uuid.uuid4().hex[:12]}"
    summary_job.rq_job_id = local_job_id
    db.session.commit()

    worker = threading.Thread(
        target=_run_summary_job_in_background,
        args=(summary_job.id,),
        daemon=True,
        name=f"summary-job-{summary_job.id}",
    )
    worker.start()
    return local_job_id


def _run_summary_job_in_background(summary_job_id: int) -> None:
    try:
        process_pdf_summary(summary_job_id)
    except Exception as exc:
        with app.app_context():
            summary_job = db.session.get(SummaryJob, summary_job_id)
            if summary_job is None:
                return

            file_record = summary_job.file
            summary_job.status = JOB_STATUS_FAILED
            summary_job.error = f"Worker crash: {exc}"
            summary_job.finished_at = datetime.utcnow()

            if file_record is not None:
                file_record.summary_status = SUMMARY_STATUS_FAILED
                file_record.summary_error = f"Worker crash: {exc}"

            db.session.commit()


def extract_pdf_text(file_path: str) -> str:
    pdf_reader = PdfReader(file_path)
    text_chunks = []

    for page in pdf_reader.pages:
        extracted_text = (page.extract_text() or "").strip()
        if extracted_text:
            text_chunks.append(extracted_text)

    return "\n".join(text_chunks).strip()


def normalize_summary_json(raw_json: Dict[str, Any]) -> Dict[str, Any]:
    one_line = str(raw_json.get("one_line_summary") or "").strip()
    if not one_line:
        one_line = "No concise summary was generated."

    def normalized_list(key: str, expected_count: int, fallback_prefix: str):
        source = raw_json.get(key)
        if not isinstance(source, list):
            source = []

        cleaned = [str(item).strip() for item in source if str(item).strip()]
        while len(cleaned) < expected_count:
            cleaned.append(f"{fallback_prefix} {len(cleaned) + 1}")

        return cleaned[:expected_count]

    return {
        "one_line_summary": one_line,
        "key_points": normalized_list("key_points", 3, "Key point"),
        "keywords": normalized_list("keywords", 5, "Keyword"),
        "suggested_actions": normalized_list("suggested_actions", 3, "Action"),
    }


def generate_ai_summary(text: str) -> Dict[str, Any]:
    api_key = current_app.config.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    model_name = current_app.config.get("OPENAI_MODEL", "gpt-4o-mini")
    base_url = current_app.config.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    client = OpenAI(api_key=api_key, base_url=base_url)

    system_prompt = (
        "You summarize study materials. Always return strict JSON with keys: "
        "one_line_summary, key_points, keywords, suggested_actions."
    )
    user_prompt = (
        "Summarize the following study material in Chinese. "
        "Return exactly 1 one_line_summary, 3 key_points, 5 keywords, and 3 suggested_actions. "
        "Do not output markdown.\n\n"
        f"CONTENT:\n{text}"
    )

    completion = client.chat.completions.create(
        model=model_name,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    raw_content = completion.choices[0].message.content or "{}"
    parsed_json = json.loads(raw_content)
    return normalize_summary_json(parsed_json)


def process_pdf_summary(summary_job_id: int) -> None:
    with app.app_context():
        max_attempts = max(current_app.config["SUMMARY_MAX_ATTEMPTS"], 1)
        retry_delay = max(current_app.config["SUMMARY_RETRY_DELAY_SECONDS"], 0)

        for attempt in range(1, max_attempts + 1):
            summary_job = db.session.get(SummaryJob, summary_job_id)
            if summary_job is None:
                return

            file_record = summary_job.file
            if file_record is None:
                return

            summary_job.status = JOB_STATUS_RUNNING
            summary_job.started_at = datetime.utcnow()
            summary_job.attempts = attempt
            file_record.summary_status = SUMMARY_STATUS_RUNNING
            db.session.commit()

            try:
                room_slug = file_record.room.slug
                stored_path = get_stored_file_path(room_slug, file_record.stored_name)

                if not os.path.exists(stored_path):
                    raise FileNotFoundError("Uploaded file is missing from storage.")

                extracted_text = extract_pdf_text(stored_path)
                min_chars = current_app.config["SUMMARY_MIN_TEXT_CHARS"]
                if len(extracted_text) < min_chars:
                    raise ValueError(f"Extracted text is too short (< {min_chars} chars).")

                max_chars = current_app.config["SUMMARY_MAX_TEXT_CHARS"]
                cleaned_text = extracted_text[:max_chars]

                summary_json = generate_ai_summary(cleaned_text)

                file_record.summary_status = SUMMARY_STATUS_DONE
                file_record.summary_text = summary_json["one_line_summary"]
                file_record.summary_json = summary_json
                file_record.summary_error = None

                summary_job.status = JOB_STATUS_DONE
                summary_job.error = None
                summary_job.finished_at = datetime.utcnow()
                db.session.commit()
                return
            except Exception as exc:
                error_message = str(exc)
                summary_job.error = error_message
                file_record.summary_error = error_message

                if attempt < max_attempts:
                    summary_job.status = JOB_STATUS_QUEUED
                    summary_job.finished_at = None
                    file_record.summary_status = SUMMARY_STATUS_PENDING
                    db.session.commit()
                    if retry_delay:
                        time.sleep(retry_delay)
                    continue

                summary_job.status = JOB_STATUS_FAILED
                summary_job.finished_at = datetime.utcnow()
                file_record.summary_status = SUMMARY_STATUS_FAILED
                db.session.commit()
                return


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
