import json
import os
import re
import threading
import time
import uuid
import hashlib
import zipfile
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from xml.etree import ElementTree as ET

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
from sqlalchemy import inspect, or_, text
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix


db = SQLAlchemy()

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "pdf", "doc", "docx"}
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
WORD_EXTENSIONS = {"doc", "docx"}
MIME_TYPES = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
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

DISCUSSION_STATUS_IDLE = "idle"
DISCUSSION_STATUS_RUNNING = "running"
DISCUSSION_STATUS_DONE = "done"
DISCUSSION_STATUS_FAILED = "failed"

ONLINE_WINDOW_SECONDS = 90
PRESENCE_HEARTBEAT_SECONDS = 30
DISCUSSION_RECOMPUTE_MIN_SECONDS = 30

discussion_timers_lock = threading.Lock()
discussion_timers: Dict[int, threading.Timer] = {}
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1f\x7f]")


class Room(db.Model):
    __tablename__ = "rooms"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    passcode_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by_ip = db.Column(db.String(64), nullable=True)
    owner_viewer_token = db.Column(db.String(64), nullable=True)
    discussion_ended_at = db.Column(db.DateTime, nullable=True)
    discussion_status = db.Column(db.String(32), nullable=False, default=DISCUSSION_STATUS_IDLE)
    discussion_summary_version = db.Column(db.Integer, nullable=False, default=0)

    files = db.relationship(
        "FileRecord",
        back_populates="room",
        cascade="all, delete-orphan",
        order_by=lambda: FileRecord.created_at.desc(),
    )
    participants = db.relationship(
        "RoomParticipant",
        back_populates="room",
        cascade="all, delete-orphan",
    )
    discussion_summaries = db.relationship(
        "RoomDiscussionSummary",
        back_populates="room",
        cascade="all, delete-orphan",
        order_by=lambda: RoomDiscussionSummary.version.desc(),
    )
    line_threads = db.relationship(
        "PDFLineThread",
        back_populates="room",
        cascade="all, delete-orphan",
    )
    line_comments = db.relationship(
        "PDFLineComment",
        back_populates="room",
        cascade="all, delete-orphan",
    )


class FileRecord(db.Model):
    __tablename__ = "files"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    original_name = db.Column(db.String(255), nullable=False)
    original_name_full = db.Column(db.Text, nullable=True)
    stored_name = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    size_bytes = db.Column(db.BigInteger, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    uploader_ip = db.Column(db.String(64), nullable=True)
    uploader_viewer_token = db.Column(db.String(64), nullable=True, index=True)
    uploader_nickname = db.Column(db.String(40), nullable=True)
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
    comments = db.relationship(
        "FileComment",
        back_populates="file",
        cascade="all, delete-orphan",
        order_by=lambda: FileComment.created_at.asc(),
    )
    stars = db.relationship(
        "FileStar",
        back_populates="file",
        cascade="all, delete-orphan",
    )
    read_states = db.relationship(
        "FileReadState",
        back_populates="file",
        cascade="all, delete-orphan",
    )
    line_threads = db.relationship(
        "PDFLineThread",
        back_populates="file",
        cascade="all, delete-orphan",
        order_by=lambda: PDFLineThread.updated_at.desc(),
    )
    line_comments = db.relationship(
        "PDFLineComment",
        back_populates="file",
        cascade="all, delete-orphan",
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


class FileComment(db.Model):
    __tablename__ = "file_comments"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = db.Column(db.Integer, db.ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    viewer_token = db.Column(db.String(64), nullable=False, index=True)
    nickname = db.Column(db.String(40), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    file = db.relationship("FileRecord", back_populates="comments")


class PDFLineThread(db.Model):
    __tablename__ = "pdf_line_threads"
    __table_args__ = (db.UniqueConstraint("file_id", "page_number", "anchor_hash", name="uq_line_thread_anchor"),)

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = db.Column(db.Integer, db.ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = db.Column(db.Integer, nullable=False)
    quote_text = db.Column(db.Text, nullable=True)
    quote_prefix = db.Column(db.Text, nullable=True)
    quote_suffix = db.Column(db.Text, nullable=True)
    quote_start = db.Column(db.Integer, nullable=True)
    quote_end = db.Column(db.Integer, nullable=True)
    source_type = db.Column(db.String(16), nullable=False, default="pdf")
    anchor_scope = db.Column(db.String(16), nullable=False, default="text")
    segment_key = db.Column(db.String(160), nullable=True)
    segment_start = db.Column(db.Integer, nullable=True)
    segment_end = db.Column(db.Integer, nullable=True)
    anchor_hash = db.Column(db.String(96), nullable=False, index=True)
    created_by_token = db.Column(db.String(64), nullable=False, index=True)
    created_by_nickname = db.Column(db.String(40), nullable=False)
    is_resolved = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    room = db.relationship("Room", back_populates="line_threads")
    file = db.relationship("FileRecord", back_populates="line_threads")
    messages = db.relationship(
        "PDFLineComment",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by=lambda: PDFLineComment.id.asc(),
    )


class PDFLineComment(db.Model):
    __tablename__ = "pdf_line_comments"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = db.Column(db.Integer, db.ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    thread_id = db.Column(db.Integer, db.ForeignKey("pdf_line_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    viewer_token = db.Column(db.String(64), nullable=False, index=True)
    nickname = db.Column(db.String(40), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    edited_at = db.Column(db.DateTime, nullable=True)

    room = db.relationship("Room", back_populates="line_comments")
    file = db.relationship("FileRecord", back_populates="line_comments")
    thread = db.relationship("PDFLineThread", back_populates="messages")


class FileStar(db.Model):
    __tablename__ = "file_stars"
    __table_args__ = (db.UniqueConstraint("file_id", "viewer_token", name="uq_file_star_viewer"),)

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = db.Column(db.Integer, db.ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    viewer_token = db.Column(db.String(64), nullable=False, index=True)
    nickname = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    file = db.relationship("FileRecord", back_populates="stars")


class FileReadState(db.Model):
    __tablename__ = "file_read_states"
    __table_args__ = (db.UniqueConstraint("file_id", "viewer_token", name="uq_file_read_viewer"),)

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = db.Column(db.Integer, db.ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    viewer_token = db.Column(db.String(64), nullable=False, index=True)
    nickname = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_read = db.Column(db.Boolean, nullable=False, default=True)

    file = db.relationship("FileRecord", back_populates="read_states")


class RoomParticipant(db.Model):
    __tablename__ = "room_participants"
    __table_args__ = (db.UniqueConstraint("room_id", "viewer_token", name="uq_room_participant"),)

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    viewer_token = db.Column(db.String(64), nullable=False, index=True)
    nickname = db.Column(db.String(40), nullable=False)
    joined_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_action_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    upload_count = db.Column(db.Integer, nullable=False, default=0)
    comment_count = db.Column(db.Integer, nullable=False, default=0)

    room = db.relationship("Room", back_populates="participants")


class RoomDiscussionSummary(db.Model):
    __tablename__ = "room_discussion_summaries"
    __table_args__ = (db.UniqueConstraint("room_id", "version", name="uq_room_discussion_version"),)

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(32), nullable=False, default=DISCUSSION_STATUS_RUNNING)
    triggered_by_token = db.Column(db.String(64), nullable=True)
    source_last_comment_id = db.Column(db.Integer, nullable=True)
    summary_json = db.Column(db.JSON, nullable=True)
    summary_text = db.Column(db.Text, nullable=True)
    error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    room = db.relationship("Room", back_populates="discussion_summaries")


db.Index("idx_files_room_created_at", FileRecord.room_id, FileRecord.created_at)
db.Index("idx_jobs_file_id", SummaryJob.file_id)
db.Index("idx_file_comments_file_created_at", FileComment.file_id, FileComment.created_at)
db.Index("idx_file_comments_room_created_at", FileComment.room_id, FileComment.created_at)
db.Index("idx_file_stars_room_created_at", FileStar.room_id, FileStar.created_at)
db.Index("idx_file_read_states_room_updated_at", FileReadState.room_id, FileReadState.updated_at)
db.Index("idx_files_room_uploader_created_at", FileRecord.room_id, FileRecord.uploader_viewer_token, FileRecord.created_at)
db.Index("idx_room_participants_room_last_seen_at", RoomParticipant.room_id, RoomParticipant.last_seen_at)
db.Index("idx_room_discussion_summaries_room_updated_at", RoomDiscussionSummary.room_id, RoomDiscussionSummary.updated_at)
db.Index("idx_line_threads_file_page_updated_at", PDFLineThread.file_id, PDFLineThread.page_number, PDFLineThread.updated_at)
db.Index(
    "idx_line_threads_file_source_segment_anchor",
    PDFLineThread.file_id,
    PDFLineThread.source_type,
    PDFLineThread.segment_key,
    PDFLineThread.anchor_hash,
)
db.Index("idx_line_comments_thread_id", PDFLineComment.thread_id, PDFLineComment.id)
db.Index("idx_line_comments_room_file_id", PDFLineComment.room_id, PDFLineComment.file_id, PDFLineComment.id)


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
        DISCUSSION_RECOMPUTE_MIN_SECONDS=int(os.getenv("DISCUSSION_RECOMPUTE_MIN_SECONDS", str(DISCUSSION_RECOMPUTE_MIN_SECONDS))),
        ONLINE_WINDOW_SECONDS=int(os.getenv("ONLINE_WINDOW_SECONDS", str(ONLINE_WINDOW_SECONDS))),
        PRESENCE_HEARTBEAT_SECONDS=int(os.getenv("PRESENCE_HEARTBEAT_SECONDS", str(PRESENCE_HEARTBEAT_SECONDS))),
        DISCUSSION_ASYNC=os.getenv("DISCUSSION_ASYNC", "1") != "0",
        DEFAULT_ROOM_SLUG=os.getenv("DEFAULT_ROOM_SLUG", "demo"),
        DEFAULT_ROOM_NAME=os.getenv("DEFAULT_ROOM_NAME", "Demo Room"),
        DEFAULT_ROOM_PASSCODE=os.getenv("DEFAULT_ROOM_PASSCODE", "demo1234"),
        PASSWORD_HASH_METHOD=os.getenv("PASSWORD_HASH_METHOD", "scrypt"),
        PASSWORD_HASH_FALLBACK_METHOD=os.getenv("PASSWORD_HASH_FALLBACK_METHOD", "pbkdf2:sha256:600000"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    if test_config:
        app.config.update(test_config)

    # Respect X-Forwarded-* headers behind reverse proxies (Railway, etc.).
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)  # type: ignore[assignment]

    db.init_app(app)

    register_error_handlers(app)
    register_routes(app)

    with app.app_context():
        os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
        db.create_all()
        upgrade_schema_for_existing_databases()
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

        owner_viewer_token = ensure_room_viewer_token(room_slug)
        room = Room(
            name=room_name,
            slug=room_slug,
            passcode_hash=hash_passcode(passcode),
            created_by_ip=get_client_ip(),
            owner_viewer_token=owner_viewer_token,
            discussion_status=DISCUSSION_STATUS_IDLE,
            discussion_summary_version=0,
        )
        db.session.add(room)
        db.session.commit()

        mark_room_authorized(room.slug)
        upsert_room_participant(
            room=room,
            viewer_token=owner_viewer_token,
            nickname=get_room_viewer_nickname(room_slug),
            action="create_room",
        )
        write_access_log(room_id=room.id, action="create_room")

        share_url = request.host_url.rstrip("/") + url_for("room_page", room_slug=room.slug)

        return jsonify(
            {
                "success": True,
                "room": serialize_room(room),
                "share_url": share_url,
                "discussion": serialize_discussion_state(room),
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
        viewer_token = ensure_room_viewer_token(room.slug)
        ensure_room_owner_binding(room, viewer_token)
        upsert_room_participant(
            room=room,
            viewer_token=viewer_token,
            nickname=get_room_viewer_nickname(room.slug),
            action="auth_room",
        )
        write_access_log(room_id=room.id, action="auth_room")

        return jsonify({"success": True, "room": serialize_room(room)})

    @app.get("/api/rooms/<room_slug>/profile")
    def get_room_profile_api(room_slug: str) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        viewer_token = get_room_viewer_token(room_slug)
        viewer_nickname = get_room_viewer_nickname(room_slug)
        ensure_room_owner_binding(room, viewer_token)
        upsert_room_participant(
            room=room,
            viewer_token=viewer_token,
            nickname=viewer_nickname,
            action="get_profile",
        )
        return jsonify(
            {
                "success": True,
                "room": serialize_room(room),
                "viewer": {
                    "has_profile": bool(viewer_nickname),
                    "nickname": viewer_nickname,
                    "viewer_token": viewer_token,
                    "is_owner": bool(viewer_token and room.owner_viewer_token == viewer_token),
                },
                "discussion": serialize_discussion_state(room),
            }
        )

    @app.post("/api/rooms/<room_slug>/profile")
    def upsert_room_profile_api(room_slug: str) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        data = request.get_json(silent=True) or {}
        nickname = str(data.get("nickname") or "").strip()

        if len(nickname) < 2 or len(nickname) > 20:
            return jsonify({"success": False, "message": "Nickname must be between 2 and 20 characters."}), 400

        viewer_token = ensure_room_viewer_token(room_slug)
        ensure_room_owner_binding(room, viewer_token)
        set_room_viewer_nickname(room_slug, nickname)
        upsert_room_participant(room=room, viewer_token=viewer_token, nickname=nickname, action="set_profile")
        write_access_log(room_id=room.id, action="set_profile")

        return jsonify(
            {
                "success": True,
                "viewer": {
                    "nickname": nickname,
                    "viewer_token": "session-scoped",
                    "is_owner": bool(room.owner_viewer_token and viewer_token == room.owner_viewer_token),
                },
                "discussion": serialize_discussion_state(room),
            }
        )

    @app.post("/api/rooms/<room_slug>/upload")
    def upload_to_room_api(room_slug: str) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        return handle_file_upload(room=room, deprecated=False, bypass_auth=False, require_profile=True)

    @app.get("/api/rooms/<room_slug>/files")
    def list_room_files_api(room_slug: str) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        viewer_token = get_room_viewer_token(room_slug)
        ensure_room_owner_binding(room, viewer_token)
        viewer_nickname = get_room_viewer_nickname(room_slug)
        uploader_token = (request.args.get("uploader_token") or "").strip() or None
        file_type = (request.args.get("file_type") or "all").strip().lower()
        if file_type not in {"all", "image", "pdf", "doc", "docx", "word"}:
            file_type = "all"
        selected_file_id_raw = (request.args.get("selected_file_id") or "").strip()
        selected_file_id = int(selected_file_id_raw) if selected_file_id_raw.isdigit() else None

        query = FileRecord.query.filter_by(room_id=room.id)
        if uploader_token:
            query = query.filter(FileRecord.uploader_viewer_token == uploader_token)

        room_files = query.order_by(FileRecord.created_at.desc(), FileRecord.id.desc()).all()
        filtered_files = []
        for file_record in room_files:
            extension = get_extension(file_record.stored_name)
            current_type = get_file_type_from_extension(extension)
            if file_type == "word" and current_type not in WORD_EXTENSIONS:
                continue
            if file_type != "all" and file_type != "word" and current_type != file_type:
                continue
            filtered_files.append(file_record)

        serialized_files = [serialize_file(file_record, viewer_token=viewer_token) for file_record in filtered_files]
        starred_files = sum(1 for file_record in serialized_files if file_record["collab"]["starred_by_me"])
        unread_files = sum(1 for file_record in serialized_files if not file_record["collab"]["read_by_me"])

        return jsonify(
            {
                "success": True,
                "room": serialize_room(room),
                "viewer": {
                    "has_profile": bool(viewer_nickname),
                    "nickname": viewer_nickname,
                    "viewer_token": viewer_token,
                },
                "metrics": {
                    "total_files": len(serialized_files),
                    "starred_files": starred_files,
                    "unread_files": unread_files,
                },
                "discussion": serialize_discussion_state(room),
                "filters": {
                    "uploader_token": uploader_token,
                    "file_type": file_type,
                    "selected_file_id": selected_file_id,
                },
                "files": serialized_files,
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

        viewer_token = get_room_viewer_token(room_slug)
        return jsonify(
            {
                "success": True,
                "job": serialize_job(summary_job),
                "file": serialize_file(summary_job.file, viewer_token=viewer_token),
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

    @app.post("/api/rooms/<room_slug>/presence")
    def report_room_presence_api(room_slug: str) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        viewer_token = ensure_room_viewer_token(room_slug)
        viewer_nickname = get_room_viewer_nickname(room_slug)
        participant = upsert_room_participant(
            room=room,
            viewer_token=viewer_token,
            nickname=viewer_nickname,
            action="presence",
        )

        return jsonify(
            {
                "success": True,
                "presence": {
                    "viewer_token": viewer_token,
                    "nickname": viewer_nickname,
                    "last_seen_at": participant.last_seen_at.isoformat() + "Z",
                    "heartbeat_seconds": current_app.config["PRESENCE_HEARTBEAT_SECONDS"],
                },
            }
        )

    @app.get("/api/rooms/<room_slug>/collaborators")
    def list_room_collaborators_api(room_slug: str) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        viewer_token = get_room_viewer_token(room_slug)
        participants = RoomParticipant.query.filter_by(room_id=room.id).all()
        collaborators = [serialize_participant(room.id, participant, viewer_token) for participant in participants]

        def iso_to_epoch(value: Optional[str]) -> float:
            if not value:
                return 0.0
            normalized = value.replace("Z", "")
            try:
                return datetime.fromisoformat(normalized).timestamp()
            except Exception:
                return 0.0

        def sort_key(item: Dict[str, Any]):
            uploaded_first = 0 if item["upload_count"] > 0 else 1
            online_first = 0 if item["is_online"] else 1
            last_action = iso_to_epoch(item.get("last_action_at"))
            return (uploaded_first, online_first, -last_action, item["nickname"].lower())

        collaborators.sort(key=sort_key)
        return jsonify(
            {
                "success": True,
                "room": serialize_room(room),
                "viewer_token": viewer_token,
                "collaborators": collaborators,
            }
        )

    @app.get("/api/rooms/<room_slug>/files/<int:file_id>/comments")
    def list_file_comments_api(room_slug: str, file_id: int) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        file_record = FileRecord.query.filter_by(id=file_id, room_id=room.id).first()
        if file_record is None:
            return jsonify({"success": False, "message": "File not found."}), 404

        after_id_raw = (request.args.get("after_id") or "").strip()
        after_id = int(after_id_raw) if after_id_raw.isdigit() else None

        query = FileComment.query.filter_by(room_id=room.id, file_id=file_id)
        if after_id is not None:
            comments = query.filter(FileComment.id > after_id).order_by(FileComment.id.asc()).all()
            next_after_id = comments[-1].id if comments else after_id
        else:
            latest_comments = query.order_by(FileComment.created_at.desc(), FileComment.id.desc()).limit(50).all()
            comments = list(reversed(latest_comments))
            next_after_id = comments[-1].id if comments else 0

        return jsonify(
            {
                "success": True,
                "comments": [serialize_comment(comment) for comment in comments],
                "cursor": {"after_id": next_after_id},
            }
        )

    @app.post("/api/rooms/<room_slug>/files/<int:file_id>/comments")
    def create_file_comment_api(room_slug: str, file_id: int) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        file_record = FileRecord.query.filter_by(id=file_id, room_id=room.id).first()
        if file_record is None:
            return jsonify({"success": False, "message": "File not found."}), 404

        viewer_token = get_room_viewer_token(room_slug)
        viewer_nickname = get_room_viewer_nickname(room_slug)
        if not viewer_token or not viewer_nickname:
            return jsonify({"success": False, "message": "Please set your nickname before commenting."}), 400

        data = request.get_json(silent=True) or {}
        content = str(data.get("content") or "").strip()
        if not content:
            return jsonify({"success": False, "message": "Comment cannot be empty."}), 400
        if len(content) > 300:
            return jsonify({"success": False, "message": "Comment is too long (max 300 characters)."}), 400

        comment = FileComment(
            room_id=room.id,
            file_id=file_id,
            viewer_token=viewer_token,
            nickname=viewer_nickname,
            content=content,
        )
        db.session.add(comment)
        db.session.commit()

        upsert_room_participant(
            room=room,
            viewer_token=viewer_token,
            nickname=viewer_nickname,
            action="add_comment",
            increment_comment=1,
        )
        maybe_queue_discussion_summary(room=room, triggered_by_token=viewer_token)
        write_access_log(room_id=room.id, action="add_comment", file_id=file_id)
        return jsonify({"success": True, "comment": serialize_comment(comment)})

    @app.get("/api/rooms/<room_slug>/files/<int:file_id>/line-threads")
    def list_pdf_line_threads_api(room_slug: str, file_id: int) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        file_record = FileRecord.query.filter_by(id=file_id, room_id=room.id).first()
        if file_record is None:
            return jsonify({"success": False, "message": "File not found."}), 404
        extension = get_extension(file_record.stored_name)
        file_type = get_file_type_from_extension(extension)
        if file_type not in {"pdf", "docx", "doc"}:
            return jsonify({"success": False, "message": "Line comments are only available for PDF and Word files."}), 400

        viewer_token = get_room_viewer_token(room_slug)
        page_raw = (request.args.get("page") or "").strip()
        page_number = int(page_raw) if page_raw.isdigit() else None
        if page_raw and (page_number is None or page_number <= 0):
            return jsonify({"success": False, "message": "Query parameter 'page' must be a positive integer."}), 400
        segment_key = (request.args.get("segment_key") or "").strip() or None

        query = PDFLineThread.query.filter_by(room_id=room.id, file_id=file_id)
        if page_number is not None:
            query = query.filter(PDFLineThread.page_number == page_number)
        if segment_key is not None:
            query = query.filter(PDFLineThread.segment_key == segment_key)

        if page_number is None and segment_key is None:
            threads = query.order_by(PDFLineThread.updated_at.desc(), PDFLineThread.id.desc()).limit(100).all()
        else:
            threads = query.order_by(PDFLineThread.updated_at.desc(), PDFLineThread.id.desc()).all()

        return jsonify(
            {
                "success": True,
                "file": serialize_file(file_record, viewer_token=viewer_token),
                "page_number": page_number,
                "segment_key": segment_key,
                "source_type": file_type,
                "threads": [serialize_line_thread(thread, viewer_token) for thread in threads],
            }
        )

    @app.post("/api/rooms/<room_slug>/files/<int:file_id>/line-threads")
    def create_pdf_line_thread_api(room_slug: str, file_id: int) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        file_record = FileRecord.query.filter_by(id=file_id, room_id=room.id).first()
        if file_record is None:
            return jsonify({"success": False, "message": "File not found."}), 404
        extension = get_extension(file_record.stored_name)
        file_type = get_file_type_from_extension(extension)
        if file_type not in {"pdf", "docx", "doc"}:
            return jsonify({"success": False, "message": "Line comments are only available for PDF and DOCX files."}), 400
        if file_type == "doc":
            return jsonify({"success": False, "message": "`.doc` 请先转换为 `.docx` 后再进行划线评论。"}), 400

        viewer_token = get_room_viewer_token(room_slug)
        viewer_nickname = get_room_viewer_nickname(room_slug)
        if not viewer_token or not viewer_nickname:
            return jsonify({"success": False, "message": "Please set your nickname before commenting."}), 400

        data = request.get_json(silent=True) or {}
        content = str(data.get("content") or "").strip()
        if not content:
            return jsonify({"success": False, "message": "Comment cannot be empty."}), 400
        if len(content) > 300:
            return jsonify({"success": False, "message": "Comment is too long (max 300 characters)."}), 400

        source_type = file_type
        anchor_scope_raw = str(data.get("anchor_scope") or "").strip().lower()
        anchor_scope = anchor_scope_raw or ("segment" if file_type == "docx" else "text")
        if anchor_scope not in {"text", "page", "segment"}:
            anchor_scope = "text" if file_type == "pdf" else "segment"
        if file_type == "pdf" and anchor_scope == "segment":
            anchor_scope = "text"
        if file_type == "docx" and anchor_scope == "page":
            anchor_scope = "segment"

        page_raw = data.get("page_number")
        try:
            page_number = int(page_raw)
        except Exception:
            page_number = 0
        if file_type == "pdf" and page_number <= 0:
            return jsonify({"success": False, "message": "Field 'page_number' must be a positive integer."}), 400
        if file_type == "docx" and page_number <= 0:
            page_number = 1

        quote_text = sanitize_line_quote_fragment(data.get("quote_text"))
        quote_prefix = sanitize_line_quote_fragment(data.get("quote_prefix"), max_length=120)
        quote_suffix = sanitize_line_quote_fragment(data.get("quote_suffix"), max_length=120)

        quote_start = data.get("quote_start")
        quote_end = data.get("quote_end")
        quote_start_int: Optional[int]
        quote_end_int: Optional[int]
        try:
            quote_start_int = int(quote_start) if quote_start is not None else None
        except Exception:
            quote_start_int = None
        try:
            quote_end_int = int(quote_end) if quote_end is not None else None
        except Exception:
            quote_end_int = None

        segment_key = str(data.get("segment_key") or "").strip()
        if file_type == "docx" and anchor_scope == "segment" and not segment_key:
            return jsonify({"success": False, "message": "Field 'segment_key' is required for DOCX segment comments."}), 400

        segment_start_raw = data.get("segment_start")
        segment_end_raw = data.get("segment_end")
        try:
            segment_start = int(segment_start_raw) if segment_start_raw is not None else None
        except Exception:
            segment_start = None
        try:
            segment_end = int(segment_end_raw) if segment_end_raw is not None else None
        except Exception:
            segment_end = None
        if segment_start is not None and segment_end is not None and segment_end <= segment_start:
            return jsonify({"success": False, "message": "Field 'segment_end' must be greater than 'segment_start'."}), 400

        anchor_hash = compute_line_anchor_hash(
            page_number=page_number,
            quote_text=quote_text,
            quote_prefix=quote_prefix,
            quote_suffix=quote_suffix,
            quote_start=quote_start_int,
            quote_end=quote_end_int,
            source_type=source_type,
            anchor_scope=anchor_scope,
            segment_key=segment_key,
            segment_start=segment_start,
            segment_end=segment_end,
        )

        existing_thread = PDFLineThread.query.filter_by(
            room_id=room.id,
            file_id=file_id,
            page_number=page_number,
            anchor_hash=anchor_hash,
        ).first()

        created_new_thread = False
        if existing_thread is None:
            existing_thread = PDFLineThread(
                room_id=room.id,
                file_id=file_id,
                page_number=page_number,
                quote_text=quote_text,
                quote_prefix=quote_prefix,
                quote_suffix=quote_suffix,
                quote_start=quote_start_int,
                quote_end=quote_end_int,
                source_type=source_type,
                anchor_scope=anchor_scope,
                segment_key=segment_key or None,
                segment_start=segment_start,
                segment_end=segment_end,
                anchor_hash=anchor_hash,
                created_by_token=viewer_token,
                created_by_nickname=viewer_nickname,
                is_resolved=False,
            )
            db.session.add(existing_thread)
            db.session.flush()
            created_new_thread = True

        message = PDFLineComment(
            room_id=room.id,
            file_id=file_id,
            thread_id=existing_thread.id,
            viewer_token=viewer_token,
            nickname=viewer_nickname,
            content=content,
            is_deleted=False,
        )
        existing_thread.updated_at = datetime.utcnow()
        db.session.add(message)
        db.session.commit()

        upsert_room_participant(
            room=room,
            viewer_token=viewer_token,
            nickname=viewer_nickname,
            action="add_line_comment",
            increment_comment=1,
        )
        maybe_queue_discussion_summary(room=room, triggered_by_token=viewer_token)
        write_access_log(room_id=room.id, action="add_line_comment", file_id=file_id)

        return jsonify(
            {
                "success": True,
                "created_new_thread": created_new_thread,
                "thread": serialize_line_thread(existing_thread, viewer_token),
                "comment": serialize_line_comment(message, viewer_token),
            }
        )

    @app.post("/api/rooms/<room_slug>/line-threads/<int:thread_id>/messages")
    def create_pdf_line_message_api(room_slug: str, thread_id: int) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        thread = PDFLineThread.query.filter_by(id=thread_id, room_id=room.id).first()
        if thread is None:
            return jsonify({"success": False, "message": "Line thread not found."}), 404

        viewer_token = get_room_viewer_token(room_slug)
        viewer_nickname = get_room_viewer_nickname(room_slug)
        if not viewer_token or not viewer_nickname:
            return jsonify({"success": False, "message": "Please set your nickname before replying."}), 400

        data = request.get_json(silent=True) or {}
        content = str(data.get("content") or "").strip()
        if not content:
            return jsonify({"success": False, "message": "Comment cannot be empty."}), 400
        if len(content) > 300:
            return jsonify({"success": False, "message": "Comment is too long (max 300 characters)."}), 400

        message = PDFLineComment(
            room_id=room.id,
            file_id=thread.file_id,
            thread_id=thread.id,
            viewer_token=viewer_token,
            nickname=viewer_nickname,
            content=content,
            is_deleted=False,
        )
        thread.updated_at = datetime.utcnow()
        db.session.add(message)
        db.session.commit()

        upsert_room_participant(
            room=room,
            viewer_token=viewer_token,
            nickname=viewer_nickname,
            action="reply_line_comment",
            increment_comment=1,
        )
        maybe_queue_discussion_summary(room=room, triggered_by_token=viewer_token)
        write_access_log(room_id=room.id, action="reply_line_comment", file_id=thread.file_id)

        return jsonify(
            {
                "success": True,
                "thread": serialize_line_thread(thread, viewer_token),
                "comment": serialize_line_comment(message, viewer_token),
            }
        )

    @app.patch("/api/rooms/<room_slug>/line-comments/<int:comment_id>")
    def edit_pdf_line_comment_api(room_slug: str, comment_id: int) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        comment = PDFLineComment.query.filter_by(id=comment_id, room_id=room.id).first()
        if comment is None:
            return jsonify({"success": False, "message": "Line comment not found."}), 404

        viewer_token = get_room_viewer_token(room_slug)
        if not viewer_token or comment.viewer_token != viewer_token:
            return jsonify({"success": False, "message": "Only the comment author can edit this comment."}), 403
        if comment.is_deleted:
            return jsonify({"success": False, "message": "Deleted comments cannot be edited."}), 400

        data = request.get_json(silent=True) or {}
        content = str(data.get("content") or "").strip()
        if not content:
            return jsonify({"success": False, "message": "Comment cannot be empty."}), 400
        if len(content) > 300:
            return jsonify({"success": False, "message": "Comment is too long (max 300 characters)."}), 400

        comment.content = content
        comment.edited_at = datetime.utcnow()
        comment.updated_at = datetime.utcnow()
        if comment.thread is not None:
            comment.thread.updated_at = datetime.utcnow()
        db.session.commit()

        maybe_queue_discussion_summary(room=room, triggered_by_token=viewer_token)
        write_access_log(room_id=room.id, action="edit_line_comment", file_id=comment.file_id)
        return jsonify({"success": True, "comment": serialize_line_comment(comment, viewer_token)})

    @app.delete("/api/rooms/<room_slug>/line-comments/<int:comment_id>")
    def delete_pdf_line_comment_api(room_slug: str, comment_id: int) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        comment = PDFLineComment.query.filter_by(id=comment_id, room_id=room.id).first()
        if comment is None:
            return jsonify({"success": False, "message": "Line comment not found."}), 404

        viewer_token = get_room_viewer_token(room_slug)
        if not viewer_token or comment.viewer_token != viewer_token:
            return jsonify({"success": False, "message": "Only the comment author can delete this comment."}), 403

        if not comment.is_deleted:
            comment.is_deleted = True
            comment.updated_at = datetime.utcnow()
            if comment.thread is not None:
                comment.thread.updated_at = datetime.utcnow()
            db.session.commit()

            maybe_queue_discussion_summary(room=room, triggered_by_token=viewer_token)
            write_access_log(room_id=room.id, action="delete_line_comment", file_id=comment.file_id)

        return jsonify({"success": True, "comment": serialize_line_comment(comment, viewer_token)})

    @app.put("/api/rooms/<room_slug>/files/<int:file_id>/star")
    def toggle_file_star_api(room_slug: str, file_id: int) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        file_record = FileRecord.query.filter_by(id=file_id, room_id=room.id).first()
        if file_record is None:
            return jsonify({"success": False, "message": "File not found."}), 404

        viewer_token = get_room_viewer_token(room_slug)
        viewer_nickname = get_room_viewer_nickname(room_slug)
        if not viewer_token or not viewer_nickname:
            return jsonify({"success": False, "message": "Please set your nickname before starring files."}), 400

        data = request.get_json(silent=True) or {}
        starred = data.get("starred")
        if not isinstance(starred, bool):
            return jsonify({"success": False, "message": "Field 'starred' must be boolean."}), 400

        existing_star = FileStar.query.filter_by(file_id=file_id, viewer_token=viewer_token).first()
        if starred and existing_star is None:
            db.session.add(
                FileStar(
                    room_id=room.id,
                    file_id=file_id,
                    viewer_token=viewer_token,
                    nickname=viewer_nickname,
                )
            )
        elif not starred and existing_star is not None:
            db.session.delete(existing_star)
        elif existing_star is not None:
            existing_star.nickname = viewer_nickname

        db.session.commit()
        upsert_room_participant(
            room=room,
            viewer_token=viewer_token,
            nickname=viewer_nickname,
            action="star_file" if starred else "unstar_file",
        )
        write_access_log(room_id=room.id, action="star_file" if starred else "unstar_file", file_id=file_id)

        return jsonify(
            {
                "success": True,
                "collab": build_file_collab(file_record.id, viewer_token),
            }
        )

    @app.put("/api/rooms/<room_slug>/files/<int:file_id>/read")
    def toggle_file_read_api(room_slug: str, file_id: int) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        file_record = FileRecord.query.filter_by(id=file_id, room_id=room.id).first()
        if file_record is None:
            return jsonify({"success": False, "message": "File not found."}), 404

        viewer_token = get_room_viewer_token(room_slug)
        viewer_nickname = get_room_viewer_nickname(room_slug)
        if not viewer_token or not viewer_nickname:
            return jsonify({"success": False, "message": "Please set your nickname before changing read status."}), 400

        data = request.get_json(silent=True) or {}
        read_value = data.get("read")
        if not isinstance(read_value, bool):
            return jsonify({"success": False, "message": "Field 'read' must be boolean."}), 400

        existing_state = FileReadState.query.filter_by(file_id=file_id, viewer_token=viewer_token).first()
        if existing_state is None:
            existing_state = FileReadState(
                room_id=room.id,
                file_id=file_id,
                viewer_token=viewer_token,
                nickname=viewer_nickname,
                is_read=read_value,
            )
            db.session.add(existing_state)
        else:
            existing_state.is_read = read_value
            existing_state.nickname = viewer_nickname
            existing_state.updated_at = datetime.utcnow()

        db.session.commit()
        upsert_room_participant(
            room=room,
            viewer_token=viewer_token,
            nickname=viewer_nickname,
            action="mark_read" if read_value else "mark_unread",
        )
        write_access_log(room_id=room.id, action="mark_read" if read_value else "mark_unread", file_id=file_id)

        return jsonify(
            {
                "success": True,
                "collab": build_file_collab(file_record.id, viewer_token),
            }
        )

    @app.post("/api/rooms/<room_slug>/discussion/end")
    def end_room_discussion_api(room_slug: str) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        viewer_token = get_room_viewer_token(room_slug)
        ensure_room_owner_binding(room, viewer_token)
        if not viewer_token or room.owner_viewer_token != viewer_token:
            return jsonify({"success": False, "message": "Only the room owner can end discussion."}), 403

        room.discussion_ended_at = datetime.utcnow()
        room.discussion_status = DISCUSSION_STATUS_RUNNING
        db.session.commit()

        upsert_room_participant(
            room=room,
            viewer_token=viewer_token,
            nickname=get_room_viewer_nickname(room_slug),
            action="end_discussion",
        )
        maybe_queue_discussion_summary(room=room, triggered_by_token=viewer_token, force=True)
        write_access_log(room_id=room.id, action="discussion_end")
        return jsonify({"success": True, "discussion": serialize_discussion_state(room)})

    @app.get("/api/rooms/<room_slug>/discussion/summary")
    def get_room_discussion_summary_api(room_slug: str) -> Any:
        room, error_response = get_room_for_api(room_slug, require_auth=True)
        if error_response:
            return error_response

        latest_summary = (
            RoomDiscussionSummary.query.filter_by(room_id=room.id)
            .order_by(RoomDiscussionSummary.version.desc())
            .first()
        )
        if latest_summary is not None and isinstance(latest_summary.summary_json, dict):
            normalized_summary_json = normalize_discussion_summary_payload(latest_summary.summary_json)
            if normalized_summary_json != latest_summary.summary_json:
                latest_summary.summary_json = normalized_summary_json
                latest_summary.summary_text = json.dumps(normalized_summary_json, ensure_ascii=False)
                latest_summary.updated_at = datetime.utcnow()
                db.session.commit()
        return jsonify(
            {
                "success": True,
                "discussion": serialize_discussion_state(room),
                "summary": serialize_discussion_summary(latest_summary),
            }
        )

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
                    FileRecord.original_name_full == filename,
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
        return handle_file_upload(room=default_room, deprecated=True, bypass_auth=True, require_profile=False)

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


def get_file_type_from_extension(extension: str) -> str:
    ext = (extension or "").lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext == "pdf":
        return "pdf"
    if ext == "docx":
        return "docx"
    if ext == "doc":
        return "doc"
    return "other"


def sanitize_original_filename(raw_filename: str, extension: str) -> str:
    normalized = str(raw_filename or "").replace("\\", "/").strip()
    basename = normalized.rsplit("/", 1)[-1]
    cleaned = CONTROL_CHAR_PATTERN.sub("", basename).strip()
    if cleaned:
        return cleaned
    suffix = f".{extension}" if extension else ""
    return f"file-{uuid.uuid4().hex}{suffix}"


def sanitize_line_quote_fragment(raw_text: Any, max_length: Optional[int] = None) -> str:
    text = str(raw_text or "")
    text = CONTROL_CHAR_PATTERN.sub("", text)
    text = text.replace("\ufffd", "").replace("\ufeff", "")
    text = re.sub(r"\s+", " ", text).strip()
    if max_length is not None:
        text = text[:max_length]
    return text


def get_file_original_name(file_record: FileRecord) -> str:
    candidate = (file_record.original_name_full or file_record.original_name or "").strip()
    if candidate:
        return candidate
    return file_record.stored_name


def compute_line_anchor_hash(
    page_number: int,
    quote_text: str,
    quote_prefix: str = "",
    quote_suffix: str = "",
    quote_start: Optional[int] = None,
    quote_end: Optional[int] = None,
    source_type: str = "pdf",
    anchor_scope: str = "text",
    segment_key: str = "",
    segment_start: Optional[int] = None,
    segment_end: Optional[int] = None,
) -> str:
    normalized_quote_text = sanitize_line_quote_fragment(quote_text)
    normalized_quote_prefix = sanitize_line_quote_fragment(quote_prefix)
    normalized_quote_suffix = sanitize_line_quote_fragment(quote_suffix)
    payload = "|".join(
        [
            (source_type or "pdf").strip().lower(),
            (anchor_scope or "text").strip().lower(),
            str(max(page_number, 1)),
            normalized_quote_text,
            normalized_quote_prefix,
            normalized_quote_suffix,
            str(-1 if quote_start is None else int(quote_start)),
            str(-1 if quote_end is None else int(quote_end)),
            (segment_key or "").strip(),
            str(-1 if segment_start is None else int(segment_start)),
            str(-1 if segment_end is None else int(segment_end)),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_client_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.remote_addr or "unknown"


def room_session_key(room_slug: str) -> str:
    return f"room_auth::{room_slug}"


def room_viewer_token_session_key(room_slug: str) -> str:
    return f"room_viewer::{room_slug}::token"


def room_viewer_nickname_session_key(room_slug: str) -> str:
    return f"room_viewer::{room_slug}::nickname"


def is_room_authorized(room_slug: str) -> bool:
    return bool(session.get(room_session_key(room_slug)))


def mark_room_authorized(room_slug: str) -> None:
    session[room_session_key(room_slug)] = True
    session.modified = True


def get_room_viewer_token(room_slug: str) -> Optional[str]:
    token = session.get(room_viewer_token_session_key(room_slug))
    if not token:
        return None
    return str(token)


def ensure_room_viewer_token(room_slug: str) -> str:
    existing_token = get_room_viewer_token(room_slug)
    if existing_token:
        return existing_token

    token = uuid.uuid4().hex
    session[room_viewer_token_session_key(room_slug)] = token
    session.modified = True
    return token


def ensure_room_owner_binding(room: Room, viewer_token: Optional[str]) -> bool:
    if not viewer_token:
        return False
    if room.owner_viewer_token == viewer_token:
        return True

    if not room.owner_viewer_token:
        room.owner_viewer_token = viewer_token
        db.session.commit()
        return True

    creator_ip = (room.created_by_ip or "").strip()
    requester_ip = get_client_ip().strip()
    if creator_ip and creator_ip not in {"unknown", "system"} and requester_ip and requester_ip == creator_ip:
        owner_participant = RoomParticipant.query.filter_by(
            room_id=room.id, viewer_token=room.owner_viewer_token
        ).first()
        owner_nickname = (owner_participant.nickname or "").strip() if owner_participant else ""
        viewer_nickname = get_room_viewer_nickname(room.slug)
        if owner_nickname and owner_nickname != viewer_nickname:
            return False
        room.owner_viewer_token = viewer_token
        db.session.commit()
        return True

    return False


def get_room_viewer_nickname(room_slug: str) -> str:
    nickname = session.get(room_viewer_nickname_session_key(room_slug))
    if not nickname:
        return ""
    return str(nickname).strip()


def set_room_viewer_nickname(room_slug: str, nickname: str) -> None:
    session[room_viewer_nickname_session_key(room_slug)] = nickname.strip()
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
    return url_for("uploaded_file", room_slug=room_slug, stored_name=stored_name)


def build_room_file_absolute_url(room_slug: str, stored_name: str) -> str:
    return request.host_url.rstrip("/") + url_for("uploaded_file", room_slug=room_slug, stored_name=stored_name)


def build_legacy_file_url(stored_name: str) -> str:
    return request.host_url.rstrip("/") + f"/uploads/{stored_name}"


def hash_passcode(passcode: str) -> str:
    method = str(current_app.config.get("PASSWORD_HASH_METHOD", "scrypt") or "scrypt").strip()
    fallback_method = str(
        current_app.config.get("PASSWORD_HASH_FALLBACK_METHOD", "pbkdf2:sha256:600000")
        or "pbkdf2:sha256:600000"
    ).strip()
    try:
        return generate_password_hash(passcode, method=method)
    except (ValueError, TypeError, MemoryError) as exc:
        if fallback_method and fallback_method != method:
            current_app.logger.warning(
                "password hash method fallback: primary=%s fallback=%s reason=%s",
                method,
                fallback_method,
                exc,
            )
            return generate_password_hash(passcode, method=fallback_method)
        raise


def serialize_room(room: Room) -> Dict[str, Any]:
    return {
        "id": room.id,
        "slug": room.slug,
        "name": room.name,
        "created_at": room.created_at.isoformat() + "Z",
        "discussion_status": room.discussion_status,
        "discussion_ended_at": room.discussion_ended_at.isoformat() + "Z" if room.discussion_ended_at else None,
        "discussion_summary_version": room.discussion_summary_version,
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


def serialize_discussion_state(room: Room) -> Dict[str, Any]:
    viewer_token = get_room_viewer_token(room.slug)
    return {
        "status": room.discussion_status,
        "ended_at": room.discussion_ended_at.isoformat() + "Z" if room.discussion_ended_at else None,
        "summary_version": room.discussion_summary_version,
        "is_owner": bool(viewer_token and room.owner_viewer_token and viewer_token == room.owner_viewer_token),
        "owner_bound": bool(room.owner_viewer_token),
    }


def serialize_discussion_summary(summary: Optional[RoomDiscussionSummary]) -> Optional[Dict[str, Any]]:
    if summary is None:
        return None

    return {
        "id": summary.id,
        "version": summary.version,
        "status": summary.status,
        "triggered_by_token": summary.triggered_by_token,
        "source_last_comment_id": summary.source_last_comment_id,
        "summary_json": summary.summary_json,
        "summary_text": summary.summary_text,
        "error": summary.error,
        "created_at": summary.created_at.isoformat() + "Z" if summary.created_at else None,
        "updated_at": summary.updated_at.isoformat() + "Z" if summary.updated_at else None,
    }


def serialize_comment(comment: FileComment) -> Dict[str, Any]:
    return {
        "id": comment.id,
        "room_id": comment.room_id,
        "file_id": comment.file_id,
        "nickname": comment.nickname,
        "content": comment.content,
        "created_at": comment.created_at.isoformat() + "Z",
    }


def serialize_line_comment(comment: PDFLineComment, viewer_token: Optional[str]) -> Dict[str, Any]:
    display_content = "[评论已删除]" if comment.is_deleted else comment.content
    return {
        "id": comment.id,
        "room_id": comment.room_id,
        "file_id": comment.file_id,
        "thread_id": comment.thread_id,
        "nickname": comment.nickname,
        "content": display_content,
        "raw_content": comment.content,
        "is_deleted": comment.is_deleted,
        "is_mine": bool(viewer_token and comment.viewer_token == viewer_token),
        "created_at": comment.created_at.isoformat() + "Z" if comment.created_at else None,
        "updated_at": comment.updated_at.isoformat() + "Z" if comment.updated_at else None,
        "edited_at": comment.edited_at.isoformat() + "Z" if comment.edited_at else None,
    }


def serialize_line_thread(thread: PDFLineThread, viewer_token: Optional[str]) -> Dict[str, Any]:
    messages = [serialize_line_comment(item, viewer_token) for item in thread.messages]
    return {
        "id": thread.id,
        "room_id": thread.room_id,
        "file_id": thread.file_id,
        "source_type": (thread.source_type or "pdf").lower(),
        "anchor_scope": (thread.anchor_scope or "text").lower(),
        "page_number": thread.page_number,
        "segment_key": thread.segment_key,
        "segment_start": thread.segment_start,
        "segment_end": thread.segment_end,
        "quote_text": sanitize_line_quote_fragment(thread.quote_text),
        "quote_prefix": sanitize_line_quote_fragment(thread.quote_prefix, max_length=120),
        "quote_suffix": sanitize_line_quote_fragment(thread.quote_suffix, max_length=120),
        "quote_start": thread.quote_start,
        "quote_end": thread.quote_end,
        "anchor_hash": thread.anchor_hash,
        "created_by_token": thread.created_by_token,
        "created_by_nickname": thread.created_by_nickname,
        "is_resolved": thread.is_resolved,
        "is_created_by_me": bool(viewer_token and thread.created_by_token == viewer_token),
        "created_at": thread.created_at.isoformat() + "Z" if thread.created_at else None,
        "updated_at": thread.updated_at.isoformat() + "Z" if thread.updated_at else None,
        "messages": messages,
        "message_count": len(messages),
    }


def serialize_participant(room_id: int, participant: RoomParticipant, viewer_token: Optional[str]) -> Dict[str, Any]:
    online_window_seconds = current_app.config["ONLINE_WINDOW_SECONDS"]
    is_online = participant.last_seen_at >= datetime.utcnow() - timedelta(seconds=online_window_seconds)
    recent_uploads = (
        FileRecord.query.filter_by(room_id=room_id, uploader_viewer_token=participant.viewer_token)
        .order_by(FileRecord.created_at.desc(), FileRecord.id.desc())
        .limit(5)
        .all()
    )
    total_uploads = FileRecord.query.filter_by(room_id=room_id, uploader_viewer_token=participant.viewer_token).count()

    uploads_payload = []
    for file_record in recent_uploads[:5]:
        extension = get_extension(file_record.stored_name)
        uploads_payload.append(
            {
                "id": file_record.id,
                "original_name": get_file_original_name(file_record),
                "type": get_file_type_from_extension(extension),
            }
        )

    extra_upload_count = max(total_uploads - 5, 0)
    return {
        "viewer_token": participant.viewer_token,
        "nickname": participant.nickname,
        "joined_at": participant.joined_at.isoformat() + "Z" if participant.joined_at else None,
        "last_seen_at": participant.last_seen_at.isoformat() + "Z" if participant.last_seen_at else None,
        "last_action_at": participant.last_action_at.isoformat() + "Z" if participant.last_action_at else None,
        "is_online": is_online,
        "upload_count": participant.upload_count,
        "comment_count": participant.comment_count,
        "is_me": bool(viewer_token and participant.viewer_token == viewer_token),
        "recent_uploads": uploads_payload,
        "extra_upload_count": extra_upload_count,
    }


def build_file_collab(file_id: int, viewer_token: Optional[str]) -> Dict[str, Any]:
    comment_count = FileComment.query.filter_by(file_id=file_id).count()
    line_thread_count = PDFLineThread.query.filter_by(file_id=file_id).count()
    star_count = FileStar.query.filter_by(file_id=file_id).count()
    read_count = FileReadState.query.filter_by(file_id=file_id, is_read=True).count()

    starred_by_me = False
    read_by_me = False
    if viewer_token:
        starred_by_me = FileStar.query.filter_by(file_id=file_id, viewer_token=viewer_token).first() is not None
        read_state = FileReadState.query.filter_by(file_id=file_id, viewer_token=viewer_token).first()
        read_by_me = bool(read_state and read_state.is_read)

    return {
        "comment_count": comment_count,
        "line_thread_count": line_thread_count,
        "star_count": star_count,
        "read_count": read_count,
        "starred_by_me": starred_by_me,
        "read_by_me": read_by_me,
    }


def serialize_file(file_record: FileRecord, legacy: bool = False, viewer_token: Optional[str] = None) -> Dict[str, Any]:
    extension = get_extension(file_record.stored_name)
    file_type = get_file_type_from_extension(extension)
    latest_job_id = file_record.jobs[0].id if file_record.jobs else None

    payload = {
        "id": file_record.id,
        "room_slug": file_record.room.slug,
        "filename": file_record.stored_name,
        "stored_name": file_record.stored_name,
        "original_name": get_file_original_name(file_record),
        "mime_type": file_record.mime_type,
        "size": file_record.size_bytes,
        "size_mb": round(file_record.size_bytes / (1024 * 1024), 2),
        "modified": file_record.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "type": file_type,
        "url": build_room_file_url(file_record.room.slug, file_record.stored_name),
        "absolute_url": build_room_file_absolute_url(file_record.room.slug, file_record.stored_name),
        "summary_status": file_record.summary_status,
        "summary_text": file_record.summary_text,
        "summary_json": file_record.summary_json,
        "summary_error": file_record.summary_error,
        "summary_job_id": latest_job_id,
        "uploader_viewer_token": file_record.uploader_viewer_token,
        "uploader_nickname": file_record.uploader_nickname,
        "is_uploaded_by_me": bool(viewer_token and file_record.uploader_viewer_token == viewer_token),
        "collab": build_file_collab(file_record.id, viewer_token),
    }

    if legacy:
        payload["url"] = build_legacy_file_url(file_record.stored_name)
        payload["absolute_url"] = payload["url"]

    return payload


def ensure_default_room() -> Room:
    default_room_slug = current_app.config["DEFAULT_ROOM_SLUG"]
    default_room = Room.query.filter_by(slug=default_room_slug).first()

    if default_room is None:
        default_room = Room(
            slug=default_room_slug,
            name=current_app.config["DEFAULT_ROOM_NAME"],
            passcode_hash=hash_passcode(current_app.config["DEFAULT_ROOM_PASSCODE"]),
            created_by_ip="system",
            discussion_status=DISCUSSION_STATUS_IDLE,
            discussion_summary_version=0,
        )
        db.session.add(default_room)
        db.session.commit()
    else:
        updated = False
        if not default_room.discussion_status:
            default_room.discussion_status = DISCUSSION_STATUS_IDLE
            updated = True
        if default_room.discussion_summary_version is None:
            default_room.discussion_summary_version = 0
            updated = True
        if updated:
            db.session.commit()

    return default_room


def upsert_room_participant(
    room: Room,
    viewer_token: Optional[str],
    nickname: str,
    action: str,
    increment_upload: int = 0,
    increment_comment: int = 0,
) -> Optional[RoomParticipant]:
    if not viewer_token:
        return None

    clean_nickname = (nickname or "").strip() or "匿名协作者"
    participant = RoomParticipant.query.filter_by(room_id=room.id, viewer_token=viewer_token).first()
    now = datetime.utcnow()

    if participant is None:
        participant = RoomParticipant(
            room_id=room.id,
            viewer_token=viewer_token,
            nickname=clean_nickname,
            joined_at=now,
            last_seen_at=now,
            last_action_at=now,
            upload_count=max(increment_upload, 0),
            comment_count=max(increment_comment, 0),
        )
        db.session.add(participant)
    else:
        participant.nickname = clean_nickname
        participant.last_seen_at = now
        participant.last_action_at = now
        if increment_upload:
            participant.upload_count = max(participant.upload_count + increment_upload, 0)
        if increment_comment:
            participant.comment_count = max(participant.comment_count + increment_comment, 0)

    db.session.commit()
    if action:
        current_app.logger.info(
            "participant updated room=%s token=%s action=%s upload_count=%s comment_count=%s",
            room.slug,
            viewer_token[:8],
            action,
            participant.upload_count,
            participant.comment_count,
        )
    return participant


def maybe_queue_discussion_summary(room: Room, triggered_by_token: Optional[str], force: bool = False) -> None:
    if not room.discussion_ended_at:
        return

    latest_summary = (
        RoomDiscussionSummary.query.filter_by(room_id=room.id)
        .order_by(RoomDiscussionSummary.version.desc())
        .first()
    )
    min_interval = max(current_app.config["DISCUSSION_RECOMPUTE_MIN_SECONDS"], 1)
    now = datetime.utcnow()

    should_run_now = force
    if not should_run_now:
        if latest_summary is None:
            should_run_now = True
        elif latest_summary.updated_at is None:
            should_run_now = True
        else:
            should_run_now = (now - latest_summary.updated_at).total_seconds() >= min_interval

    if should_run_now:
        enqueue_discussion_summary(room.id, triggered_by_token)
        return

    if latest_summary and latest_summary.updated_at:
        delay_seconds = min_interval - (now - latest_summary.updated_at).total_seconds()
    else:
        delay_seconds = min_interval
    delay_seconds = max(int(delay_seconds), 1)

    with discussion_timers_lock:
        existing_timer = discussion_timers.get(room.id)
        if existing_timer is not None and existing_timer.is_alive():
            return

        timer = threading.Timer(delay_seconds, lambda: enqueue_discussion_summary(room.id, triggered_by_token))
        timer.daemon = True
        discussion_timers[room.id] = timer
        timer.start()


def enqueue_discussion_summary(room_id: int, triggered_by_token: Optional[str]) -> None:
    with app.app_context():
        room = db.session.get(Room, room_id)
        if room is None:
            return

        room.discussion_status = DISCUSSION_STATUS_RUNNING
        next_version = (room.discussion_summary_version or 0) + 1
        room.discussion_summary_version = next_version

        latest_comment = (
            FileComment.query.filter_by(room_id=room.id)
            .order_by(FileComment.id.desc())
            .first()
        )
        summary_record = RoomDiscussionSummary(
            room_id=room.id,
            version=next_version,
            status=DISCUSSION_STATUS_RUNNING,
            triggered_by_token=triggered_by_token,
            source_last_comment_id=latest_comment.id if latest_comment else None,
        )
        db.session.add(summary_record)
        db.session.commit()

        if not current_app.config["DISCUSSION_ASYNC"]:
            process_discussion_summary(room_id, summary_record.id)
            return

        worker = threading.Thread(
            target=_run_discussion_summary_in_background,
            args=(room_id, summary_record.id),
            daemon=True,
            name=f"discussion-summary-{room_id}-{summary_record.id}",
        )
        worker.start()


def _run_discussion_summary_in_background(room_id: int, summary_id: int) -> None:
    try:
        process_discussion_summary(room_id, summary_id)
    except Exception as exc:
        with app.app_context():
            room = db.session.get(Room, room_id)
            summary_record = db.session.get(RoomDiscussionSummary, summary_id)
            if room and summary_record:
                room.discussion_status = DISCUSSION_STATUS_FAILED
                summary_record.status = DISCUSSION_STATUS_FAILED
                summary_record.error = str(exc)
                summary_record.updated_at = datetime.utcnow()
                db.session.commit()


def build_discussion_summary_json(room: Room) -> Dict[str, Any]:
    room_files = (
        FileRecord.query.filter_by(room_id=room.id)
        .order_by(FileRecord.created_at.asc(), FileRecord.id.asc())
        .all()
    )
    comments = (
        FileComment.query.filter_by(room_id=room.id)
        .order_by(FileComment.created_at.asc(), FileComment.id.asc())
        .all()
    )
    line_threads = (
        PDFLineThread.query.filter_by(room_id=room.id)
        .order_by(PDFLineThread.created_at.asc(), PDFLineThread.id.asc())
        .all()
    )
    line_comments = (
        PDFLineComment.query.filter_by(room_id=room.id)
        .order_by(PDFLineComment.created_at.asc(), PDFLineComment.id.asc())
        .all()
    )

    file_map = {file_record.id: file_record for file_record in room_files}
    grouped: Dict[str, Dict[str, Any]] = {}

    def get_or_create_file_item(file_record: FileRecord) -> Dict[str, Any]:
        owner_nickname = (file_record.uploader_nickname or "未命名上传者").strip() or "未命名上传者"
        owner_group = grouped.setdefault(
            owner_nickname,
            {
                "owner_nickname": owner_nickname,
                "owner_summary": "",
                "files": {},
                "claimable_actions": [],
                "action_board": {"processing": [], "follow_up": []},
            },
        )
        return owner_group["files"].setdefault(
            file_record.id,
            {
                "file_id": file_record.id,
                "file_name": get_file_original_name(file_record),
                "file_type": get_file_type_from_extension(get_extension(file_record.stored_name)),
                "full_comments": [],
                "line_comments": [],
                "comment_details": [],
                "line_feedback": [],
                "file_takeaways": [],
                "action_board": {"processing": [], "follow_up": []},
            },
        )

    for comment in comments:
        file_record = file_map.get(comment.file_id)
        if file_record is None:
            continue
        file_item = get_or_create_file_item(file_record)
        detail = {
            "commenter_nickname": comment.nickname,
            "comment_content": comment.content,
            "created_at": comment.created_at.isoformat() + "Z",
        }
        file_item["full_comments"].append(detail)
        file_item["comment_details"].append(detail)

    line_messages_by_thread: Dict[int, list] = {}
    for message in line_comments:
        if message.is_deleted:
            continue
        line_messages_by_thread.setdefault(message.thread_id, []).append(
            {
                "commenter_nickname": message.nickname,
                "comment_content": message.content,
                "created_at": message.created_at.isoformat() + "Z",
            }
        )

    for thread in line_threads:
        file_record = file_map.get(thread.file_id)
        if file_record is None:
            continue
        file_item = get_or_create_file_item(file_record)
        thread_payload = {
            "thread_id": thread.id,
            "source_type": (thread.source_type or "pdf").lower(),
            "anchor_scope": (thread.anchor_scope or "text").lower(),
            "page_number": thread.page_number,
            "segment_key": thread.segment_key,
            "segment_start": thread.segment_start,
            "segment_end": thread.segment_end,
            "quote_text": sanitize_line_quote_fragment(thread.quote_text),
            "quote_prefix": sanitize_line_quote_fragment(thread.quote_prefix, max_length=120),
            "quote_suffix": sanitize_line_quote_fragment(thread.quote_suffix, max_length=120),
            "quote_start": thread.quote_start,
            "quote_end": thread.quote_end,
            "comments": line_messages_by_thread.get(thread.id, []),
        }
        file_item["line_comments"].append(thread_payload)
        file_item["line_feedback"].append(thread_payload)

    summary_groups = []
    for owner_name, owner_group in grouped.items():
        file_items = list(owner_group["files"].values())
        owner_processing: List[str] = []
        owner_follow_up: List[str] = []
        claim_actions: List[str] = []

        for item in file_items:
            processing_actions: List[str] = []
            follow_up_actions: List[str] = []

            for line_item in item["line_comments"][:3]:
                first_quote = str(line_item.get("quote_text") or "").strip()
                if first_quote:
                    scope_prefix = (
                        f"第{line_item['page_number']}页"
                        if line_item.get("source_type") == "pdf"
                        else f"段落 {line_item.get('segment_key') or '-'}"
                    )
                    processing_actions.append(f"处理《{item['file_name']}》{scope_prefix}引用：{first_quote[:42]}")

            for full_comment in item["full_comments"][:3]:
                follow_up_actions.append(f"跟进《{item['file_name']}》全文评论：{full_comment['comment_content'][:42]}")

            if not processing_actions:
                processing_actions.append(f"处理《{item['file_name']}》：补充结构化结论与负责人。")
            if not follow_up_actions:
                follow_up_actions.append(f"跟进《{item['file_name']}》：暂无全文评论，建议会后补充。")

            item["action_board"]["processing"] = processing_actions[:4]
            item["action_board"]["follow_up"] = follow_up_actions[:4]
            item["file_takeaways"] = [
                f"全文评论 {len(item['full_comments'])} 条，划线评论 {len(item['line_comments'])} 条。",
                "优先处理高频被提及片段，并明确会后责任人。",
            ]

            owner_processing.extend(item["action_board"]["processing"])
            owner_follow_up.extend(item["action_board"]["follow_up"])
            claim_actions.extend(item["action_board"]["processing"][:2] + item["action_board"]["follow_up"][:2])

        if not claim_actions:
            claim_actions = ["暂无明确认领事项，建议会后补充行动项。"]

        owner_group["action_board"]["processing"] = owner_processing[:6]
        owner_group["action_board"]["follow_up"] = owner_follow_up[:6]
        owner_group["owner_summary"] = f"共 {len(file_items)} 份文件被评论，建议先处理划线评论，再跟进全文评论。"
        owner_group["claimable_actions"] = claim_actions[:6]

        summary_groups.append(
            {
                "owner_nickname": owner_name,
                "owner_summary": owner_group["owner_summary"],
                "files": file_items,
                "claimable_actions": owner_group["claimable_actions"],
                "action_board": owner_group["action_board"],
            }
        )

    return {
        "meeting_overview": {
            "room_name": room.name,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "total_files": len(room_files),
            "total_comments": len(comments),
            "total_line_threads": len(line_threads),
            "total_line_comments": sum(len(item) for item in line_messages_by_thread.values()),
        },
        "by_commented_owner": summary_groups,
        "cross_actions": [
            "优先处理高频评论与高频划线评论涉及的资料。",
            "对有争议的引用片段补充统一结论，并明确负责人。",
            "将会后完成情况回填到房间评论形成闭环。",
        ],
    }


def normalize_discussion_text_key(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*([,，.。:：;；!！?？、])\s*", r"\1", text)
    return text


def normalize_discussion_text_list(value: Any, max_items: int = 12) -> List[str]:
    source = value if isinstance(value, list) else []
    seen: Set[str] = set()
    normalized: List[str] = []
    for item in source:
        raw = str(item or "").strip()
        key = normalize_discussion_text_key(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(raw)
        if len(normalized) >= max_items:
            break
    return normalized


def normalize_discussion_display_text(value: Any) -> str:
    text = str(value or "")
    text = CONTROL_CHAR_PATTERN.sub("", text)
    text = text.replace("\ufffd", "").replace("\ufeff", "")
    return re.sub(r"\s+", " ", text).strip()


def normalize_discussion_actor_key(value: Any) -> str:
    return normalize_discussion_display_text(value).lower()


def format_line_comment_scope(line_item: Dict[str, Any]) -> str:
    source_type = normalize_discussion_display_text(line_item.get("source_type") or "pdf").lower()
    quote = normalize_discussion_display_text(line_item.get("quote_text"))
    if source_type == "docx":
        segment_key = normalize_discussion_display_text(line_item.get("segment_key")) or "-"
        return f"段落{segment_key}引用「{quote}」" if quote else f"段落{segment_key}（无引用）"
    page_number = line_item.get("page_number") or 1
    return f"第{page_number}页引用「{quote}」" if quote else f"第{page_number}页（无引用）"


def format_summary_detail_line(
    file_name: Any,
    scope_text: str,
    commenter_name: Any,
    comment_content: Any,
    target_owner: Any = None,
) -> str:
    normalized_file = normalize_discussion_display_text(file_name) or "该文件"
    normalized_scope = normalize_discussion_display_text(scope_text) or "全文"
    normalized_commenter = normalize_discussion_display_text(commenter_name) or "匿名"
    normalized_content = normalize_discussion_display_text(comment_content)
    prefix = ""
    if target_owner is not None:
        normalized_target = normalize_discussion_display_text(target_owner)
        if normalized_target:
            prefix = f"评给{normalized_target}"
    return f"{prefix}《{normalized_file}》{normalized_scope}｜{normalized_commenter}：{normalized_content}"


def get_file_comments_lists(file_item: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    full_comments = file_item.get("full_comments") if isinstance(file_item.get("full_comments"), list) else []
    line_comments = file_item.get("line_comments") if isinstance(file_item.get("line_comments"), list) else []
    return full_comments, line_comments


def build_file_processing_details(file_item: Dict[str, Any], owner_nickname: str) -> List[str]:
    file_name = normalize_discussion_display_text(file_item.get("file_name")) or "该文件"
    owner_key = normalize_discussion_actor_key(owner_nickname)
    full_comments, line_comments = get_file_comments_lists(file_item)
    details: List[str] = []

    for full_comment in full_comments:
        if not isinstance(full_comment, dict):
            continue
        commenter = normalize_discussion_display_text(full_comment.get("commenter_nickname")) or "匿名"
        commenter_key = normalize_discussion_actor_key(commenter)
        comment_content = normalize_discussion_display_text(full_comment.get("comment_content"))
        if not comment_content:
            continue
        if owner_key and commenter_key == owner_key:
            continue
        details.append(format_summary_detail_line(file_name, "全文", commenter, comment_content))

    for line_item in line_comments:
        if not isinstance(line_item, dict):
            continue
        scope = format_line_comment_scope(line_item)
        comments = line_item.get("comments") if isinstance(line_item.get("comments"), list) else []
        for message in comments:
            if not isinstance(message, dict):
                continue
            commenter = normalize_discussion_display_text(message.get("commenter_nickname")) or "匿名"
            commenter_key = normalize_discussion_actor_key(commenter)
            comment_content = normalize_discussion_display_text(message.get("comment_content"))
            if not comment_content:
                continue
            if owner_key and commenter_key == owner_key:
                continue
            details.append(format_summary_detail_line(file_name, scope, commenter, comment_content))

    return normalize_discussion_text_list(details, max_items=500)


def build_file_followup_details(file_item: Dict[str, Any], owner_nickname: str) -> List[str]:
    file_name = normalize_discussion_display_text(file_item.get("file_name")) or "该文件"
    owner_key = normalize_discussion_actor_key(owner_nickname)
    if not owner_key:
        return []

    full_comments, line_comments = get_file_comments_lists(file_item)
    details: List[str] = []

    for full_comment in full_comments:
        if not isinstance(full_comment, dict):
            continue
        commenter = normalize_discussion_display_text(full_comment.get("commenter_nickname")) or "匿名"
        if normalize_discussion_actor_key(commenter) != owner_key:
            continue
        comment_content = normalize_discussion_display_text(full_comment.get("comment_content"))
        if not comment_content:
            continue
        details.append(format_summary_detail_line(file_name, "全文", commenter, comment_content))

    for line_item in line_comments:
        if not isinstance(line_item, dict):
            continue
        scope = format_line_comment_scope(line_item)
        comments = line_item.get("comments") if isinstance(line_item.get("comments"), list) else []
        for message in comments:
            if not isinstance(message, dict):
                continue
            commenter = normalize_discussion_display_text(message.get("commenter_nickname")) or "匿名"
            if normalize_discussion_actor_key(commenter) != owner_key:
                continue
            comment_content = normalize_discussion_display_text(message.get("comment_content"))
            if not comment_content:
                continue
            details.append(format_summary_detail_line(file_name, scope, commenter, comment_content))

    return normalize_discussion_text_list(details, max_items=500)


def build_owner_processing_details(owner_group: Dict[str, Any]) -> List[str]:
    owner_name = normalize_discussion_display_text(owner_group.get("owner_nickname")) or "未命名上传者"
    files = owner_group.get("files") if isinstance(owner_group.get("files"), list) else []
    details: List[str] = []
    for file_item in files:
        if not isinstance(file_item, dict):
            continue
        details.extend(build_file_processing_details(file_item, owner_name))
    return normalize_discussion_text_list(details, max_items=500)


def build_owner_followup_details(all_owner_groups: List[Dict[str, Any]], owner_nickname: str) -> List[str]:
    owner_name = normalize_discussion_display_text(owner_nickname)
    owner_key = normalize_discussion_actor_key(owner_name)
    if not owner_key:
        return []

    details: List[str] = []
    for owner_group in all_owner_groups:
        if not isinstance(owner_group, dict):
            continue
        target_owner = normalize_discussion_display_text(owner_group.get("owner_nickname")) or "未命名上传者"
        if normalize_discussion_actor_key(target_owner) == owner_key:
            continue
        files = owner_group.get("files") if isinstance(owner_group.get("files"), list) else []
        for file_item in files:
            if not isinstance(file_item, dict):
                continue
            file_name = normalize_discussion_display_text(file_item.get("file_name")) or "该文件"
            full_comments, line_comments = get_file_comments_lists(file_item)

            for full_comment in full_comments:
                if not isinstance(full_comment, dict):
                    continue
                commenter = normalize_discussion_display_text(full_comment.get("commenter_nickname")) or "匿名"
                if normalize_discussion_actor_key(commenter) != owner_key:
                    continue
                comment_content = normalize_discussion_display_text(full_comment.get("comment_content"))
                if not comment_content:
                    continue
                details.append(
                    format_summary_detail_line(file_name, "全文", commenter, comment_content, target_owner=target_owner)
                )

            for line_item in line_comments:
                if not isinstance(line_item, dict):
                    continue
                scope = format_line_comment_scope(line_item)
                comments = line_item.get("comments") if isinstance(line_item.get("comments"), list) else []
                for message in comments:
                    if not isinstance(message, dict):
                        continue
                    commenter = normalize_discussion_display_text(message.get("commenter_nickname")) or "匿名"
                    if normalize_discussion_actor_key(commenter) != owner_key:
                        continue
                    comment_content = normalize_discussion_display_text(message.get("comment_content"))
                    if not comment_content:
                        continue
                    details.append(
                        format_summary_detail_line(file_name, scope, commenter, comment_content, target_owner=target_owner)
                    )

    return normalize_discussion_text_list(details, max_items=500)


def extract_legacy_owner_action_details(owner_group: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    processing: List[str] = []
    follow_up: List[str] = []

    owner_action_board = owner_group.get("action_board") if isinstance(owner_group.get("action_board"), dict) else {}
    processing.extend(normalize_discussion_text_list(owner_action_board.get("processing"), max_items=500))
    follow_up.extend(normalize_discussion_text_list(owner_action_board.get("follow_up"), max_items=500))

    files = owner_group.get("files") if isinstance(owner_group.get("files"), list) else []
    for file_item in files:
        if not isinstance(file_item, dict):
            continue
        action_board = file_item.get("action_board") if isinstance(file_item.get("action_board"), dict) else {}
        processing.extend(normalize_discussion_text_list(action_board.get("processing"), max_items=500))
        follow_up.extend(normalize_discussion_text_list(action_board.get("follow_up"), max_items=500))

    claimable_actions = owner_group.get("claimable_actions") if isinstance(owner_group.get("claimable_actions"), list) else []
    for action in claimable_actions:
        text = normalize_discussion_display_text(action)
        if not text:
            continue
        if text.startswith("处理"):
            processing.append(text)
        elif text.startswith("跟进"):
            follow_up.append(text)

    return (
        normalize_discussion_text_list(processing, max_items=500),
        normalize_discussion_text_list(follow_up, max_items=500),
    )


def infer_file_action_board_from_claims(
    file_item: Dict[str, Any],
    owner_claimable_actions: List[str],
    owner_nickname: str = "",
) -> Dict[str, Any]:
    file_name = normalize_discussion_display_text(file_item.get("file_name"))
    action_board = file_item.get("action_board") if isinstance(file_item.get("action_board"), dict) else {}
    processing = normalize_discussion_text_list(action_board.get("processing"), max_items=500)
    follow_up = normalize_discussion_text_list(action_board.get("follow_up"), max_items=500)
    consumed_keys: Set[str] = set()

    def action_matches_file(action_text: str) -> bool:
        if not file_name:
            return False
        return f"《{file_name}》" in action_text or file_name in action_text

    for action in owner_claimable_actions:
        if not action_matches_file(action):
            continue
        normalized_key = normalize_discussion_text_key(action)
        if action.startswith("处理"):
            if normalized_key not in {normalize_discussion_text_key(item) for item in processing}:
                processing.append(action)
            consumed_keys.add(normalized_key)
        elif action.startswith("跟进"):
            if normalized_key not in {normalize_discussion_text_key(item) for item in follow_up}:
                follow_up.append(action)
            consumed_keys.add(normalized_key)

    processing_details = build_file_processing_details(file_item, owner_nickname)
    followup_details = build_file_followup_details(file_item, owner_nickname)
    processing = normalize_discussion_text_list(processing_details + processing, max_items=500)
    follow_up = normalize_discussion_text_list(followup_details + follow_up, max_items=500)

    consumed_keys.update(normalize_discussion_text_key(item) for item in processing + follow_up)
    consumed_keys.discard("")
    return {
        "processing": processing,
        "follow_up": follow_up,
        "consumed_keys": consumed_keys,
    }


def normalize_discussion_summary_payload(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return payload

    normalized_payload: Dict[str, Any] = dict(payload)
    source_groups = payload.get("by_commented_owner")
    if not isinstance(source_groups, list):
        normalized_payload["by_commented_owner"] = []
        return normalized_payload

    normalized_groups: List[Dict[str, Any]] = []
    for owner_group_raw in source_groups:
        if not isinstance(owner_group_raw, dict):
            continue

        owner_group = dict(owner_group_raw)
        owner_name = normalize_discussion_display_text(owner_group.get("owner_nickname")) or "未命名上传者"
        owner_group["owner_nickname"] = owner_name
        owner_claimable_actions = normalize_discussion_text_list(owner_group.get("claimable_actions"), max_items=500)
        source_files = owner_group.get("files") if isinstance(owner_group.get("files"), list) else []
        normalized_files: List[Dict[str, Any]] = []

        for file_item_raw in source_files:
            if not isinstance(file_item_raw, dict):
                continue
            file_item = dict(file_item_raw)

            full_comments = file_item.get("full_comments")
            if not isinstance(full_comments, list):
                full_comments = file_item.get("comment_details") if isinstance(file_item.get("comment_details"), list) else []

            line_comments = file_item.get("line_comments")
            if not isinstance(line_comments, list):
                line_comments = file_item.get("line_feedback") if isinstance(file_item.get("line_feedback"), list) else []

            file_item["full_comments"] = full_comments
            file_item["line_comments"] = line_comments
            file_item["comment_details"] = full_comments
            file_item["line_feedback"] = line_comments

            action_board = infer_file_action_board_from_claims(file_item, owner_claimable_actions, owner_name)
            file_item["action_board"] = {
                "processing": action_board["processing"],
                "follow_up": action_board["follow_up"],
            }

            if not isinstance(file_item.get("file_takeaways"), list) or not file_item.get("file_takeaways"):
                file_item["file_takeaways"] = [
                    f"全文评论 {len(full_comments)} 条，划线评论 {len(line_comments)} 条。",
                    "优先处理高频被提及片段，并明确会后责任人。",
                ]

            normalized_files.append(file_item)

        owner_group["files"] = normalized_files
        owner_group["claimable_actions"] = owner_claimable_actions
        normalized_groups.append(owner_group)

    for owner_group in normalized_groups:
        owner_name = normalize_discussion_display_text(owner_group.get("owner_nickname")) or "未命名上传者"
        processing_details = build_owner_processing_details(owner_group)
        followup_details = build_owner_followup_details(normalized_groups, owner_name)
        legacy_processing, legacy_followup = extract_legacy_owner_action_details(owner_group)

        if processing_details:
            processing_details = normalize_discussion_text_list(processing_details, max_items=500)
        else:
            processing_details = normalize_discussion_text_list(legacy_processing, max_items=500)

        if followup_details:
            followup_details = normalize_discussion_text_list(followup_details, max_items=500)
        else:
            followup_details = normalize_discussion_text_list(legacy_followup, max_items=500)

        owner_group["processing_details"] = processing_details
        owner_group["follow_up_details"] = followup_details
        owner_group["action_board"] = {
            "processing": processing_details,
            "follow_up": followup_details,
        }

        owner_consumed_keys: Set[str] = set()
        owner_consumed_keys.update(normalize_discussion_text_key(item) for item in processing_details + followup_details)
        for file_item in owner_group.get("files") or []:
            if not isinstance(file_item, dict):
                continue
            file_action_board = file_item.get("action_board") if isinstance(file_item.get("action_board"), dict) else {}
            owner_consumed_keys.update(
                normalize_discussion_text_key(item)
                for item in (file_action_board.get("processing") or []) + (file_action_board.get("follow_up") or [])
            )
        owner_consumed_keys.discard("")

        filtered_claimable: List[str] = []
        seen_claimable: Set[str] = set()
        for action in owner_group.get("claimable_actions") or []:
            key = normalize_discussion_text_key(action)
            if not key or key in seen_claimable or key in owner_consumed_keys:
                continue
            seen_claimable.add(key)
            filtered_claimable.append(action)
        owner_group["claimable_actions"] = filtered_claimable

    normalized_payload["by_commented_owner"] = normalized_groups
    if not isinstance(normalized_payload.get("cross_actions"), list):
        normalized_payload["cross_actions"] = []
    if not isinstance(normalized_payload.get("meeting_overview"), dict):
        normalized_payload["meeting_overview"] = {}
    return normalized_payload


def enforce_verbatim_discussion_payload(base_payload: Dict[str, Any], ai_payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(ai_payload, dict):
        return base_payload

    def normalize_text_list(value: Any, fallback: List[str], max_items: int = 8) -> List[str]:
        if not isinstance(value, list):
            value = fallback
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return cleaned[:max_items] if cleaned else fallback[:max_items]

    def normalize_action_board(value: Any, fallback: Dict[str, Any]) -> Dict[str, List[str]]:
        fallback_processing = fallback.get("processing") or []
        fallback_follow_up = fallback.get("follow_up") or []
        if not isinstance(value, dict):
            return {
                "processing": normalize_text_list([], fallback_processing),
                "follow_up": normalize_text_list([], fallback_follow_up),
            }
        return {
            "processing": normalize_text_list(value.get("processing"), fallback_processing),
            "follow_up": normalize_text_list(value.get("follow_up"), fallback_follow_up),
        }

    result: Dict[str, Any] = {
        "meeting_overview": ai_payload.get("meeting_overview") or base_payload.get("meeting_overview", {}),
        "cross_actions": ai_payload.get("cross_actions") or base_payload.get("cross_actions", []),
        "by_commented_owner": [],
    }

    ai_owner_map: Dict[str, Dict[str, Any]] = {}
    for owner_group in ai_payload.get("by_commented_owner") or []:
        if not isinstance(owner_group, dict):
            continue
        owner_name = str(owner_group.get("owner_nickname") or "").strip()
        if owner_name:
            ai_owner_map[owner_name] = owner_group

    for source_owner in base_payload.get("by_commented_owner") or []:
        owner_name = str(source_owner.get("owner_nickname") or "").strip()
        ai_owner_group = ai_owner_map.get(owner_name, {})
        ai_file_map: Dict[str, Dict[str, Any]] = {}
        for ai_file in ai_owner_group.get("files") or []:
            if not isinstance(ai_file, dict):
                continue
            file_key = str(ai_file.get("file_name") or ai_file.get("file_id") or "").strip()
            if file_key:
                ai_file_map[file_key] = ai_file

        merged_files = []
        for source_file in source_owner.get("files") or []:
            source_copy = dict(source_file)
            file_key = str(source_file.get("file_name") or source_file.get("file_id") or "").strip()
            ai_file = ai_file_map.get(file_key, {})

            source_copy["file_takeaways"] = normalize_text_list(
                ai_file.get("file_takeaways"), source_copy.get("file_takeaways") or []
            )
            source_copy["action_board"] = normalize_action_board(
                ai_file.get("action_board"),
                source_copy.get("action_board") or {"processing": [], "follow_up": []},
            )
            source_copy["comment_details"] = source_copy.get("full_comments") or source_copy.get("comment_details") or []
            source_copy["line_feedback"] = source_copy.get("line_comments") or source_copy.get("line_feedback") or []
            merged_files.append(source_copy)

        merged_owner = {
            "owner_nickname": owner_name,
            "owner_summary": str(ai_owner_group.get("owner_summary") or source_owner.get("owner_summary") or "").strip(),
            "files": merged_files,
            "claimable_actions": normalize_text_list(
                ai_owner_group.get("claimable_actions"),
                source_owner.get("claimable_actions") or [],
                max_items=10,
            ),
            "action_board": normalize_action_board(
                ai_owner_group.get("action_board"),
                source_owner.get("action_board") or {"processing": [], "follow_up": []},
            ),
        }
        result["by_commented_owner"].append(merged_owner)

    return result


def generate_ai_discussion_summary(base_payload: Dict[str, Any]) -> Dict[str, Any]:
    api_key = current_app.config.get("OPENAI_API_KEY", "")
    if not api_key:
        return base_payload

    model_name = current_app.config.get("OPENAI_MODEL", "gpt-4o-mini")
    base_url = current_app.config.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    client = OpenAI(api_key=api_key, base_url=base_url)
    is_official_openai = "api.openai.com" in base_url

    system_prompt = (
        "You are a meeting summarization assistant. Return strict JSON with keys: "
        "meeting_overview, by_commented_owner, cross_actions. "
        "Each item in by_commented_owner must include owner_nickname, owner_summary, files, claimable_actions, action_board. "
        "Each file item must include file_name, full_comments, line_comments, file_takeaways, action_board. "
        "Hard constraints: "
        "full_comments[].comment_content and line_comments[].quote_text/comments[].comment_content "
        "must be copied exactly from input, no paraphrase/translation/shortening."
    )
    user_prompt = (
        "基于下面的会议讨论原始结构，输出更清晰的中文总结JSON，保持字段结构不变，"
        "并确保可用于会后认领。\n\n"
        f"{json.dumps(base_payload, ensure_ascii=False)}"
    )
    messages = (
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        if is_official_openai
        else [{"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"}]
    )

    payload: Dict[str, Any] = {
        "model": model_name,
        "temperature": 0.2,
        "messages": messages,
    }
    if is_official_openai:
        payload["response_format"] = {"type": "json_object"}

    completion = client.chat.completions.create(**payload)
    content = completion.choices[0].message.content
    if isinstance(content, list):
        content = "\n".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content)
    raw_content = str(content or "").strip()
    parsed = try_parse_summary_json(raw_content)
    if isinstance(parsed, dict) and parsed:
        return enforce_verbatim_discussion_payload(base_payload, parsed)
    return base_payload


def process_discussion_summary(room_id: int, summary_id: int) -> None:
    with app.app_context():
        room = db.session.get(Room, room_id)
        summary_record = db.session.get(RoomDiscussionSummary, summary_id)
        if room is None or summary_record is None:
            return

        try:
            summary_json = build_discussion_summary_json(room)
            summary_json = generate_ai_discussion_summary(summary_json)
            summary_json = normalize_discussion_summary_payload(summary_json)
            summary_record.summary_json = summary_json
            summary_record.summary_text = json.dumps(summary_json, ensure_ascii=False)
            summary_record.status = DISCUSSION_STATUS_DONE
            summary_record.error = None
            summary_record.updated_at = datetime.utcnow()
            room.discussion_status = DISCUSSION_STATUS_DONE
            db.session.commit()
        except Exception as exc:
            summary_record.status = DISCUSSION_STATUS_FAILED
            summary_record.error = str(exc)
            summary_record.updated_at = datetime.utcnow()
            room.discussion_status = DISCUSSION_STATUS_FAILED
            db.session.commit()

        with discussion_timers_lock:
            timer = discussion_timers.get(room.id)
            if timer and not timer.is_alive():
                discussion_timers.pop(room.id, None)


def upgrade_schema_for_existing_databases() -> None:
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())

    if "rooms" in existing_tables:
        room_columns = {column["name"] for column in inspector.get_columns("rooms")}
        with db.engine.begin() as conn:
            if "owner_viewer_token" not in room_columns:
                conn.execute(text("ALTER TABLE rooms ADD COLUMN owner_viewer_token VARCHAR(64)"))
            if "discussion_ended_at" not in room_columns:
                conn.execute(text("ALTER TABLE rooms ADD COLUMN discussion_ended_at TIMESTAMP"))
            if "discussion_status" not in room_columns:
                conn.execute(text(f"ALTER TABLE rooms ADD COLUMN discussion_status VARCHAR(32) DEFAULT '{DISCUSSION_STATUS_IDLE}'"))
            if "discussion_summary_version" not in room_columns:
                conn.execute(text("ALTER TABLE rooms ADD COLUMN discussion_summary_version INTEGER DEFAULT 0"))

    if "files" in existing_tables:
        file_column_defs = {column["name"]: column for column in inspector.get_columns("files")}
        file_columns = set(file_column_defs.keys())
        with db.engine.begin() as conn:
            if "uploader_viewer_token" not in file_columns:
                conn.execute(text("ALTER TABLE files ADD COLUMN uploader_viewer_token VARCHAR(64)"))
            if "uploader_nickname" not in file_columns:
                conn.execute(text("ALTER TABLE files ADD COLUMN uploader_nickname VARCHAR(40)"))
            if "original_name_full" not in file_columns:
                conn.execute(text("ALTER TABLE files ADD COLUMN original_name_full TEXT"))

            original_name_type = str(file_column_defs.get("original_name", {}).get("type", "")).lower()
            if "varchar" in original_name_type and db.engine.dialect.name == "postgresql":
                conn.execute(text("ALTER TABLE files ALTER COLUMN original_name TYPE TEXT"))

            conn.execute(
                text(
                    "UPDATE files "
                    "SET original_name_full = original_name "
                    "WHERE (original_name_full IS NULL OR original_name_full = '') AND original_name IS NOT NULL"
                )
            )

    # Lightweight migrator for line-thread collaboration tables.
    db.metadata.create_all(
        bind=db.engine,
        tables=[PDFLineThread.__table__, PDFLineComment.__table__],
        checkfirst=True,
    )
    with db.engine.begin() as conn:
        line_thread_columns = {column["name"] for column in inspector.get_columns("pdf_line_threads")}
        if "source_type" not in line_thread_columns:
            conn.execute(text("ALTER TABLE pdf_line_threads ADD COLUMN source_type VARCHAR(16) DEFAULT 'pdf'"))
        if "anchor_scope" not in line_thread_columns:
            conn.execute(text("ALTER TABLE pdf_line_threads ADD COLUMN anchor_scope VARCHAR(16) DEFAULT 'text'"))
        if "segment_key" not in line_thread_columns:
            conn.execute(text("ALTER TABLE pdf_line_threads ADD COLUMN segment_key VARCHAR(160)"))
        if "segment_start" not in line_thread_columns:
            conn.execute(text("ALTER TABLE pdf_line_threads ADD COLUMN segment_start INTEGER"))
        if "segment_end" not in line_thread_columns:
            conn.execute(text("ALTER TABLE pdf_line_threads ADD COLUMN segment_end INTEGER"))
        conn.execute(
            text(
                "UPDATE pdf_line_threads "
                "SET source_type = COALESCE(NULLIF(source_type, ''), 'pdf'), "
                "anchor_scope = COALESCE(NULLIF(anchor_scope, ''), 'text')"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_line_threads_file_page_updated_at "
                "ON pdf_line_threads (file_id, page_number, updated_at)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_line_threads_file_source_segment_anchor "
                "ON pdf_line_threads (file_id, source_type, segment_key, anchor_hash)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_line_comments_thread_id "
                "ON pdf_line_comments (thread_id, id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_line_comments_room_file_id "
                "ON pdf_line_comments (room_id, file_id, id)"
            )
        )


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


def handle_file_upload(room: Room, deprecated: bool, bypass_auth: bool, require_profile: bool = False) -> Any:
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
    preserved_original_name = sanitize_original_filename(uploaded_file.filename, extension)
    stored_name = f"{uuid.uuid4().hex}.{extension}"
    viewer_token = get_room_viewer_token(room.slug)
    viewer_nickname = get_room_viewer_nickname(room.slug)

    if require_profile and (not viewer_token or not viewer_nickname):
        return jsonify({"success": False, "message": "Please set your nickname before uploading files."}), 400

    room_folder = get_room_upload_folder(room.slug, ensure=True)
    file_path = os.path.join(room_folder, stored_name)
    uploaded_file.save(file_path)

    file_size = os.path.getsize(file_path)
    mime_type = MIME_TYPES.get(extension, uploaded_file.mimetype or "application/octet-stream")
    summary_supported = extension in {"pdf", "docx"}
    summary_status = SUMMARY_STATUS_PENDING if summary_supported else SUMMARY_STATUS_NOT_APPLICABLE

    file_record = FileRecord(
        room_id=room.id,
        original_name=preserved_original_name[:255],
        original_name_full=preserved_original_name,
        stored_name=stored_name,
        mime_type=mime_type,
        size_bytes=file_size,
        uploader_ip=get_client_ip(),
        uploader_viewer_token=viewer_token,
        uploader_nickname=viewer_nickname or None,
        summary_status=summary_status,
    )
    if extension == "doc":
        file_record.summary_error = "`.doc` 摘要暂不支持，请转换为 `.docx` 后重试。"
    db.session.add(file_record)
    db.session.commit()

    summary_job = None
    if summary_supported:
        summary_job = SummaryJob(
            file_id=file_record.id,
            job_type="docx_summary" if extension == "docx" else "pdf_summary",
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
    if viewer_token:
        upsert_room_participant(
            room=room,
            viewer_token=viewer_token,
            nickname=viewer_nickname,
            action="upload_file",
            increment_upload=1,
        )

    payload = {
        "success": True,
        "message": "File uploaded successfully.",
        "room": serialize_room(room),
        "file_id": file_record.id,
        "summary_job_id": summary_job.id if summary_job else None,
        "file": serialize_file(file_record, legacy=deprecated, viewer_token=viewer_token),
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
        app.logger.exception("Summary background worker crashed for job_id=%s", summary_job_id)
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


def extract_docx_text(file_path: str) -> str:
    with zipfile.ZipFile(file_path) as archive:
        try:
            xml_payload = archive.read("word/document.xml")
        except KeyError:
            return ""

    root = ET.fromstring(xml_payload)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    body = root.find("w:body", namespace)
    if body is None:
        return ""

    text_chunks = []
    paragraph_tag = f"{{{namespace['w']}}}p"
    table_tag = f"{{{namespace['w']}}}tbl"

    def extract_node_text(node: ET.Element) -> str:
        text_parts = []
        for text_node in node.findall(".//w:t", namespace):
            value = (text_node.text or "").strip()
            if value:
                text_parts.append(value)
        return "".join(text_parts).strip()

    for child in list(body):
        if child.tag == paragraph_tag:
            paragraph_text = extract_node_text(child)
            if paragraph_text:
                text_chunks.append(paragraph_text)
            continue

        if child.tag != table_tag:
            continue

        for row in child.findall(".//w:tr", namespace):
            row_cells = []
            for cell in row.findall("./w:tc", namespace):
                cell_text = extract_node_text(cell)
                if cell_text:
                    row_cells.append(cell_text)
            if row_cells:
                text_chunks.append(" | ".join(row_cells))

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


def sanitize_summary_source_text(text: str) -> str:
    # Remove control chars and collapse whitespace to improve proxy compatibility.
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def try_parse_summary_json(raw_content: str) -> Optional[Dict[str, Any]]:
    if not raw_content:
        return None

    candidates = []

    # Original content.
    candidates.append(raw_content.strip())

    # Remove markdown fences.
    fence_cleaned = raw_content.strip()
    fence_cleaned = re.sub(r"^```(?:json)?", "", fence_cleaned).strip()
    fence_cleaned = re.sub(r"```$", "", fence_cleaned).strip()
    candidates.append(fence_cleaned)

    # Extract JSON object substring.
    if "{" in raw_content and "}" in raw_content:
        start = raw_content.find("{")
        end = raw_content.rfind("}")
        if start >= 0 and end > start:
            candidates.append(raw_content[start : end + 1].strip())

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue

    return None


def fallback_summary_from_text(raw_content: str) -> Dict[str, Any]:
    cleaned = sanitize_summary_source_text(raw_content)
    if not cleaned:
        raise RuntimeError("Model returned empty content.")

    # Split by common sentence delimiters and preserve useful fragments.
    parts = [p.strip() for p in re.split(r"[。！？.!?；;\n\r]+", cleaned) if p.strip()]
    if not parts:
        parts = [cleaned]

    one_line = parts[0][:140]
    key_points = (parts[:3] + ["补充要点 1", "补充要点 2", "补充要点 3"])[:3]

    # Basic keyword extraction by token frequency and length.
    tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,16}", cleaned)
    seen = set()
    keywords = []
    for token in tokens:
        lowered = token.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        keywords.append(token)
        if len(keywords) >= 5:
            break
    if len(keywords) < 5:
        keywords.extend(["主题", "重点", "结论", "术语", "行动"][: 5 - len(keywords)])

    suggested_actions = [
        "先根据一句话摘要确认主题边界",
        "按关键点整理 3 条可复述笔记",
        "基于关键词制定下一步学习清单",
    ]

    return {
        "one_line_summary": one_line,
        "key_points": key_points,
        "keywords": keywords,
        "suggested_actions": suggested_actions,
    }


def generate_ai_summary(text: str) -> Dict[str, Any]:
    api_key = current_app.config.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    model_name = current_app.config.get("OPENAI_MODEL", "gpt-4o-mini")
    base_url = current_app.config.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    client = OpenAI(api_key=api_key, base_url=base_url)
    is_official_openai = "api.openai.com" in base_url

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

    if is_official_openai:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    else:
        # Some proxy gateways are stricter on system messages.
        messages = [
            {"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"},
        ]

    request_payload: Dict[str, Any] = {
        "model": model_name,
        "temperature": 0.2,
        "messages": messages,
    }
    if is_official_openai:
        request_payload["response_format"] = {"type": "json_object"}

    completion = client.chat.completions.create(**request_payload)

    raw_content = completion.choices[0].message.content
    if isinstance(raw_content, list):
        text_parts = []
        for item in raw_content:
            if isinstance(item, dict):
                text_parts.append(str(item.get("text", "")))
            else:
                text_parts.append(str(item))
        raw_content = "\n".join([p for p in text_parts if p]).strip()
    elif raw_content is None:
        raw_content = ""
    else:
        raw_content = str(raw_content)

    parsed_json = try_parse_summary_json(raw_content)
    if parsed_json is not None:
        return normalize_summary_json(parsed_json)

    # Proxy providers may return plain text; fallback to resilient text parsing.
    app.logger.warning(
        "Summary response was not valid JSON; fallback parser activated. base_url=%s model=%s raw_preview=%s",
        base_url,
        model_name,
        raw_content[:180],
    )
    return normalize_summary_json(fallback_summary_from_text(raw_content))


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

                summary_extension = get_extension(file_record.stored_name or "")
                summary_file_type = get_file_type_from_extension(summary_extension)
                if summary_file_type == "pdf":
                    extracted_text = extract_pdf_text(stored_path)
                elif summary_file_type == "docx":
                    extracted_text = extract_docx_text(stored_path)
                else:
                    raise ValueError("Summary generation is not supported for this file type.")

                extracted_text = sanitize_summary_source_text(extracted_text)
                min_chars = current_app.config["SUMMARY_MIN_TEXT_CHARS"]
                if len(extracted_text) < min_chars:
                    raise ValueError(f"Extracted text is too short (< {min_chars} chars).")

                max_chars = current_app.config["SUMMARY_MAX_TEXT_CHARS"]
                base_url = current_app.config.get("OPENAI_BASE_URL", "")
                is_official_openai = "api.openai.com" in base_url

                # Proxy providers are often sensitive to very long prompts.
                provider_cap = max_chars if is_official_openai else min(max_chars, 4000)
                attempt_cap = max(600, provider_cap // (2 ** (attempt - 1)))
                cleaned_text = extracted_text[:attempt_cap]

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
                app.logger.error(
                    "Summary generation failed room=%s file_id=%s job_id=%s type=%s attempt=%s/%s used_chars=%s base_url=%s model=%s error=%s",
                    file_record.room.slug,
                    file_record.id,
                    summary_job.id,
                    summary_file_type if "summary_file_type" in locals() else "unknown",
                    attempt,
                    max_attempts,
                    len(cleaned_text) if "cleaned_text" in locals() else 0,
                    current_app.config.get("OPENAI_BASE_URL", ""),
                    current_app.config.get("OPENAI_MODEL", ""),
                    error_message,
                )
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

