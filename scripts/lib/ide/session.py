"""IDE 会话扫描模块。

扫描各 IDE 的会话存储位置，返回统一格式的会话列表。
支持会话 resume 命令构造与跨 IDE 共享格式转换。

支持的会话存储格式：
- Claude Code: ~/.claude/projects/<project-hash>/<session-id>.jsonl
- Codex: ~/.codex/sessions/<session-id>/rollout.jsonl + archived_sessions/
- Cursor: ~/.cursor/acp-sessions/<session-id>/{meta.json, store.db}
- Kimi Code: ~/.kimi-code/sessions/<workDirKey>/<session-id>/state.json + agents/*/wire.jsonl
- WorkBuddy: ~/.workbuddy/sessions/<session-id>/{state.json, events.jsonl}
- OpenCode/OpenClaw/Qoder/Trae: 类 WorkBuddy 结构（推测，按实际探测调整）

统一会话格式：
{
    "id": str,                  # 会话 ID
    "ide": str,                 # IDE key
    "title": str,               # 会话标题（无则取首条消息摘要）
    "cwd": str,                 # 工作目录
    "created_at": str,          # ISO-8601
    "updated_at": str,          # ISO-8601
    "messages_count": int,      # 消息数（估算）
    "file_path": str,           # 主会话文件路径
    "size_bytes": int,          # 文件大小
}
"""
import json
import re
from pathlib import Path
from datetime import datetime


# ===== 通用工具 =====

def _safe_stat(p: Path) -> dict:
    """安全获取文件 stat，失败返回空字典。"""
    try:
        st = p.stat()
        return {
            "size_bytes": st.st_size,
            "created_at": datetime.fromtimestamp(st.st_ctime).isoformat(),
            "updated_at": datetime.fromtimestamp(st.st_mtime).isoformat(),
        }
    except Exception:
        return {}


def _count_jsonl_messages(p: Path) -> int:
    """统计 jsonl 文件行数（估算消息数）。"""
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def _extract_title_from_jsonl(p: Path, max_chars: int = 60) -> str:
    """从 jsonl 第一条 user 消息提取标题。"""
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                # Claude/Codex 格式：type=user/message, message.content
                msg = obj.get("message") or obj
                content = msg.get("content") or msg.get("text") or ""
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            content = item.get("text", "")
                            break
                if isinstance(content, str) and content.strip():
                    text = content.strip().replace("\n", " ")
                    return text[:max_chars] + ("..." if len(text) > max_chars else "")
    except Exception:
        pass
    return ""


# ===== 各 IDE 会话扫描器 =====

def scan_claude_sessions(sessions_dir: Path, ide_key: str = "Claude") -> list[dict]:
    """扫描 Claude Code 会话：sessions_dir = ~/.claude/projects。

    结构：<project-hash>/<session-id>.jsonl
    project-hash 由 cwd 路径转换：/ → -
    """
    results = []
    if not sessions_dir.exists():
        return results
    for project_dir in sessions_dir.iterdir():
        if not project_dir.is_dir():
            continue
        # 反推 cwd：-Users-yangxuezeng-Desktop-X → /Users/yangxuezeng/Desktop/X
        cwd = "/" + project_dir.name.lstrip("-").replace("-", "/")
        for session_file in project_dir.glob("*.jsonl"):
            stat = _safe_stat(session_file)
            title = _extract_title_from_jsonl(session_file) or session_file.stem
            results.append({
                "id": session_file.stem,
                "ide": ide_key,
                "title": title,
                "cwd": cwd,
                "created_at": stat.get("created_at", ""),
                "updated_at": stat.get("updated_at", ""),
                "messages_count": _count_jsonl_messages(session_file),
                "file_path": str(session_file),
                "size_bytes": stat.get("size_bytes", 0),
            })
    return results


def scan_codex_sessions(sessions_dir: Path, ide_key: str = "Codex") -> list[dict]:
    """扫描 Codex 会话：sessions_dir = ~/.codex/sessions。

    结构：
    - <session-id>/rollout.jsonl（活跃会话）
    - archived_sessions/<session-id>/rollout.jsonl（归档会话）
    - rollout-<timestamp>-<session-id>.jsonl（旧格式单文件）
    rollout.jsonl 首行含 session_meta：{type:session_meta, id, timestamp, cwd, ...}
    """
    results = []
    if not sessions_dir.exists():
        return results

    # 子目录形式
    for session_dir in sessions_dir.iterdir():
        if not session_dir.is_dir():
            continue
        rollout = session_dir / "rollout.jsonl"
        if not rollout.exists():
            continue
        stat = _safe_stat(rollout)
        cwd = ""
        created_at = stat.get("created_at", "")
        # 读首行 session_meta
        try:
            with open(rollout, "r", encoding="utf-8", errors="ignore") as f:
                first = f.readline()
                meta = json.loads(first)
                if meta.get("type") == "session_meta":
                    cwd = meta.get("cwd", "")
                    created_at = meta.get("timestamp", created_at)
        except Exception:
            pass
        title = _extract_title_from_jsonl(rollout) or session_dir.name
        results.append({
            "id": session_dir.name,
            "ide": ide_key,
            "title": title,
            "cwd": cwd,
            "created_at": created_at,
            "updated_at": stat.get("updated_at", ""),
            "messages_count": _count_jsonl_messages(rollout),
            "file_path": str(rollout),
            "size_bytes": stat.get("size_bytes", 0),
        })

    # 归档目录
    archived = sessions_dir.parent / "archived_sessions"
    if archived.exists():
        for session_dir in archived.iterdir():
            if not session_dir.is_dir():
                continue
            rollout = session_dir / "rollout.jsonl"
            if not rollout.exists():
                continue
            stat = _safe_stat(rollout)
            title = _extract_title_from_jsonl(rollout) or session_dir.name
            results.append({
                "id": session_dir.name,
                "ide": ide_key,
                "title": f"[archived] {title}",
                "cwd": "",
                "created_at": stat.get("created_at", ""),
                "updated_at": stat.get("updated_at", ""),
                "messages_count": _count_jsonl_messages(rollout),
                "file_path": str(rollout),
                "size_bytes": stat.get("size_bytes", 0),
            })

    # 旧格式单文件 rollout-*.jsonl
    for f in sessions_dir.glob("rollout-*.jsonl"):
        stat = _safe_stat(f)
        # 文件名格式：rollout-<timestamp>-<session-id>.jsonl
        m = re.match(r"rollout-[\dT-]+-(.+)\.jsonl", f.name)
        sid = m.group(1) if m else f.stem
        results.append({
            "id": sid,
            "ide": ide_key,
            "title": _extract_title_from_jsonl(f) or f.stem,
            "cwd": "",
            "created_at": stat.get("created_at", ""),
            "updated_at": stat.get("updated_at", ""),
            "messages_count": _count_jsonl_messages(f),
            "file_path": str(f),
            "size_bytes": stat.get("size_bytes", 0),
        })

    return results


def scan_cursor_sessions(sessions_dir: Path, ide_key: str = "Cursor") -> list[dict]:
    """扫描 Cursor 会话：sessions_dir = ~/.cursor/acp-sessions。

    结构：<session-id>/{meta.json, store.db}
    meta.json: {schemaVersion, cwd, ...}
    """
    results = []
    if not sessions_dir.exists():
        return results
    for session_dir in sessions_dir.iterdir():
        if not session_dir.is_dir():
            continue
        meta_file = session_dir / "meta.json"
        if not meta_file.exists():
            continue
        cwd = ""
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            cwd = meta.get("cwd", "")
        except Exception:
            pass
        stat = _safe_stat(meta_file)
        # store.db 是 SQLite，无法直接统计消息数，用文件大小估算
        store_db = session_dir / "store.db"
        size = stat.get("size_bytes", 0) + (_safe_stat(store_db).get("size_bytes", 0) if store_db.exists() else 0)
        results.append({
            "id": session_dir.name,
            "ide": ide_key,
            "title": f"Cursor Session {session_dir.name[:8]}",
            "cwd": cwd,
            "created_at": stat.get("created_at", ""),
            "updated_at": stat.get("updated_at", ""),
            "messages_count": 0,  # 需解析 SQLite，暂不统计
            "file_path": str(meta_file),
            "size_bytes": size,
        })
    return results


def scan_kimi_sessions(sessions_dir: Path, ide_key: str = "KimiCode") -> list[dict]:
    """扫描 Kimi Code 会话：sessions_dir = ~/.kimi-code/sessions。

    结构：<workDirKey>/<session-id>/state.json + agents/*/wire.jsonl
    state.json: {createdAt, updatedAt, title, ...}
    workDirKey 格式：wd_<user>_<hash>，无法反推 cwd，需查 session_index.jsonl
    """
    results = []
    if not sessions_dir.exists():
        return results

    # 读 session_index.jsonl 获取 workDir 映射
    workdir_map = {}
    index_file = sessions_dir.parent / "session_index.jsonl"
    if index_file.exists():
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                        workdir_map[obj.get("sessionDir", "")] = obj.get("workDir", "")
                    except Exception:
                        continue
        except Exception:
            pass

    for workdir_key_dir in sessions_dir.iterdir():
        if not workdir_key_dir.is_dir():
            continue
        for session_dir in workdir_key_dir.iterdir():
            if not session_dir.is_dir():
                continue
            state_file = session_dir / "state.json"
            if not state_file.exists():
                continue
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
            except Exception:
                state = {}
            stat = _safe_stat(state_file)
            cwd = workdir_map.get(str(session_dir), "")
            title = state.get("title", "") or session_dir.name
            # 统计 wire.jsonl 行数
            msg_count = 0
            for agent_dir in (session_dir / "agents").iterdir() if (session_dir / "agents").exists() else []:
                wire = agent_dir / "wire.jsonl"
                if wire.exists():
                    msg_count += _count_jsonl_messages(wire)
            results.append({
                "id": session_dir.name,
                "ide": ide_key,
                "title": title,
                "cwd": cwd,
                "created_at": state.get("createdAt", stat.get("created_at", "")),
                "updated_at": state.get("updatedAt", stat.get("updated_at", "")),
                "messages_count": msg_count,
                "file_path": str(state_file),
                "size_bytes": stat.get("size_bytes", 0),
            })
    return results


def scan_generic_sessions(sessions_dir: Path, ide_key: str) -> list[dict]:
    """通用扫描器：用于 WorkBuddy/OpenClaw/Qoder 等结构未知的 IDE。

    策略：扫描子目录，每个子目录视为一个会话，查找 state.json/jsonl 文件。
    """
    results = []
    if not sessions_dir.exists():
        return results
    for session_dir in sessions_dir.iterdir():
        if not session_dir.is_dir():
            continue
        # 优先 state.json，其次任意 .jsonl
        state_file = session_dir / "state.json"
        main_file = None
        if state_file.exists():
            main_file = state_file
        else:
            jsonl_files = list(session_dir.glob("*.jsonl"))
            if jsonl_files:
                main_file = jsonl_files[0]
        if not main_file:
            continue
        stat = _safe_stat(main_file)
        title = ""
        cwd = ""
        if main_file.name == "state.json":
            try:
                with open(main_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                title = state.get("title", "")
                cwd = state.get("cwd", "")
            except Exception:
                pass
        if not title:
            title = _extract_title_from_jsonl(main_file) if main_file.suffix == ".jsonl" else session_dir.name
        results.append({
            "id": session_dir.name,
            "ide": ide_key,
            "title": title or session_dir.name,
            "cwd": cwd,
            "created_at": stat.get("created_at", ""),
            "updated_at": stat.get("updated_at", ""),
            "messages_count": _count_jsonl_messages(main_file) if main_file.suffix == ".jsonl" else 0,
            "file_path": str(main_file),
            "size_bytes": stat.get("size_bytes", 0),
        })
    return results


# ===== 调度入口 =====

# IDE key → 扫描器映射
IDE_SESSION_SCANNERS = {
    "Claude": scan_claude_sessions,
    "Codex": scan_codex_sessions,
    "Cursor": scan_cursor_sessions,
    "KimiCode": scan_kimi_sessions,
    "WorkBuddy": lambda d, k="WorkBuddy": scan_generic_sessions(d, k),
    "OpenClaw": lambda d, k="OpenClaw": scan_generic_sessions(d, k),
    "Qoder": lambda d, k="Qoder": scan_generic_sessions(d, k),
    "OpenCode": lambda d, k="OpenCode": scan_generic_sessions(d, k),
    "Trae": lambda d, k="Trae": scan_generic_sessions(d, k),
    "TraeCN": lambda d, k="TraeCN": scan_generic_sessions(d, k),
    "TraeSoloCN": lambda d, k="TraeSoloCN": scan_generic_sessions(d, k),
}


def list_sessions(ide_key: str, sessions_dir: str | Path) -> list[dict]:
    """列出指定 IDE 的所有会话。

    Args:
        ide_key: IDE 标识（如 "Claude"）
        sessions_dir: 会话目录路径

    Returns:
        统一格式的会话列表，按 updated_at 倒序排列
    """
    sessions_dir = Path(sessions_dir) if sessions_dir else Path()
    scanner = IDE_SESSION_SCANNERS.get(ide_key)
    if not scanner:
        # 未知 IDE 用通用扫描器
        scanner = lambda d, k=ide_key: scan_generic_sessions(d, k)
    try:
        results = scanner(sessions_dir, ide_key) if ide_key in IDE_SESSION_SCANNERS else scanner(sessions_dir)
    except Exception:
        results = []
    # 按 updated_at 倒序
    results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return results


# ===== 会话 resume 命令构造 =====

# 各 IDE 的 resume 命令模板（{exe} 为可执行文件，{session_id} 为会话 ID，{cwd} 为工作目录）
IDE_RESUME_COMMANDS = {
    "Claude": "{exe} --resume {session_id}",                  # claude --resume <id>
    "Codex": "{exe} --resume {session_id}",                   # codex --resume <id>
    "KimiCode": "{exe} --session {session_id}",               # kimi --session <id>
    "Cursor": "{exe} --continue",                             # Cursor 无 CLI resume，只能 --continue 最近会话
    "OpenCode": "{exe} --resume {session_id}",
    "Qoder": "{exe} --resume {session_id}",
    "OpenClaw": "{exe} --resume {session_id}",
    "WorkBuddy": "{exe} --resume {session_id}",
}


def build_resume_command(ide_key: str, exe_path: str, session_id: str, cwd: str = "") -> str:
    """构造恢复会话的命令行。

    Returns:
        完整命令字符串。若 IDE 不支持 resume，返回空字符串。
    """
    template = IDE_RESUME_COMMANDS.get(ide_key)
    if not template or not exe_path:
        return ""
    return template.format(exe=exe_path, session_id=session_id, cwd=cwd)


# ===== 跨 IDE 会话共享格式 =====

def export_session(session: dict) -> dict:
    """将会话导出为通用 JSON 格式（用于跨 IDE 共享）。

    通用格式：
    {
        "format": "agentbuddy-session-v1",
        "source_ide": str,
        "session_id": str,
        "title": str,
        "cwd": str,
        "created_at": str,
        "updated_at": str,
        "messages_count": int,
        "raw_file": str,         # 原始会话文件路径
        "messages": list,        # 提取的消息列表（user/assistant 交替）
    }
    """
    file_path = session.get("file_path", "")
    messages = []
    if file_path and Path(file_path).suffix == ".jsonl":
        messages = _extract_messages_from_jsonl(Path(file_path))
    return {
        "format": "agentbuddy-session-v1",
        "source_ide": session.get("ide", ""),
        "session_id": session.get("id", ""),
        "title": session.get("title", ""),
        "cwd": session.get("cwd", ""),
        "created_at": session.get("created_at", ""),
        "updated_at": session.get("updated_at", ""),
        "messages_count": session.get("messages_count", 0),
        "raw_file": file_path,
        "messages": messages,
    }


def _extract_messages_from_jsonl(p: Path, max_messages: int = 200) -> list[dict]:
    """从 jsonl 文件提取消息列表（统一格式）。

    返回：[{role, content, timestamp}]
    """
    messages = []
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if len(messages) >= max_messages:
                    break
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                # 兼容 Claude/Codex/Kimi 格式
                role = obj.get("role") or obj.get("type", "")
                msg = obj.get("message") or obj
                content = msg.get("content") or msg.get("text") or ""
                if isinstance(content, list):
                    text_parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif isinstance(item, str):
                            text_parts.append(item)
                    content = "\n".join(text_parts)
                if not isinstance(content, str):
                    content = str(content)
                # 规范化 role
                if role in ("user", "human"):
                    role = "user"
                elif role in ("assistant", "ai", "agent"):
                    role = "assistant"
                elif role in ("system",):
                    role = "system"
                else:
                    continue  # 跳过非消息类型（session_meta 等）
                if not content.strip():
                    continue
                messages.append({
                    "role": role,
                    "content": content[:5000],  # 截断长消息
                    "timestamp": obj.get("timestamp", ""),
                })
    except Exception:
        pass
    return messages


def import_session_to_ide(session_data: dict, target_ide: str, target_dir: str) -> str:
    """将通用会话格式导入到目标 IDE。

    策略：将 messages 拼接为 markdown 摘要文件，写入目标 IDE 的会话目录。
    各 IDE 原生格式不兼容，导入为 markdown 摘要可在新会话中作为上下文引用。

    Returns:
        写入的文件路径。
    """
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    sid = session_data.get("session_id", "imported")[:36] or "imported"
    out_file = target_dir / f"imported-{sid}.md"
    lines = [
        f"# Imported Session: {session_data.get('title', '')}",
        "",
        f"- **Source IDE**: {session_data.get('source_ide', '')}",
        f"- **Session ID**: {session_data.get('session_id', '')}",
        f"- **Original cwd**: {session_data.get('cwd', '')}",
        f"- **Created**: {session_data.get('created_at', '')}",
        f"- **Messages**: {session_data.get('messages_count', 0)}",
        "",
        "---",
        "",
    ]
    for msg in session_data.get("messages", []):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        lines.append(f"## {role.upper()}")
        lines.append("")
        lines.append(content)
        lines.append("")
    out_file.write_text("\n".join(lines), encoding="utf-8")
    return str(out_file)


__all__ = [
    "list_sessions", "build_resume_command",
    "export_session", "import_session_to_ide",
    "IDE_SESSION_SCANNERS", "IDE_RESUME_COMMANDS",
]
