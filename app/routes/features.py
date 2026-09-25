"""Student profile, focus utilities, calendar, and grounded session files."""
import os
import json
import re
import math
import mimetypes
from collections import Counter
from datetime import datetime, timedelta, date
import calendar as pycalendar
from werkzeug.utils import secure_filename
from flask import Blueprint, current_app, render_template, request, jsonify, send_file, abort, session
from flask_login import login_required, current_user
from app import db
from app.models import UserProfile, LearningSession, SessionDocument, CalendarEvent, Subscription, PaymentRecord, CodeSnippet, LearningBehavior, TopicMastery, EmailOTP, AttendanceStamp

features_bp = Blueprint("features", __name__)
AVATARS = [f"orbit-{i}" for i in range(1, 16)]


def _tokenize(text):
    return re.findall(r"[a-z0-9]{2,}", (text or "").lower())


def _chunks(text, size=850, overlap=120):
    words = text.split()
    step = size - overlap
    return [" ".join(words[i:i + size]) for i in range(0, len(words), step) if words[i:i + size]]


def _embeddings(texts):
    """Use provider embeddings when available; unsupported providers use lexical rank only."""
    import requests
    provider, key = current_user.ai_provider, current_user.get_ai_api_key()
    try:
        if provider == "openai":
            r = requests.post("https://api.openai.com/v1/embeddings", headers={"Authorization": f"Bearer {key}"},
                              json={"model": "text-embedding-3-small", "input": [t[:8000] for t in texts]}, timeout=25)
            r.raise_for_status(); return [row["embedding"] for row in sorted(r.json()["data"], key=lambda x: x["index"])]
        if provider == "google":
            items = [{"model": "models/gemini-embedding-001", "content": {"parts": [{"text": t[:8000]}]}} for t in texts]
            r = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents",
                              headers={"x-goog-api-key": key}, json={"requests": items}, timeout=25)
            r.raise_for_status(); return [row["values"] for row in r.json()["embeddings"]]
        if provider == "huggingface":
            r = requests.post("https://router.huggingface.co/hf-inference/models/BAAI/bge-small-en-v1.5",
                              headers={"Authorization": f"Bearer {key}"}, json={"inputs": [t[:8000] for t in texts], "normalize": True}, timeout=30)
            r.raise_for_status(); vectors = r.json()
            # Sentence embedding providers return one vector per string. Some
            # feature-extraction backends return token vectors; mean-pool those.
            output = []
            for vector in vectors:
                if vector and isinstance(vector[0], list):
                    vector = [sum(row[i] for row in vector)/len(vector) for i in range(len(vector[0]))]
                output.append(vector)
            return output
    except Exception:
        return []
    return []


def _cosine(a, b):
    if not a or not b or len(a) != len(b): return 0.0
    dot = sum(x*y for x, y in zip(a,b))
    den = math.sqrt(sum(x*x for x in a) * sum(y*y for y in b))
    return dot / den if den else 0.0


def hybrid_retrieve(text, query, limit=4, cached_vectors=None, query_vector=None):
    """RRF fusion of semantic cosine rank and a small BM25-style lexical rank."""
    chunks = _chunks(text)
    if not chunks: return []
    query_terms = Counter(_tokenize(query))
    doc_terms = [Counter(_tokenize(chunk)) for chunk in chunks]
    avg_len = max(1, sum(sum(t.values()) for t in doc_terms) / len(doc_terms))
    df = Counter(term for terms in doc_terms for term in terms)
    lexical = []
    for i, terms in enumerate(doc_terms):
        score = 0.0; length = sum(terms.values())
        for term, qcount in query_terms.items():
            tf = terms.get(term, 0)
            if not tf: continue
            idf = math.log(1 + (len(chunks)-df[term]+0.5)/(df[term]+0.5))
            score += idf * (tf*2.2)/(tf + 1.2*(0.25 + 0.75*length/avg_len)) * min(qcount, 2)
        lexical.append((score, i))
    lexical_rank = {idx: rank for rank, (_, idx) in enumerate(sorted(lexical, reverse=True), 1)}
    qvec = query_vector or _embeddings([query])
    sem_rank = {}
    if qvec:
        # Embed only the best lexical candidates to keep upload/chat latency and API
        # usage bounded, then fuse the ranks from both retrieval methods.
        candidate_ids = [idx for _, idx in sorted(lexical, reverse=True)[:min(24, len(chunks))]]
        vectors = cached_vectors if cached_vectors and len(cached_vectors) == len(chunks) else _embeddings([chunks[idx] for idx in candidate_ids])
        if cached_vectors and len(cached_vectors) == len(chunks):
            candidate_ids = list(range(len(chunks)))
        semantic = [(_cosine(qvec[0], vector), idx) for idx, vector in zip(candidate_ids, vectors)]
        sem_rank = {idx: rank for rank, (_, idx) in enumerate(sorted(semantic, reverse=True), 1)}
    ranks = []
    for i, chunk in enumerate(chunks):
        # Reciprocal-rank fusion (k=60) avoids comparing incompatible raw scores.
        score = (1/(60+lexical_rank.get(i, len(chunks)+1)))
        if sem_rank: score += 1/(60+sem_rank.get(i, len(chunks)+1))
        ranks.append((score, chunk, lexical[i][0]))
    ranks.sort(reverse=True, key=lambda row: row[0])
    return [{"text": chunk, "score": score, "lexical": lex} for score, chunk, lex in ranks[:limit]]


@features_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    record = UserProfile.query.filter_by(user_id=current_user.id).first()
    if not record:
        record = UserProfile(user_id=current_user.id)
        db.session.add(record); db.session.commit()
    if request.method == "POST":
        record.full_name = request.form.get("full_name", "")[:120]
        record.date_of_birth = request.form.get("date_of_birth", "")[:10]
        record.grade = request.form.get("grade", "")[:40]
        record.teaching_style = request.form.get("teaching_style", "balanced")[:32]
        behavior = LearningBehavior.query.filter_by(user_id=current_user.id).first()
        if behavior:
            behavior.preferred_style = record.teaching_style
        chosen = request.form.get("avatar", "orbit-1")
        if chosen in AVATARS: record.avatar = chosen
        picture = request.files.get("picture")
        if request.form.get("remove_picture") == "1" and not (picture and picture.filename): record.picture_path = None
        if picture and picture.filename:
            extension = os.path.splitext(secure_filename(picture.filename))[1].lower()
            if extension not in {".png", ".jpg", ".jpeg", ".webp", ".gif"} or not picture.mimetype.startswith("image/"):
                return jsonify({"error": "Choose a PNG, JPEG, WebP, or GIF image."}), 400
            if request.content_length and request.content_length > 5 * 1024 * 1024:
                return jsonify({"error": "Profile pictures must be under 5 MB."}), 413
            directory = os.path.join(current_app.instance_path, "avatars", str(current_user.id))
            os.makedirs(directory, exist_ok=True)
            name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{secure_filename(picture.filename)[:100] or 'profile-image'}"
            path = os.path.join(directory, name)
            picture.save(path); record.picture_path = path
        db.session.commit()
        return jsonify({"success": True, "message": "Profile updated."}) if request.is_json else render_template("features/profile.html", profile=record, avatars=AVATARS, saved=True)
    return render_template("features/profile.html", profile=record, avatars=AVATARS)


@features_bp.route("/profile/picture")
@login_required
def profile_picture():
    row = UserProfile.query.filter_by(user_id=current_user.id).first_or_404()
    if not row.picture_path or not os.path.isfile(row.picture_path): abort(404)
    return send_file(row.picture_path, conditional=True)


@features_bp.route("/profile/password", methods=["POST"])
@login_required
def change_password():
    data = request.get_json() or {}
    if not current_user.check_password(data.get("current_password", "")):
        return jsonify({"error": "Current password is incorrect."}), 400
    new = data.get("new_password", "")
    if len(new) < 10 or not re.search(r"[A-Z]", new) or not re.search(r"[0-9]", new) or not re.search(r"[^A-Za-z0-9]", new):
        return jsonify({"error": "Use at least 10 characters with uppercase, number, and symbol."}), 400
    current_user.set_password(new); db.session.commit()
    return jsonify({"success": True, "message": "Password changed."})


@features_bp.route("/profile/delete", methods=["POST"])
@login_required
def delete_account():
    from flask_login import logout_user
    data = request.get_json() or {}
    if not current_user.check_password(data.get("password", "")):
        return jsonify({"error": "Password did not match."}), 400
    user = current_user._get_current_object()
    SessionDocument.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    CalendarEvent.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    from app.models import GameUsage, GameScore
    GameUsage.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    GameScore.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    Subscription.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    PaymentRecord.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    CodeSnippet.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    EmailOTP.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    LearningBehavior.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    TopicMastery.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    AttendanceStamp.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    UserProfile.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    for folder in (os.path.join(current_app.instance_path, "documents", str(user.id)), os.path.join(current_app.instance_path, "avatars", str(user.id))):
        if os.path.isdir(folder):
            import shutil
            shutil.rmtree(folder)
    logout_user(); db.session.delete(user); db.session.commit()
    return jsonify({"success": True, "redirect": "/"})


@features_bp.route("/session/<int:session_id>/documents", methods=["GET", "POST"])
@login_required
def session_documents(session_id):
    study = LearningSession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()
    if request.method == "GET":
        return jsonify([{"id": d.id, "filename": d.filename, "url": f"/features/documents/{d.id}", "can_preview": current_user.plan in {"pro", "team"}} for d in SessionDocument.query.filter_by(session_id=study.id, user_id=current_user.id).all()])
    upload = request.files.get("file")
    if not upload or not upload.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Upload a PDF file."}), 400
    try:
        from pypdf import PdfReader
        reader = PdfReader(upload.stream)
        if len(reader.pages) > 100:
            return jsonify({"error": "PDF must contain 100 pages or fewer."}), 400
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception as exc:
        return jsonify({"error": f"Could not read this PDF: {str(exc)[:180]}"}), 400
    if len(text) < 80:
        return jsonify({"error": "This PDF has no readable text. Scanned PDFs need OCR before upload."}), 400
    chunks = _chunks(text)
    # Topic gate uses hybrid lexical ranking and provider embeddings when available.
    topic_terms = set(_tokenize(study.topic)); best_overlap = max((len(topic_terms & set(_tokenize(c))) for c in chunks), default=0)
    supported_embeddings = current_user.ai_provider in {"openai", "google", "huggingface"}
    stored_vectors = []
    topic_vector = _embeddings([study.topic]) if supported_embeddings else []
    if topic_vector:
        for start in range(0, len(chunks), 32): stored_vectors.extend(_embeddings(chunks[start:start + 32]))
        if len(stored_vectors) != len(chunks): stored_vectors = []
    semantic_hits = sorted((_cosine(topic_vector[0], vector), i) for i, vector in enumerate(stored_vectors)) if topic_vector and stored_vectors else []
    semantic_threshold = float(os.getenv("BYOB_SEMANTIC_MIN", "0.30"))
    # 0.30 is a configurable starting heuristic, not a universal evidence-based
    # cutoff; acceptance also considers topic-term evidence and relative ranking.
    semantic_gate = len(semantic_hits) >= 2 and semantic_hits[-1][0] >= semantic_threshold and semantic_hits[-1][0] > semantic_hits[-2][0] * 1.12
    relevant = best_overlap >= min(2, max(1, len(topic_terms))) or semantic_gate
    if not relevant:
        return jsonify({"error": "This PDF does not look related to this session topic. Please upload notes on the current topic."}), 422
    directory = os.path.join(current_app.instance_path, "documents", str(current_user.id), str(study.id))
    os.makedirs(directory, exist_ok=True)
    filename = secure_filename(upload.filename)[:150] or "study-notes.pdf"
    path = os.path.join(directory, f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{filename}")
    upload.stream.seek(0); upload.save(path)
    doc = SessionDocument(session_id=study.id, user_id=current_user.id, filename=filename, storage_path=path, extracted_text=text,
                          embedding_provider=current_user.ai_provider, embeddings_json=json.dumps(stored_vectors) if stored_vectors else None)
    db.session.add(doc); db.session.commit()
    return jsonify({"success": True, "document": {"id": doc.id, "filename": filename, "url": f"/features/documents/{doc.id}", "can_preview": current_user.plan in {"pro", "team"}}})


@features_bp.route("/documents/<int:document_id>")
@login_required
def open_document(document_id):
    doc = SessionDocument.query.filter_by(id=document_id, user_id=current_user.id).first_or_404()
    if current_user.plan not in {"pro", "team"}:
        return jsonify({"error": "Split-screen PDF preview is available on Scholar and Academy. Your uploaded document remains available to ground this session."}), 403
    return send_file(doc.storage_path, mimetype=mimetypes.guess_type(doc.filename)[0] or "application/octet-stream", as_attachment=False, download_name=doc.filename)


@features_bp.route("/relax")
@login_required
def relax(): return render_template("features/relax.html")


@features_bp.route("/music")
@login_required
def music(): return render_template("features/music.html")


@features_bp.route("/calendar", methods=["GET", "POST"])
@login_required
def calendar():
    if request.method == "POST":
        data = request.get_json() or {}
        try: starts = datetime.fromisoformat(data.get("starts_at", ""))
        except ValueError: return jsonify({"error": "Choose a valid date and time."}), 400
        event = CalendarEvent(user_id=current_user.id, title=data.get("title", "")[:160], details=data.get("details", "")[:1000], starts_at=starts)
        if not event.title: return jsonify({"error": "Event title is required."}), 400
        db.session.add(event); db.session.commit()
        return jsonify({"success": True, "id": event.id})
    now = datetime.utcnow()
    year = request.args.get("year", now.year, type=int); month = request.args.get("month", now.month, type=int)
    if month < 1 or month > 12: month, year = now.month, now.year
    first = date(year, month, 1); start = first - timedelta(days=first.weekday())
    grid = [start + timedelta(days=i) for i in range(42)]
    attendance = {row.attended_on for row in AttendanceStamp.query.filter(
        AttendanceStamp.user_id == current_user.id,
        AttendanceStamp.attended_on >= date(year, 1, 1),
        AttendanceStamp.attended_on <= date(year, 12, 31)).all()}
    event_days = {row.starts_at.date() for row in CalendarEvent.query.filter_by(user_id=current_user.id).all()}
    rows = CalendarEvent.query.filter_by(user_id=current_user.id).order_by(CalendarEvent.starts_at).all()
    prev_month = (first - timedelta(days=1)); next_month = (date(year, month, pycalendar.monthrange(year, month)[1]) + timedelta(days=1))
    month_attendance = sum(1 for day in attendance if day.month == month)
    return render_template("features/calendar.html", events=rows, grid=grid, view_year=year,
        view_month=month, month_name=pycalendar.month_name[month], today=date.today(), attendance=attendance,
        event_days=event_days, month_attendance=month_attendance, year_attendance=len(attendance),
        prev_month=prev_month, next_month=next_month)


@features_bp.route("/calculator")
@login_required
def calculator():
    return render_template("features/calculator.html")


@features_bp.route("/video")
@login_required
def video():
    sessions = LearningSession.query.filter_by(user_id=current_user.id).order_by(LearningSession.started_at.desc()).limit(30).all()
    return render_template("features/video.html", sessions=sessions)


@features_bp.route("/video/transcript", methods=["POST"])
@login_required
def video_transcript():
    session_id = request.form.get("session_id", type=int)
    study = LearningSession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()
    upload = request.files.get("transcript")
    transcript = ""; filename = "video-transcript.txt"
    if upload and upload.filename:
        if not upload.filename.lower().endswith((".txt", ".vtt", ".srt")):
            return jsonify({"error": "Transcript must be a .txt, .vtt, or .srt file."}), 400
        transcript = upload.read(2_000_000).decode("utf-8", errors="ignore"); filename = secure_filename(upload.filename)
    else:
        video = request.files.get("video")
        if video and video.filename:
            if current_user.ai_provider != "openai":
                return jsonify({"error": "Automatic video transcription currently needs an OpenAI API key. You can attach a .txt, .vtt, or .srt transcript with any tutor provider."}), 400
            import shutil, subprocess, tempfile
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg: return jsonify({"error": "Install ffmpeg to transcribe local video, or upload its captions file."}), 503
            tempdir = tempfile.mkdtemp(prefix="learnorbit-transcript-")
            try:
                source = os.path.join(tempdir, secure_filename(video.filename) or "source-video")
                audio = os.path.join(tempdir, "audio.mp3"); video.save(source)
                subprocess.run([ffmpeg, "-y", "-i", source, "-vn", "-t", "600", "-ac", "1", "-b:a", "64k", audio], check=True, timeout=90, capture_output=True)
                with open(audio, "rb") as audio_file:
                    import requests
                    response = requests.post("https://api.openai.com/v1/audio/transcriptions", headers={"Authorization": f"Bearer {current_user.get_ai_api_key('openai')}"}, files={"file": ("audio.mp3", audio_file, "audio/mpeg")}, data={"model": "whisper-1", "response_format": "text"}, timeout=120)
                    response.raise_for_status(); transcript = response.text
                filename = (secure_filename(video.filename) or "video") + "-transcript.txt"
            except Exception as exc:
                return jsonify({"error": f"Could not transcribe this video. Check ffmpeg and OpenAI access: {str(exc)[:160]}"}), 502
            finally:
                import shutil
                shutil.rmtree(tempdir, ignore_errors=True)
        else:
            link = request.form.get("video_url", "").strip()
            if link:
                return jsonify({"error": "A video link alone cannot provide a transcript here. Upload its captions (.vtt/.srt/.txt); YouTube caption downloads require video-owner authorization."}), 400
            return jsonify({"error": "Choose a video file or provide a transcript/captions file."}), 400
    transcript = transcript.strip()
    if len(transcript) < 80: return jsonify({"error": "The transcript is empty or too short to ground a tutor."}), 400
    terms = set(_tokenize(study.topic)); overlap = max((len(terms & set(_tokenize(c))) for c in _chunks(transcript)), default=0)
    vectors = _embeddings([study.topic, transcript[:8000]])
    semantic_ok = len(vectors) == 2 and _cosine(vectors[0], vectors[1]) >= float(os.getenv("BYOB_SEMANTIC_MIN", "0.30"))
    if overlap < min(2, max(1, len(terms))) and not semantic_ok:
        return jsonify({"error": "This transcript does not appear relevant to the selected session topic. Choose a related session or transcript."}), 422
    directory = os.path.join(current_app.instance_path, "documents", str(current_user.id), str(study.id)); os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"video-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{filename}")
    with open(path, "w", encoding="utf-8") as out: out.write(transcript)
    chunks = _chunks(transcript); stored_vectors = []
    if vectors:
        for start in range(0, len(chunks), 32): stored_vectors.extend(_embeddings(chunks[start:start + 32]))
        if len(stored_vectors) != len(chunks): stored_vectors = []
    doc = SessionDocument(session_id=study.id, user_id=current_user.id, filename=filename, storage_path=path, extracted_text=transcript,
                          embedding_provider=current_user.ai_provider, embeddings_json=json.dumps(stored_vectors) if stored_vectors else None)
    db.session.add(doc); db.session.commit()
    return jsonify({"success": True, "message": f"Transcript added to {study.topic}. Open the session to chat with it." , "redirect": f"/tutor/{study.id}"})


PLANS = {"pro": (9.99, "Scholar"), "team": (24.99, "Academy")}


@features_bp.route("/pricing")
@login_required
def pricing():
    active = Subscription.query.filter_by(user_id=current_user.id, status="active").order_by(Subscription.id.desc()).first()
    return render_template("features/pricing.html", plans=PLANS, subscription=active)


@features_bp.route("/checkout/<plan>")
@login_required
def checkout_page(plan):
    if plan not in PLANS: abort(404)
    return render_template("features/checkout.html", plan=plan, plan_name=PLANS[plan][1], amount=PLANS[plan][0])


@features_bp.route("/checkout", methods=["POST"])
@login_required
def checkout():
    data = request.get_json() or {}
    plan = data.get("plan")
    if plan not in PLANS: return jsonify({"error": "Choose a valid subscription."}), 400
    if not data.get("cardholder", "").strip() or not re.fullmatch(r"\d{4}", data.get("card_last4", "")):
        return jsonify({"error": "Enter a cardholder name and the last four digits for the demo checkout."}), 400
    amount, _ = PLANS[plan]
    prior = Subscription.query.filter_by(user_id=current_user.id, status="active").order_by(Subscription.id.desc()).first()
    now = datetime.utcnow()
    if prior and prior.plan == plan:
        return jsonify({"error": "This plan is already active."}), 400
    if prior and amount < PLANS.get(prior.plan, (0,))[0]:
        prior.scheduled_plan = plan
        prior.cancel_at_period_end = False
        db.session.commit()
        return jsonify({"success": True, "message": f"Your downgrade to {PLANS[plan][1]} is scheduled for {prior.current_period_end.strftime('%B %d, %Y')}. Your current plan remains active until then."})
    if prior:
        prior.status = "replaced"
    sub = Subscription(user_id=current_user.id, plan=plan, current_period_start=now, current_period_end=now + timedelta(days=30))
    payment = PaymentRecord(user_id=current_user.id, plan=plan, amount=amount, status="demo", reference=f"LO-DEMO-{now.strftime('%Y%m%d%H%M%S%f')}")
    current_user.plan = plan
    db.session.add_all([sub, payment]); db.session.commit()
    email_sent = _email_invoice(payment)
    return jsonify({"success": True, "message": "Demo checkout complete. No real payment was collected." + (" Invoice emailed." if email_sent else " Download your invoice; email delivery is not configured."), "invoice": f"/features/invoice/{payment.id}"})


@features_bp.route("/subscription/cancel", methods=["POST"])
@login_required
def cancel_subscription():
    sub = Subscription.query.filter_by(user_id=current_user.id, status="active").order_by(Subscription.id.desc()).first()
    if not sub: return jsonify({"error": "No active subscription to cancel."}), 404
    sub.cancel_at_period_end = True; db.session.commit()
    return jsonify({"success": True, "message": f"Subscription will end on {sub.current_period_end.strftime('%B %d, %Y')}. Your access remains until then."})


def _invoice_pdf(payment):
    from fpdf import FPDF
    import unicodedata
    def plain(value): return unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    pdf = FPDF(); pdf.add_page(); pdf.set_auto_page_break(auto=False)
    pdf.set_fill_color(40,107,91);pdf.rect(0,0,210,12,"F")
    pdf.set_xy(18,25);pdf.set_font("Helvetica","B",24);pdf.set_text_color(32,43,38);pdf.cell(112,13,"LearnOrbit",new_x="RIGHT",new_y="TOP")
    pdf.set_font("Helvetica","B",11);pdf.set_text_color(40,107,91);pdf.cell(0,13,"DEMO INVOICE",align="R",new_x="LMARGIN",new_y="NEXT")
    pdf.set_draw_color(40,107,91);pdf.set_line_width(.8);pdf.line(18,45,192,45)
    pdf.set_xy(18,55);pdf.set_font("Helvetica","",10);pdf.set_text_color(90,104,96);pdf.cell(0,7,"PAYMENT REFERENCE",new_x="LMARGIN",new_y="NEXT")
    pdf.set_font("Helvetica","B",13);pdf.set_text_color(32,43,38);pdf.cell(0,9,plain(payment.reference),new_x="LMARGIN",new_y="NEXT")
    pdf.set_fill_color(226,243,235);pdf.set_draw_color(186,214,201);pdf.rect(18,83,174,74,"DF")
    details=[("STUDENT",f"{current_user.username} ({current_user.email})"),("PLAN",PLANS[payment.plan][1]),("ISSUED",payment.created_at.strftime('%d %B %Y')),("STATUS","DEMO ONLY - no real charge processed")]
    y=92
    for label,value in details:
        pdf.set_xy(26,y);pdf.set_font("Helvetica","B",8);pdf.set_text_color(40,107,91);pdf.cell(35,7,label)
        pdf.set_font("Helvetica","",10);pdf.set_text_color(32,43,38);pdf.cell(0,7,plain(value));y+=14
    pdf.set_draw_color(40,107,91);pdf.set_line_width(1.5);pdf.ellipse(139,174,48,30,"D");pdf.set_font("Helvetica","B",10);pdf.set_text_color(40,107,91);pdf.set_xy(141,182);pdf.cell(44,6,"LEARNORBIT",align="C",new_x="LMARGIN",new_y="NEXT");pdf.set_font("Helvetica","B",7);pdf.set_xy(141,189);pdf.cell(44,5,"DEMO PAYMENT",align="C")
    pdf.set_xy(18,173);pdf.set_font("Helvetica","B",10);pdf.set_text_color(90,104,96);pdf.cell(45,9,"TOTAL",new_x="LMARGIN",new_y="NEXT");pdf.set_font("Helvetica","B",22);pdf.set_text_color(32,43,38);pdf.cell(100,15,plain(f"USD {payment.amount:.2f}"))
    pdf.set_xy(18,230);pdf.set_font("Helvetica","I",9);pdf.set_text_color(90,104,96);pdf.multi_cell(130,6,"This document records a LearnOrbit demonstration checkout. No real payment was processed.")
    pdf.set_fill_color(40,107,91);pdf.rect(0,285,210,12,"F")
    return bytes(pdf.output())


def _email_invoice(payment):
    host = os.getenv("SMTP_HOST"); recipient = current_user.email
    if not host: return False
    try:
        import smtplib
        from email.message import EmailMessage
        message = EmailMessage(); message["Subject"] = "Your LearnOrbit demo invoice"; message["From"] = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "")); message["To"] = recipient
        message.set_content("Attached is your LearnOrbit demo invoice. This is a simulated checkout; no real payment was collected.")
        message.add_attachment(_invoice_pdf(payment), maintype="application", subtype="pdf", filename=f"{payment.reference}.pdf")
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=15) as server:
            server.starttls()
            if os.getenv("SMTP_USER"): server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD", ""))
            server.send_message(message)
        return True
    except Exception:
        current_app.logger.exception("Invoice email delivery failed")
        return False


@features_bp.route("/invoice/<int:payment_id>")
@login_required
def invoice(payment_id):
    payment = PaymentRecord.query.filter_by(id=payment_id, user_id=current_user.id).first_or_404()
    from io import BytesIO
    return send_file(BytesIO(_invoice_pdf(payment)), mimetype="application/pdf", as_attachment=True, download_name=f"{payment.reference}.pdf")


@features_bp.route("/practice-code", methods=["GET", "POST"])
@login_required
def practice_code():
    if current_user.plan == "free": return render_template("features/upgrade_required.html", feature="Practice Code"), 403
    if request.method == "POST":
        data = request.get_json() or {}; code = data.get("source_code", "")
        if len(code) > 20000: return jsonify({"error": "Code is limited to 20,000 characters."}), 413
        item = CodeSnippet.query.filter_by(id=data.get("id"), user_id=current_user.id).first() if data.get("id") else None
        if not item: item = CodeSnippet(user_id=current_user.id, source_code="")
        item.title = data.get("title", "Untitled")[:120]; item.language = data.get("language", "python")[:24]; item.source_code = code
        db.session.add(item); db.session.commit()
        return jsonify({"success": True, "id": item.id})
    snippets = CodeSnippet.query.filter_by(user_id=current_user.id).order_by(CodeSnippet.updated_at.desc()).all()
    return render_template("features/practice_code.html", snippets=snippets)


@features_bp.route("/practice-code/run", methods=["POST"])
@login_required
def run_code():
    if current_user.plan == "free": return jsonify({"error": "Practice Code requires Scholar or Academy."}), 403
    now_ts = datetime.utcnow().timestamp(); runs = [stamp for stamp in session.get("code_run_times", []) if now_ts - stamp < 60]
    if len(runs) >= 5: return jsonify({"error": "Please wait a minute before running more code."}), 429
    runs.append(now_ts); session["code_run_times"] = runs
    data = request.get_json() or {}; language = data.get("language", "python")
    ids = {"python": 71, "javascript": 63, "java": 62, "cpp": 54, "c": 50}
    if language not in ids or len(data.get("source_code", "")) > 20000: return jsonify({"error": "Unsupported language or code is too long."}), 400
    endpoint = os.getenv("JUDGE0_ENDPOINT", "https://ce.judge0.com")
    try:
        import requests
        response = requests.post(endpoint.rstrip("/") + "/submissions?base64_encoded=false&wait=true", json={"language_id": ids[language], "source_code": data.get("source_code", ""), "stdin": data.get("stdin", "")[:4000]}, timeout=15)
        response.raise_for_status(); result = response.json()
        return jsonify({"stdout": result.get("stdout"), "stderr": result.get("stderr"), "compile_output": result.get("compile_output"), "status": (result.get("status") or {}).get("description", "Unknown"), "time": result.get("time"), "memory": result.get("memory")})
    except Exception as exc:
        return jsonify({"error": f"Code runner unavailable. Configure JUDGE0_ENDPOINT or retry later. {str(exc)[:120]}"}), 502
