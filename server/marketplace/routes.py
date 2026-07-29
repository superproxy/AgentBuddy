"""插件市场 API 路由（Flask Blueprint）。

独立部署模式：不依赖 config_server.py 的辅助函数。
publish 接收客户端打包好的 zip 文件上传。
"""
import io
import zipfile
from pathlib import Path

import yaml
from flask import Blueprint, jsonify, request, send_file

from .storage import load_index, save_index, now_iso


def create_marketplace_bp(marketplace_dir: Path):
    """创建市场 Blueprint。

    Args:
        marketplace_dir: marketplace 数据目录（index.json + packages/）
    """
    packages_dir = marketplace_dir / "packages"
    index_file = marketplace_dir / "index.json"

    bp = Blueprint("marketplace", __name__)

    @bp.route("", methods=["GET"])
    def marketplace_list():
        """浏览市场。支持 ?q= 搜索（匹配 name/description/tags）。"""
        q = (request.args.get("q") or "").strip().lower()
        items = load_index(index_file)
        if q:
            filtered = []
            for it in items:
                haystack = " ".join([
                    it.get("name", ""),
                    it.get("description", ""),
                    it.get("author", ""),
                    " ".join(it.get("tags", [])),
                ]).lower()
                if q in haystack:
                    filtered.append(it)
            items = filtered
        return jsonify({"ok": True, "data": items, "total": len(items)})

    @bp.route("/publish", methods=["POST"])
    def marketplace_publish():
        """发布插件到市场。

        接收客户端打包好的 zip 文件上传（multipart/form-data）。
        从 zip 中的 plugin.yaml 提取元数据。

        Form fields:
            file: zip 文件
            tags: JSON 数组字符串（可选）
        """
        uploaded = request.files.get("file")
        if not uploaded:
            return jsonify({"ok": False, "error": "缺少 file 文件"}), 400

        tags_str = request.form.get("tags", "[]")
        try:
            import json
            tags = json.loads(tags_str) if tags_str else []
        except (json.JSONDecodeError, ValueError):
            tags = []

        try:
            zip_bytes = uploaded.read()
            buf = io.BytesIO(zip_bytes)

            # 从 zip 中提取 plugin.yaml 元数据
            plugin_name = uploaded.filename or "plugin"
            version = "1.0.0"
            description = ""
            author = "AgentBuddy"

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
                                author = data.get("author", "AgentBuddy").strip() or "AgentBuddy"
                        except Exception:
                            pass
                        break

            buf.seek(0)

            # 保存到 marketplace/packages/
            safe_name = "".join(c for c in plugin_name if c.isalnum() or c in ("-", "_"))
            pkg_name = f"{safe_name or 'plugin'}-{version}.zip"
            packages_dir.mkdir(parents=True, exist_ok=True)
            pkg_path = packages_dir / pkg_name
            pkg_path.write_bytes(buf.getvalue())
            pkg_size = pkg_path.stat().st_size

            # 更新索引
            items = load_index(index_file)
            item_id = f"{plugin_name}-{version}"
            items = [it for it in items if it.get("id") != item_id]
            entry = {
                "id": item_id,
                "name": plugin_name,
                "version": version,
                "description": description,
                "author": author,
                "file": f"packages/{pkg_name}",
                "size": pkg_size,
                "published_at": now_iso(),
                "tags": tags if isinstance(tags, list) else [],
                "downloads": 0,
            }
            items.append(entry)
            save_index(marketplace_dir, items)

            return jsonify({"ok": True, "data": entry})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @bp.route("/download", methods=["GET"])
    def marketplace_download():
        """下载市场中的插件 zip。Query: id=xxx"""
        item_id = (request.args.get("id") or "").strip()
        if not item_id:
            return jsonify({"ok": False, "error": "缺少 id 参数"}), 400
        items = load_index(index_file)
        entry = next((it for it in items if it.get("id") == item_id), None)
        if not entry:
            return jsonify({"ok": False, "error": "插件不存在"}), 404
        pkg_path = marketplace_dir / entry["file"]
        if not pkg_path.exists():
            return jsonify({"ok": False, "error": "包文件丢失"}), 404
        # 增加下载计数
        entry["downloads"] = entry.get("downloads", 0) + 1
        save_index(marketplace_dir, items)
        buf = io.BytesIO(pkg_path.read_bytes())
        buf.seek(0)
        return send_file(buf, as_attachment=True,
                         download_name=Path(entry["file"]).name,
                         mimetype="application/zip")

    @bp.route("/install", methods=["GET"])
    def marketplace_install():
        """从市场安装插件（返回 zip，客户端自行导入）。Query: id=xxx"""
        item_id = (request.args.get("id") or "").strip()
        if not item_id:
            return jsonify({"ok": False, "error": "缺少 id 参数"}), 400
        items = load_index(index_file)
        entry = next((it for it in items if it.get("id") == item_id), None)
        if not entry:
            return jsonify({"ok": False, "error": "插件不存在"}), 404
        pkg_path = marketplace_dir / entry["file"]
        if not pkg_path.exists():
            return jsonify({"ok": False, "error": "包文件丢失"}), 404
        # 增加下载计数
        entry["downloads"] = entry.get("downloads", 0) + 1
        save_index(marketplace_dir, items)
        buf = io.BytesIO(pkg_path.read_bytes())
        buf.seek(0)
        return send_file(buf, as_attachment=True,
                         download_name=Path(entry["file"]).name,
                         mimetype="application/zip")

    @bp.route("/remove", methods=["DELETE"])
    def marketplace_remove():
        """从市场移除插件。Query: id=xxx"""
        item_id = (request.args.get("id") or "").strip()
        if not item_id:
            return jsonify({"ok": False, "error": "缺少 id 参数"}), 400
        items = load_index(index_file)
        entry = next((it for it in items if it.get("id") == item_id), None)
        if not entry:
            return jsonify({"ok": False, "error": "插件不存在"}), 404
        # 删除包文件
        pkg_path = marketplace_dir / entry["file"]
        if pkg_path.exists():
            pkg_path.unlink()
        # 从索引移除
        items = [it for it in items if it.get("id") != item_id]
        save_index(marketplace_dir, items)
        return jsonify({"ok": True, "id": item_id})

    return bp
