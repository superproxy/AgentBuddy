#!/usr/bin/env bash
# ============================================================
# AgentBuddy 市场垃圾数据清理脚本 — 在服务器上运行
#
# 用法：
#   cd /root/AgentBuddy/server
#   ./cleanup-market.sh              # 演练模式（只看会删什么，不动数据）
#   ./cleanup-market.sh --apply      # 实际执行（自动备份数据库 + 重启服务）
#   ./cleanup-market.sh --apply --admin 3   # 清理 + 把用户 id=3 提升为 admin
#
# 清理对象（JUNK_IDS 可自行增删）：
#   - 早期测试发布的垃圾插件及其 packages/*.zip 包文件
#   - 残留的点赞/收藏记录
#   - 数据库无对应记录的孤儿 zip 包文件
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

DB="data/agentbuddy.db"

# 要清理的插件 ID（全名精确匹配）
JUNK_IDS=(
  "claude-code-skills-10-2026-v2code-ai-1.0.0"
  "claude-code-skills-推荐10-个值得安装的技能2026-v2code-ai-编程服务平台-1.0.0"
  "ljyd-1.0.0"
  "ljyd-dev-1.0.0"
  "github-repo-bootstrap-1.0.0"
  "ljyd-zentao-1.0.0"
  "arch-1.0.0"
)

APPLY=0
ADMIN_ID=""
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1; shift ;;
    --admin) ADMIN_ID="${2:-}"; shift 2 ;;
    *) echo "未知参数: $1（支持 --apply / --admin <用户id>）"; exit 1 ;;
  esac
done

[ -f "$DB" ] || { echo "❌ 数据库不存在: $DB（请在 server 目录下运行）"; exit 1; }

echo "=============================================="
echo " AgentBuddy 市场清理  $([ $APPLY -eq 1 ] && echo '【实际执行】' || echo '【演练模式】')"
echo " 数据库: $DB"
echo "=============================================="

APPLY="$APPLY" ADMIN_ID="$ADMIN_ID" JUNK_IDS="$(printf '%s\n' "${JUNK_IDS[@]}")" python3 <<'PYEOF'
import os, sys, time, shutil, sqlite3

apply = os.environ.get('APPLY') == '1'
admin_id = os.environ.get('ADMIN_ID', '').strip()
junk_ids = [l for l in os.environ.get('JUNK_IDS', '').splitlines() if l.strip()]

conn = sqlite3.connect('data/agentbuddy.db')
conn.row_factory = sqlite3.Row

# ---- 1. 备份 ----
if apply:
    os.makedirs('data/backups', exist_ok=True)
    bak = f"data/backups/agentbuddy-{time.strftime('%Y%m%d-%H%M%S')}.db"
    shutil.copy2('data/agentbuddy.db', bak)
    print(f"[备份] {bak}")

# ---- 2. 目标插件现状 ----
print("\n[目标插件]")
qmarks = ','.join('?' * len(junk_ids))
rows = conn.execute(
    f"SELECT id, name, author_id, scope, file FROM plugins WHERE id IN ({qmarks})", junk_ids
).fetchall()
found = {r['id'] for r in rows}
for r in rows:
    print(f"  将删  {r['id'][:52]:52s} author={r['author_id']} scope={r['scope']}")
for j in junk_ids:
    if j not in found:
        print(f"  跳过  {j[:52]:52s} （已不存在）")

# ---- 3. 删除插件 + 关联数据 + 包文件 ----
if apply:
    pkg_dir = 'data/marketplace/packages'
    deleted_pkg = 0
    for r in rows:
        conn.execute("DELETE FROM plugin_likes WHERE plugin_id = ?", (r['id'],))
        conn.execute("DELETE FROM plugin_favorites WHERE plugin_id = ?", (r['id'],))
        conn.execute("DELETE FROM plugins WHERE id = ?", (r['id'],))
        f = r['file'] or ''
        if f:
            p = os.path.join(pkg_dir, os.path.basename(f))
            if os.path.exists(p):
                os.remove(p)
                deleted_pkg += 1
    # 孤儿 zip：DB 无记录的包文件
    orphan_zips = []
    if os.path.isdir(pkg_dir):
        db_files = {os.path.basename(r['file'] or '') for r in conn.execute("SELECT file FROM plugins")}
        for fn in os.listdir(pkg_dir):
            if fn.endswith('.zip') and fn not in db_files:
                os.remove(os.path.join(pkg_dir, fn))
                orphan_zips.append(fn)
    conn.commit()
    print(f"\n[删除] 插件 {len(rows)} 条 | 包文件 {deleted_pkg} 个 | 孤儿 zip {len(orphan_zips)} 个")
    for fn in orphan_zips:
        print(f"  孤儿包已删: {fn}")

# ---- 4. 提升管理员（可选）----
if apply and admin_id:
    conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (int(admin_id),))
    conn.commit()
    u = conn.execute("SELECT id, username, role FROM users WHERE id = ?", (int(admin_id),)).fetchone()
    print(f"\n[提权] {'user id=' + str(u['id']) + ' (' + u['username'] + ') → admin' if u else '未找到用户 id=' + admin_id}")

# ---- 5. 清理后市场全量 ----
print(f"\n[结果] 市场剩余插件: {conn.execute('SELECT COUNT(*) FROM plugins').fetchone()[0]} 条")
for r in conn.execute("SELECT id, author_id, scope FROM plugins ORDER BY published_at DESC"):
    print(f"  {r['id'][:52]:52s} author={r['author_id']} scope={r['scope']}")
conn.close()
if not apply:
    print("\n（演练模式，未改动任何数据。确认无误后加 --apply 执行）")
PYEOF

# ---- 6. 重启服务 ----
if [ $APPLY -eq 1 ] && [ -x ./run.sh ]; then
  echo ""
  echo "[重启] ./run.sh restart"
  ./run.sh restart || echo "⚠ 自动重启失败，请手动重启服务"
fi
