"""Web 服务密码管理。

密码统一由 AgentBuddy 生成并持久化在 ~/.agentbuddy/web_passwords.json，
启动 Web 服务时通过命令注入（按 ide.yaml web_install 配置）：

- password_arg（codexapp）：CLI 参数 `--password <pwd>`
- password_env（CodeBuddy/OpenCode）：环境变量注入启动命令
  （CODEBUDDY_GATEWAY_PASSWORD 优先级高于 settings.json；
   OPENCODE_SERVER_PASSWORD 启用 HTTP Basic Auth）

免登录 URL 风格（url_style）：
- query: http://host:port?password=xxx（CodeBuddy）
- path:  http://host:port/password=xxx（codexapp）
- basic: http://user:pass@host:port（OpenCode Basic Auth）
"""
import json
import secrets
from pathlib import Path
from urllib.parse import quote

_STORE = Path.home() / ".agentbuddy" / "web_passwords.json"


def _load() -> dict:
    try:
        return json.loads(_STORE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    _STORE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _new_password() -> str:
    return secrets.token_urlsafe(24)


def get_or_create_password(ide_key: str) -> str:
    """读取已有密码；不存在则生成并持久化。"""
    data = _load()
    pwd = data.get(ide_key, {}).get("password")
    if pwd:
        return pwd
    pwd = _new_password()
    data[ide_key] = {"password": pwd}
    _save(data)
    return pwd


def regenerate_password(ide_key: str) -> str:
    """重新生成密码并持久化（重启服务后生效，旧链接立即失效）。"""
    pwd = _new_password()
    data = _load()
    data[ide_key] = {"password": pwd}
    _save(data)
    return pwd


def get_password(ide_key: str) -> str | None:
    return _load().get(ide_key, {}).get("password") or None


def build_auth_url(base: str, password: str, style: str = "query",
                   username: str = "") -> str:
    """构造带密码的免登录 URL。"""
    if not password:
        return base
    pwd = quote(password, safe="")
    if style == "path":
        return f"{base}/password={pwd}"
    if style == "basic":
        user = quote(username or "opencode", safe="")
        return f"http://{user}:{pwd}@{base.split('://', 1)[-1]}"
    return f"{base}?password={pwd}"


def web_urls(port: int, password: str, style: str = "query",
             username: str = "") -> dict:
    base = f"http://localhost:{int(port)}"
    return {
        "url": base,
        "url_with_password": build_auth_url(base, password, style, username),
    }


__all__ = [
    "get_or_create_password", "regenerate_password", "get_password",
    "web_urls", "build_auth_url",
]
