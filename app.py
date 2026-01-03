from datetime import UTC, datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

import click
from flask import Flask, abort, redirect, render_template, request, url_for
from flask import flash
from flask.cli import with_appcontext
from flask_login import (LoginManager, current_user, login_required,
                         login_user, logout_user)
from sqlalchemy import func
from werkzeug.utils import secure_filename

from agent.rule_agent import RuleBasedAgent
from config import Config
from database import db
from models import FoundItem, LostItem, MatchResult, User
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
Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "请先登录以继续。"
login_manager.login_message_category = "warning"
login_manager.init_app(app)

with app.app_context():
    db.create_all()

match_service = MatchService(db.session)
agent = RuleBasedAgent(match_service)


@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    if not user_id:
        return None
    return db.session.get(User, int(user_id))


def _parse_datetime(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(UTC)
    # HTML datetime-local input uses format YYYY-MM-DDTHH:MM
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC)


def _allowed_image(filename: str) -> bool:
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in app.config["ALLOWED_IMAGE_EXTENSIONS"]


def _save_uploaded_image(file_storage) -> Optional[str]:
    if file_storage is None or file_storage.filename == "":
        return None
    if not _allowed_image(file_storage.filename):
        return None
    secure_name = secure_filename(file_storage.filename)
    ext = secure_name.rsplit(".", 1)[1].lower()
    unique_name = f"{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid4().hex}.{ext}"
    upload_path = Path(app.config["UPLOAD_FOLDER"]) / unique_name
    file_storage.save(upload_path)
    return f"uploads/{unique_name}"


@app.get("/")
def index():
    # Get all items for display (everyone sees the full list)
    all_lost_items = match_service.all_lost_items()
    all_found_items = match_service.all_found_items()
    # support simple search via ?q=keyword (search category, description, location)
    q = (request.args.get('q') or '').strip()
    if q:
        pattern = f"%{q}%"
        all_lost_items = LostItem.query.filter(
            (LostItem.category.ilike(pattern))
            | (LostItem.description.ilike(pattern))
            | (LostItem.location.ilike(pattern))
        ).order_by(LostItem.occurred_at.desc()).all()
        all_found_items = FoundItem.query.filter(
            (FoundItem.category.ilike(pattern))
            | (FoundItem.description.ilike(pattern))
            | (FoundItem.location.ilike(pattern))
        ).order_by(FoundItem.occurred_at.desc()).all()
    
    # Get user's own items if authenticated
    my_lost_items = []
    my_found_items = []
    if current_user.is_authenticated:
        # apply same search when user is logged in
        if q:
            my_lost_items = LostItem.query.filter(
                LostItem.user_id == current_user.id,
                ((LostItem.category.ilike(pattern)) | (LostItem.description.ilike(pattern)) | (LostItem.location.ilike(pattern)))
            ).order_by(LostItem.occurred_at.desc()).all()
            my_found_items = FoundItem.query.filter(
                FoundItem.user_id == current_user.id,
                ((FoundItem.category.ilike(pattern)) | (FoundItem.description.ilike(pattern)) | (FoundItem.location.ilike(pattern)))
            ).order_by(FoundItem.occurred_at.desc()).all()
        else:
            my_lost_items = match_service.all_lost_items(current_user.id, include_all=False)
            my_found_items = match_service.all_found_items(current_user.id, include_all=False)
    
    # Determine which matches to show (user's matches or recent)
    if current_user.is_authenticated:
        matches = match_service.matches_for_user(current_user.id)
    else:
        matches = match_service.recent_matches()

    return render_template(
        "index.html",
        categories=ITEM_CATEGORIES,
        all_lost_items=all_lost_items,
        all_found_items=all_found_items,
        my_lost_items=my_lost_items,
        my_found_items=my_found_items,
        matches=matches,
    )


@app.get('/my', endpoint='my')
@login_required
def my_page():
    # user's personal page (原先登录时的主页内容)
    my_lost_items = match_service.all_lost_items(current_user.id, include_all=False)
    my_found_items = match_service.all_found_items(current_user.id, include_all=False)
    matches = match_service.matches_for_user(current_user.id)
    return render_template('my.html', categories=ITEM_CATEGORIES, my_lost_items=my_lost_items, my_found_items=my_found_items, matches=matches)


@app.get("/lost/<int:lost_id>")
def view_lost_item(lost_id: int):
    item = db.session.get(LostItem, lost_id)
    if item is None:
        flash("失物信息不存在。", "warning")
        return redirect(url_for("index"))
    
    is_owner = current_user.is_authenticated and item.user_id == current_user.id
    item_matches = match_service.matches_for_lost(lost_id) if is_owner else []
    
    return render_template(
        "item_detail.html",
        item=item,
        item_type="lost",
        is_owner=is_owner,
        item_matches=item_matches,
    )


@app.get("/found/<int:found_id>")
def view_found_item(found_id: int):
    item = db.session.get(FoundItem, found_id)
    if item is None:
        flash("招领信息不存在。", "warning")
        return redirect(url_for("index"))
    
    is_owner = current_user.is_authenticated and item.user_id == current_user.id
    item_matches = match_service.matches_for_found(found_id) if is_owner else []
    
    return render_template(
        "item_detail.html",
        item=item,
        item_type="found",
        is_owner=is_owner,
        item_matches=item_matches,
    )


@app.post("/lost/<int:lost_id>/match")
@login_required
def trigger_lost_match(lost_id: int):
    if not match_service.owns_lost_item(lost_id, current_user.id):
        abort(403)
    item = db.session.get(LostItem, lost_id)
    if item is None:
        flash("失物信息不存在。", "warning")
        return redirect(url_for("index"))
    agent.handle_new_lost(item)
    flash("智能体已触发匹配，结果已更新。", "success")
    return redirect(url_for("view_lost_item", lost_id=lost_id))


@app.post("/found/<int:found_id>/match")
@login_required
def trigger_found_match(found_id: int):
    if not match_service.owns_found_item(found_id, current_user.id):
        abort(403)
    item = db.session.get(FoundItem, found_id)
    if item is None:
        flash("招领信息不存在。", "warning")
        return redirect(url_for("index"))
    agent.handle_new_found(item)
    flash("智能体已触发匹配，结果已更新。", "success")
    return redirect(url_for("view_found_item", found_id=found_id))


@app.route("/lost/new", methods=["GET", "POST"])
@login_required
def create_lost_item():
    if request.method == "GET":
        return render_template("lost_form.html", categories=ITEM_CATEGORIES)

    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    location = request.form.get("location", "").strip()
    occurred_at = _parse_datetime(request.form.get("occurred_at"))
    reporter_name = request.form.get("reporter_name", "").strip() or None
    contact_info = request.form.get("contact_info", "").strip() or None
    image_file = request.files.get("image")

    if not category or not description or not location:
        flash("请填写完整的失物信息。", "danger")
        return redirect(url_for("index"))

    image_path: Optional[str] = None
    if image_file and image_file.filename:
        if not _allowed_image(image_file.filename):
            flash("仅支持上传 PNG/JPG/GIF/WebP 等图片格式。", "danger")
            return redirect(url_for("create_lost_item"))
        try:
            image_path = _save_uploaded_image(image_file)
        except Exception as exc:  # pragma: no cover - unexpected file I/O errors
            app.logger.exception("保存失物图片失败", exc_info=exc)
            flash("上传图片时出现问题，请稍后重试。", "danger")
            return redirect(url_for("create_lost_item"))

    if contact_info is None and current_user.is_authenticated:
        contact_info = current_user.username

    lost_item = LostItem(
        category=category,
        description=description,
        location=location,
        occurred_at=occurred_at,
        reporter_name=reporter_name,
        contact_info=contact_info,
        image_path=image_path,
        owner=current_user,
    )
    db.session.add(lost_item)
    db.session.commit()

    agent.handle_new_lost(lost_item)
    flash("失物信息已提交，智能体推荐已更新。", "success")
    return redirect(url_for("index", lost_id=lost_item.id))


# Backwards-compatible POST route used by tests and short-form submissions
@app.post("/lost")
@login_required
def create_lost_item_short():
    return create_lost_item()


@app.route("/lost/<int:lost_id>/edit", methods=["GET", "POST"])
@login_required
def edit_lost_item(lost_id: int):
    if not match_service.owns_lost_item(lost_id, current_user.id):
        abort(403)
    item = db.session.get(LostItem, lost_id)
    if item is None:
        flash("失物信息不存在。", "warning")
        return redirect(url_for("index"))

    if request.method == "GET":
        return render_template("lost_form.html", categories=ITEM_CATEGORIES, item=item)

    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    location = request.form.get("location", "").strip()
    occurred_at = _parse_datetime(request.form.get("occurred_at"))
    reporter_name = request.form.get("reporter_name", "").strip() or None
    contact_info = request.form.get("contact_info", "").strip() or None
    image_file = request.files.get("image")

    if not category or not description or not location:
        flash("请填写完整的失物信息。", "danger")
        return redirect(url_for("view_lost_item", lost_id=lost_id))

    if image_file and image_file.filename:
        if not _allowed_image(image_file.filename):
            flash("仅支持上传 PNG/JPG/GIF/WebP 等图片格式。", "danger")
            return redirect(url_for("edit_lost_item", lost_id=lost_id))
        try:
            image_path = _save_uploaded_image(image_file)
            item.image_path = image_path
        except Exception as exc:  # pragma: no cover - unexpected file I/O errors
            app.logger.exception("保存失物图片失败", exc_info=exc)
            flash("上传图片时出现问题，请稍后重试。", "danger")
            return redirect(url_for("edit_lost_item", lost_id=lost_id))

    # Update fields
    item.category = category
    item.description = description
    item.location = location
    item.occurred_at = occurred_at
    item.reporter_name = reporter_name
    item.contact_info = contact_info or item.contact_info

    db.session.commit()

    # Re-run matching for the edited item
    agent.handle_new_lost(item)
    flash("失物信息已更新。智能体推荐已刷新。", "success")
    return redirect(url_for("view_lost_item", lost_id=lost_id))


@app.route("/found/new", methods=["GET", "POST"])
@login_required
def create_found_item():
    if request.method == "GET":
        return render_template("found_form.html", categories=ITEM_CATEGORIES)

    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    location = request.form.get("location", "").strip()
    occurred_at = _parse_datetime(request.form.get("occurred_at"))
    reporter_name = request.form.get("reporter_name", "").strip() or None
    contact_info = request.form.get("contact_info", "").strip() or None
    image_file = request.files.get("image")

    if not category or not description or not location:
        flash("请填写完整的招领信息。", "danger")
        return redirect(url_for("index"))

    image_path: Optional[str] = None
    if image_file and image_file.filename:
        if not _allowed_image(image_file.filename):
            flash("仅支持上传 PNG/JPG/GIF/WebP 等图片格式。", "danger")
            return redirect(url_for("create_found_item"))
        try:
            image_path = _save_uploaded_image(image_file)
        except Exception as exc:  # pragma: no cover - unexpected file I/O errors
            app.logger.exception("保存招领图片失败", exc_info=exc)
            flash("上传图片时出现问题，请稍后重试。", "danger")
            return redirect(url_for("create_found_item"))

    if contact_info is None and current_user.is_authenticated:
        contact_info = current_user.username

    found_item = FoundItem(
        category=category,
        description=description,
        location=location,
        occurred_at=occurred_at,
        reporter_name=reporter_name,
        contact_info=contact_info,
        image_path=image_path,
        owner=current_user,
    )
    db.session.add(found_item)
    db.session.commit()

    agent.handle_new_found(found_item)
    flash("招领信息已提交，智能体推荐已更新。", "success")
    return redirect(url_for("index", found_id=found_item.id))


# Backwards-compatible POST route used by tests and short-form submissions
@app.post("/found")
@login_required
def create_found_item_short():
    return create_found_item()


@app.route("/found/<int:found_id>/edit", methods=["GET", "POST"])
@login_required
def edit_found_item(found_id: int):
    if not match_service.owns_found_item(found_id, current_user.id):
        abort(403)
    item = db.session.get(FoundItem, found_id)
    if item is None:
        flash("招领信息不存在。", "warning")
        return redirect(url_for("index"))

    if request.method == "GET":
        return render_template("found_form.html", categories=ITEM_CATEGORIES, item=item)

    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    location = request.form.get("location", "").strip()
    occurred_at = _parse_datetime(request.form.get("occurred_at"))
    reporter_name = request.form.get("reporter_name", "").strip() or None
    contact_info = request.form.get("contact_info", "").strip() or None
    image_file = request.files.get("image")

    if not category or not description or not location:
        flash("请填写完整的招领信息。", "danger")
        return redirect(url_for("view_found_item", found_id=found_id))

    if image_file and image_file.filename:
        if not _allowed_image(image_file.filename):
            flash("仅支持上传 PNG/JPG/GIF/WebP 等图片格式。", "danger")
            return redirect(url_for("edit_found_item", found_id=found_id))
        try:
            image_path = _save_uploaded_image(image_file)
            item.image_path = image_path
        except Exception as exc:  # pragma: no cover - unexpected file I/O errors
            app.logger.exception("保存招领图片失败", exc_info=exc)
            flash("上传图片时出现问题，请稍后重试。", "danger")
            return redirect(url_for("edit_found_item", found_id=found_id))

    # Update fields
    item.category = category
    item.description = description
    item.location = location
    item.occurred_at = occurred_at
    item.reporter_name = reporter_name
    item.contact_info = contact_info or item.contact_info

    db.session.commit()

    # Re-run matching for the edited item
    agent.handle_new_found(item)
    flash("招领信息已更新。智能体推荐已刷新。", "success")
    return redirect(url_for("view_found_item", found_id=found_id))


@app.post("/lost/<int:lost_id>/delete")
@login_required
def delete_lost_item(lost_id: int):
    item = db.session.get(LostItem, lost_id)
    if item is None:
        flash("失物信息不存在。", "warning")
        return redirect(url_for("index"))
    # allow owner or admin to delete
    if not (current_user.is_admin or item.user_id == current_user.id):
        abort(403)
    match_service.delete_lost_item(lost_id)
    flash("失物信息已删除。", "info")
    return redirect(url_for("index"))


@app.post("/found/<int:found_id>/delete")
@login_required
def delete_found_item(found_id: int):
    item = db.session.get(FoundItem, found_id)
    if item is None:
        flash("招领信息不存在。", "warning")
        return redirect(url_for("index"))
    # allow owner or admin to delete
    if not (current_user.is_admin or item.user_id == current_user.id):
        abort(403)
    match_service.delete_found_item(found_id)
    flash("招领信息已删除。", "info")
    return redirect(url_for("index"))


@app.post("/matches/<int:match_id>/complete")
@login_required
def complete_match(match_id: int):
    match = db.session.get(MatchResult, match_id)
    if match is None:
        flash("未找到匹配记录。", "warning")
        return redirect(url_for("index"))
    allowed_user_ids = {match.lost_item.user_id, match.found_item.user_id}
    if current_user.id not in allowed_user_ids:
        abort(403)
    match_service.mark_match_completed(match_id)
    flash("匹配已确认完成。", "success")
    return redirect(url_for("index", match_id=match.id))


@app.get("/matches/<int:match_id>/messages")
@login_required
def get_match_messages(match_id: int):
    # only participants can view
    if not match_service.is_match_participant(match_id, current_user.id):
        abort(403)
    messages = match_service.messages_for_match(match_id)
    return {"messages": [m.to_dict() for m in messages]}


@app.post("/matches/<int:match_id>/messages")
@login_required
def post_match_message(match_id: int):
    # only participants can send
    if not match_service.is_match_participant(match_id, current_user.id):
        abort(403)
    content = request.form.get("content", "").strip()
    if not content:
        flash("消息不能为空。", "danger")
        return redirect(url_for("index"))
    message = match_service.add_message(match_id, current_user.id, content)
    return {
        "message": message.to_dict(),
    }


@app.route("/auth/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if not username or not password:
            flash("用户名和密码均为必填项。", "danger")
            return render_template("auth_register.html", username=username)
        if password != confirm:
            flash("两次输入的密码不一致。", "danger")
            return render_template("auth_register.html", username=username)
        if db.session.scalar(db.select(User).filter_by(username=username)):
            flash("该用户名已被注册。", "danger")
            return render_template("auth_register.html")

        user = User(username=username)
        user.set_password(password)
        # First registered account becomes administrator for later management tasks.
        existing_users = db.session.scalar(db.select(func.count()).select_from(User))
        if existing_users == 0:
            user.is_admin = True
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash("注册成功，已自动登录。", "success")
        return redirect(url_for("index"))

    return render_template("auth_register.html")


@app.route("/auth/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user: Optional[User] = db.session.scalar(db.select(User).filter_by(username=username))
        if user is None or not user.check_password(password):
            flash("用户名或密码错误。", "danger")
            return render_template("auth_login.html", username=username)

        login_user(user)
        flash("登录成功。", "success")
        next_url = request.args.get("next")
        return redirect(next_url or url_for("index"))

    return render_template("auth_login.html")


@app.post("/auth/logout")
@login_required
def logout():
    logout_user()
    flash("您已退出登录。", "info")
    return redirect(url_for("login"))


@app.cli.command("promote-admin")
@click.argument("username")
@with_appcontext
def promote_admin(username: str) -> None:
    user: Optional[User] = db.session.scalar(db.select(User).filter_by(username=username))
    if user is None:
        click.echo(f"未找到用户：{username}", err=True)
        raise SystemExit(1)
    if user.is_admin:
        click.echo(f"用户 {username} 已是管理员。")
        return
    user.is_admin = True
    db.session.commit()
    click.echo(f"用户 {username} 已被设为管理员。")


if __name__ == "__main__":
    app.run(debug=True)
