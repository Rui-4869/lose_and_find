from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from flask import Flask, redirect, render_template, request, url_for
from flask import flash

from agent.rule_agent import RuleBasedAgent
from config import Config
from database import db
from models import FoundItem, LostItem
from services import MatchService


ITEM_CATEGORIES = [
    "证件",
    "电子产品",
    "书本资料",
    "衣物配件",
    "钥匙",
    "生活用品",
    "其他",
]


app = Flask(__name__)
app.config.from_object(Config)


def _ensure_sqlite_dir(database_uri: str) -> None:
    if not database_uri.startswith("sqlite:///"):
        return
    raw_path = database_uri.replace("sqlite:///", "", 1)
    db_path = Path(raw_path)
    if not db_path.is_absolute():
        db_path = Path(app.root_path) / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_dir(app.config["SQLALCHEMY_DATABASE_URI"])

db.init_app(app)

with app.app_context():
    db.create_all()

match_service = MatchService(db.session)
agent = RuleBasedAgent(match_service)


def _parse_datetime(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(UTC)
    # HTML datetime-local input uses format YYYY-MM-DDTHH:MM
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC)


@app.get("/")
def index():
    highlight_lost_id = request.args.get("lost_id", type=int)
    highlight_found_id = request.args.get("found_id", type=int)
    highlight_match_id = request.args.get("match_id", type=int)

    lost_items = match_service.all_lost_items()
    found_items = match_service.all_found_items()

    if highlight_lost_id:
        matches = match_service.matches_for_lost(highlight_lost_id)
    elif highlight_found_id:
        matches = match_service.matches_for_found(highlight_found_id)
    else:
        matches = match_service.recent_matches()

    return render_template(
        "index.html",
        categories=ITEM_CATEGORIES,
        lost_items=lost_items,
        found_items=found_items,
        matches=matches,
        highlight_lost_id=highlight_lost_id,
        highlight_found_id=highlight_found_id,
        highlight_match_id=highlight_match_id,
    )


@app.post("/lost")
def create_lost_item():
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    location = request.form.get("location", "").strip()
    occurred_at = _parse_datetime(request.form.get("occurred_at"))
    reporter_name = request.form.get("reporter_name", "").strip() or None
    contact_info = request.form.get("contact_info", "").strip() or None

    if not category or not description or not location:
        flash("请填写完整的失物信息。", "danger")
        return redirect(url_for("index"))

    lost_item = LostItem(
        category=category,
        description=description,
        location=location,
        occurred_at=occurred_at,
        reporter_name=reporter_name,
        contact_info=contact_info,
    )
    db.session.add(lost_item)
    db.session.commit()

    agent.handle_new_lost(lost_item)
    flash("失物信息已提交，智能体推荐已更新。", "success")
    return redirect(url_for("index", lost_id=lost_item.id))


@app.post("/found")
def create_found_item():
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    location = request.form.get("location", "").strip()
    occurred_at = _parse_datetime(request.form.get("occurred_at"))
    reporter_name = request.form.get("reporter_name", "").strip() or None
    contact_info = request.form.get("contact_info", "").strip() or None

    if not category or not description or not location:
        flash("请填写完整的招领信息。", "danger")
        return redirect(url_for("index"))

    found_item = FoundItem(
        category=category,
        description=description,
        location=location,
        occurred_at=occurred_at,
        reporter_name=reporter_name,
        contact_info=contact_info,
    )
    db.session.add(found_item)
    db.session.commit()

    agent.handle_new_found(found_item)
    flash("招领信息已提交，智能体推荐已更新。", "success")
    return redirect(url_for("index", found_id=found_item.id))


@app.post("/lost/<int:lost_id>/delete")
def delete_lost_item(lost_id: int):
    match_service.delete_lost_item(lost_id)
    flash("失物信息已删除。", "info")
    return redirect(url_for("index"))


@app.post("/found/<int:found_id>/delete")
def delete_found_item(found_id: int):
    match_service.delete_found_item(found_id)
    flash("招领信息已删除。", "info")
    return redirect(url_for("index"))


@app.post("/matches/<int:match_id>/complete")
def complete_match(match_id: int):
    match = match_service.mark_match_completed(match_id)
    if match is None:
        flash("未找到匹配记录。", "warning")
        return redirect(url_for("index"))
    flash("匹配已确认完成。", "success")
    return redirect(url_for("index", match_id=match.id))


if __name__ == "__main__":
    app.run(debug=True)
