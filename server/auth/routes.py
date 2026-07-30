"""认证 + 团队空间路由（Flask Blueprint）。

API:
    POST   /api/auth/register       注册
    POST   /api/auth/login          登录
    GET    /api/auth/me             当前用户信息
    GET    /api/teams               我的团队列表
    POST   /api/teams               创建团队
    POST   /api/teams/<id>/invite   邀请成员（通过用户名）
    DELETE /api/teams/<id>/members/<username>  移除成员
    GET    /api/teams/<id>/plugins  团队内插件
"""
import bcrypt
from flask import Blueprint, jsonify, request, g

from .models import (
    get_db, now_iso,
    is_team_member, is_team_owner,
    create_invitation, get_pending_invitations, respond_invitation,
)
from .middleware import generate_token, require_auth, get_current_user


def create_auth_bp() -> Blueprint:
    bp = Blueprint("auth", __name__)

    # ==================== 认证 ====================

    @bp.route("/auth/register", methods=["POST"])
    def register():
        """注册。Body: { username, password, email? }"""
        data = request.get_json(force=True, silent=True) or {}
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        email = (data.get("email") or "").strip()

        if not username:
            return jsonify({"ok": False, "error": "用户名不能为空"}), 400
        if len(password) < 8:
            return jsonify({"ok": False, "error": "密码至少 8 位"}), 400

        conn = get_db()
        # 检查用户名是否已存在
        if conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
            conn.close()
            return jsonify({"ok": False, "error": "用户名已存在"}), 409

        # 首个注册的用户自动成为管理员
        user_count = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
        role = "admin" if user_count == 0 else "member"

        # 创建用户
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        cursor = conn.execute(
            "INSERT INTO users (username, password, email, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, hashed, email, role, now_iso()),
        )
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()

        token = generate_token(user_id, username)
        return jsonify({"ok": True, "data": {"id": user_id, "username": username, "email": email, "role": role, "token": token}})

    @bp.route("/auth/login", methods=["POST"])
    def login():
        """登录。Body: { username, password }"""
        data = request.get_json(force=True, silent=True) or {}
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""

        if not username or not password:
            return jsonify({"ok": False, "error": "用户名和密码不能为空"}), 400

        conn = get_db()
        row = conn.execute(
            "SELECT id, username, password, email, role FROM users WHERE username = ?", (username,)
        ).fetchone()
        conn.close()

        if not row or not bcrypt.checkpw(password.encode("utf-8"), row["password"].encode("utf-8")):
            return jsonify({"ok": False, "error": "用户名或密码错误"}), 401

        token = generate_token(row["id"], row["username"])
        return jsonify({"ok": True, "data": {"id": row["id"], "username": row["username"], "email": row["email"], "role": row["role"], "token": token}})

    @bp.route("/auth/me", methods=["GET"])
    @require_auth
    def me():
        """获取当前用户信息。"""
        return jsonify({"ok": True, "data": g.current_user})

    @bp.route("/auth/change-password", methods=["POST"])
    @require_auth
    def change_password():
        """修改密码。Body: { old_password, new_password }"""
        data = request.get_json(force=True, silent=True) or {}
        old_password = data.get("old_password") or ""
        new_password = data.get("new_password") or ""

        if not old_password or not new_password:
            return jsonify({"ok": False, "error": "旧密码和新密码不能为空"}), 400
        if len(new_password) < 8:
            return jsonify({"ok": False, "error": "新密码至少 8 位"}), 400

        uid = g.current_user["id"]
        conn = get_db()
        row = conn.execute("SELECT password FROM users WHERE id = ?", (uid,)).fetchone()
        if not row or not bcrypt.checkpw(old_password.encode("utf-8"), row["password"].encode("utf-8")):
            conn.close()
            return jsonify({"ok": False, "error": "旧密码错误"}), 401

        hashed = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        conn.execute("UPDATE users SET password = ? WHERE id = ?", (hashed, uid))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})

    # ==================== 团队空间 ====================

    @bp.route("/teams", methods=["GET"])
    @require_auth
    def teams_list():
        """我加入的团队列表。"""
        uid = g.current_user["id"]
        conn = get_db()
        rows = conn.execute(
            """SELECT t.id, t.name, t.description, t.owner_id, t.created_at,
                      tm.role,
                      (SELECT COUNT(*) FROM team_members WHERE team_id = t.id) AS member_count
               FROM teams t
               JOIN team_members tm ON tm.team_id = t.id AND tm.user_id = ?
               ORDER BY t.created_at DESC""",
            (uid,),
        ).fetchall()
        conn.close()
        teams = [dict(r) for r in rows]
        return jsonify({"ok": True, "data": teams})

    @bp.route("/teams", methods=["POST"])
    @require_auth
    def teams_create():
        """创建团队。Body: { name, description? }"""
        data = request.get_json(force=True, silent=True) or {}
        name = (data.get("name") or "").strip()
        description = (data.get("description") or "").strip()

        if not name:
            return jsonify({"ok": False, "error": "团队名称不能为空"}), 400

        uid = g.current_user["id"]
        conn = get_db()
        cursor = conn.execute(
            "INSERT INTO teams (name, description, owner_id, created_at) VALUES (?, ?, ?, ?)",
            (name, description, uid, now_iso()),
        )
        team_id = cursor.lastrowid
        # 创建者自动加入为 owner
        conn.execute(
            "INSERT INTO team_members (team_id, user_id, role, joined_at) VALUES (?, ?, 'owner', ?)",
            (team_id, uid, now_iso()),
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "data": {"id": team_id, "name": name, "description": description, "owner_id": uid, "role": "owner", "member_count": 1}})

    @bp.route("/teams/<int:team_id>/invite", methods=["POST"])
    @require_auth
    def teams_invite(team_id):
        """邀请成员（发送邀请，对方需接受）。Body: { username, message? }"""
        data = request.get_json(force=True, silent=True) or {}
        username = (data.get("username") or "").strip()
        message = (data.get("message") or "").strip()

        if not username:
            return jsonify({"ok": False, "error": "用户名不能为空"}), 400

        uid = g.current_user["id"]
        conn = get_db()

        # 检查是否是团队成员
        if not is_team_member(team_id, uid):
            conn.close()
            return jsonify({"ok": False, "error": "你不是该团队成员"}), 403

        # 查找用户
        target = conn.execute("SELECT id, username FROM users WHERE username = ?", (username,)).fetchone()
        if not target:
            conn.close()
            return jsonify({"ok": False, "error": f"用户 {username} 不存在"}), 404

        # 检查是否已在团队
        existing = conn.execute(
            "SELECT 1 FROM team_members WHERE team_id = ? AND user_id = ?",
            (team_id, target["id"]),
        ).fetchone()
        if existing:
            conn.close()
            return jsonify({"ok": False, "error": f"{username} 已在团队中"}), 409

        # 检查是否已有待处理邀请
        pending = conn.execute(
            "SELECT 1 FROM invitations WHERE team_id = ? AND invitee_id = ? AND status = 'pending'",
            (team_id, target["id"]),
        ).fetchone()
        if pending:
            conn.close()
            return jsonify({"ok": False, "error": f"已向 {username} 发送过邀请，等待对方确认"}), 409

        conn.close()

        # 创建邀请记录
        inv = create_invitation(team_id, uid, target["id"], message)
        return jsonify({"ok": True, "data": inv})

    # ==================== 邀请管理 ====================

    @bp.route("/invitations", methods=["GET"])
    @require_auth
    def invitations_list():
        """我的待处理邀请列表。"""
        uid = g.current_user["id"]
        invs = get_pending_invitations(uid)
        return jsonify({"ok": True, "data": invs})

    @bp.route("/invitations/<int:inv_id>/accept", methods=["POST"])
    @require_auth
    def invitation_accept(inv_id):
        """接受邀请。"""
        uid = g.current_user["id"]
        inv = respond_invitation(inv_id, uid, accept=True)
        if not inv:
            return jsonify({"ok": False, "error": "邀请不存在或已处理"}), 404
        return jsonify({"ok": True, "data": inv})

    @bp.route("/invitations/<int:inv_id>/decline", methods=["POST"])
    @require_auth
    def invitation_decline(inv_id):
        """拒绝邀请。"""
        uid = g.current_user["id"]
        inv = respond_invitation(inv_id, uid, accept=False)
        if not inv:
            return jsonify({"ok": False, "error": "邀请不存在或已处理"}), 404
        return jsonify({"ok": True, "data": inv})

    @bp.route("/teams/<int:team_id>/members", methods=["GET"])
    @require_auth
    def teams_members(team_id):
        """获取团队成员列表。"""
        uid = g.current_user["id"]
        conn = get_db()
        # 必须是团队成员才能看
        membership = conn.execute(
            "SELECT 1 FROM team_members WHERE team_id = ? AND user_id = ?", (team_id, uid)
        ).fetchone()
        if not membership:
            conn.close()
            return jsonify({"ok": False, "error": "无权访问"}), 403

        rows = conn.execute(
            """SELECT u.id, u.username, u.email, tm.role, tm.joined_at
               FROM team_members tm
               JOIN users u ON u.id = tm.user_id
               WHERE tm.team_id = ?
               ORDER BY tm.role DESC, tm.joined_at ASC""",
            (team_id,),
        ).fetchall()
        conn.close()
        return jsonify({"ok": True, "data": [dict(r) for r in rows]})

    @bp.route("/teams/<int:team_id>/members/<username>", methods=["DELETE"])
    @require_auth
    def teams_remove_member(team_id, username):
        """移除团队成员（仅 owner 可操作）。"""
        uid = g.current_user["id"]
        conn = get_db()

        # 检查操作者是否是 owner
        owner = conn.execute(
            "SELECT role FROM team_members WHERE team_id = ? AND user_id = ?", (team_id, uid)
        ).fetchone()
        if not owner or owner["role"] != "owner":
            conn.close()
            return jsonify({"ok": False, "error": "仅团队创建者可移除成员"}), 403

        target = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if not target:
            conn.close()
            return jsonify({"ok": False, "error": "用户不存在"}), 404

        if target["id"] == uid:
            conn.close()
            return jsonify({"ok": False, "error": "不能移除自己"}), 400

        conn.execute("DELETE FROM team_members WHERE team_id = ? AND user_id = ?", (team_id, target["id"]))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})

    @bp.route("/teams/<int:team_id>", methods=["DELETE"])
    @require_auth
    def teams_delete(team_id):
        """删除团队（仅 owner 可操作）。"""
        uid = g.current_user["id"]
        conn = get_db()
        owner = conn.execute(
            "SELECT role FROM team_members WHERE team_id = ? AND user_id = ?", (team_id, uid)
        ).fetchone()
        if not owner or owner["role"] != "owner":
            conn.close()
            return jsonify({"ok": False, "error": "仅团队创建者可删除"}), 403

        conn.execute("DELETE FROM team_members WHERE team_id = ?", (team_id,))
        conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})

    return bp
