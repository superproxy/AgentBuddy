#!/usr/bin/env bash
# AgentBuddy MySQL 一键安装脚本
#
# 用法：
#   ./scripts/setup_mysql.sh                                   # 自动生成随机密码
#   ./scripts/setup_mysql.sh --root-password <旧root密码>      # 已有 root 密码时
#   ./scripts/setup_mysql.sh --db-password <自定义db密码>       # 指定 agentbuddy 用户密码
#   ./scripts/setup_mysql.sh --root-password <root> --db-password <db>
#
# 功能：
#   1. 检测/安装 MySQL 服务（apt/yum/dnf 自适应）
#   2. 启动并设置开机自启
#   3. 安全初始化（可选设 root 密码、删匿名用户、禁远程 root）
#   4. 创建 agentbuddy 数据库 + 用户
#   5. 随机强密码写入 .env（AGENTBUDDY_DB_BACKEND / AGENTBUDDY_DB_URL）
#
# 不包含（独立脚本职责清晰）：
#   - Python 依赖 PyMySQL（由 run.sh 的 setup_deps 处理）
#   - 表结构创建（由 app.py 启动时 init_db() 自动建表）
#   - 数据迁移（由 scripts/migrate_sqlite_to_mysql.py 单独处理）

set -e

# 切到 server/ 目录（脚本在 server/scripts/ 下）
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

DB_NAME="agentbuddy"
DB_USER="agentbuddy"
DB_HOST="127.0.0.1"
DB_PORT="3306"
ENV_FILE=".env"
ROOT_PASSWORD=""
DB_PASSWORD=""

# === 颜色 ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# === 参数解析 ===
while [[ $# -gt 0 ]]; do
    case "$1" in
        --root-password) ROOT_PASSWORD="$2"; shift 2 ;;
        --db-password)   DB_PASSWORD="$2"; shift 2 ;;
        --db-name)       DB_NAME="$2"; shift 2 ;;
        --db-user)       DB_USER="$2"; shift 2 ;;
        -h|--help)
            grep -E "^# " "$0" | sed 's/^# //'
            exit 0
            ;;
        *) error "未知参数: $1"; exit 1 ;;
    esac
done

# 生成随机密码（如未指定 db 密码）
if [ -z "$DB_PASSWORD" ]; then
    if command -v openssl &>/dev/null; then
        DB_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)
    else
        DB_PASSWORD=$(head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 24)
    fi
    info "未指定 --db-password，已生成随机密码"
fi

# === 检测包管理器 ===
detect_pkg_mgr() {
    if command -v apt-get &>/dev/null; then
        echo "apt"
    elif command -v dnf &>/dev/null; then
        echo "dnf"
    elif command -v yum &>/dev/null; then
        echo "yum"
    else
        echo ""
    fi
}

PKG_MGR=$(detect_pkg_mgr)
if [ -z "$PKG_MGR" ]; then
    error "不支持的包管理器（仅支持 apt/yum/dnf）"
    exit 1
fi
info "包管理器: $PKG_MGR"

# === 安装 MySQL ===
install_mysql() {
    if command -v mysql &>/dev/null; then
        info "MySQL 已安装: $(mysql --version)"
        return 0
    fi

    info "通过 $PKG_MGR 安装 MySQL..."
    case "$PKG_MGR" in
        apt)
            apt-get update -qq
            DEBIAN_FRONTEND=noninteractive apt-get install -y -qq mysql-server
            ;;
        dnf)
            $PKG_MGR install -y mysql-server
            ;;
        yum)
            $PKG_MGR install -y mysql-server
            ;;
    esac

    if ! command -v mysql &>/dev/null; then
        error "MySQL 安装失败"
        exit 1
    fi
    info "MySQL 安装完成: $(mysql --version)"
}

# === 启动服务并设置开机自启 ===
start_mysql() {
    info "启动 MySQL 服务..."
    # apt 系统服务名是 mysql，yum/dnf 是 mysqld
    local svc_name="mysql"
    if [ "$PKG_MGR" = "yum" ] || [ "$PKG_MGR" = "dnf" ]; then
        svc_name="mysqld"
    fi

    # 启动（若已启动会幂等跳过）
    systemctl start "$svc_name" 2>/dev/null || service "$svc_name" start 2>/dev/null || {
        warn "systemctl/service 启动失败，尝试 mysqld_safe..."
        mysqld_safe --user=mysql &
        sleep 3
    }

    # 开机自启
    systemctl enable "$svc_name" 2>/dev/null || warn "无法设置开机自启（不影响本次运行）"

    # 等待 MySQL 就绪
    info "等待 MySQL 就绪..."
    local retries=30
    while [ $retries -gt 0 ]; do
        if mysqladmin ping -uroot ${ROOT_PASSWORD:+-p$ROOT_PASSWORD} --silent 2>/dev/null; then
            info "MySQL 已就绪"
            return 0
        fi
        retries=$((retries - 1))
        sleep 1
    done
    error "MySQL 启动超时"
    exit 1
}

# === 安全初始化 + 建库建用户 ===
init_mysql() {
    local root_arg=""
    [ -n "$ROOT_PASSWORD" ] && root_arg="-p$ROOT_PASSWORD"

    # 若未提供 root 密码，尝试无密码连接（apt 安装的 MySQL 默认无密码）
    if [ -z "$ROOT_PASSWORD" ]; then
        if ! mysql -uroot -e "SELECT 1" &>/dev/null; then
            error "无法以无密码方式连接 root，请通过 --root-password 提供 root 密码"
            exit 1
        fi
    fi

    # 安全初始化（仅当提供了 root 密码时执行；apt 新装的 MySQL 默认无密码可跳过）
    if [ -n "$ROOT_PASSWORD" ]; then
        info "执行安全初始化（设 root 密码 / 删匿名 / 禁远程 root）..."
        mysql -uroot $root_arg <<SQL || warn "部分安全初始化步骤失败，继续"
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '$ROOT_PASSWORD';
DELETE FROM mysql.user WHERE User='';
DELETE FROM mysql.user WHERE User='root' AND Host NOT IN ('localhost','127.0.0.1','::1');
DROP DATABASE IF EXISTS test;
FLUSH PRIVILEGES;
SQL
    fi

    # 创建数据库 + 用户
    info "创建数据库 $DB_NAME 和用户 $DB_USER ..."
    mysql -uroot $root_arg <<SQL
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- 用户已存在则更新密码
CREATE USER IF NOT EXISTS '$DB_USER'@'$DB_HOST' IDENTIFIED BY '$DB_PASSWORD';
ALTER USER '$DB_USER'@'$DB_HOST' IDENTIFIED BY '$DB_PASSWORD';
GRANT ALL ON \`$DB_NAME\`.* TO '$DB_USER'@'$DB_HOST';
-- 兼容 localhost
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
ALTER USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
GRANT ALL ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost';
FLUSH PRIVILEGES;
SQL

    # 验证连接
    if mysql -u"$DB_USER" -p"$DB_PASSWORD" -h"$DB_HOST" -e "USE \`$DB_NAME\`; SELECT 1;" &>/dev/null; then
        info "数据库连接验证通过"
    else
        error "数据库连接验证失败，请检查用户/密码/权限"
        exit 1
    fi
}

# === 写入 .env ===
write_env() {
    local db_url="mysql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"

    # 备份
    if [ -f "$ENV_FILE" ]; then
        cp "$ENV_FILE" "$ENV_FILE.bak.$(date +%s)"
        info "已备份 $ENV_FILE -> $ENV_FILE.bak.*"
    fi

    # 移除旧 DB 配置
    local tmp="$ENV_FILE.tmp.$$"
    if [ -f "$ENV_FILE" ]; then
        grep -v "^AGENTBUDDY_DB_" "$ENV_FILE" > "$tmp" 2>/dev/null || cp "$ENV_FILE" "$tmp"
    else
        echo "# AgentBuddy env" > "$tmp"
    fi

    # 追加新配置
    cat >> "$tmp" <<EOF

# === 数据库（MySQL，由 scripts/setup_mysql.sh 生成） ===
AGENTBUDDY_DB_BACKEND=mysql
AGENTBUDDY_DB_URL=$db_url
EOF

    mv "$tmp" "$ENV_FILE"
    info "配置已写入 $ENV_FILE:"
    info "  AGENTBUDDY_DB_BACKEND=mysql"
    info "  AGENTBUDDY_DB_URL=mysql://$DB_USER:****@$DB_HOST:$DB_PORT/$DB_NAME"
}

# === 主流程 ===
info "=== AgentBuddy MySQL 安装脚本 ==="
info "  数据库名: $DB_NAME"
info "  用户名:   $DB_USER"
info "  主机:     $DB_HOST:$DB_PORT"
echo ""

install_mysql
start_mysql
init_mysql
write_env

echo ""
info "=== MySQL 安装配置完成 ==="
info "  数据库: $DB_NAME"
info "  用户名: $DB_USER"
info "  密码:   $DB_PASSWORD"
echo ""
info "下一步："
info "  1. 安装 Python 依赖: pip install PyMySQL"
info "  2. 重启服务: ./run.sh restart"
info "  3. （可选）从 SQLite 迁移数据: python3 scripts/migrate_sqlite_to_mysql.py"
info "  4. 完成迁移后切换 backend: 确认 .env 中 AGENTBUDDY_DB_BACKEND=mysql"
