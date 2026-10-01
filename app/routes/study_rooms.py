"""Bounded, text-only study rooms."""

import secrets
from datetime import datetime

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import User


study_rooms_bp = Blueprint("study_rooms", __name__)

ROOM_NAME_LIMIT = 80
MESSAGE_LIMIT = 1000
INVITE_CODE_LIMIT = 64
ROOM_MEMBER_LIMIT = 25
MESSAGE_BATCH_LIMIT = 50


class StudyRoom(db.Model):
    __tablename__ = "study_rooms"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(ROOM_NAME_LIMIT), nullable=False)
    invite_code = db.Column(db.String(INVITE_CODE_LIMIT), unique=True, nullable=False, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class StudyRoomMembership(db.Model):
    __tablename__ = "study_room_memberships"
    __table_args__ = (
        db.UniqueConstraint("room_id", "user_id", name="uq_study_room_member"),
    )

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("study_rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    joined_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class StudyRoomMessage(db.Model):
    __tablename__ = "study_room_messages"
    __table_args__ = (db.Index("ix_study_room_messages_room_id_id", "room_id", "id"),)

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("study_rooms.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    body = db.Column(db.String(MESSAGE_LIMIT), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


def _has_scholar_entitlement():
    return current_app.config.get("PRICING", {}).get(
        getattr(current_user, "plan", None), {}
    ).get("study_rooms", False)


def _premium_required():
    if _has_scholar_entitlement():
        return None
    message = "Study Rooms require Scholar or a higher plan."
    if request.path.endswith("/api/rooms") or "/api/rooms/" in request.path:
        return jsonify({"error": message, "upgrade_url": "/features/pricing"}), 403
    return render_template("features/upgrade_required.html", feature="Study Rooms"), 403


def _json_body():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _member_of(room_id):
    return StudyRoomMembership.query.filter_by(
        room_id=room_id, user_id=current_user.id
    ).first() is not None


def _message_json(message, username):
    return {
        "id": message.id,
        "text": message.body,
        "username": username,
        "created_at": message.created_at.isoformat(timespec="seconds") + "Z",
    }


@study_rooms_bp.route("/", methods=["GET"])
@login_required
def index():
    denied = _premium_required()
    if denied:
        return denied

    rooms = (
        StudyRoom.query.join(StudyRoomMembership, StudyRoomMembership.room_id == StudyRoom.id)
        .filter(StudyRoomMembership.user_id == current_user.id)
        .order_by(StudyRoom.created_at.desc(), StudyRoom.id.desc())
        .all()
    )
    counts = {}
    if rooms:
        rows = (
            db.session.query(StudyRoomMembership.room_id, db.func.count(StudyRoomMembership.id))
            .filter(StudyRoomMembership.room_id.in_([room.id for room in rooms]))
            .group_by(StudyRoomMembership.room_id)
            .all()
        )
        counts = dict(rows)
    return render_template("features/study_rooms.html", rooms=rooms, member_counts=counts)


@study_rooms_bp.route("/api/rooms", methods=["POST"])
@login_required
def create_room():
    denied = _premium_required()
    if denied:
        return denied

    name = _json_body().get("name")
    if not isinstance(name, str):
        return jsonify({"error": "Enter a room name."}), 400
    name = name.strip()
    if not name:
        return jsonify({"error": "Enter a room name."}), 400
    if len(name) > ROOM_NAME_LIMIT:
        return jsonify({"error": f"Room names must be {ROOM_NAME_LIMIT} characters or fewer."}), 400

    room = StudyRoom(
        name=name,
        invite_code=secrets.token_urlsafe(12),
        owner_id=current_user.id,
    )
    db.session.add(room)
    db.session.flush()
    db.session.add(StudyRoomMembership(room_id=room.id, user_id=current_user.id))
    db.session.commit()
    return jsonify({
        "success": True,
        "room": {"id": room.id, "name": room.name, "invite_code": room.invite_code},
    }), 201


@study_rooms_bp.route("/api/rooms/join", methods=["POST"])
@login_required
def join_room():
    denied = _premium_required()
    if denied:
        return denied

    code = _json_body().get("invite_code")
    if not isinstance(code, str):
        return jsonify({"error": "Enter an invite code."}), 400
    code = code.strip()
    if not code or len(code) > INVITE_CODE_LIMIT:
        return jsonify({"error": "Enter a valid invite code."}), 400
    room = StudyRoom.query.filter_by(invite_code=code).first()
    if not room:
        return jsonify({"error": "That invite code was not found."}), 404
    if _member_of(room.id):
        return jsonify({"success": True, "room": {"id": room.id, "name": room.name}, "already_joined": True})

    member_count = StudyRoomMembership.query.filter_by(room_id=room.id).count()
    if member_count >= ROOM_MEMBER_LIMIT:
        return jsonify({"error": "This room has reached its member limit."}), 409
    db.session.add(StudyRoomMembership(room_id=room.id, user_id=current_user.id))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if not _member_of(room.id):
            return jsonify({"error": "Could not join the room. Please try again."}), 409
    return jsonify({"success": True, "room": {"id": room.id, "name": room.name}})


@study_rooms_bp.route("/api/rooms/<int:room_id>/leave", methods=["POST"])
@login_required
def leave_room(room_id):
    denied = _premium_required()
    if denied:
        return denied

    room = StudyRoom.query.filter_by(id=room_id).first()
    membership = StudyRoomMembership.query.filter_by(
        room_id=room_id, user_id=current_user.id
    ).first()
    if room is None or membership is None:
        return jsonify({"error": "Room not found or you are not a member."}), 404

    was_owner = room.owner_id == current_user.id
    db.session.delete(membership)
    ownership_transferred = False
    room_deleted = False
    if was_owner:
        successor = (
            StudyRoomMembership.query.filter_by(room_id=room_id)
            .order_by(StudyRoomMembership.joined_at.asc(), StudyRoomMembership.id.asc())
            .first()
        )
        if successor:
            room.owner_id = successor.user_id
            ownership_transferred = True
        else:
            StudyRoomMessage.query.filter_by(room_id=room_id).delete(synchronize_session=False)
            StudyRoom.query.filter_by(id=room_id).delete(synchronize_session=False)
            room_deleted = True

    db.session.commit()
    return jsonify({
        "success": True,
        "room_deleted": room_deleted,
        "ownership_transferred": ownership_transferred,
    })


@study_rooms_bp.route("/api/rooms/<int:room_id>/messages", methods=["GET"])
@login_required
def read_messages(room_id):
    denied = _premium_required()
    if denied:
        return denied
    if not _member_of(room_id):
        return jsonify({"error": "Room not found or you are not a member."}), 404
    room = StudyRoom.query.filter_by(id=room_id).first()
    if room is None:
        return jsonify({"error": "Room not found or you are not a member."}), 404

    try:
        after_id = max(0, int(request.args.get("after", "0")))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid message cursor."}), 400

    query = (
        db.session.query(StudyRoomMessage, User.username)
        .join(User, User.id == StudyRoomMessage.user_id)
        .filter(StudyRoomMessage.room_id == room_id)
    )
    if after_id:
        rows = query.filter(StudyRoomMessage.id > after_id).order_by(StudyRoomMessage.id.asc()).limit(MESSAGE_BATCH_LIMIT).all()
    else:
        rows = query.order_by(StudyRoomMessage.id.desc()).limit(MESSAGE_BATCH_LIMIT).all()
        rows.reverse()
    return jsonify({
        "messages": [_message_json(message, username) for message, username in rows],
        "next_after": rows[-1][0].id if rows else after_id,
        "is_owner": room.owner_id == current_user.id,
    })


@study_rooms_bp.route("/api/rooms/<int:room_id>/messages", methods=["POST"])
@login_required
def send_message(room_id):
    denied = _premium_required()
    if denied:
        return denied
    if not _member_of(room_id):
        return jsonify({"error": "Room not found or you are not a member."}), 404

    text = _json_body().get("text")
    if not isinstance(text, str):
        return jsonify({"error": "Enter a text message."}), 400
    text = text.strip()
    if not text:
        return jsonify({"error": "Messages cannot be empty."}), 400
    if len(text) > MESSAGE_LIMIT:
        return jsonify({"error": f"Messages must be {MESSAGE_LIMIT} characters or fewer."}), 400

    message = StudyRoomMessage(room_id=room_id, user_id=current_user.id, body=text)
    db.session.add(message)
    db.session.commit()
    return jsonify({"success": True, "message": _message_json(message, current_user.username)}), 201
