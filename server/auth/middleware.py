"""JWT token 验证中间件。

使用方式：
    from .middleware import require_auth, optional_auth, get_current_user

    @bp.route("/publish", methods=["POST"])
    @require_auth
    def publish():
        user = get_current_user()  # → { id, username }
        ...
"""
import os
import functools
import jwt
from flask import request, g
from .models import get_db

# JWT 密钥（可通过环境变量覆盖）
JWT_SECRET = os.environ.get("AGENTBUDDY_JWT_SECRET", "agentbuddy-server-secret-2026")
JWT_ALGORITHM = "HS256"


def generate_token(user_id: int, username: str) -> str:
    """生成 JWT token。"""
    payload = {"id": user_id, "username": username}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    """解码 JWT token，失败返回 None。"""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def _extract_token() -> str | None:
    """从请求头提取 token。"""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def get_current_user() -> dict | None:
    """获取当前登录用户（从 g.current_user 读取，由 require_auth 设置）。"""
    user = getattr(g, "current_user", None)
    if user:
        return dict(user)

    token = _extract_token()
    if not token:
        return None

    payload = decode_token(token)
    if not payload:
        return None

    conn = get_db()
    row = conn.execute(
        "SELECT id, username, email, role FROM users WHERE id = ?", (payload["id"],)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def require_auth(fn):
    """装饰器：要求登录，未登录返回 401。"""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return {"ok": False, "error": "请先登录"}, 401
        g.current_user = user
        return fn(*args, **kwargs)
    return wrapper


def optional_auth(fn):
    """装饰器：可选登录，登录了设置 g.current_user，未登录也放行。"""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if user:
            g.current_user = user
        return fn(*args, **kwargs)
    return wrapper
