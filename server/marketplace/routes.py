"""插件市场 API 路由（Flask Blueprint）。

使用 SQLite 存储插件元数据，zip 包文件存储在 packages/ 目录。

鉴权：
- browse / download / install：无需登录
- publish / remove / like：需要登录
- remove 权限：仅 author 或团队 owner
"""
import io
import json
import zipfile
from pathlib import Path

import yaml
from flask import Blueprint, jsonify, request, send_file, g

from auth.models import (
    plugin_list, plugin_get, plugin_save, plugin_delete,
    plugin_increment_downloads, plugin_toggle_like,
    get_db, now_iso,
)
from auth.middleware import require_auth


def create_marketplace_bp(marketplace_dir: Path):
    """创建市场 Blueprint。

    Args:
        marketplace_dir: marketplace 数据目录（packages/*.zip）
    """
    packages_dir = marketplace_dir / "packages"

    bp = Blueprint("marketplace", __name__)

    @bp.route("", methods=["GET"])
    def marketplace_list():
        """浏览市场。支持 ?q= 搜索，?scope= 过滤。无需登录。"""
        q = (request.args.get("q") or "").strip().lower()
        scope = (request.args.get("scope") or "").strip()
        items = plugin_list(q=q, scope=scope)
        return jsonify({"ok": True, "data": items, "total": len(items)})

    @bp.route("/publish", methods=["POST"])
    @require_auth
    def marketplace_publish():
        """发布插件到市场。需要登录。

        Form fields:
            file: zip 文件
            tags: JSON 数组字符串（可选）
            scope: public / team（默认 public）
            team_id: 团队 ID（scope=team 时必填）
        """
        user = g.current_user
        uploaded = request.files.get("file")
        if not uploaded:
            return jsonify({"ok": False, "error": "缺少 file 文件"}), 400

        tags_str = request.form.get("tags", "[]")
        try:
            tags = json.loads(tags_str) if tags_str else []
        except (json.JSONDecodeError, ValueError):
            tags = []

        scope = request.form.get("scope", "public").strip()
        team_id = request.form.get("team_id", type=int)

        # scope=team 时校验团队成员身份
        if scope == "team":
            if not team_id:
                return jsonify({"ok": False, "error": "发布到团队空间需要 team_id"}), 400
            conn = get_db()
            membership = conn.execute(
                "SELECT 1 FROM team_members WHERE team_id = ? AND user_id = ?",
                (team_id, user["id"]),
            ).fetchone()
            conn.close()
            if not membership:
                return jsonify({"ok": False, "error": "你不是该团队成员"}), 403

        try:
            zip_bytes = uploaded.read()
            buf = io.BytesIO(zip_bytes)

            plugin_name = uploaded.filename or "plugin"
            version = "1.0.0"
            description = ""
            author = user["username"]

            with zipfile.ZipFile(buf, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = info.filename
                    if name.endswith(".plugin.yaml") or name.endswith(".plugin.yml"):
                        try:
                            data = yaml.safe_load(zf.read(name).decode("utf-8"))
                            if isinstance(data, dict):
                                plugin_name = data.get("name", Path(name).stem)
                                version = str(data.get("version", "1.0.0")).strip() or "1.0.0"
                                description = data.get("description", "").strip()
                                yaml_author = data.get("author", "").strip()
                                if yaml_author:
                                    author = yaml_author
                        except Exception:
                            pass
                        break

            buf.seek(0)

            safe_name = "".join(c for c in plugin_name if c.isalnum() or c in ("-", "_"))
            pkg_name = f"{safe_name or 'plugin'}-{version}.zip"
            packages_dir.mkdir(parents=True, exist_ok=True)
            pkg_path = packages_dir / pkg_name
            pkg_path.write_bytes(buf.getvalue())
            pkg_size = pkg_path.stat().st_size

            item_id = f"{plugin_name}-{version}"
            entry = {
                "id": item_id,
                "name": plugin_name,
                "version": version,
                "description": description,
                "author": author,
                "author_id": user["id"],
                "file": f"packages/{pkg_name}",
                "size": pkg_size,
                "published_at": now_iso(),
                "tags": tags if isinstance(tags, list) else [],
                "downloads": 0,
                "likes": 0,
                "scope": scope,
                "team_id": team_id if scope == "team" else None,
            }
            plugin_save(entry)

            return jsonify({"ok": True, "data": entry})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @bp.route("/mine", methods=["GET"])
    @require_auth
    def marketplace_mine():
        """我发布的插件。"""
        user = g.current_user
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM plugins WHERE author_id = ? ORDER BY published_at DESC",
            (user["id"],),
        ).fetchall()
        conn.close()
        from auth.models import _plugin_row_to_dict
        items = [_plugin_row_to_dict(r) for r in rows]
        return jsonify({"ok": True, "data": items, "total": len(items)})

    @bp.route("/download", methods=["GET"])
    def marketplace_download():
        """下载市场中的插件 zip。Query: id=xxx"""
        item_id = (request.args.get("id") or "").strip()
        if not item_id:
            return jsonify({"ok": False, "error": "缺少 id 参数"}), 400
        entry = plugin_get(item_id)
        if not entry:
            return jsonify({"ok": False, "error": "插件不存在"}), 404
        pkg_path = marketplace_dir / entry["file"]
        if not pkg_path.exists():
            return jsonify({"ok": False, "error": "包文件丢失"}), 404
        plugin_increment_downloads(item_id)
        buf = io.BytesIO(pkg_path.read_bytes())
        buf.seek(0)
        return send_file(buf, as_attachment=True,
                         download_name=Path(entry["file"]).name,
                         mimetype="application/zip")

    @bp.route("/install", methods=["GET"])
    def marketplace_install():
        """从市场安装插件（返回 zip）。Query: id=xxx"""
        item_id = (request.args.get("id") or "").strip()
        if not item_id:
            return jsonify({"ok": False, "error": "缺少 id 参数"}), 400
        entry = plugin_get(item_id)
        if not entry:
            return jsonify({"ok": False, "error": "插件不存在"}), 404
        pkg_path = marketplace_dir / entry["file"]
        if not pkg_path.exists():
            return jsonify({"ok": False, "error": "包文件丢失"}), 404
        plugin_increment_downloads(item_id)
        buf = io.BytesIO(pkg_path.read_bytes())
        buf.seek(0)
        return send_file(buf, as_attachment=True,
                         download_name=Path(entry["file"]).name,
                         mimetype="application/zip")

    @bp.route("/remove", methods=["DELETE"])
    @require_auth
    def marketplace_remove():
        """从市场移除插件。需要登录。

        权限：仅 author 或团队 owner 可删除。
        """
        user = g.current_user
        item_id = (request.args.get("id") or "").strip()
        if not item_id:
            return jsonify({"ok": False, "error": "缺少 id 参数"}), 400
        entry = plugin_get(item_id)
        if not entry:
            return jsonify({"ok": False, "error": "插件不存在"}), 404

        author_id = entry.get("author_id")
        is_author = author_id == user["id"]

        # 团队插件，检查是否是团队 owner
        is_team_owner = False
        if entry.get("scope") == "team" and entry.get("team_id"):
            conn = get_db()
            owner = conn.execute(
                "SELECT role FROM team_members WHERE team_id = ? AND user_id = ?",
                (entry["team_id"], user["id"]),
            ).fetchone()
            conn.close()
            is_team_owner = owner and owner["role"] == "owner"

        if not is_author and not is_team_owner:
            return jsonify({"ok": False, "error": "无权删除此插件（仅作者或团队 owner 可删除）"}), 403

        # 删除包文件
        pkg_path = marketplace_dir / entry["file"]
        if pkg_path.exists():
            pkg_path.unlink()
        plugin_delete(item_id)
        return jsonify({"ok": True, "id": item_id})

    @bp.route("/<plugin_id>/like", methods=["POST"])
    @require_auth
    def marketplace_like(plugin_id):
        """点赞/取消点赞。"""
        user = g.current_user
        entry = plugin_get(plugin_id)
        if not entry:
            return jsonify({"ok": False, "error": "插件不存在"}), 404
        liked = plugin_toggle_like(plugin_id, user["id"])
        return jsonify({"ok": True, "data": {"liked": liked}})

    return bp
