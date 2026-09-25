"""
LearnOrbit Games Routes — Brain Break Zone
"""

from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from app import db, csrf
from app.models import GameUsage, GameScore

games_bp = Blueprint("games", __name__)

GAMES = [
    {"id": "tictactoe", "name": "Tic Tac Toe", "icon": "grid-3x3", "desc": "Classic! Beat the AI or a friend.", "color": "#6366f1"},
    {"id": "memory", "name": "Memory Match", "icon": "layers-2", "desc": "Flip cards to match pairs. Train your brain!", "color": "#8b5cf6"},
    {"id": "snake", "name": "Snake", "icon": "move", "desc": "Grow the snake, don't crash. Retro vibes!", "color": "#10b981"},
    {"id": "wordle", "name": "Wordle", "icon": "case-sensitive", "desc": "Guess the 5-letter word in 6 tries.", "color": "#f59e0b"},
    {"id": "2048", "name": "2048", "icon": "grid-2x2-check", "desc": "Slide tiles and reach 2048. Math-ish!", "color": "#ef4444"},
    {"id": "breakout", "name": "Breakout", "icon": "blocks", "desc": "Classic brick-breaker. Stress reliever!", "color": "#06b6d4"},
    {"id": "quickmath", "name": "Quick Math", "icon": "sigma", "desc": "Solve quick mental-math rounds.", "color": "#f59e0b"},
    {"id": "reaction", "name": "Reaction Lab", "icon": "mouse-pointer-2", "desc": "Test your focus and reaction time.", "color": "#06b6d4"},
]


@games_bp.route("/")
@login_required
def index():
    since = datetime.utcnow() - timedelta(hours=1)
    rows = GameUsage.query.filter(GameUsage.user_id == current_user.id, GameUsage.started_at >= since).all()
    used = sum(max(0, ((row.ended_at or datetime.utcnow()) - row.started_at).total_seconds()) for row in rows)
    remaining = max(0, 900 - int(used))
    if remaining == 0:
        return render_template("features/games_locked.html", seconds_left=remaining), 429
    return render_template("games/index.html", games=GAMES, game_seconds_left=remaining)


@games_bp.route("/<game_id>")
@login_required
def play(game_id):
    game = next((g for g in GAMES if g["id"] == game_id), None)
    if not game:
        from flask import abort
        abort(404)
    since = datetime.utcnow() - timedelta(hours=1)
    rows = GameUsage.query.filter(GameUsage.user_id == current_user.id, GameUsage.started_at >= since).all()
    used = sum(max(0, ((row.ended_at or datetime.utcnow()) - row.started_at).total_seconds()) for row in rows)
    if used >= 900:
        return render_template("features/games_locked.html", seconds_left=0), 429
    GameUsage.query.filter_by(user_id=current_user.id, ended_at=None).update({"ended_at": datetime.utcnow()})
    db.session.add(GameUsage(user_id=current_user.id)); db.session.commit()
    return render_template(f"games/{game_id}.html", game=game)


@games_bp.route("/usage/close", methods=["POST"])
@login_required
@csrf.exempt
def close_usage():
    row = GameUsage.query.filter_by(user_id=current_user.id, ended_at=None).order_by(GameUsage.started_at.desc()).first()
    if row: row.ended_at = datetime.utcnow(); db.session.commit()
    return jsonify({"success": True})


@games_bp.route("/score", methods=["POST"])
@login_required
def save_score():
    data = request.get_json() or {}
    game_id = str(data.get("game_id", ""))
    if game_id not in {game["id"] for game in GAMES}: return jsonify({"error":"Unknown game."}), 400
    try: score = max(0, min(1_000_000, int(data.get("score", 0))))
    except (TypeError, ValueError): return jsonify({"error": "Score must be a number."}), 400
    db.session.add(GameScore(user_id=current_user.id, game_id=game_id, score=score)); db.session.commit()
    return jsonify({"success":True})


@games_bp.route("/scores")
@login_required
def scores():
    from sqlalchemy import func
    best = db.session.query(GameScore.game_id, func.max(GameScore.score)).filter_by(user_id=current_user.id).group_by(GameScore.game_id).all()
    return jsonify({game: score for game, score in best})
