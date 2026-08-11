"""Web 服务密码管理。

为支持密码认证的 IDE Web 服务（web_install.auth == "password"）生成随机密码并
持久化到 ~/.agentbuddy/web_passwords.json，提供"查看密码 / 复制带密码链接 / 重置密码"能力。

- 密码用 secrets.token_urlsafe(12)（约 16 字符，URL 安全，可放入 ?password= 查询参数）
- 密码不会写入仓库，仅存本地用户目录
"""
import json
import secrets
import time
from pathlib import Path

_PASSWORDS_FILE = Path.home() / ".agentbuddy" / "web_passwords.json"


def _load() -> dict:
    try:
        return json.loads(_PASSWORDS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict) -> None:
    try:
        _PASSWORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PASSWORDS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _new_password() -> str:
    return secrets.token_urlsafe(12)


def get_or_create_password(ide_key: str) -> str:
    """读取已有密码；不存在则生成并持久化。"""
    data = _load()
    entry = data.get(ide_key)
    if entry and entry.get("password"):
        return entry["password"]
    pwd = _new_password()
    data[ide_key] = {"password": pwd, "created_at": int(time.time())}
    _save(data)
    return pwd


def regenerate_password(ide_key: str) -> str:
    """重新生成密码并持久化（旧链接立即失效）。"""
    pwd = _new_password()
    data = _load()
    data[ide_key] = {"password": pwd, "created_at": int(time.time())}
    _save(data)
    return pwd


def get_password(ide_key: str) -> str | None:
    entry = _load().get(ide_key)
    return entry.get("password") if entry else None


def web_urls(port: int, password: str) -> dict:
    """构造访问 URL 与带密码的免登录 URL（?password= 仅对首页生效）。"""
    base = f"http://localhost:{int(port)}"
    return {
        "url": base,
        "url_with_password": f"{base}?password={password}",
    }


__all__ = [
    "get_or_create_password", "regenerate_password", "get_password", "web_urls",
]
