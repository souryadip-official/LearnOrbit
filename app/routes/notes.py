"""
LearnOrbit Notes Routes
"""

import os
from flask import Blueprint, render_template, request, jsonify, send_file, current_app
from flask_login import login_required, current_user
from app import db
from app.models import LearningSession
from app.services.ai_service import generate_notes
from app.services.pdf_service import export_notes_pdf

notes_bp = Blueprint("notes", __name__)


@notes_bp.route("/<int:session_id>")
@login_required
def view_notes(session_id):
    session_obj = LearningSession.query.filter_by(
        id=session_id, user_id=current_user.id).first_or_404()
    return render_template("notes/notes.html", session=session_obj)


@notes_bp.route("/<int:session_id>/generate", methods=["POST"])
@login_required
def generate(session_id):
    session_obj = LearningSession.query.filter_by(
        id=session_id, user_id=current_user.id).first_or_404()

    provider = current_user.ai_provider
    model = current_user.ai_model
    api_key = current_user.get_ai_api_key()
    if not api_key:
        return jsonify({"error": "API key missing"}), 400

    # Build summary from conversation
    conv = session_obj.conversation
    summary = "\n".join(
        f"{m['role'].upper()}: {m['content'][:200]}" for m in conv[-20:]
    )

    notes_md = generate_notes(provider, model, api_key, session_obj.topic, summary)
    session_obj.notes_md = notes_md
    db.session.commit()

    return jsonify({"notes": notes_md})


@notes_bp.route("/<int:session_id>/export-pdf")
@login_required
def export_pdf(session_id):
    session_obj = LearningSession.query.filter_by(
        id=session_id, user_id=current_user.id).first_or_404()

    if not session_obj.notes_md:
        return jsonify({"error": "Generate notes first!"}), 400

    if current_user.plan == "free":
        return jsonify({"error": "PDF export requires Scholar or Academy plan. Upgrade to unlock! 🚀"}), 403

    export_dir = current_app.config.get("EXPORT_DIR", "/tmp/learnorbit_exports")
    try:
        filepath = export_notes_pdf(
            session_obj.notes_md, session_obj.topic,
            current_user.username, export_dir
        )
        return send_file(filepath, as_attachment=True,
                         download_name=os.path.basename(filepath))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
