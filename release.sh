#!/usr/bin/env bash
# AdeBuddy Release 脚本：打 tag + 推送，触发 GitHub Actions 自动构建发布
#
# 用法:
#   ./release.sh              # 交互式输入版本号
#   ./release.sh 1.0.0        # 指定版本号
#   ./release.sh 1.0.0 -p     # 跳过确认直接推送
#
# 流程:
#   1. 检查工作区干净
#   2. 确认版本号
#   3. 创建 git tag v<version>
#   4. 推送 tag 到 origin
#   5. GitHub Actions 自动构建 macOS + Windows 并发布 Release
set -e

cd "$(dirname "$0")"

# ===== 颜色 =====
G="\033[32m"
Y="\033[33m"
R="\033[31m"
C="\033[36m"
N="\033[0m"
info()  { echo -e "${G}[release]${N} $1"; }
warn()  { echo -e "${Y}[release]${N} $1"; }
fail()  { echo -e "${R}[release][ERROR]${N} $1"; exit 1; }

# ===== 参数解析 =====
VERSION="${1:-}"
AUTO_PUSH=false
if [ "$2" = "-p" ] || [ "$2" = "--push" ]; then
  AUTO_PUSH=true
fi

echo -e "${C}========================================${N}"
echo -e "${C}  AdeBuddy Release${N}"
echo -e "${C}========================================${N}"

# ===== 1. 检查工作区 =====
if [ -n "$(git status --porcelain --untracked=no)" ]; then
  warn "工作区有未提交的变更，请先提交:"
  git status --short
  fail "请先 git commit 后再 release"
fi
info "工作区干净"

# ===== 2. 确认版本号 =====
if [ -z "$VERSION" ]; then
  # 自动推断：取最近 tag + patch +1
  LATEST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
  if [ -n "$LATEST_TAG" ]; then
    LATEST_VER="${LATEST_TAG#v}"
    # 简单地 patch +1 (x.y.z -> x.y.(z+1))
    MAJOR=$(echo "$LATEST_VER" | cut -d. -f1)
    MINOR=$(echo "$LATEST_VER" | cut -d. -f2)
    PATCH=$(echo "$LATEST_VER" | cut -d. -f3)
    PATCH=$((PATCH + 1))
    SUGGESTED="$MAJOR.$MINOR.$PATCH"
    echo -e "${Y}上一个版本: ${LATEST_TAG}${N}"
    echo -n "输入版本号 [${SUGGESTED}]: "
    read -r INPUT
    VERSION="${INPUT:-$SUGGESTED}"
  else
    echo -n "输入版本号 (如 1.0.0): "
    read -r VERSION
  fi
fi

if [ -z "$VERSION" ]; then
  fail "版本号不能为空"
fi

TAG="v${VERSION}"
info "版本: $VERSION  Tag: $TAG"

# ===== 3. 检查 tag 是否已存在 =====
if git rev-parse "$TAG" >/dev/null 2>&1; then
  fail "Tag $TAG 已存在，请用其他版本号"
fi

# ===== 4. 确认推送 =====
if [ "$AUTO_PUSH" != true ]; then
  echo ""
  echo -e "${Y}即将执行:${N}"
  echo "  1. git tag $TAG"
  echo "  2. git push origin $TAG"
  echo "  3. GitHub Actions 自动构建 macOS + Windows"
  echo "  4. 自动创建 GitHub Release (含 .dmg / .zip / .exe)"
  echo ""
  echo -n "确认发布? [y/N]: "
  read -r CONFIRM
  if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    warn "已取消"
    exit 0
  fi
fi

# ===== 5. 创建并推送 tag =====
info "创建 tag: $TAG"
git tag "$TAG"

info "推送 tag: $TAG"
git push origin "$TAG"

# ===== 6. 完成 =====
echo ""
echo -e "${G}========================================${N}"
echo -e "${G}  Release 已触发!${N}"
echo -e "${G}========================================${N}"
echo ""
echo "  Tag:        $TAG"
echo "  Actions:    https://github.com/$(git remote get-url origin | sed 's|.*github.com[:/]||;s|\.git$||')/actions"
echo "  Releases:   https://github.com/$(git remote get-url origin | sed 's|.*github.com[:/]||;s|\.git$||')/releases"
echo ""
echo "  构建完成后，Releases 页面将出现:"
echo "    - AdeBuddy-${VERSION}-macos.dmg / .zip"
echo "    - AdeBuddy-Setup-${VERSION}-x64.exe"
echo ""
