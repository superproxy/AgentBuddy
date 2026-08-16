"""数据库抽象层 — SQLite / MySQL 双驱动，统一接口。

设计原则：
1. 应用层只调用 get_db() / execute() / row_to_dict() 等函数；
2. SQL 方言差异由本层在执行前自动翻译（INSERT IGNORE / AUTO_INCREMENT / 占位符 / ON CONFLICT）；
3. 默认 SQLite（零配置兜底），通过环境变量切换到 MySQL；
4. 支持 ?  占位符风格（应用层不变），底层按 backend 转换为 %s。

环境变量：
    AGENTBUDDY_DB_BACKEND   sqlite（默认） / mysql
    AGENTBUDDY_DB_URL       mysql://user:pass@host:port/dbname  （backend=mysql 时必填）
    AGENTBUDDY_DB_POOL_SIZE 连接池大小（MySQL，默认 5）

使用示例：
    from db import get_db, row_to_dict, now_iso
    conn = get_db()
    rows = conn.execute("SELECT * FROM users WHERE id = ?", (1,)).fetchall()
    user = row_to_dict(rows[0])
    conn.close()
"""
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

# === 全局配置 ===
_BACKEND: str | None = None       # "sqlite" / "mysql"
_DB_PATH: Path | None = None      # SQLite 文件路径
_DB_URL: str | None = None        # MySQL 连接 URL
_POOL_SIZE: int = 5               # MySQL 连接池
_POOL: list = []                  # 连接池实例（惰性创建）
_INIT_SQL: str | None = None      # 初始化 SQL（建表，由上层 set_init_sql 设置）


# === 配置 API ===
def set_sqlite_path(path: Path) -> None:
    """设置 SQLite 数据库文件路径（与 app.py 的 set_db_path 兼容）。"""
    global _BACKEND, _DB_PATH
    _BACKEND = "sqlite"
    _DB_PATH = path
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def set_mysql_url(url: str) -> None:
    """设置 MySQL 连接 URL。"""
    global _BACKEND, _DB_URL
    _BACKEND = "mysql"
    _DB_URL = url


def set_init_sql(sql: str) -> None:
    """设置初始化 SQL（建表语句），由上层模块（auth.models）注册。

    SQL 应使用 MySQL 方言（AUTO_INCREMENT / INSERT IGNORE），
    本层在 SQLite 模式下自动翻译。
    """
    global _INIT_SQL
    _INIT_SQL = sql


def backend() -> str:
    """当前 backend（sqlite / mysql）。"""
    if _BACKEND is not None:
        return _BACKEND
    # 从环境变量读取
    b = os.environ.get("AGENTBUDDY_DB_BACKEND", "sqlite").strip().lower()
    if b not in ("sqlite", "mysql"):
        b = "sqlite"
    return b


def is_mysql() -> bool:
    return backend() == "mysql"


# === SQL 方言翻译 ===

def translate_sql_for_sqlite(sql: str) -> str:
    """将 MySQL 方言 SQL 翻译为 SQLite 兼容形式。

    翻译规则（保守，避免误伤）：
        INT PRIMARY KEY AUTO_INCREMENT -> INTEGER PRIMARY KEY AUTOINCREMENT
        AUTO_INCREMENT                -> AUTOINCREMENT   （仅 CREATE TABLE 上下文）
        INSERT IGNORE INTO            -> INSERT OR IGNORE INTO
        ON DUPLICATE KEY UPDATE ...   -> 删除（用 INSERT OR IGNORE 兜底）
        ENGINE=InnoDB ...             -> 删除（SQLite 不识别）
        DEFAULT CHARSET=...           -> 删除
        %s                           -> ?
    """
    # 1. 占位符
    out = sql.replace("%s", "?")
    # 2. INT PRIMARY KEY AUTO_INCREMENT -> INTEGER PRIMARY KEY AUTOINCREMENT
    out = re.sub(
        r"\bINT\s+PRIMARY\s+KEY\s+AUTO_INCREMENT\b",
        "INTEGER PRIMARY KEY AUTOINCREMENT",
        out,
        flags=re.IGNORECASE,
    )
    # 3. 单独的 AUTO_INCREMENT -> AUTOINCREMENT
    out = re.sub(r"\bAUTO_INCREMENT\b", "AUTOINCREMENT", out)
    # 4. INSERT IGNORE
    out = re.sub(r"\bINSERT\s+IGNORE\s+INTO\b", "INSERT OR IGNORE INTO", out, flags=re.IGNORECASE)
    # 5. ON DUPLICATE KEY UPDATE ... （去掉，依赖 INSERT OR IGNORE 兜底）
    #    匹配到字符串末尾（executescript 已按 ; 拆分，单条语句无 ;）
    out = re.sub(
        r"\s*ON\s+DUPLICATE\s+KEY\s+UPDATE\s+.*$",
        "",
        out,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # 6. ENGINE=InnoDB ... / DEFAULT CHARSET=... （MySQL 建表尾巴，SQLite 删掉）
    out = re.sub(r"\s*ENGINE\s*=\s*\w+(\s+\w+\s*=\s*\w+)*", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s*DEFAULT\s+CHARSET\s*=\s*\w+", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s*CHARACTER\s+SET\s+\w+", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s*COLLATE\s+\w+", "", out, flags=re.IGNORECASE)
    # 7. VARCHAR(n) -> TEXT（SQLite 类型亲和，VARCHAR 也行，但保留更兼容）
    #    实际 SQLite 接受 VARCHAR(n)，不需要翻译
    # 8. INDEX idx_xxx (col) 建表内联索引 — SQLite 不支持 CREATE TABLE 内 INDEX 子句
    out = re.sub(r",\s*INDEX\s+\w+\s*\([^)]*\)", "", out, flags=re.IGNORECASE)
    # 9. ON DELETE CASCADE ON UPDATE ... 这类 SQLite 支持，不动
    return out


def translate_sql_for_mysql(sql: str) -> str:
    """MySQL 模式下，确保 SQL 用 MySQL 方言。

    应用层如果误用了 SQLite 写法，这里做最小修正：
        INSERT OR IGNORE -> INSERT IGNORE
        AUTOINCREMENT    -> AUTO_INCREMENT
        ?                -> %s
    """
    out = sql
    out = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT IGNORE INTO", out, flags=re.IGNORECASE)
    out = re.sub(r"\bAUTOINCREMENT\b", "AUTO_INCREMENT", out)
    out = out.replace("?", "%s")
    # ON CONFLICT(id) DO UPDATE SET ... -> ON DUPLICATE KEY UPDATE ...
    # 仅处理最常见的 upsert 写法
    m = re.search(
        r"ON\s+CONFLICT\s*\(\s*(\w+)\s*\)\s+DO\s+UPDATE\s+SET\s+(.*?)(?=\)|;|$)",
        out,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if m:
        set_clause = m.group(2)
        # 把 excluded.col 转为 VALUES(col)
        set_clause = re.sub(
            r"excluded\.(\w+)",
            r"VALUES(\1)",
            set_clause,
            flags=re.IGNORECASE,
        )
        out = out[: m.start()] + f"ON DUPLICATE KEY UPDATE {set_clause}" + out[m.end():]
    return out


def translate(sql: str) -> str:
    """按当前 backend 翻译 SQL。"""
    if is_mysql():
        return translate_sql_for_mysql(sql)
    return translate_sql_for_sqlite(sql)


# === 连接管理 ===

class _SQLiteCompat:
    """对 sqlite3.Connection 的薄包装，提供与 MySQL DictCursor 一致的接口。

    SQLite 原生就支持 sqlite3.Row（已通过 row_factory 设置），
    本类只在 execute 前翻译 SQL，保持应用层调用方式不变。
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def execute(self, sql: str, params: Iterable | None = None):
        return self._conn.execute(translate(sql), params or ())

    def executescript(self, sql: str):
        # SQLite 的 executescript 不支持 ? 占位符，且整段执行；
        # 我们逐句拆分（按 ;) 并翻译
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        for stmt in statements:
            if stmt:
                self._conn.execute(translate_sql_for_sqlite(stmt))
        return self._conn

    def commit(self):
        return self._conn.commit()

    def close(self):
        return self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._conn.close()


def _new_sqlite_conn():
    if _DB_PATH is None:
        raise RuntimeError("SQLite 路径未设置，请先调用 set_sqlite_path()")
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return _SQLiteCompat(conn)


def _new_mysql_conn():
    """创建 MySQL 连接（DictCursor）。"""
    global _DB_URL
    if not _DB_URL:
        env_url = os.environ.get("AGENTBUDDY_DB_URL", "").strip()
        if not env_url:
            raise RuntimeError("MySQL backend 需要配置 AGENTBUDDY_DB_URL")
        _DB_URL = env_url
    url = _DB_URL

    try:
        import pymysql  # noqa: F401
    except ImportError as e:
        raise RuntimeError("MySQL backend 需要 PyMySQL: pip install PyMySQL") from e

    from urllib.parse import urlparse
    u = urlparse(url)
    if u.scheme not in ("mysql", "mysql+pymysql"):
        raise RuntimeError(f"AGENTBUDDY_DB_URL scheme 必须 mysql://, 实际: {u.scheme}")
    user = u.username or "root"
    password = u.password or ""
    host = u.hostname or "127.0.0.1"
    port = u.port or 3306
    db = (u.path or "/agentbuddy").lstrip("/")

    import pymysql
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    return conn


def get_db():
    """获取数据库连接。

    SQLite：每次新建连接（与原 auth.models 行为一致）。
    MySQL：从连接池取一条；池为空则新建。
    """
    if is_mysql():
        # 简单连接池：从池中取，没有就新建
        if _POOL:
            return _POOL.pop()
        return _new_mysql_conn()
    return _new_sqlite_conn()


def release(conn) -> None:
    """归还连接到池（MySQL）/ 直接 close（SQLite）。

    应用层可以直接 conn.close()，本函数用于跨 backend 统一归还。
    """
    if conn is None:
        return
    if is_mysql():
        try:
            # 滚回未提交事务，避免污染下一次使用
            conn.rollback()
        except Exception:
            pass
        if len(_POOL) < _POOL_SIZE:
            _POOL.append(conn)
        else:
            try:
                conn.close()
            except Exception:
                pass
    else:
        try:
            conn.close()
        except Exception:
            pass


# === Row 转换 ===

def row_to_dict(row) -> dict | None:
    """将 sqlite3.Row / pymysql DictRow 统一转为 dict。"""
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)
    except (TypeError, ValueError):
        return None


def rows_to_dicts(rows) -> list[dict]:
    return [row_to_dict(r) for r in rows] if rows else []


# === 建表 ===

def init_db(sql: str | None = None) -> None:
    """执行建表 SQL（幂等）。

    优先用本函数 sql 参数；为空则用 set_init_sql 注册的全局 SQL。
    """
    ddl = sql or _INIT_SQL
    if not ddl:
        return
    conn = get_db()
    try:
        if is_mysql():
            # MySQL：原生 executescript 不存在，拆分按 ; 执行
            statements = [s.strip() for s in ddl.split(";") if s.strip()]
            for stmt in statements:
                if stmt:
                    conn.execute(translate_sql_for_mysql(stmt))
            conn.commit()
        else:
            # SQLite
            conn.executescript(translate_sql_for_sqlite(ddl))
            conn.commit()
    finally:
        release(conn)


# === 辅助：参数占位符 ===

def placeholders(n: int) -> str:
    """返回 n 个占位符（按当前 backend 自动选 ? 或 %s）。"""
    ph = "?" if not is_mysql() else "%s"
    return ",".join([ph] * n)


def in_clause(plugin_ids: list) -> tuple[str, list]:
    """构造 IN (?, ?, ...) 子句及参数列表（按 backend 自适应占位符）。"""
    if not plugin_ids:
        # 永远不应为空，空时给一个永假条件
        return ("0", [])
    return (placeholders(len(plugin_ids)), list(plugin_ids))


# === 日期工具 ===

def now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# === 自检 ===

def ping() -> dict:
    """自检：返回 backend / 连通性信息。"""
    info = {"backend": backend()}
    if is_mysql():
        info["url"] = _DB_URL or os.environ.get("AGENTBUDDY_DB_URL", "")
    else:
        info["path"] = str(_DB_PATH) if _DB_PATH else None
    try:
        conn = get_db()
        if is_mysql():
            row = conn.execute("SELECT 1 AS ok").fetchone()
            info["ok"] = bool(row)
        else:
            row = conn.execute("SELECT 1 AS ok").fetchone()
            info["ok"] = row_to_dict(row)["ok"] == 1
        release(conn)
    except Exception as e:
        info["ok"] = False
        info["error"] = f"{type(e).__name__}: {e}"
    return info
