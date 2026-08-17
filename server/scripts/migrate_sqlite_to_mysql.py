"""SQLite → MySQL 数据迁移脚本。

用法：
    python3 scripts/migrate_sqlite_to_mysql.py
    python3 scripts/migrate_sqlite_to_mysql.py --sqlite data/agentbuddy.db \\
        --mysql-url mysql://agentbuddy:pass@127.0.0.1:3306/agentbuddy

前置条件：
1. 已通过 scripts/setup_mysql.sh 完成 MySQL 安装与建库；
2. 服务端 .env 中已配置 AGENTBUDDY_DB_BACKEND=mysql 和 AGENTBUDDY_DB_URL；
3. MySQL 库已通过 app.py 启动一次自动建表（或本脚本会调用 set_mysql_url 触发建表）。

迁移顺序（按外键依赖）：
    users → teams → team_members → plugins → plugin_likes → plugin_favorites → invitations

幂等：跳过已存在的 id（INSERT IGNORE）。
"""
import argparse
import os
import sys
from pathlib import Path

# 让 server/ 加入 sys.path，使 db / auth.models 可 import
SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))

# 加载 .env
from _env_loader import load_env_file
load_env_file()

import sqlite3
import pymysql
from urllib.parse import urlparse


def open_sqlite(sqlite_path: Path) -> sqlite3.Connection:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite 数据库不存在: {sqlite_path}")
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    return conn


def open_mysql(mysql_url: str) -> pymysql.connections.Connection:
    u = urlparse(mysql_url)
    if u.scheme not in ("mysql", "mysql+pymysql"):
        raise RuntimeError(f"AGENTBUDDY_DB_URL scheme 必须 mysql://, 实际: {u.scheme}")
    return pymysql.connect(
        host=u.hostname or "127.0.0.1",
        port=u.port or 3306,
        user=u.username or "root",
        password=u.password or "",
        database=(u.path or "/agentbuddy").lstrip("/"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def ensure_mysql_tables(mysql_conn):
    """确保 MySQL 表结构存在（调用 auth.models 建表）。"""
    from auth.models import _DDL
    statements = [s.strip() for s in _DDL.split(";") if s.strip()]
    with mysql_conn.cursor() as cur:
        for stmt in statements:
            if stmt:
                cur.execute(stmt)
    mysql_conn.commit()


def migrate_table(sqlite_conn, mysql_conn, table: str, columns: list[str],
                  placeholders_count: int) -> int:
    """通用迁移：SELECT * → INSERT IGNORE。

    columns: 列名顺序（与 INSERT 字段一致）
    placeholders_count: VALUES 占位符个数（应等于 len(columns)）
    """
    col_list = ", ".join(columns)
    ph_list = ", ".join(["%s"] * placeholders_count)
    sql = f"INSERT IGNORE INTO {table} ({col_list}) VALUES ({ph_list})"

    rows = sqlite_conn.execute(f"SELECT {col_list} FROM {table}").fetchall()
    migrated = 0
    skipped = 0
    with mysql_conn.cursor() as cur:
        for r in rows:
            values = [r[c] for c in columns]
            try:
                cur.execute(sql, values)
                migrated += 1
            except pymysql.err.IntegrityError:
                skipped += 1
    mysql_conn.commit()
    return migrated, skipped


def main():
    parser = argparse.ArgumentParser(description="SQLite → MySQL 迁移")
    parser.add_argument("--sqlite", type=Path,
                        default=SERVER_DIR / "data" / "agentbuddy.db",
                        help="SQLite 数据库路径")
    parser.add_argument("--mysql-url", type=str,
                        default=os.environ.get("AGENTBUDDY_DB_URL", ""),
                        help="MySQL 连接 URL（默认读 .env AGENTBUDDY_DB_URL）")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅打印将要迁移的行数，不实际写入")
    args = parser.parse_args()

    if not args.mysql_url:
        print("[ERROR] 需要提供 --mysql-url 或在 .env 配置 AGENTBUDDY_DB_URL")
        sys.exit(1)

    print(f"[1/4] 打开 SQLite: {args.sqlite}")
    sconn = open_sqlite(args.sqlite)

    print(f"[2/4] 打开 MySQL: {args.mysql_url.split('@')[-1] if '@' in args.mysql_url else args.mysql_url}")
    mconn = open_mysql(args.mysql_url)

    print("[3/4] 确保 MySQL 表结构存在...")
    ensure_mysql_tables(mconn)

    if args.dry_run:
        print("[dry-run] 各表行数（SQLite）：")
        for t in ["users", "teams", "team_members", "plugins",
                  "plugin_likes", "plugin_favorites", "invitations"]:
            n = sconn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {n}")
        sconn.close()
        mconn.close()
        return

    print("[4/4] 开始迁移（按外键依赖顺序，INSERT IGNORE 跳过已存在）...")
    plan = [
        ("users", ["id", "username", "password", "email", "role", "created_at"]),
        ("teams", ["id", "name", "description", "owner_id", "created_at"]),
        ("team_members", ["team_id", "user_id", "role", "joined_at"]),
        ("plugins", ["id", "name", "version", "description", "author", "author_id",
                     "file", "size", "published_at", "tags", "downloads", "likes",
                     "scope", "team_id"]),
        ("plugin_likes", ["plugin_id", "user_id", "created_at"]),
        ("plugin_favorites", ["plugin_id", "user_id", "created_at"]),
        ("invitations", ["id", "team_id", "inviter_id", "invitee_id", "status",
                        "message", "created_at", "responded_at"]),
    ]

    total_migrated = 0
    total_skipped = 0
    for table, cols in plan:
        n, s = migrate_table(sconn, mconn, table, cols, len(cols))
        total_migrated += n
        total_skipped += s
        print(f"  {table}: migrated={n} skipped={s}")

    sconn.close()
    mconn.close()
    print(f"\n[OK] 迁移完成: migrated={total_migrated} skipped(已存在)={total_skipped}")
    print("\n下一步：")
    print("  1. 确认 .env 中 AGENTBUDDY_DB_BACKEND=mysql")
    print("  2. 重启服务: ./run.sh restart")
    print("  3. 验证应用正常后，可归档旧 SQLite: mv data/agentbuddy.db data/agentbuddy.db.bak")


if __name__ == "__main__":
    main()
