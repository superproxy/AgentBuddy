https://opencode.ai/


# 直接安装 (YOLO)
curl -fsSL https://opencode.ai/install | bash

# 软件包管理器
npm i -g opencode-ai@latest        # 也可使用 bun/pnpm/yarn
scoop install opencode             # Windows
choco install opencode             # Windows
brew install anomalyco/tap/opencode # macOS 和 Linux（推荐，始终保持最新）
brew install opencode              # macOS 和 Linux（官方 brew formula，更新频率较低）
sudo pacman -S opencode            # Arch Linux (Stable)
paru -S opencode-bin               # Arch Linux (Latest from AUR)
mise use -g opencode               # 任意系统
nix run nixpkgs#opencode           # 或用 github:anomalyco/opencode 获取最新 dev 分支



## cli
https://opencode.ai/docs/zh-cn/cli/

## web
https://opencode.ai/docs/zh-cn/web/


OPENCODE_SERVER_PASSWORD=123456
opencode web --hostname 0.0.0.0

## 规则
https://opencode.ai/docs/zh-cn/rules/

## ide
https://opencode.ai/docs/zh-cn/ide/