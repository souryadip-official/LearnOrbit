"""LearnOrbit's small, ledger-backed token and cosmetic reward shop."""

from datetime import datetime

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import OrbitReward, OrbitTokenTransaction, OrbitWallet

rewards_bp = Blueprint("rewards", __name__)
REWARDS = {
    "curiosity": {"name": "Curiosity Badge", "cost": 15, "icon": "sparkles"},
    "orbit": {"name": "Orbit Explorer Badge", "cost": 30, "icon": "orbit"},
    "supernova": {"name": "Supernova Badge", "cost": 50, "icon": "star"},
}


@rewards_bp.route("/")
@login_required
def index():
    wallet = OrbitWallet.query.filter_by(user_id=current_user.id).first()
    transactions = (OrbitTokenTransaction.query.filter_by(user_id=current_user.id)
                    .order_by(OrbitTokenTransaction.created_at.desc()).limit(12).all())
    owned = {reward.reward_key for reward in OrbitReward.query.filter_by(user_id=current_user.id).all()}
    return render_template(
        "features/rewards.html",
        balance=wallet.balance if wallet else 0,
        transactions=transactions,
        owned=owned,
        rewards=REWARDS,
    )


@rewards_bp.route("/redeem", methods=["POST"])
@login_required
def redeem():
    data = request.get_json(silent=True)
    reward_key = data.get("reward_key") if isinstance(data, dict) else None
    reward = REWARDS.get(reward_key)
    if not reward:
        return jsonify({"error": "Choose a reward from the catalog."}), 400
    if OrbitReward.query.filter_by(user_id=current_user.id, reward_key=reward_key).first():
        return jsonify({"error": "You already own this reward."}), 409

    wallet = OrbitWallet.query.filter_by(user_id=current_user.id).first()
    if not wallet:
        return jsonify({"error": f"You need {reward['cost']} Orbit Tokens for this reward."}), 400
    debited = (OrbitWallet.query.filter_by(user_id=current_user.id)
               .filter(OrbitWallet.balance >= reward["cost"])
               .update(
                   {OrbitWallet.balance: OrbitWallet.balance - reward["cost"]},
                   synchronize_session=False,
               ))
    if not debited:
        db.session.rollback()
        return jsonify({"error": f"You need {reward['cost']} Orbit Tokens for this reward."}), 400
    db.session.add(OrbitReward(user_id=current_user.id, reward_key=reward_key))
    db.session.add(OrbitTokenTransaction(
        user_id=current_user.id,
        amount=-reward["cost"],
        event_key=f"redeem:{reward_key}",
        description=f"Redeemed {reward['name']}",
    ))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "This reward was just redeemed in another request. Refresh your wallet."}), 409
    wallet = db.session.get(OrbitWallet, wallet.id)
    return jsonify({"success": True, "balance": wallet.balance, "reward": reward["name"]})
