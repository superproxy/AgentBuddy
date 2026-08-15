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
import os
import re
import sys
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


def _extract_cwd_from_jsonl(p: Path) -> str:
    """从 jsonl 文件中提取 cwd 字段（支持嵌套）。

    各 IDE 的 cwd 存储位置不同：
    - Claude: 顶层 cwd 字段（type=user 行）
    - Codex: payload.cwd 字段（type=session_meta 行）
    - 其他: 尝试顶层 cwd，再尝试 payload.cwd

    比从 project_hash 目录名反编码更准确（路径含 - 时反编码不可逆）。
    """
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                # 优先顶层 cwd
                cwd = obj.get("cwd", "")
                if cwd:
                    return cwd
                # 再尝试 payload.cwd（Codex 格式）
                payload = obj.get("payload")
                if isinstance(payload, dict):
                    cwd = payload.get("cwd", "")
                    if cwd:
                        return cwd
    except Exception:
        pass
    return ""


# ===== 各 IDE 会话扫描器 =====

def scan_claude_sessions(sessions_dir: Path, ide_key: str = "Claude") -> list[dict]:
    """扫描 Claude Code 会话：sessions_dir = ~/.claude/projects。

    结构：<project-hash>/<session-id>.jsonl
    project-hash 由 cwd 路径转换：/ → -
    cwd 优先从 jsonl 文件内读取（准确），fallback 到目录名反编码。
    """
    results = []
    if not sessions_dir.exists():
        return results
    for project_dir in sessions_dir.iterdir():
        if not project_dir.is_dir():
            continue
        # 反推 cwd：C--Users-59300 → C:\Users\59300（路径含 - 时不可逆，仅作 fallback）
        fallback_cwd = _decode_project_hash(project_dir.name)
        for session_file in project_dir.glob("*.jsonl"):
            stat = _safe_stat(session_file)
            title = _extract_title_from_jsonl(session_file) or session_file.stem
            # 优先从 jsonl 内读取 cwd（准确），fallback 到目录名反编码
            cwd = _extract_cwd_from_jsonl(session_file) or fallback_cwd
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

    结构（新格式）：
    - YYYY/MM/DD/rollout-<timestamp>-<session-id>.jsonl
    结构（旧格式）：
    - <session-id>/rollout.jsonl（活跃会话）
    - archived_sessions/<session-id>/rollout.jsonl（归档会话）
    - rollout-<timestamp>-<session-id>.jsonl（旧格式单文件）

    cwd 在 payload.cwd 字段（type=session_meta 行），用 _extract_cwd_from_jsonl 读取。
    """
    results = []
    if not sessions_dir.exists():
        return results

    # 新格式：YYYY/MM/DD/rollout-*.jsonl（递归扫描日期目录）
    for rollout in sessions_dir.rglob("rollout-*.jsonl"):
        stat = _safe_stat(rollout)
        # 文件名格式：rollout-<timestamp>-<session-id>.jsonl
        m = re.match(r"rollout-[\dT-]+-(.+)\.jsonl", rollout.name)
        sid = m.group(1) if m else rollout.stem
        cwd = _extract_cwd_from_jsonl(rollout)
        results.append({
            "id": sid,
            "ide": ide_key,
            "title": _extract_title_from_jsonl(rollout) or rollout.stem,
            "cwd": cwd,
            "created_at": stat.get("created_at", ""),
            "updated_at": stat.get("updated_at", ""),
            "messages_count": _count_jsonl_messages(rollout),
            "file_path": str(rollout),
            "size_bytes": stat.get("size_bytes", 0),
        })

    # 旧格式：子目录形式 <session-id>/rollout.jsonl
    for session_dir in sessions_dir.iterdir():
        if not session_dir.is_dir():
            continue
        # 跳过日期目录（新格式已通过 rglob 扫描）
        if re.match(r"^\d{4}$", session_dir.name):
            continue
        rollout = session_dir / "rollout.jsonl"
        if not rollout.exists():
            continue
        stat = _safe_stat(rollout)
        cwd = _extract_cwd_from_jsonl(rollout)
        title = _extract_title_from_jsonl(rollout) or session_dir.name
        results.append({
            "id": session_dir.name,
            "ide": ide_key,
            "title": title,
            "cwd": cwd,
            "created_at": stat.get("created_at", ""),
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
            cwd = _extract_cwd_from_jsonl(rollout)
            title = _extract_title_from_jsonl(rollout) or session_dir.name
            results.append({
                "id": session_dir.name,
                "ide": ide_key,
                "title": f"[archived] {title}",
                "cwd": cwd,
                "created_at": stat.get("created_at", ""),
                "updated_at": stat.get("updated_at", ""),
                "messages_count": _count_jsonl_messages(rollout),
                "file_path": str(rollout),
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

    Kimi CLI（旧版，~/.kimi/sessions）结构相同，通过 ide_key 区分。
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


def _decode_project_hash(name: str) -> str:
    """将 project_hash 目录名反编码为工作目录路径。

    支持两种编码格式：
    - Claude: ``C--Users-59300`` → ``C:\\Users\\59300``（双横线代表 :\\，单横线代表 \\）
    - TraeCN: ``-d-yxz-MyAgentPlugin`` → ``D:\\yxz\\MyAgentPlugin``（前导 -，单横线分隔）
    - macOS: ``-Users-yangxuezeng-Desktop`` → ``/Users/yangxuezeng/Desktop``
    """
    # Claude Windows 格式：单字母 + -- 开头（如 C--Users-59300）
    m = re.match(r'^([a-zA-Z])--(.+)$', name)
    if m:
        drive = m.group(1).upper()
        rest = m.group(2).replace("-", "\\")
        return drive + ":\\" + rest
    # 去掉前导 -
    if name.startswith("-"):
        name = name[1:]
    parts = [p for p in name.split("-") if p]
    if not parts:
        return ""
    # Windows 路径：第一段是单字母盘符（如 c/d/e）
    if len(parts[0]) == 1 and parts[0].isalpha():
        drive = parts[0].upper()
        return drive + ":\\" + "\\".join(parts[1:]) if len(parts) > 1 else drive + ":\\"
    # macOS/Linux 路径
    return "/" + "/".join(parts)


def scan_trae_cn_sessions(sessions_dir: Path, ide_key: str = "TraeCN") -> list[dict]:
    """扫描 Trae CN 会话：sessions_dir = ~/.trae-cn/memory/projects。

    结构：<project_hash>/<YYYYMMDD>/session_memory_<uuid>.jsonl
    每个 jsonl 文件是一个会话记忆，每行记录：
    {intent, actions, outcome, learned, message_summary_time, message_id}

    - 会话 ID = 文件名中的 uuid
    - 标题 = 第一行 intent 字段
    - 时间 = 第一行 message_summary_time（格式 "2026-07-03 08:51:57"）
    - cwd = project_hash 反编码
    """
    results = []
    if not sessions_dir.exists():
        return results

    # 递归扫描：projects/<project_hash>/<date>/session_memory_*.jsonl
    for jsonl_file in sessions_dir.rglob("session_memory_*.jsonl"):
        # 提取会话 ID：session_memory_<uuid>.jsonl -> <uuid>
        session_id = jsonl_file.stem.replace("session_memory_", "")
        if not session_id:
            continue

        stat = _safe_stat(jsonl_file)

        # 从路径提取 project_hash 和日期
        # 路径结构：projects/<project_hash>/<date>/session_memory_xxx.jsonl
        try:
            date_dir = jsonl_file.parent
            project_hash_dir = date_dir.parent
            project_hash = project_hash_dir.name
            date_str = date_dir.name  # YYYYMMDD
        except Exception:
            project_hash = ""
            date_str = ""

        cwd = _decode_project_hash(project_hash)

        # 读取第一行提取 intent 和 message_summary_time
        title = ""
        updated_at = ""
        try:
            with open(jsonl_file, "r", encoding="utf-8", errors="ignore") as f:
                first_line = f.readline()
                obj = json.loads(first_line)
                title = obj.get("intent", "") or ""
                # message_summary_time 格式："2026-07-03 08:51:57" -> ISO 格式
                summary_time = obj.get("message_summary_time", "")
                if summary_time:
                    try:
                        # "2026-07-03 08:51:57" -> "2026-07-03T08:51:57"
                        updated_at = summary_time.replace(" ", "T")
                    except Exception:
                        updated_at = summary_time
        except Exception:
            pass

        # cwd fallback：_decode_project_hash 路径含 - 时不可逆，
        # 从 intent 字段中用正则提取 Windows/macOS 路径作为补充
        if not cwd or not os.path.isdir(cwd):
            if title:
                # Windows 路径：C:\xxx — 只匹配 ASCII 路径字符，遇中文停止
                m = re.search(r'([a-zA-Z]:\\[\w\\\-./ ]+)', title)
                if m:
                    cwd = m.group(1).rstrip('.,;，。 \t')
                    # 验证路径存在
                    if not os.path.isdir(cwd):
                        cwd = ""
                if not cwd:
                    # macOS/Linux 路径：/Users/xxx 或 /home/xxx
                    m = re.search(r'(/(?:Users|home|tmp|var|opt|etc)/[\w\-./ ]+)', title)
                    if m:
                        cwd = m.group(1).rstrip('.,;，。 \t')
                        if not os.path.isdir(cwd):
                            cwd = ""

        # 如果没有从内容获取到时间，回退到文件 mtime
        if not updated_at:
            updated_at = stat.get("updated_at", "")

        results.append({
            "id": session_id,
            "ide": ide_key,
            "title": title[:80] + ("..." if len(title) > 80 else "") if title else f"Session {session_id[:8]}",
            "cwd": cwd,
            "created_at": stat.get("created_at", ""),
            "updated_at": updated_at,
            "messages_count": _count_jsonl_messages(jsonl_file),
            "file_path": str(jsonl_file),
            "size_bytes": stat.get("size_bytes", 0),
        })
    return results


def _find_trae_cli_sessions_dir() -> Path:
    """查找 traecli 的 sessions 目录。

    Windows: ~/AppData/Local/trae-cli/sessions/
    macOS:   ~/Library/Application Support/trae-cli/sessions/
    Linux:   ~/.local/share/trae-cli/sessions/
    """
    home = Path.home()
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local"))
        return Path(local_appdata) / "trae-cli" / "sessions"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "trae-cli" / "sessions"
    return home / ".local" / "share" / "trae-cli" / "sessions"


def scan_trae_cli_sessions(sessions_dir: Path, ide_key: str = "TraeCN") -> list[dict]:
    """扫描 Trae CN 会话：合并 CLI 会话和 App 会话。

    CLI 会话：~/AppData/Local/trae-cli/sessions/<uuid>/session.json
    App 会话：~/.trae-cn/memory/projects/<hash>/<date>/session_memory_<uuid>.jsonl
    """
    results = []

    # --- 1. CLI 会话 ---
    cli_sessions_dir = _find_trae_cli_sessions_dir()
    if cli_sessions_dir.exists():
        for session_dir in cli_sessions_dir.iterdir():
            if not session_dir.is_dir():
                continue
            session_file = session_dir / "session.json"
            if not session_file.exists():
                continue

            stat = _safe_stat(session_file)
            session_id = session_dir.name
            title = ""
            cwd = ""
            created_at = ""
            updated_at = ""

            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                session_id = data.get("id", session_dir.name)
                created_at = data.get("created_at", "")
                updated_at = data.get("updated_at", "")
                metadata = data.get("metadata", {})
                title = metadata.get("title", "")
                cwd = metadata.get("cwd", "")
            except Exception:
                pass

            # 统计消息数（events.jsonl）
            events_file = session_dir / "events.jsonl"
            messages_count = _count_jsonl_messages(events_file) if events_file.exists() else 0

            if not updated_at:
                updated_at = stat.get("updated_at", "")

        results.append({
            "id": session_id,
            "ide": ide_key,
            "title": title[:80] + ("..." if len(title) > 80 else "") if title else f"Session {session_id[:8]}",
            "cwd": cwd,
            "created_at": created_at or stat.get("created_at", ""),
            "updated_at": updated_at,
            "messages_count": messages_count,
            "file_path": str(session_file),
            "size_bytes": stat.get("size_bytes", 0),
            "source": "cli",
        })

    # --- 2. App 会话（Trae CN IDE）---
    app_sessions_dir = Path.home() / ".trae-cn" / "memory" / "projects"
    if app_sessions_dir.exists():
        for jsonl_file in app_sessions_dir.rglob("session_memory_*.jsonl"):
            session_id = jsonl_file.stem.replace("session_memory_", "")
            if not session_id:
                continue

            stat = _safe_stat(jsonl_file)

            try:
                date_dir = jsonl_file.parent
                project_hash_dir = date_dir.parent
                project_hash = project_hash_dir.name
            except Exception:
                project_hash = ""

            cwd = _decode_project_hash(project_hash)

            title = ""
            updated_at = ""
            try:
                with open(jsonl_file, "r", encoding="utf-8", errors="ignore") as f:
                    first_line = f.readline()
                    obj = json.loads(first_line)
                    title = obj.get("intent", "") or ""
                    summary_time = obj.get("message_summary_time", "")
                    if summary_time:
                        try:
                            updated_at = summary_time.replace(" ", "T")
                        except Exception:
                            updated_at = summary_time
            except Exception:
                pass

            if not cwd or not os.path.isdir(cwd):
                pass

            results.append({
                "id": session_id,
                "ide": ide_key,
                "title": title[:80] + ("..." if len(title) > 80 else "") if title else f"Session {session_id[:8]}",
                "cwd": cwd,
                "created_at": stat.get("created_at", ""),
                "updated_at": updated_at,
                "messages_count": 0,
                "file_path": str(jsonl_file),
                "size_bytes": stat.get("size_bytes", 0),
                "source": "app",
            })

    return results


def _extract_zcode_title_from_jsonl(p: Path, max_chars: int = 80) -> str:
    """从 ZCode rollout jsonl 提取标题（第一条真实 user 消息内容）。

    ZCode rollout jsonl 每行格式：
    {completedAt, durationMs, requestId, model, request:{body:{messages:[...]}}, ...}

    跳过 system-reminder、空内容等非真实用户输入。
    """
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                # request.body.messages 是 OpenAI 格式消息数组
                messages = (
                    obj.get("request", {}).get("body", {}).get("messages", [])
                )
                if not isinstance(messages, list):
                    continue
                for msg in messages:
                    if not isinstance(msg, dict):
                        continue
                    if msg.get("role") != "user":
                        continue
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        # content 可能是 [{type: "text", text: "..."}]
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                content = item.get("text", "")
                                break
                    if not isinstance(content, str):
                        continue
                    # 跳过 system-reminder 包裹的消息和空内容
                    stripped = content.strip()
                    if not stripped:
                        continue
                    if stripped.startswith("<system-reminder>"):
                        continue
                    if stripped.startswith("<command-name>"):
                        continue
                    text = stripped.replace("\n", " ")
                    return text[:max_chars] + ("..." if len(text) > max_chars else "")
    except Exception:
        pass
    return ""


def scan_zcode_sessions(sessions_dir: Path, ide_key: str = "ZCode") -> list[dict]:
    """扫描 ZCode 会话：sessions_dir = ~/.zcode/cli/rollout。

    结构：model-io-sess_<uuid>.jsonl（每行一条模型 I/O 记录）
    关联目录：~/.zcode/cli/artifacts/sess_<uuid>/（工具调用记录）

    - 会话 ID = sess_<uuid>
    - 标题 = 第一条 user 消息内容
    - 时间 = 第一行 completedAt 或文件 mtime
    - messages_count = jsonl 行数
    """
    results = []
    if not sessions_dir.exists():
        return results

    # ZCode 配置根目录：rollout 的上两级是 ~/.zcode
    # rollout -> cli -> .zcode
    zcode_root = sessions_dir.parent.parent  # ~/.zcode
    artifacts_dir = zcode_root / "cli" / "artifacts"

    for jsonl_file in sessions_dir.glob("model-io-sess_*.jsonl"):
        # 提取会话 ID：model-io-sess_<uuid>.jsonl -> sess_<uuid>
        session_id = jsonl_file.stem  # model-io-sess_<uuid>
        if not session_id.startswith("model-io-sess_"):
            continue
        # 完整会话 ID = sess_<uuid>（去掉 model-io- 前缀）
        full_session_id = session_id.replace("model-io-", "")

        stat = _safe_stat(jsonl_file)

        # 提取标题和时间
        title = _extract_zcode_title_from_jsonl(jsonl_file)
        updated_at = ""
        created_at = ""
        try:
            with open(jsonl_file, "r", encoding="utf-8", errors="ignore") as f:
                first_line = f.readline()
                obj = json.loads(first_line)
                completed_at = obj.get("completedAt", "")
                if completed_at:
                    # completedAt 是 ISO-8601 带Z后缀，直接用
                    updated_at = completed_at
                    created_at = completed_at
        except Exception:
            pass

        if not updated_at:
            updated_at = stat.get("updated_at", "")
        if not created_at:
            created_at = stat.get("created_at", "")

        # 统计工具调用数（artifacts/sess_<uuid>/call_*.json）
        tool_calls = 0
        artifact_dir = artifacts_dir / full_session_id
        if artifact_dir.exists():
            try:
                tool_calls = len(list(artifact_dir.glob("call_*.json")))
            except Exception:
                pass

        results.append({
            "id": full_session_id,
            "ide": ide_key,
            "title": title or f"Session {full_session_id[-8:]}",
            "cwd": "",  # ZCode rollout 不直接记录 cwd
            "created_at": created_at,
            "updated_at": updated_at,
            "messages_count": _count_jsonl_messages(jsonl_file),
            "file_path": str(jsonl_file),
            "size_bytes": stat.get("size_bytes", 0),
            "tool_calls": tool_calls,
        })
    return results


# ===== 调度入口 =====

# IDE key → 扫描器映射
IDE_SESSION_SCANNERS = {
    "Claude": scan_claude_sessions,
    "Codex": scan_codex_sessions,
    "Cursor": scan_cursor_sessions,
    "CodeBuddy": lambda d, k="CodeBuddy": scan_generic_sessions(d, k),
    "KimiCLI": lambda d, k="KimiCLI": scan_kimi_sessions(d, k),
    "KimiCode": scan_kimi_sessions,
    "WorkBuddy": lambda d, k="WorkBuddy": scan_generic_sessions(d, k),
    "OpenClaw": lambda d, k="OpenClaw": scan_generic_sessions(d, k),
    "Qoder": lambda d, k="Qoder": scan_generic_sessions(d, k),
    "QoderCN": lambda d, k="QoderCN": scan_generic_sessions(d, k),
    "OpenCode": lambda d, k="OpenCode": scan_generic_sessions(d, k),
    "Trae": lambda d, k="Trae": scan_generic_sessions(d, k),
    "TraeCN": scan_trae_cli_sessions,
    "TraeSoloCN": scan_trae_cli_sessions,
    "ZCode": scan_zcode_sessions,
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
# 命令格式均来自官方文档验证，详见 AGENTS.md
IDE_RESUME_COMMANDS = {
    "Claude": "{exe} --resume {session_id}",                  # claude --resume <id>  (docs.anthropic.com)
    "Codex": "{exe} resume {session_id}",                    # codex resume <id>     (用户确认)
    "KimiCLI": "{exe} --session {session_id}",                # kimi --session <id>   (kimi-cli.com)
    "KimiCode": "{exe} --session {session_id}",               # kimi --session <id>   (kimi-cli.com)
    "Cursor": "{exe} --continue",                             # cursor --continue     (无 --resume，只能继续最近会话)
    "OpenCode": "{exe} --session {session_id}",               # opencode --session <id>  (open-code.ai/docs/cli)
    "Qoder": "{exe} -r {session_id}",                         # qodercli -r <id>      (docs.qoder.com)
    "QoderCN": "{exe} -r {session_id}",                       # qoderclicn -r <id>    (help.aliyun.com)
    "WorkBuddy": "{exe} --resume {session_id}",               # codebuddy --resume <id>  (codebuddy.ai/docs)
    "CodeBuddy": "{exe} --resume {session_id}",               # codebuddy --resume <id>  (codebuddy.cn/docs/cli/headless)
    "TraeCN": "{exe} --resume {session_id}",                  # traecli --resume <id> (docs.trae.cn)
    "Copilot": "{exe} --resume {session_id}",                  # copilot --resume <id>  (docs.github.com/en/copilot/cli)
}


def build_resume_command(ide_key: str, exe_path: str, session_id: str, cwd: str = "", source: str = "") -> str:
    """构造恢复会话的命令行。

    Args:
        ide_key: IDE 标识
        exe_path: 可执行文件路径
        session_id: 会话 ID
        cwd: 工作目录
        source: 会话来源（"cli" / "app"），用于区分 TraeCN CLI 和 App 会话

    Returns:
        完整命令字符串。若 IDE 不支持 resume，返回空字符串。
    """
    template = IDE_RESUME_COMMANDS.get(ide_key)
    if not template or not exe_path:
        return ""
    # TraeCN App 会话不走 CLI resume，由 launch.py 的 _try_app 处理
    if ide_key == "TraeCN" and source == "app":
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
