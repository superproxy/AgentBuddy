# 三层分离设计：cli / api / vue

- **日期**：2026-08-14
- **状态**：已确认，待写实施计划
- **作者**：brainstorming session
- **关联**：承接 `2026-07-02-agentctl-refactor-design.md`（agentctl 重构）和 `2026-07-02-config-web-ui-design.md`（Web UI 设计）

## 1. 背景

当前工程结构存在三层职责混杂问题：

- `scripts/` —— CLI 入口（`agentctl.py`）+ 共享业务库（`lib/`）
- `tools/` —— 桌面 Flask API（单文件 `config_server.py` ~2000 行）
- `server/` —— 远程 Flask 服务（marketplace + auth + ai_generator）
- `frontend/` —— Vue 3 SPA
- `app.py` —— pywebview 桌面壳
- `template/` / `tests/` / `docs/` —— 仓库级共享资源

**核心痛点**：

1. 三层职责在目录层面没有清晰边界，桌面 api（`tools/`）和远程 api（`server/`）并行存在但关系模糊
2. 共享业务库（`scripts/lib/`）通过 `sys.path.insert(0, SCRIPTS_DIR)` 让三处调用方（`agentctl.py` / `config_server.py` / `tests/`）都能 `from lib.X import Y`，路径耦合目录结构
3. CLI 无法独立发布为 PyPI 包 —— 它依赖 `scripts/lib/` 但 `scripts/` 不是可安装的包

## 2. 目标

- **为独立发布做准备**：CLI 可独立打包成 PyPI 包（`pip install agentctl`）/ pipx / PyInstaller 单文件 exe；桌面应用和远程服务可独立部署
- **明确三层边界**：cli / api / vue 各自目录清晰，职责单一
- **共享代码规范化**：消除 `sys.path.insert` hack，改用 Python 包管理
- **保留向后兼容**：git mv 保留历史，分阶段迁移，每阶段可独立验证

## 3. 非目标

- 不引入 `core/` 共享包层（保持三层扁平结构）
- 不重写现有业务逻辑，只做目录重组和 import 路径调整
- 不合并桌面 api 和远程 api（保留双服务设计）
- 不引入 monorepo 工具（pnpm workspace / lerna 等），保持单仓库简单结构

## 4. 设计

### 4.1 目标目录结构

```
MyAgentPlugin/
├── cli/                          # 原 scripts/，Python 包 = agentctl
│   ├── __init__.py               # 新增（空）
│   ├── agentctl.py               # CLI 入口
│   ├── lib/                      # 共享业务库（内部相对 import 不变）
│   │   ├── __init__.py           # 保留（空）
│   │   ├── llm.py
│   │   ├── mcp.py
│   │   ├── skills.py
│   │   ├── plugins.py
│   │   ├── config_io.py
│   │   ├── logging.py
│   │   ├── paths.py
│   │   ├── placeholder.py
│   │   ├── provider_catalog.py
│   │   ├── mcp_market.py
│   │   ├── skill_market.py
│   │   └── ide/                  # 18+ IDE 分发器（内部相对 import 不变）
│   │       ├── __init__.py
│   │       ├── _meta.py
│   │       ├── base.py
│   │       ├── detect.py
│   │       ├── install.py
│   │       ├── launch.py
│   │       ├── session.py
│   │       ├── ide.yaml
│   │       ├── agents.py
│   │       ├── cherrystudio.py
│   │       ├── claude.py
│   │       ├── codebuddy.py
│   │       ├── codex.py
│   │       ├── commandcode.py
│   │       ├── cursor.py
│   │       ├── deepseek.py
│   │       ├── hermes.py
│   │       ├── idea.py
│   │       ├── kimi.py
│   │       ├── openclaw.py
│   │       ├── opencode.py
│   │       ├── openworker.py
│   │       ├── pi.py
│   │       ├── qoder.py
│   │       ├── qodercn.py
│   │       ├── trae.py
│   │       ├── vscode.py
│   │       ├── webpass.py
│   │       ├── workbuddy.py
│   │       └── zcode.py
│   ├── cleanup.py
│   └── pyproject.toml            # name="agentctl", entry_points 声明
├── desktop/                      # 新增聚合层（桌面应用 = 壳 + service + frontend）
│   ├── launcher.py               # 原 app.py（pywebview 壳）
│   ├── service/                  # 原 tools/
│   │   └── config_server.py      # 桌面 Flask API
│   └── frontend/                 # 原 frontend/，Vue 3 SPA
│       ├── src/
│       │   ├── api/
│       │   ├── components/
│       │   ├── stores/
│       │   ├── views/
│       │   ├── App.vue
│       │   ├── main.ts
│       │   └── style.css
│       ├── env.d.ts
│       ├── index.html
│       ├── package.json
│       ├── package-lock.json
│       ├── tsconfig.json
│       ├── tsconfig.node.json
│       └── vite.config.ts
├── server/                       # 保持独立（远程服务）
│   ├── ai_generator/
│   ├── auth/
│   ├── marketplace/
│   ├── web/
│   ├── app.py
│   ├── requirements.txt
│   ├── run.bat
│   ├── run.sh
│   ├── DEPLOY.md
│   └── README.md
├── template/                     # 仓库级共享资源（不变）
├── tests/                        # 仓库级测试（import 路径需改）
├── docs/
├── tools/                        # 删除（已迁移到 desktop/service/）
├── scripts/                      # 删除（已迁移到 cli/）
├── frontend/                     # 删除（已迁移到 desktop/frontend/）
├── app.py                        # 删除（已迁移到 desktop/launcher.py）
├── build.py                      # 路径需调整
├── build.cmd / build.sh
├── release.cmd / release.sh
├── install.cmd / install.sh
├── run.cmd / run.sh
├── MyAgentConfig.spec            # PyInstaller spec，路径需调整
├── app.spec                      # PyInstaller spec，路径需调整
├── installer.iss
├── pyproject.toml                # 仓库根（仅声明 dev 依赖 + 工具配置）
├── pytest.ini
├── requirements-build.txt
├── AGENTS.md
├── BUILD.md
├── README.md
└── LICENSE
```

### 4.2 三层职责与发布形态

| 层 | 目录 | 职责 | 独立发布形态 |
|---|---|---|---|
| **cli** | `cli/` | `agentctl` 命令 + 共享业务库（`lib/`） | PyPI 包（`pip install agentctl`）/ pipx / PyInstaller 单文件 exe |
| **api** | `desktop/service/`（桌面）+ `server/`（远程） | Flask HTTP API，依赖 `agentctl` 包 | desktop 嵌入 pywebview；server 独立 Docker / systemd |
| **vue** | `desktop/frontend/` | Vue 3 SPA | 静态站点 CDN / 嵌入桌面 |

### 4.3 共享代码访问方式：editable install

**决策**：使用 Python 包管理替代 `sys.path.insert` hack。

#### 包名与 import 路径

- `cli/pyproject.toml` 声明包名 `agentctl`
- `cli/` 顶层加 `__init__.py`（空文件），使其成为 `agentctl` 包
- `cli/lib/` 保持为子包 `agentctl.lib`
- `cli/lib/ide/` 保持为子包 `agentctl.lib.ide`

#### import 重写规则

| 原路径 | 新路径 |
|---|---|
| `from lib.llm import X` | `from agentctl.lib.llm import X` |
| `from lib.ide import IDE_REGISTRY` | `from agentctl.lib.ide import IDE_REGISTRY` |
| `from lib.ide.deepseek import DeepSeekTarget` | `from agentctl.lib.ide.deepseek import DeepSeekTarget` |
| `from lib.skills import copy_skills_safe` | `from agentctl.lib.skills import copy_skills_safe` |
| `import lib.llm as llm_mod` | `import agentctl.lib.llm as llm_mod` |

#### `cli/lib/` 内部相对 import（不动）

`cli/lib/ide/__init__.py` 内的 `from .base import IdeTarget`、`cli/lib/ide/deepseek.py` 内的 `from lib.logging import ...` 等。

**注意**：`lib/` 内部如果有 `from lib.X import Y` 这种绝对路径写法，需要改为相对路径 `from ..X import Y` 或新绝对路径 `from agentctl.lib.X import Y`。需要在阶段 2 仔细排查。

#### 入口点声明

`cli/pyproject.toml`：

```toml
[project]
name = "agentctl"
version = "3.5.0"
description = "AI 智能体配置统一 CLI"
requires-python = ">=3.9"
dependencies = [
    "pyyaml>=6.0",
    "requests>=2.28",
    # 其他 cli/lib 实际依赖
]

[project.scripts]
agentctl = "agentctl.agentctl:main"

[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["agentctl*"]
```

**注意**：`cli/agentctl.py` 当前没有 `main()` 函数（直接执行 `if __name__ == "__main__":`），需要在阶段 2 提取 `main()` 入口。

#### 开发环境安装

```bash
# 仓库根目录
pip install -e cli/
# 之后全局可用
agentctl --help
python -c "from agentctl.lib.llm import load_split_env_config; print('ok')"
```

### 4.4 仓库根 pyproject.toml

仓库根加 `pyproject.toml`，仅用于声明 dev 依赖和工具配置（不打包）：

```toml
[project]
name = "agentbuddy-workspace"
version = "0.0.0"
description = "AgentBuddy 开发工作区（不发布）"

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.setuptools]
# 不打包根目录
```

### 4.5 调用方 import 重写清单

#### `cli/agentctl.py`

- 删除第 29 行：`sys.path.insert(0, str(Path(__file__).resolve().parent))`
- 第 31-32 行改写：
  ```python
  # 原：from lib.logging import ...
  from agentctl.lib.logging import (
      COLOR_CYAN, COLOR_GREEN, COLOR_YELLOW, COLOR_RED, COLOR_DARKGRAY, COLOR_RESET,
      info, warn, error, hint, header,
  )
  # 原：from lib import llm, mcp, skills, plugins
  from agentctl.lib import llm, mcp, skills, plugins
  # 原：from lib.ide import get_ide, IDE_REGISTRY
  from agentctl.lib.ide import get_ide, IDE_REGISTRY
  # 原：from lib.ide._meta import get_ide_protocols
  from agentctl.lib.ide._meta import get_ide_protocols
  ```
- 提取 `main()` 函数，保留 `if __name__ == "__main__": main()`

#### `desktop/service/config_server.py`

- 删除第 192 行：`sys.path.insert(0, str(SCRIPTS_DIR))`
- 第 193-225 行所有 `from lib.X import` 改为 `from agentctl.lib.X import`
- 第 1052、1073、1158、1185、2128、2742、2751、2754、2757 行的函数内 `from lib.X import` 同样改写
- `SCRIPTS_DIR` 常量如果还被其他地方引用，保留但不再用于 sys.path

#### `desktop/launcher.py`（原 app.py）

- 第 244 行 `runpy.run_path(str(script_path), ...)` —— 检查是否还需要，如果只是调用 agentctl，可以直接 `from agentctl.agentctl import main; main()`
- 第 369 行 `config_server.app.run(...)` —— 改为 `from desktop.service.config_server import app` 或类似（注意：desktop 不是 Python 包，可能需要调整）
- 第 14 行 `import runpy` 可能可以删除

#### `server/app.py`

检查是否依赖 `scripts/lib/`。根据初步查看，`server/app.py` 主要依赖 `auth/`、`marketplace/`、`ai_generator/`（都在 `server/` 目录内），**不依赖 lib/**。待阶段 3 确认。

#### `tests/`

5 个测试文件都需要改：

- `test_agentctl.py`：删 sys.path hack，改 `from agentctl.lib import llm, skills, plugins`
- `test_llm_sync_regressions.py`：删 sys.path hack，改 `from agentctl.lib.ide.openworker import ...`
- `test_mcp_market.py`：删 sys.path hack，改 `from agentctl.lib.mcp_market import ...`
- `test_llm_placeholder.py`：删 sys.path hack，改 `from agentctl.lib import llm as llm_mod`
- 其他测试文件检查是否也有类似 hack

### 4.6 PyInstaller spec 路径修正

`MyAgentConfig.spec` 和 `app.spec` 里所有引用 `scripts/`、`tools/`、`frontend/`、`app.py` 的路径需要同步调整：

- `scripts/` → `cli/`
- `tools/` → `desktop/service/`
- `frontend/` → `desktop/frontend/`
- `app.py` → `desktop/launcher.py`
- PyInstaller entry point：`app.py` → `desktop/launcher.py`
- datas 收集路径：`(scripts/, scripts)` → `(cli/, cli)`、`(tools/, tools)` → `(desktop/service/, desktop/service)`
- hiddenimports：可能需要新增 `agentctl.lib.*` 系列（PyInstaller 对 editable install 的处理需要测试）

### 4.7 前端打包路径修正

#### `desktop/frontend/vite.config.ts`

检查 `outDir` 配置。当前可能是 `../tools/dist` 或类似，需要改为 `../service/dist` 或 `dist`（默认）。

#### `desktop/service/config_server.py` 的 `WEB_DIR`

当前可能是 `Path(__file__).parent / "web"` 或 `Path(__file__).parent.parent / "frontend" / "dist"`，需要改为 `Path(__file__).parent.parent / "frontend" / "dist"`。

#### `desktop/frontend/tsconfig.json` 的 `paths`

`@/*` 指向 `src/*`，不受目录改名影响。

### 4.8 构建脚本路径修正

- `build.py`：所有 `scripts/`、`tools/`、`frontend/`、`app.py` 引用改为新路径
- `build.cmd` / `build.sh`：同上
- `release.cmd` / `release.sh`：同上
- `install.cmd` / `install.sh`：同上
- `run.cmd` / `run.sh`：同上
- `installer.iss`：Inno Setup 脚本里的路径

### 4.9 CI / hook / 文档路径修正

- `.githooks/pre-commit`：检查是否引用 `scripts/` 路径
- `.github/workflows/build-release.yml`：所有路径引用
- `.github/workflows/tests.yml`：同上
- `AGENTS.md`：引用的 `scripts/`、`tools/`、`frontend/` 路径
- `docs/*.md`：所有路径引用
- `README.md`：安装说明、目录结构说明

## 5. 迁移分阶段计划

每阶段独立可验证，可独立提交。

### 阶段 1：目录重命名（git mv，保留历史）

**目标**：纯目录搬迁，不改任何代码。

**操作**：

```bash
git mv scripts cli
mkdir desktop
git mv tools desktop/service
git mv frontend desktop/frontend
git mv app.py desktop/launcher.py
```

**验证**：

- `git log --follow cli/agentctl.py` 能追溯到 `scripts/agentctl.py` 的历史
- 目录结构符合 4.1 节
- 所有代码文件**未修改**（git status 应显示纯 renamed）

**回滚**：`git reset --hard HEAD` 或反向 git mv。

### 阶段 2：cli/ 改成 Python 包（核心阶段）

**目标**：建立 `agentctl` 包，改写 `cli/agentctl.py` 的 import。

**操作**：

1. 新建 `cli/__init__.py`（空文件）
2. 新建 `cli/pyproject.toml`（见 4.3 节）
3. 新建仓库根 `pyproject.toml`（见 4.4 节）
4. 排查 `cli/lib/` 内部的绝对 import（`from lib.X import`）改为相对或新绝对路径
5. 改写 `cli/agentctl.py`：
   - 删除 `sys.path.insert(0, str(Path(__file__).resolve().parent))`
   - 改写所有 `from lib.X import` 为 `from agentctl.lib.X import`
   - 提取 `main()` 函数
6. `pip install -e cli/` 验证

**验证**：

```bash
pip install -e cli/
python -c "from agentctl.lib.llm import load_split_env_config; print('ok')"
python -c "from agentctl.lib.ide import IDE_REGISTRY; print(list(IDE_REGISTRY.keys()))"
agentctl --help
agentctl generate
```

**回滚**：`pip uninstall agentctl` + `git checkout cli/`。

### 阶段 3：api 层接入（desktop/service/）

**目标**：`desktop/service/config_server.py` 接入 `agentctl` 包。

**操作**：

1. 删除 `desktop/service/config_server.py` 第 192 行 `sys.path.insert(0, str(SCRIPTS_DIR))`
2. 改写所有 `from lib.X import` 为 `from agentctl.lib.X import`（约 25 处）
3. 检查 `SCRIPTS_DIR` 常量是否还被其他逻辑引用，调整或删除
4. 检查 `WEB_DIR`、`PROJECT_ROOT` 等路径常量是否正确（因目录搬迁）
5. 启动 `python desktop/service/config_server.py` 验证

**验证**：

```bash
python desktop/service/config_server.py
# 访问 http://127.0.0.1:5050/api/version，应返回版本信息
# 访问 http://127.0.0.1:5050/api/llm，应返回 llm 配置
```

**回滚**：`git checkout desktop/service/`。

### 阶段 4：launcher 接入

**目标**：`desktop/launcher.py`（原 app.py）适配新结构。

**操作**：

1. 检查 `import config_server`（第 366 行）路径是否正确 —— 因 `config_server.py` 从 `tools/` 搬到 `desktop/service/`，import 路径需调整
2. 检查 `_run_script` 函数（第 230 行 `runpy.run_path`）—— 是否还需要通过 runpy 调用 agentctl，或可以直接 `from agentctl.agentctl import main; main()`
3. 检查 `PROJECT_ROOT`、`SCRIPTS_DIR` 等路径常量
4. 检查 frozen 模式下的资源定位（`_bootstrap_resources`、`_MEIPASS`）

**验证**：

```bash
python desktop/launcher.py
# pywebview 窗口打开，Flask 后端在 5050 端口启动
# 前端能正常加载、API 能正常响应
```

**回滚**：`git checkout desktop/launcher.py`。

### 阶段 5：tests/ 接入

**目标**：删除所有 `sys.path.insert(0, SCRIPTS_DIR)` hack，改用 `agentctl` 包。

**操作**：

1. 排查 `tests/` 下所有文件，找到所有 `sys.path.insert(0, ...)` 和 `from lib.X import`
2. 删除 sys.path hack
3. 改写 `from lib.X import` 为 `from agentctl.lib.X import`
4. 运行 `pytest` 验证

**验证**：

```bash
pytest -q
# 期望：90 passed（与重构前一致）
```

**回滚**：`git checkout tests/`。

### 阶段 6：构建脚本路径修正

**目标**：所有构建脚本和 PyInstaller spec 适配新路径。

**操作**：

1. `build.py`：搜索所有 `scripts/`、`tools/`、`frontend/`、`app.py` 引用，改为新路径
2. `build.cmd` / `build.sh`：同上
3. `release.cmd` / `release.sh`：同上
4. `install.cmd` / `install.sh`：同上
5. `run.cmd` / `run.sh`：同上
6. `MyAgentConfig.spec`：entry point、datas、hiddenimports
7. `app.spec`：同上
8. `installer.iss`：Inno Setup 路径

**验证**：

```bash
python build.py --skip-tests
# 或
./build.cmd
# PyInstaller 打包成功，产物可运行
```

**回滚**：`git checkout build.py build.cmd ...`。

### 阶段 7：前端路径修正

**目标**：`desktop/frontend/` 的构建产物路径与 `desktop/service/` 对齐。

**操作**：

1. `desktop/frontend/vite.config.ts`：检查 `outDir`，确保构建产物路径正确
2. `desktop/service/config_server.py` 的 `WEB_DIR`：指向 `desktop/frontend/dist`
3. 构建前端：`cd desktop/frontend && npx vite build`
4. 启动 service 验证前端能加载

**验证**：

```bash
cd desktop/frontend && npx vite build
cd ../..
python desktop/service/config_server.py
# 访问 http://127.0.0.1:5050/，前端页面正常加载
```

**回滚**：`git checkout desktop/frontend/vite.config.ts desktop/service/config_server.py`。

### 阶段 8：server/ 检查

**目标**：确认 `server/app.py` 不依赖 `lib/`，如有依赖则改写。

**操作**：

1. 排查 `server/` 下所有文件，搜索 `from lib.` 或 `import lib`
2. 如果有，改写为 `from agentctl.lib.X import`
3. 如果没有，跳过此阶段

**验证**：

```bash
cd server && python app.py
# 远程服务正常启动
```

**回滚**：`git checkout server/`。

### 阶段 9：CI / hook / 文档路径修正

**目标**：CI 配置、git hook、文档引用同步更新。

**操作**：

1. `.githooks/pre-commit`：检查路径引用
2. `.github/workflows/build-release.yml`：所有路径引用
3. `.github/workflows/tests.yml`：所有路径引用
4. `AGENTS.md`：引用的 `scripts/`、`tools/`、`frontend/`、`app.py` 路径
5. `docs/*.md`：所有路径引用
6. `README.md`：安装说明、目录结构说明
7. `BUILD.md`：构建说明

**验证**：

- pre-commit hook 执行成功
- CI 配置语法正确（可用 `actionlint` 或手动触发）
- 文档中的路径示例可执行

**回滚**：`git checkout .githooks/ .github/ AGENTS.md docs/ README.md BUILD.md`。

### 阶段 10：全量回归 + 发布前验证

**目标**：执行 AGENTS.md 第 7 节「发布前验证清单」。

**操作**：

```bash
# 1. generate + sync 全流程
python cli/agentctl.py generate
python cli/agentctl.py sync --ide All --force --scope llm,mcp,skill,rules

# 2. 检查产物无占位符残留（路径已变）
grep '\${' config/ide/codex/config.toml config/ide/codex/auth.json
grep '\${' config/ide/claude/settings.json
grep '\${' config/proxy/config.yaml

# 3. 前端构建
cd desktop/frontend && npx vite build

# 4. 单元测试
python -m pytest -q

# 5. 桌面应用启动
python desktop/launcher.py

# 6. 远程服务启动
cd server && python app.py
```

**验证**：全部通过。

## 6. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| `cli/agentctl.py` 用 `__file__` 定位 `PROJECT_ROOT`，包化后 `__file__` 仍在 `cli/` | PROJECT_ROOT 解析错误 | 阶段 2 仔细测试，保留 `_resolve_project_root()` 的 frozen-aware 逻辑 |
| PyInstaller spec 引用旧路径 | 打包失败 | 阶段 6 同步修正，阶段 10 验证打包产物可运行 |
| `desktop/launcher.py` 的 frozen 模式资源定位（`_MEIPASS`、`_bootstrap_resources`） | 桌面应用无法启动 | 阶段 4 重点测试 frozen 模式 |
| `cli/lib/` 内部存在 `from lib.X import` 绝对路径（非相对） | 包化后 import 失败 | 阶段 2 排查并改写为相对 import `from ..X import` 或 `from agentctl.lib.X import` |
| editable install 在 PyInstaller 打包时的行为未知 | 打包后 import 失败 | 阶段 6 测试；如有问题，PyInstaller spec 显式声明 hiddenimports |
| `tools/config_server.py` 单文件 ~2000 行，改写 import 时遗漏 | 部分 API 失效 | 阶段 3 用 grep 全量替换，阶段 10 全量回归 |
| 前端 `vite.config.ts` 的 `outDir` 改动导致构建产物路径错误 | 前端 404 | 阶段 7 验证 service 能加载前端 |

## 7. 验收标准

- [ ] `pip install -e cli/` 成功，`agentctl --help` 可用
- [ ] `python -c "from agentctl.lib.llm import load_split_env_config"` 不报错
- [ ] `python -c "from agentctl.lib.ide import IDE_REGISTRY; assert 'DeepSeek' in IDE_REGISTRY"` 通过
- [ ] `pytest -q` 全部通过（90 passed）
- [ ] `python desktop/service/config_server.py` 启动，API 可访问
- [ ] `python desktop/launcher.py` 启动，pywebview 窗口正常
- [ ] `cd desktop/frontend && npx vite build` 构建成功
- [ ] `cd server && python app.py` 远程服务启动
- [ ] `python build.py --skip-tests` 打包成功，产物可运行
- [ ] `grep -r "sys.path.insert.*SCRIPTS_DIR" cli/ desktop/ tests/` 无结果
- [ ] `grep -r "from lib\." cli/agentctl.py desktop/service/config_server.py tests/` 无结果（除非是相对 import）

## 8. 未来扩展

- **cli 独立发布到 PyPI**：阶段 2 完成后，`cd cli/ && python -m build && twine upload dist/*` 即可
- **server Docker 化**：`server/Dockerfile` 基于 `python:3.11-slim`，`pip install agentctl` 作为依赖
- **frontend 独立 CDN 部署**：`desktop/frontend/dist/` 上传到 CDN，service 通过环境变量配置前端 URL
- **多 cli 入口**：`cli/pyproject.toml` 可声明多个 `[project.scripts]`，如 `agentctl-market`、`agentctl-sync`
