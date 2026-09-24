"""
LearnOrbit Games Routes — Brain Break Zone
"""

from flask import Blueprint, render_template
from flask_login import login_required

games_bp = Blueprint("games", __name__)

GAMES = [
    {"id": "tictactoe", "name": "Tic Tac Toe", "emoji": "⭕", "desc": "Classic! Beat the AI or a friend.", "color": "#6366f1"},
    {"id": "memory", "name": "Memory Match", "emoji": "🃏", "desc": "Flip cards to match pairs. Train your brain!", "color": "#8b5cf6"},
    {"id": "snake", "name": "Snake", "emoji": "🐍", "desc": "Grow the snake, don't crash. Retro vibes!", "color": "#10b981"},
    {"id": "wordle", "name": "Wordle", "emoji": "🔤", "desc": "Guess the 5-letter word in 6 tries.", "color": "#f59e0b"},
    {"id": "2048", "name": "2048", "emoji": "🔢", "desc": "Slide tiles and reach 2048. Math-ish!", "color": "#ef4444"},
    {"id": "breakout", "name": "Breakout", "emoji": "🧱", "desc": "Classic brick-breaker. Stress reliever!", "color": "#06b6d4"},
]


@games_bp.route("/")
@login_required
def index():
    return render_template("games/index.html", games=GAMES)


@games_bp.route("/<game_id>")
@login_required
def play(game_id):
    game = next((g for g in GAMES if g["id"] == game_id), None)
    if not game:
        from flask import abort
        abort(404)
    return render_template(f"games/{game_id}.html", game=game)
