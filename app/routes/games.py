"""
LearnOrbit Games Routes — Brain Break Zone
"""

from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user
from app import db, csrf
from app.models import GameUsage, GameScore, User

games_bp = Blueprint("games", __name__)

GAMES = [
    {"id": "tictactoe", "name": "Tic Tac Toe", "icon": "grid-3x3", "desc": "Classic! Beat the AI or a friend.", "color": "#6366f1", "unit": "wins", "better": "high", "instructions": "Take turns placing X or O in an empty square. Make three in a row horizontally, vertically, or diagonally to win. On a laptop, click a square; on a phone or tablet, tap it."},
    {"id": "memory", "name": "Memory Match", "icon": "layers-2", "desc": "Flip cards to match pairs. Train your brain!", "color": "#8b5cf6", "unit": "pts", "better": "high", "instructions": "Flip two cards at a time and remember their positions. Matching pairs stay revealed; find all pairs in as few moves as you can. Click cards with a mouse or tap them on a touchscreen."},
    {"id": "snake", "name": "Snake", "icon": "move", "desc": "Grow the snake, don't crash. Retro vibes!", "color": "#10b981", "unit": "pts", "better": "high", "instructions": "Guide the snake to collect food and grow without hitting a wall or its own tail. Use arrow keys or WASD on a keyboard; use the on-screen direction pad or swipe on touchscreens."},
    {"id": "wordle", "name": "Wordle", "icon": "case-sensitive", "desc": "Guess the 5-letter word in 6 tries.", "color": "#f59e0b", "unit": "pts", "better": "high", "instructions": "Enter a five-letter word, then submit it. Tile colors show which letters are correct and in the right place, present elsewhere, or absent. Type and press Enter on a keyboard, or use the on-screen keys on a touchscreen."},
    {"id": "2048", "name": "2048", "icon": "grid-2x2-check", "desc": "Slide tiles and reach 2048. Math-ish!", "color": "#ef4444", "unit": "pts", "better": "high", "instructions": "Move all tiles in one direction; equal values combine into their sum. Keep combining to reach 2048 without filling the board. Use arrow keys or WASD on a laptop, or swipe in a direction on a touchscreen."},
    {"id": "breakout", "name": "Breakout", "icon": "blocks", "desc": "Classic brick-breaker. Stress reliever!", "color": "#06b6d4", "unit": "pts", "better": "high", "instructions": "Move the paddle to bounce the ball into every brick. Keep the ball in play and clear as many bricks as possible. Move your mouse on a laptop or drag your finger across the play area on a touchscreen."},
    {"id": "quickmath", "name": "Quick Math", "icon": "sigma", "desc": "Solve quick mental-math rounds.", "color": "#f59e0b", "unit": "correct", "better": "high", "instructions": "Press Start, solve each multiplication problem, and submit before the 60-second round ends. Type your answer and press Enter, or use the Submit button; both work on touchscreens."},
    {"id": "reaction", "name": "Reaction Lab", "icon": "mouse-pointer-2", "desc": "Test your focus and reaction time.", "color": "#06b6d4", "unit": "ms", "better": "low", "instructions": "Start a round and wait for the signal to change; click or tap as soon as it does. Do not click early. A lower time in milliseconds is better."},
]
GAMES_BY_ID = {game["id"]: game for game in GAMES}


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
    high_ids = [g["id"] for g in GAMES if g["better"] != "low"]
    low_ids = [g["id"] for g in GAMES if g["better"] == "low"]
    rows = []
    if high_ids:
        rows += db.session.query(GameScore.game_id, func.max(GameScore.score)).filter(
            GameScore.user_id == current_user.id, GameScore.game_id.in_(high_ids)).group_by(GameScore.game_id).all()
    if low_ids:
        rows += db.session.query(GameScore.game_id, func.min(GameScore.score)).filter(
            GameScore.user_id == current_user.id, GameScore.game_id.in_(low_ids)).group_by(GameScore.game_id).all()
    return jsonify({
        game_id: {
            "score": score,
            "color": GAMES_BY_ID[game_id]["color"],
            "unit": GAMES_BY_ID[game_id]["unit"],
            "name": GAMES_BY_ID[game_id]["name"],
        }
        for game_id, score in rows
    })


@games_bp.route("/leaderboard")
@login_required
def leaderboard():
    if not current_app.config["PRICING"].get(current_user.plan, {}).get("global_leaderboard", False):
        return render_template("games/leaderboard.html", boards=[], locked=True)
    from sqlalchemy import func

    boards = []
    for game in GAMES:
        score_value = func.min(GameScore.score) if game["better"] == "low" else func.max(GameScore.score)
        rows = (db.session.query(User.username, score_value.label("score"))
                .join(GameScore, GameScore.user_id == User.id)
                .filter(GameScore.game_id == game["id"])
                .group_by(User.id, User.username)
                .order_by(score_value.asc() if game["better"] == "low" else score_value.desc())
                .limit(10).all())
        boards.append({"game": game, "players": rows})
    return render_template("games/leaderboard.html", boards=boards, locked=False)
