"""市场认证模块 — CLI 侧 JWT 登录 / token 存储。

token + server_url 存储到 ~/.agentbuddy/auth.json，所有 plugin publish 命令复用。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .logging import info, warn, error, hint

DEFAULT_SERVER_URL = "http://123.60.75.27:5001"

_AUTH_DIR = Path.home() / ".agentbuddy"
_AUTH_FILE = _AUTH_DIR / "auth.json"


def _ensure_auth_dir():
    _AUTH_DIR.mkdir(parents=True, exist_ok=True)


def load_auth() -> dict[str, Any]:
    """读取本地认证信息。返回空 dict 表示未登录。"""
    if not _AUTH_FILE.exists():
        return {}
    try:
        return json.loads(_AUTH_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_auth(data: dict[str, Any]) -> None:
    _ensure_auth_dir()
    _AUTH_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def clear_auth() -> None:
    if _AUTH_FILE.exists():
        _AUTH_FILE.unlink()


def get_token() -> str | None:
    return load_auth().get("token")


def get_server_url() -> str:
    return load_auth().get("server_url", DEFAULT_SERVER_URL)


def get_user() -> dict | None:
    return load_auth().get("user")


def is_logged_in() -> bool:
    return bool(get_token())


# ============================================================
# API 调用
# ============================================================

def login(username: str, password: str, server_url: str | None = None) -> dict:
    """POST /api/auth/login — 登录并存储 token。"""
    import requests

    base = (server_url or get_server_url()).rstrip("/")
    resp = requests.post(
        f"{base}/api/auth/login",
        json={"username": username, "password": password},
        timeout=15,
    )
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(result.get("error", f"登录失败 (HTTP {resp.status_code})"))

    data = result["data"]
    auth_data = {
        "token": data["token"],
        "server_url": base,
        "user": {
            "id": data.get("id"),
            "username": data.get("username"),
            "email": data.get("email"),
            "role": data.get("role"),
        },
    }
    save_auth(auth_data)
    return auth_data


def register(
    username: str, password: str, email: str = "", server_url: str | None = None
) -> dict:
    """POST /api/auth/register — 注册并存储 token。"""
    import requests

    base = (server_url or get_server_url()).rstrip("/")
    body: dict[str, Any] = {"username": username, "password": password}
    if email:
        body["email"] = email
    resp = requests.post(f"{base}/api/auth/register", json=body, timeout=15)
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(result.get("error", f"注册失败 (HTTP {resp.status_code})"))

    data = result["data"]
    auth_data = {
        "token": data["token"],
        "server_url": base,
        "user": {
            "id": data.get("id"),
            "username": data.get("username"),
            "email": data.get("email"),
            "role": data.get("role"),
        },
    }
    save_auth(auth_data)
    return auth_data


def whoami() -> dict | None:
    """GET /api/auth/me — 查询当前登录用户。"""
    import requests

    token = get_token()
    if not token:
        return None
    base = get_server_url()
    resp = requests.get(
        f"{base}/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    result = resp.json()
    if not result.get("ok"):
        return None
    return result.get("data")


def logout() -> bool:
    """清除本地 token。"""
    if not is_logged_in():
        return False
    clear_auth()
    return True
