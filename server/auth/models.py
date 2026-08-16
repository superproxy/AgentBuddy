"""数据模型 — 用户、团队、成员关系、插件、点赞。

底层经 db.py 抽象层支持 SQLite / MySQL 双驱动，由环境变量
AGENTBUDDY_DB_BACKEND 切换（默认 sqlite，零配置）。
数据库连接配置由 app.py 通过 set_db_path / set_mysql_url 传入。
启动时自动从 index.json 迁移已有插件数据。
首次注册的用户自动成为管理员。
"""
import json
from pathlib import Path
from datetime import datetime, timezone
import bcrypt

import db as _db

DB_PATH: Path | None = None          # SQLite 路径（兼容旧接口）
MARKETPLACE_DIR: Path | None = None


def set_db_path(path: Path):
    """设置 SQLite 数据库文件路径（由 app.py 在启动时调用）。

    兼容旧 API：内部委托给 db.set_sqlite_path。
    """
    global DB_PATH
    DB_PATH = path
    _db.set_sqlite_path(path)
    _db.set_init_sql(_DDL)
    _db.init_db()


def set_mysql_url(url: str):
    """切换到 MySQL backend（由 app.py 在启动时按环境变量调用）。"""
    global DB_PATH
    DB_PATH = None  # MySQL 模式不用文件路径
    _db.set_mysql_url(url)
    _db.set_init_sql(_DDL)
    _db.init_db()


def set_marketplace_dir(path: Path):
    """设置 marketplace 目录（用于 index.json 迁移）。"""
    global MARKETPLACE_DIR
    MARKETPLACE_DIR = path


def get_db():
    """获取数据库连接（统一接口，SQLite/MySQL 自适应）。"""
    return _db.get_db()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def init_db():
    """初始化数据库表（幂等，已存在则跳过）。

    委托给 db.init_db(_DDL)。set_db_path / set_mysql_url 会自动调用，
    通常不需要外部手动调用本函数。
    """
    _db.init_db(_DDL)


# 建表 DDL（MySQL 方言；SQLite 模式由 db.py 自动翻译）
_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    username    VARCHAR(64) NOT NULL UNIQUE,
    password    VARCHAR(128) NOT NULL,
    email       VARCHAR(128) DEFAULT '',
    role        VARCHAR(16) NOT NULL DEFAULT 'member',
    created_at  VARCHAR(40) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS teams (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    name        VARCHAR(128) NOT NULL,
    description TEXT,
    owner_id    INT NOT NULL,
    created_at  VARCHAR(40) NOT NULL,
    FOREIGN KEY (owner_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS team_members (
    team_id     INT NOT NULL,
    user_id     INT NOT NULL,
    role        VARCHAR(16) NOT NULL DEFAULT 'member',
    joined_at  VARCHAR(40) NOT NULL,
    PRIMARY KEY (team_id, user_id),
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS plugins (
    id           VARCHAR(128) PRIMARY KEY,
    name         VARCHAR(128) NOT NULL,
    version      VARCHAR(32) NOT NULL DEFAULT '1.0.0',
    description  TEXT,
    author       VARCHAR(64) DEFAULT '管理员',
    author_id    INT DEFAULT NULL,
    file         VARCHAR(255) NOT NULL,
    size         INT DEFAULT 0,
    published_at VARCHAR(40) NOT NULL,
    tags         TEXT,
    downloads    INT DEFAULT 0,
    likes        INT DEFAULT 0,
    scope        VARCHAR(16) DEFAULT 'public',
    team_id      INT DEFAULT NULL,
    INDEX idx_plugins_author (author),
    INDEX idx_plugins_published (published_at),
    INDEX idx_plugins_downloads (downloads),
    FOREIGN KEY (author_id) REFERENCES users(id),
    FOREIGN KEY (team_id) REFERENCES teams(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS plugin_likes (
    plugin_id   VARCHAR(128) NOT NULL,
    user_id     INT NOT NULL,
    created_at  VARCHAR(40) NOT NULL,
    PRIMARY KEY (plugin_id, user_id),
    FOREIGN KEY (plugin_id) REFERENCES plugins(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS plugin_favorites (
    plugin_id   VARCHAR(128) NOT NULL,
    user_id     INT NOT NULL,
    created_at  VARCHAR(40) NOT NULL,
    PRIMARY KEY (plugin_id, user_id),
    FOREIGN KEY (plugin_id) REFERENCES plugins(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS invitations (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    team_id     INT NOT NULL,
    inviter_id  INT NOT NULL,
    invitee_id  INT NOT NULL,
    status      VARCHAR(16) NOT NULL DEFAULT 'pending',
    message     TEXT,
    created_at  VARCHAR(40) NOT NULL,
    responded_at VARCHAR(40),
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (inviter_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (invitee_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def migrate_index_json():
    """从 index.json 迁移已有插件数据到 SQLite（幂等）。"""
    if MARKETPLACE_DIR is None:
        return
    index_file = MARKETPLACE_DIR / "index.json"
    if not index_file.exists():
        return
    try:
        items = json.loads(index_file.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            return
    except Exception:
        return

    conn = get_db()
    migrated = 0
    for it in items:
        pid = it.get("id")
        if not pid:
            continue
        # 跳过已存在的
        if conn.execute("SELECT 1 FROM plugins WHERE id = ?", (pid,)).fetchone():
            continue
        tags = it.get("tags", [])
        if isinstance(tags, list):
            tags = json.dumps(tags, ensure_ascii=False)
        else:
            tags = "[]"
        conn.execute(
            """INSERT IGNORE INTO plugins
               (id, name, version, description, author, author_id, file, size,
                published_at, tags, downloads, likes, scope, team_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pid,
                it.get("name", ""),
                it.get("version", "1.0.0"),
                it.get("description", ""),
                it.get("author", "管理员"),
                it.get("author_id"),
                it.get("file", ""),
                it.get("size", 0),
                it.get("published_at", now_iso()),
                tags,
                it.get("downloads", 0),
                it.get("likes", 0),
                it.get("scope", "public"),
                it.get("team_id"),
            ),
        )
        migrated += 1
    conn.commit()
    conn.close()
    if migrated:
        print(f"[migrate] 从 index.json 迁移了 {migrated} 个插件到 SQLite")


def _create_default_admin():
    """已废弃：不再创建默认管理员。首个注册的用户自动成为 admin。"""
    pass


def is_team_member(team_id: int, user_id: int) -> bool:
    """检查用户是否为团队成员。"""
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM team_members WHERE team_id = ? AND user_id = ?",
        (team_id, user_id),
    ).fetchone()
    conn.close()
    return row is not None


def is_team_owner(team_id: int, user_id: int) -> bool:
    """检查用户是否为团队 owner。"""
    conn = get_db()
    row = conn.execute(
        "SELECT role FROM team_members WHERE team_id = ? AND user_id = ?",
        (team_id, user_id),
    ).fetchone()
    conn.close()
    return row is not None and row["role"] == "owner"


# ==================== 邀请管理 ====================

def create_invitation(team_id: int, inviter_id: int, invitee_id: int, message: str = "") -> dict:
    """创建邀请。返回邀请记录 dict。"""
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO invitations (team_id, inviter_id, invitee_id, status, message, created_at) "
        "VALUES (?, ?, ?, 'pending', ?, ?)",
        (team_id, inviter_id, invitee_id, message, now_iso()),
    )
    inv_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return get_invitation(inv_id)


def get_invitation(inv_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute(
        """SELECT i.*, t.name as team_name, t.description as team_desc,
                  u1.username as inviter_name, u2.username as invitee_name
           FROM invitations i
           JOIN teams t ON t.id = i.team_id
           JOIN users u1 ON u1.id = i.inviter_id
           JOIN users u2 ON u2.id = i.invitee_id
           WHERE i.id = ?""",
        (inv_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_pending_invitations(user_id: int) -> list[dict]:
    """获取用户的待处理邀请列表。"""
    conn = get_db()
    rows = conn.execute(
        """SELECT i.*, t.name as team_name, t.description as team_desc,
                  u.username as inviter_name
           FROM invitations i
           JOIN teams t ON t.id = i.team_id
           JOIN users u ON u.id = i.inviter_id
           WHERE i.invitee_id = ? AND i.status = 'pending'
           ORDER BY i.created_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def respond_invitation(inv_id: int, user_id: int, accept: bool) -> dict | None:
    """接受或拒绝邀请。"""
    conn = get_db()
    inv = conn.execute(
        "SELECT * FROM invitations WHERE id = ? AND invitee_id = ? AND status = 'pending'",
        (inv_id, user_id),
    ).fetchone()
    if not inv:
        conn.close()
        return None

    status = "accepted" if accept else "declined"
    conn.execute(
        "UPDATE invitations SET status = ?, responded_at = ? WHERE id = ?",
        (status, now_iso(), inv_id),
    )

    # 接受邀请 → 加入团队
    if accept:
        # 检查是否已在团队（可能已通过其他方式加入）
        existing = conn.execute(
            "SELECT 1 FROM team_members WHERE team_id = ? AND user_id = ?",
            (inv["team_id"], user_id),
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO team_members (team_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)",
                (inv["team_id"], user_id, now_iso()),
            )

    conn.commit()
    conn.close()
    return get_invitation(inv_id)


# ==================== 插件 CRUD ====================

def plugin_list(q: str = "", scope: str = "", team_id: int | None = None, user_id: int | None = None) -> list[dict]:
    """查询插件列表。"""
    conn = get_db()
    sql = "SELECT * FROM plugins"
    conditions = []
    params = []
    if scope == "public":
        conditions.append("scope = 'public'")
    elif scope == "team":
        conditions.append("scope = 'team'")
    if team_id:
        conditions.append("team_id = ?")
        params.append(team_id)
    if q:
        conditions.append("(LOWER(name) LIKE ? OR LOWER(description) LIKE ? OR LOWER(author) LIKE ?)")
        param = f"%{q.lower()}%"
        params.extend([param, param, param])
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY published_at DESC"
    rows = conn.execute(sql, params).fetchall()
    items = [_plugin_row_to_dict(r) for r in rows]
    # 附加 liked + favorited 字段
    if user_id:
        liked_ids = _get_liked_ids(conn, [i["id"] for i in items], user_id) if items else set()
        fav_ids = _get_favorited_ids(conn, [i["id"] for i in items], user_id) if items else set()
        for it in items:
            it["liked"] = it["id"] in liked_ids
            it["favorited"] = it["id"] in fav_ids
    conn.close()
    return items


def _get_liked_ids(conn, plugin_ids: list[str], user_id: int) -> set[str]:
    """批量查询用户已点赞的插件 ID。"""
    if not plugin_ids:
        return set()
    ph, params = _db.in_clause(plugin_ids)
    rows = conn.execute(
        f"SELECT plugin_id FROM plugin_likes WHERE user_id = ? AND plugin_id IN ({ph})",
        [user_id] + params,
    ).fetchall()
    return {r["plugin_id"] for r in rows}


def _get_favorited_ids(conn, plugin_ids: list[str], user_id: int) -> set[str]:
    """批量查询用户已收藏的插件 ID。"""
    if not plugin_ids:
        return set()
    ph, params = _db.in_clause(plugin_ids)
    rows = conn.execute(
        f"SELECT plugin_id FROM plugin_favorites WHERE user_id = ? AND plugin_id IN ({ph})",
        [user_id] + params,
    ).fetchall()
    return {r["plugin_id"] for r in rows}


def plugin_get(plugin_id: str, user_id: int | None = None) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM plugins WHERE id = ?", (plugin_id,)).fetchone()
    if not row:
        conn.close()
        return None
    d = _plugin_row_to_dict(row)
    if user_id:
        liked = conn.execute(
            "SELECT 1 FROM plugin_likes WHERE plugin_id = ? AND user_id = ?",
            (plugin_id, user_id),
        ).fetchone()
        d["liked"] = liked is not None
        fav = conn.execute(
            "SELECT 1 FROM plugin_favorites WHERE plugin_id = ? AND user_id = ?",
            (plugin_id, user_id),
        ).fetchone()
        d["favorited"] = fav is not None
    conn.close()
    return d


def plugin_save(entry: dict):
    """插入或更新插件（upsert）。"""
    conn = get_db()
    tags = entry.get("tags", [])
    if isinstance(tags, list):
        tags = json.dumps(tags, ensure_ascii=False)
    conn.execute(
        """INSERT INTO plugins (id, name, version, description, author, author_id, file, size,
           published_at, tags, downloads, likes, scope, team_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON DUPLICATE KEY UPDATE
             name=VALUES(name), version=VALUES(version),
             description=VALUES(description), author=VALUES(author),
             author_id=VALUES(author_id), file=VALUES(file), size=VALUES(size),
             tags=VALUES(tags), scope=VALUES(scope), team_id=VALUES(team_id)""",
        (
            entry["id"],
            entry.get("name", ""),
            entry.get("version", "1.0.0"),
            entry.get("description", ""),
            entry.get("author", "管理员"),
            entry.get("author_id"),
            entry.get("file", ""),
            entry.get("size", 0),
            entry.get("published_at", now_iso()),
            tags,
            entry.get("downloads", 0),
            entry.get("likes", 0),
            entry.get("scope", "public"),
            entry.get("team_id"),
        ),
    )
    conn.commit()
    conn.close()


def plugin_delete(plugin_id: str):
    conn = get_db()
    try:
        # MySQL/SQLite 均在 autocommit=False 下默认开启事务，无需显式 BEGIN
        conn.execute("DELETE FROM plugin_likes WHERE plugin_id = ?", (plugin_id,))
        conn.execute("DELETE FROM plugin_favorites WHERE plugin_id = ?", (plugin_id,))
        conn.execute("DELETE FROM plugins WHERE id = ?", (plugin_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def plugin_increment_downloads(plugin_id: str):
    conn = get_db()
    conn.execute("UPDATE plugins SET downloads = downloads + 1 WHERE id = ?", (plugin_id,))
    conn.commit()
    conn.close()


def plugin_toggle_like(plugin_id: str, user_id: int) -> bool:
    """切换点赞。返回 True=已点赞，False=已取消。"""
    conn = get_db()
    existing = conn.execute(
        "SELECT 1 FROM plugin_likes WHERE plugin_id = ? AND user_id = ?",
        (plugin_id, user_id),
    ).fetchone()
    if existing:
        conn.execute("DELETE FROM plugin_likes WHERE plugin_id = ? AND user_id = ?", (plugin_id, user_id))
        conn.execute("UPDATE plugins SET likes = likes - 1 WHERE id = ?", (plugin_id,))
        conn.commit()
        conn.close()
        return False
    else:
        conn.execute("INSERT INTO plugin_likes (plugin_id, user_id, created_at) VALUES (?, ?, ?)",
                     (plugin_id, user_id, now_iso()))
        conn.execute("UPDATE plugins SET likes = likes + 1 WHERE id = ?", (plugin_id,))
        conn.commit()
        conn.close()
        return True


# ==================== 收藏管理 ====================

def plugin_toggle_favorite(plugin_id: str, user_id: int) -> bool:
    """切换收藏。返回 True=已收藏，False=已取消。"""
    conn = get_db()
    existing = conn.execute(
        "SELECT 1 FROM plugin_favorites WHERE plugin_id = ? AND user_id = ?",
        (plugin_id, user_id),
    ).fetchone()
    if existing:
        conn.execute("DELETE FROM plugin_favorites WHERE plugin_id = ? AND user_id = ?", (plugin_id, user_id))
        conn.commit()
        conn.close()
        return False
    else:
        conn.execute("INSERT INTO plugin_favorites (plugin_id, user_id, created_at) VALUES (?, ?, ?)",
                     (plugin_id, user_id, now_iso()))
        conn.commit()
        conn.close()
        return True


def get_favorite_plugin_ids(user_id: int) -> set[str]:
    """获取用户收藏的插件 ID 集合。"""
    conn = get_db()
    rows = conn.execute(
        "SELECT plugin_id FROM plugin_favorites WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()
    return {r["plugin_id"] for r in rows}


def get_favorited_plugins(user_id: int) -> list[dict]:
    """获取用户收藏的插件列表。"""
    conn = get_db()
    rows = conn.execute(
            """SELECT p.* FROM plugins p
               JOIN plugin_favorites f ON f.plugin_id = p.id
               WHERE f.user_id = ?
               ORDER BY f.created_at DESC""",
            (user_id,),
        ).fetchall()
    items = [_plugin_row_to_dict(r) for r in rows]
    # 附加 liked + favorited 字段
    if items:
        liked_ids = _get_liked_ids(conn, [i["id"] for i in items], user_id)
        for it in items:
            it["liked"] = it["id"] in liked_ids
            it["favorited"] = True
    conn.close()
    return items


def _plugin_row_to_dict(row) -> dict:
    d = dict(row) if row else {}
    # tags 从 JSON 字符串转回 list
    try:
        d["tags"] = json.loads(d.get("tags", "[]"))
    except (json.JSONDecodeError, TypeError):
        d["tags"] = []
    return d


def get_liked_plugins(user_id: int) -> list[dict]:
    """获取用户点赞的插件列表。"""
    conn = get_db()
    rows = conn.execute(
            """SELECT p.* FROM plugins p
               JOIN plugin_likes l ON l.plugin_id = p.id
               WHERE l.user_id = ?
               ORDER BY l.created_at DESC""",
            (user_id,),
        ).fetchall()
    items = [_plugin_row_to_dict(r) for r in rows]
    # 附加 liked + favorited 字段
    if items:
        favorited_ids = _get_favorited_ids(conn, [i["id"] for i in items], user_id)
        for it in items:
            it["liked"] = True
            it["favorited"] = it["id"] in favorited_ids
    conn.close()
    return items
