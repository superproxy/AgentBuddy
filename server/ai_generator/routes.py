"""AI 插件生成 API 路由（Flask Blueprint）。

独立部署模式：从 server 端配置读取 LLM 配置和项目资源。
"""
import yaml
from pathlib import Path

from flask import Blueprint, jsonify, request, Response

from .generator import (
    generate_plugin,
    create_session,
    generate_plugin_chat,
    clear_session,
    get_session,
    get_session_config,
)


def create_ai_bp(project_root: Path, llm_config_path: Path):
    """创建 AI 生成 Blueprint。

    Args:
        project_root: 项目根目录（读取 skills/rules 等资源）
        llm_config_path: LLM 配置文件路径
    """
    bp = Blueprint("ai_generator", __name__)

    @bp.route("/generate", methods=["GET"])
    def ai_generate():
        """AI 生成插件配置。SSE 流式输出。

        Query: prompt=<用户需求描述>&model=<模型ID>&level=<basic|standard|expert>
        """
        prompt = (request.args.get("prompt") or "").strip()
        if not prompt:
            return jsonify({"ok": False, "error": "缺少 prompt 参数"}), 400
        model = (request.args.get("model") or "").strip()
        level = (request.args.get("level") or "").strip()

        def generate():
            for chunk in generate_plugin(prompt, project_root, preferred_model=model, level=level):
                for line in chunk.split("\n"):
                    yield f"data: {line}\n\n"

        return Response(generate(), mimetype="text/event-stream")

    @bp.route("/save", methods=["POST"])
    def ai_save():
        """保存 AI 生成的插件配置。Body: {content: <yaml字符串>}"""
        body = request.get_json(force=True)
        content = (body.get("content") or "").strip()
        if not content:
            return jsonify({"ok": False, "error": "缺少 content"}), 400
        try:
            data = yaml.safe_load(content)
            if not isinstance(data, dict) or not data.get("name"):
                return jsonify({"ok": False, "error": "无效的 plugin.yaml（缺少 name）"}), 400
            # 返回 yaml 内容，客户端自行保存
            return jsonify({"ok": True, "content": content, "name": data["name"]})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @bp.route("/chat", methods=["POST"])
    def ai_chat():
        """AI 多轮对话生成插件。SSE 流式输出。

        Body: {session_id?, message, level?, model?}
        """
        body = request.get_json(force=True)
        message = (body.get("message") or "").strip()
        if not message:
            return jsonify({"ok": False, "error": "缺少 message"}), 400

        session_id = (body.get("session_id") or "").strip()
        level = (body.get("level") or "").strip()
        model = (body.get("model") or "").strip()

        if not session_id or not get_session(session_id):
            session_id = create_session(level=level)

        def generate():
            for chunk in generate_plugin_chat(session_id, message, project_root, preferred_model=model):
                for line in chunk.split("\n"):
                    yield f"data: {line}\n\n"

        def generate_with_session():
            yield f"data: [SESSION] {session_id}\n\n"
            yield from generate()

        return Response(generate_with_session(), mimetype="text/event-stream")

    @bp.route("/session/<session_id>/config", methods=["GET"])
    def ai_session_config(session_id: str):
        """获取会话中最新的生成配置。"""
        config = get_session_config(session_id)
        if config:
            return jsonify({"ok": True, "content": config})
        return jsonify({"ok": False, "error": "会话中暂无配置"}), 404

    @bp.route("/session/<session_id>", methods=["DELETE"])
    def ai_session_clear(session_id: str):
        """清除会话。"""
        if clear_session(session_id):
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "会话不存在"}), 404

    return bp
