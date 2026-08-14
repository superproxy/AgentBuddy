# 三层分离（cli / api / vue）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将工程重构为 cli / api / vue 三层独立可发布结构，消除 sys.path hack，通过 editable install 共享业务库。

**Architecture:** `scripts/`→`cli/`（Python 包 `agentctl`）；`tools/`+`frontend/`+`app.py` 聚合到 `desktop/`（`desktop/service/` + `desktop/frontend/` + `desktop/launcher.py`）；`server/` 保持独立。共享代码 `cli/lib/` 通过 `pip install -e cli/` 访问，import 路径 `from agentctl.lib.X import`。`cli/lib/` 内部绝对 import 改为相对 import（`from .X import` / `from ..X import`）。

**Tech Stack:** Python 3.9+ / Flask / pywebview / PyInstaller / Vue 3 + Vite / pytest

## Global Constraints

- 包名：`agentctl`（pyproject.toml name + import name）
- import 路径：`from agentctl.lib.X import Y`
- `cli/lib/` 内部使用相对 import：`from .X import`（同级）、`from ..X import`（ide 子包向上一级）
- 共享代码访问方式：`pip install -e cli/`（editable install）
- PyInstaller spec 的 pathex 和 hiddenimports 必须同步更新
- 每阶段独立可验证、可回滚，每阶段一个 commit
- **不要**引入 core/ 共享包层（保持三层扁平）
- **不要**合并桌面 api 和远程 api（保留双服务）
- 测试基线：`pytest -q` 全部通过（当前 90 passed）

---

## 文件结构

### 新建文件

| 文件 | 职责 |
|---|---|
| `cli/__init__.py` | 空文件，使 `cli/` 成为 Python 包 `agentctl` |
| `cli/pyproject.toml` | 包声明，name=agentctl，entry_points |
| `pyproject.toml`（仓库根） | dev 依赖 + pytest 配置 |

### 移动文件（git mv）

| 原路径 | 新路径 |
|---|---|
| `scripts/` | `cli/` |
| `tools/` | `desktop/service/` |
| `frontend/` | `desktop/frontend/` |
| `app.py` | `desktop/launcher.py` |

### 修改文件（import 路径 + 路径常量）

| 文件 | 改动类型 |
|---|---|
| `cli/agentctl.py` | 删 sys.path + 改 import + 提取 main() |
| `cli/lib/*.py`（79 处） | `from lib.X import` → `from .X import` |
| `cli/lib/ide/*.py`（多数） | `from lib.X import` → `from ..X import` |
| `desktop/service/config_server.py` | 删 sys.path + 改 import + 路径常量 |
| `desktop/launcher.py`（原 app.py） | 路径常量 + import config_server 方式 |
| `desktop/frontend/vite.config.ts` | outDir 路径 |
| `server/ai_generator/generator.py` | 删 sys.path + 改 import |
| `tests/*.py`（8 个文件） | 删 sys.path + 改 import |
| `build.py` / `build.cmd` / `build.sh` | 路径引用 |
| `release.cmd` / `release.sh` / `run.cmd` / `run.sh` / `install.cmd` / `install.sh` | 路径引用 |
| `MyAgentConfig.spec` / `app.spec` | pathex + datas + hiddenimports |
| `.github/workflows/build-release.yml` | 路径引用 |
| `AGENTS.md` / `README.md` / `BUILD.md` | 文档路径 |

---

## Task 1: 目录重命名（git mv）

**目标**：纯目录搬迁，不改任何代码。git 保留文件历史。

**Files:**
- Move: `scripts/` → `cli/`
- Move: `tools/` → `desktop/service/`
- Move: `frontend/` → `desktop/frontend/`
- Move: `app.py` → `desktop/launcher.py`

- [ ] **Step 1: 创建 desktop/ 目录**

```bash
mkdir desktop
```

- [ ] **Step 2: git mv scripts → cli**

```bash
git mv scripts cli
```

- [ ] **Step 3: git mv tools → desktop/service**

```bash
git mv tools desktop/service
```

- [ ] **Step 4: git mv frontend → desktop/frontend**

```bash
git mv frontend desktop/frontend
```

- [ ] **Step 5: git mv app.py → desktop/launcher.py**

```bash
git mv app.py desktop/launcher.py
```

- [ ] **Step 6: 验证目录结构**

```bash
# 应看到 cli/ desktop/ server/ template/ tests/ docs/
ls -la
ls desktop/  # 应看到 launcher.py service/ frontend/
```

- [ ] **Step 7: 验证 git 保留历史**

```bash
git log --follow cli/agentctl.py | head -5
# 应看到 agentctl.py 的历史提交，证明 rename 被识别
```

- [ ] **Step 8: 验证代码文件未修改**

```bash
git status
# 应只显示 renamed，无 modified
```

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: 目录重命名 scripts→cli, tools→desktop/service, frontend→desktop/frontend, app.py→desktop/launcher.py"
```

---

## Task 2: cli/lib/ 内部 import 改为相对 import

**目标**：把 `cli/lib/` 内部 79 处 `from lib.X import` 改为相对 import，使 `cli/lib/` 成为自包含的子包。这是后续包化的前提 —— 如果不改，包化后 `from lib.X import` 会找不到 `lib` 模块。

**Files:**
- Modify: `cli/lib/mcp.py:15-20`
- Modify: `cli/lib/llm.py:11-12`
- Modify: `cli/lib/plugins.py:22-27`
- Modify: `cli/lib/skills.py:146-149`
- Modify: `cli/lib/provider_catalog.py:22`
- Modify: `cli/lib/ide/agents.py:13-15`
- Modify: `cli/lib/ide/cherrystudio.py:21-22`
- Modify: `cli/lib/ide/claude.py:9-12`
- Modify: `cli/lib/ide/base.py:11-16`
- Modify: `cli/lib/ide/codebuddy.py:14-17`
- Modify: `cli/lib/ide/codex.py:8-10`
- Modify: `cli/lib/ide/commandcode.py:14-16`
- Modify: `cli/lib/ide/cursor.py:8-10`
- Modify: `cli/lib/ide/deepseek.py:23-27`
- Modify: `cli/lib/ide/hermes.py:7-9`
- Modify: `cli/lib/ide/idea.py:12-13`
- Modify: `cli/lib/ide/kimi.py:30-32`
- Modify: `cli/lib/ide/openclaw.py:7-9`
- Modify: `cli/lib/ide/opencode.py:8-11`
- Modify: `cli/lib/ide/openworker.py:19-21`
- Modify: `cli/lib/ide/pi.py:15-17`
- Modify: `cli/lib/ide/qoder.py:7-9`
- Modify: `cli/lib/ide/qodercn.py:8-10`
- Modify: `cli/lib/ide/vscode.py:13-15`
- Modify: `cli/lib/ide/trae.py:8-10`
- Modify: `cli/lib/ide/workbuddy.py:15-18`
- Modify: `cli/lib/ide/zcode.py:10-11`

**改写规则**：
- `cli/lib/*.py` 中的 `from lib.X import` → `from .X import`（同级模块）
- `cli/lib/ide/*.py` 中的 `from lib.X import` → `from ..X import`（上一级模块）
- `cli/lib/ide/*.py` 中的 `from lib.ide.X import` → `from .X import`（同级 ide 模块）

- [ ] **Step 1: 改写 cli/lib/ 顶层模块（6 个文件）**

对 `cli/lib/mcp.py`、`cli/lib/llm.py`、`cli/lib/plugins.py`、`cli/lib/skills.py`、`cli/lib/provider_catalog.py` 中的 `from lib.X import` 改为 `from .X import`。

示例（`cli/lib/mcp.py`）：
```python
# 原：
from lib.config_io import load_env_config_file
from lib.logging import (
from lib.placeholder import prune_unresolved_blocks
from lib.plugins import iter_plugin_files

# 改为：
from .config_io import load_env_config_file
from .logging import (
from .placeholder import prune_unresolved_blocks
from .plugins import iter_plugin_files
```

- [ ] **Step 2: 改写 cli/lib/ide/ 子包模块（22 个文件）**

对 `cli/lib/ide/*.py` 中的 `from lib.X import` 改为 `from ..X import`。

示例（`cli/lib/ide/deepseek.py`）：
```python
# 原：
from lib.logging import (
from lib.skills import copy_skills_safe, write_skills_index
from lib.llm import load_split_env_config

# 改为：
from ..logging import (
from ..skills import copy_skills_safe, write_skills_index
from ..llm import load_split_env_config
```

- [ ] **Step 3: 检查 cli/lib/ide/ 内部的 `from lib.ide.X import`**

```bash
grep -rn "from lib\.ide\." cli/lib/ide/
```

如果有，改为 `from .X import`（同级 ide 模块）。预期 `cli/lib/ide/__init__.py` 已用相对 import（`from .base import`），其他文件如有 `from lib.ide.X import` 也要改。

- [ ] **Step 4: 全量验证无残留**

```bash
grep -rn "^from lib\." cli/lib/
grep -rn "^import lib\." cli/lib/
# 两个命令都应无输出
```

- [ ] **Step 5: 临时验证 import 仍可用（sys.path hack 方式）**

由于 `cli/agentctl.py` 还没改，sys.path 仍指向 `cli/`，`from lib.X import` 仍可用。但 `cli/lib/` 内部现在用相对 import，需验证：

```bash
cd cli
python -c "import sys; sys.path.insert(0, '.'); from lib.ide import IDE_REGISTRY; print(list(IDE_REGISTRY.keys())[:3])"
# 应输出前 3 个 IDE 名，证明相对 import 工作
```

- [ ] **Step 6: Commit**

```bash
git add cli/lib/
git commit -m "refactor(cli/lib): 79 处绝对 import 改为相对 import

为 cli/ 包化做准备。lib/ 内部不再依赖 sys.path 找到自身，
改用 from .X / from ..X 相对路径，使 lib/ 成为自包含子包。

cli/agentctl.py 和 tests/ 仍用 from lib.X import（由 sys.path hack 支持），
后续 Task 3/5 会改写。"
```

---

## Task 3: cli/ 改成 Python 包（核心阶段）

**目标**：建立 `agentctl` 包，改写 `cli/agentctl.py` 的 import，添加 pyproject.toml，提取 main() 入口。

**Files:**
- Create: `cli/__init__.py`（空文件）
- Create: `cli/pyproject.toml`
- Create: `pyproject.toml`（仓库根）
- Modify: `cli/agentctl.py:29-38`（删 sys.path + 改 import + 提取 main）

**Interfaces:**
- Produces: `agentctl` Python 包，`pip install -e cli/` 后全局可用
- Produces: `agentctl` CLI 入口（`agentctl --help`）
- Produces: `main()` 函数 in `cli/agentctl.py`

- [ ] **Step 1: 创建 cli/__init__.py**

```bash
# 空文件
echo. > cli/__init__.py
# 或用 Write 工具创建空文件
```

文件内容为空（或仅一行 docstring）。

- [ ] **Step 2: 创建 cli/pyproject.toml**

```toml
[project]
name = "agentctl"
version = "3.5.0"
description = "AI 智能体配置统一 CLI"
requires-python = ">=3.9"
dependencies = [
    "pyyaml>=6.0",
    "requests>=2.28",
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

注意：`[tool.setuptools.packages.find]` 的 `where = ["."]` 意味着在 `cli/` 目录下找包。因为 `cli/__init__.py` 存在，`cli/` 本身是 `agentctl` 包（通过 `name = "agentctl"` 隐式映射）。

**关键**：setuptools 需要知道 `cli/` 目录映射到 `agentctl` 包名。这通过 `package-dir` 配置：

```toml
[tool.setuptools.package-dir]
agentctl = "."
```

或更明确的方式（推荐）：

```toml
[tool.setuptools]
packages = ["agentctl", "agentctl.lib", "agentctl.lib.ide"]

[tool.setuptools.package-dir]
"agentctl" = "."
"agentctl.lib" = "lib"
"agentctl.lib.ide" = "lib/ide"
```

- [ ] **Step 3: 创建仓库根 pyproject.toml**

```toml
[project]
name = "agentbuddy-workspace"
version = "0.0.0"
description = "AgentBuddy 开发工作区（不发布，仅用于工具配置）"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

注意：这会与现有 `pytest.ini` 冲突。删除 `pytest.ini`，把内容合并到根 `pyproject.toml`。

- [ ] **Step 4: 删除 pytest.ini（内容已合并到 pyproject.toml）**

```bash
git rm pytest.ini
```

- [ ] **Step 5: 改写 cli/agentctl.py 的 import**

`cli/agentctl.py` 第 29-38 行：

```python
# 原（删除第 29-30 行）：
# 确保 scripts/ 在 sys.path 中，以便导入 lib 包
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.logging import (
    COLOR_CYAN, COLOR_GREEN, COLOR_YELLOW, COLOR_RED, COLOR_DARKGRAY, COLOR_RESET,
    info, warn, error, hint, header,
)
from lib import llm, mcp, skills, plugins
from lib.ide import get_ide, IDE_REGISTRY
from lib.ide._meta import get_ide_protocols as get_ide_protocols

# 改为：
from agentctl.lib.logging import (
    COLOR_CYAN, COLOR_GREEN, COLOR_YELLOW, COLOR_RED, COLOR_DARKGRAY, COLOR_RESET,
    info, warn, error, hint, header,
)
from agentctl.lib import llm, mcp, skills, plugins
from agentctl.lib.ide import get_ide, IDE_REGISTRY
from agentctl.lib.ide._meta import get_ide_protocols as get_ide_protocols
```

- [ ] **Step 6: 检查 cli/agentctl.py 内部其他 import**

```bash
grep -n "from lib\.\|import lib\." cli/agentctl.py
```

如有其他 `from lib.X import`（可能在函数内），也改为 `from agentctl.lib.X import`。

- [ ] **Step 7: 提取 main() 函数**

查看 `cli/agentctl.py` 末尾的 `if __name__ == "__main__":` 块，把其内容提取为 `def main():` 函数：

```python
def main():
    """CLI 主入口。"""
    parser = argparse.ArgumentParser(...)
    # ... 现有 argparse 配置 ...
    args = parser.parse_args()
    # ... 现有命令分发逻辑 ...

if __name__ == "__main__":
    main()
```

注意：保留 `sys.argv` 操作（如果有）在 `main()` 内。`_resolve_project_root()` 等辅助函数保持在模块顶层。

- [ ] **Step 8: 安装 editable**

```bash
pip install -e cli/
```

验证安装成功（无报错）。

- [ ] **Step 9: 验证 import**

```bash
python -c "from agentctl.lib.llm import load_split_env_config; print('ok')"
python -c "from agentctl.lib.ide import IDE_REGISTRY; print('DeepSeek' in IDE_REGISTRY)"
python -c "from agentctl.agentctl import main; print(callable(main))"
```

三个命令都应输出 True 或 ok。

- [ ] **Step 10: 验证 CLI 入口**

```bash
agentctl --help
# 应显示帮助信息
```

- [ ] **Step 11: 验证 PROJECT_ROOT 定位**

`cli/agentctl.py` 的 `_resolve_project_root()` 用 `__file__` 定位。包化后 `__file__` 是 `cli/agentctl.py`（editable install）或 site-packages 路径（正式安装）。测试：

```bash
cd /tmp  # 离开项目目录
agentctl generate
# 应能找到 PROJECT_ROOT（通过 __file__ 向上一级）
```

如果失败，检查 `_resolve_project_root()` 逻辑，可能需要调整路径计算。

- [ ] **Step 12: Commit**

```bash
git add cli/__init__.py cli/pyproject.toml cli/agentctl.py pyproject.toml
git rm pytest.ini
git commit -m "feat(cli): cli/ 改为 agentctl Python 包

- 新增 cli/__init__.py 和 cli/pyproject.toml
- 仓库根新增 pyproject.toml（pytest 配置迁移自 pytest.ini）
- cli/agentctl.py 删除 sys.path hack，import 改为 from agentctl.lib.X
- 提取 main() 函数作为 entry point
- pip install -e cli/ 后 agentctl 命令全局可用"
```

---

## Task 4: desktop/service/ 接入 agentctl 包

**目标**：`desktop/service/config_server.py` 删除 sys.path hack，改用 `from agentctl.lib.X import`，调整路径常量。

**Files:**
- Modify: `desktop/service/config_server.py:116-117,192-225,1052,1073,1158,1185,2128,2742,2751,2754,2757,625-652`

**Interfaces:**
- Consumes: `agentctl` 包（Task 3 产出）
- Produces: 桌面 Flask API 可独立启动

- [ ] **Step 1: 删除 sys.path hack**

`desktop/service/config_server.py` 第 192 行：

```python
# 删除：
sys.path.insert(0, str(SCRIPTS_DIR))
```

- [ ] **Step 2: 改写顶层 import（第 193-225 行）**

把所有 `from lib.X import` 改为 `from agentctl.lib.X import`：

```python
# 原：
from lib.config_io import load_env_config_file, save_env_config_file
from lib.skills import (
from lib.plugins import install_plugin, update_env_file, add_to_installed
from lib.ide.detect import detect_ide, detect_all
from lib.ide.session import list_sessions, export_session, import_session_to_ide
from lib.ide.launch import launch_ide, launch_ide_resume_session
from lib.ide.install import (
from lib.provider_catalog import (
from lib.mcp_market import (
from lib.skill_market import (

# 改为：
from agentctl.lib.config_io import load_env_config_file, save_env_config_file
from agentctl.lib.skills import (
from agentctl.lib.plugins import install_plugin, update_env_file, add_to_installed
from agentctl.lib.ide.detect import detect_ide, detect_all
from agentctl.lib.ide.session import list_sessions, export_session, import_session_to_ide
from agentctl.lib.ide.launch import launch_ide, launch_ide_resume_session
from agentctl.lib.ide.install import (
from agentctl.lib.provider_catalog import (
from agentctl.lib.mcp_market import (
from agentctl.lib.skill_market import (
```

- [ ] **Step 3: 改写函数内 import（第 1052, 1073, 1158, 1185, 2128, 2742, 2751, 2754, 2757 行）**

这些是函数内的延迟 import，用 grep 找全：

```bash
grep -n "from lib\." desktop/service/config_server.py
```

全部改为 `from agentctl.lib.X import`。

- [ ] **Step 4: 修改路径常量**

`desktop/service/config_server.py` 第 116-117 行：

```python
# 原：
PROJECT_ROOT = _resolve_project_root()
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

# 改为：
PROJECT_ROOT = _resolve_project_root()
SCRIPTS_DIR = PROJECT_ROOT / "cli"  # 原 scripts/ 已重命名为 cli/
```

注意：`SCRIPTS_DIR` 仍被 `_script_run_cmd()` 用于 subprocess 调用 agentctl，保留但指向新路径。

- [ ] **Step 5: 修改前端产物路径**

`desktop/service/config_server.py` 第 625-652 行，`index()` 和 `dist_assets()` 函数：

```python
# 原：
dist_ui = PROJECT_ROOT / "tools" / "dist-ui" / "index.html"
# ...
resp = send_from_directory(PROJECT_ROOT / "tools" / "dist-ui" / "assets", filename)

# 改为：
dist_ui = PROJECT_ROOT / "desktop" / "service" / "dist-ui" / "index.html"
# ...
resp = send_from_directory(PROJECT_ROOT / "desktop" / "service" / "dist-ui" / "assets", filename)
```

注意：保持 `dist-ui` 目录名不变（与 vite.config.ts 的 outDir 对齐，Task 7 会改 vite outDir 到 `../service/dist-ui`）。

- [ ] **Step 6: 验证 import 无残留**

```bash
grep -n "from lib\.\|import lib\." desktop/service/config_server.py
# 应无输出
```

- [ ] **Step 7: 验证 sys.path 无残留**

```bash
grep -n "sys\.path\.insert.*SCRIPTS_DIR" desktop/service/config_server.py
# 应无输出
```

- [ ] **Step 8: 启动桌面 service 验证**

```bash
python desktop/service/config_server.py
```

访问 http://127.0.0.1:5050/api/version —— 应返回版本 JSON。
访问 http://127.0.0.1:5050/api/llm —— 应返回 LLM 配置（如果 config/ 存在）。

如果前端未构建，根路径返回 503 是正常的（Task 7 会修）。

- [ ] **Step 9: Commit**

```bash
git add desktop/service/config_server.py
git commit -m "refactor(desktop/service): 接入 agentctl 包

- 删除 sys.path.insert(0, SCRIPTS_DIR) hack
- 25+ 处 from lib.X import 改为 from agentctl.lib.X import
- SCRIPTS_DIR 路径常量指向 cli/（原 scripts/）
- 前端产物路径改为 desktop/service/dist-ui/"
```

---

## Task 5: tests/ 接入 agentctl 包

**目标**：删除所有 sys.path hack，改用 `from agentctl.lib.X import`。

**Files:**
- Modify: `tests/test_agentctl.py:16-21`
- Modify: `tests/test_codex_proxy_route.py:6-8`
- Modify: `tests/test_keys_yaml.py:17-19`
- Modify: `tests/test_mcp_market.py:6-8`
- Modify: `tests/test_llm_sync_regressions.py:17-25`
- Modify: `tests/test_llm_placeholder.py:17-19`
- Modify: `tests/test_mcp_placeholder_env.py:17-19`
- Modify: `tests/test_plugin_envvars.py:22-23`
- Modify: `tests/test_legacy_migration_once.py:23-26`（依赖 app.py，需特殊处理）

**Interfaces:**
- Consumes: `agentctl` 包（Task 3 产出）
- Produces: 测试套件可运行

- [ ] **Step 1: 改写 test_agentctl.py**

```python
# 原（第 16-21 行）：
# 将 scripts/ 加入 sys.path 以导入 lib 包
sys.path.insert(0, str(SCRIPTS_DIR))

from lib import llm, skills, plugins
from lib import provider_catalog

# 改为（删除 sys.path + 改 import）：
from agentctl.lib import llm, skills, plugins
from agentctl.lib import provider_catalog
```

同时删除 `SCRIPTS_DIR` 变量定义（如果仅用于 sys.path）。

- [ ] **Step 2: 改写 test_codex_proxy_route.py**

```python
# 原：
sys.path.insert(0, str(SCRIPTS_DIR))
from lib.llm import build_proxy_model_list, flatten_env_config

# 改为：
from agentctl.lib.llm import build_proxy_model_list, flatten_env_config
```

- [ ] **Step 3: 改写 test_keys_yaml.py**

```python
# 原：
sys.path.insert(0, str(SCRIPTS_DIR))
from lib import llm as llm_mod

# 改为：
from agentctl.lib import llm as llm_mod
```

- [ ] **Step 4: 改写 test_mcp_market.py**

```python
# 原：
sys.path.insert(0, str(SCRIPTS_DIR))
from lib.mcp_market import (

# 改为：
from agentctl.lib.mcp_market import (
```

- [ ] **Step 5: 改写 test_llm_sync_regressions.py**

```python
# 原：
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
# ...
from lib.ide.openworker import OpenWorkerTarget, openworker_state_dir

# 改为：
from agentctl.lib.ide.openworker import OpenWorkerTarget, openworker_state_dir
```

- [ ] **Step 6: 改写 test_llm_placeholder.py**

```python
# 原：
sys.path.insert(0, str(SCRIPTS_DIR))
from lib import llm as llm_mod

# 改为：
from agentctl.lib import llm as llm_mod
```

- [ ] **Step 7: 改写 test_mcp_placeholder_env.py**

```python
# 原：
sys.path.insert(0, str(SCRIPTS_DIR))
from lib import mcp as mcp_mod

# 改为：
from agentctl.lib import mcp as mcp_mod
```

- [ ] **Step 8: 改写 test_plugin_envvars.py**

```python
# 原（第 22-23 行）：
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TOOLS_DIR))

# 改为：删除这两行
# 如果测试内还有 from lib.X import，改为 from agentctl.lib.X import
# 如果有 import config_server，改为 from desktop.service.config_server import（需 desktop 是包，见 Step 10）
```

- [ ] **Step 9: 改写 test_legacy_migration_once.py（特殊：依赖 app.py）**

这个测试 `import app as app_mod`，但 `app.py` 已改为 `desktop/launcher.py`。有两种处理方式：

方式 A（推荐）：把测试改为 import launcher：
```python
# 原：
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as app_mod

# 改为：
import desktop.launcher as app_mod
```

这要求 `desktop/` 是 Python 包（需 `desktop/__init__.py`）。但 `desktop/` 不是 Python 包，是聚合目录。

方式 B：通过 importlib 动态加载：
```python
import importlib.util
spec = importlib.util.spec_from_file_location("launcher", ROOT / "desktop" / "launcher.py")
app_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_mod)
```

方式 C（最简单）：`desktop/` 加 `__init__.py` 使其成为包，然后 `from desktop.launcher import ...`。但 launcher.py 会在 import 时执行顶层代码（启动 pywebview），不适合作为模块 import。

**决策**：用方式 B（importlib 动态加载），避免执行 launcher 的顶层代码。但需要检查 launcher.py 的顶层代码是否有副作用 —— 如果有，需要把副作用包装到函数中。

先看 `desktop/launcher.py` 的顶层代码：
```bash
grep -n "^if __name__\|^def \|^class " desktop/launcher.py | head -20
```

如果顶层代码只是函数定义和常量，方式 A 可行。如果有 `if __name__ == "__main__":` 之外的执行代码，需要重构。

**实际操作**：先尝试方式 A，如果失败（import 时启动了 pywebview），改用方式 B 或重构 launcher.py。

- [ ] **Step 10: 运行 pytest 验证**

```bash
pytest -q
```

期望：90 passed（与重构前一致）。

如果有失败，逐一排查。常见问题：
- import 路径错误 → 检查 `from agentctl.lib.X` 拼写
- `desktop/` 不是包 → 加 `desktop/__init__.py`（空文件）
- `config_server` 找不到 → desktop/service/ 需 `__init__.py` 或用 importlib

- [ ] **Step 11: 验证无 sys.path 残留**

```bash
grep -rn "sys\.path\.insert.*SCRIPTS_DIR\|sys\.path\.insert.*TOOLS_DIR\|sys\.path\.insert.*scripts" tests/
# 应无输出
```

- [ ] **Step 12: 验证无 from lib 残留**

```bash
grep -rn "^from lib\.\|^import lib\." tests/
# 应无输出
```

- [ ] **Step 13: Commit**

```bash
git add tests/
git commit -m "refactor(tests): 接入 agentctl 包

- 8 个测试文件删除 sys.path.insert hack
- from lib.X import 改为 from agentctl.lib.X import
- test_legacy_migration_once.py 改为动态加载 desktop/launcher.py
- pytest -q: 90 passed"
```

---

## Task 6: desktop/launcher.py 适配新结构

**目标**：原 `app.py` 适配新目录结构，修改路径常量和 import config_server 方式。

**Files:**
- Modify: `desktop/launcher.py:213-214,216-222,227-233,310-321,362-369,614-619`

**Interfaces:**
- Consumes: `desktop/service/config_server.py`
- Produces: 桌面应用可启动

- [ ] **Step 1: 修改路径常量**

`desktop/launcher.py` 第 213-214 行：

```python
# 原：
TOOLS_DIR = PROJECT_ROOT / "tools"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

# 改为：
SERVICE_DIR = PROJECT_ROOT / "desktop" / "service"
SCRIPTS_DIR = PROJECT_ROOT / "cli"  # 原 scripts/ → cli/
```

- [ ] **Step 2: 修改 sys.path 注入 config_server**

`desktop/launcher.py` 第 216-218 行：

```python
# 原：
# 把 tools/ 加入 sys.path 以便 import config_server
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

# 改为：
# 把 desktop/service/ 加入 sys.path 以便 import config_server
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))
```

注意：`config_server.py` 是单文件模块，不是包。保留 sys.path hack 是合理的（config_server 不需要包化）。

- [ ] **Step 3: 修改 _run_bundled_script 路径**

`desktop/launcher.py` 第 227-233 行：

```python
# 原：
candidates.append(PROJECT_ROOT / "scripts" / f"{script_name}.py")
# ...
candidates.append(meipass / "scripts" / f"{script_name}.py")

# 改为：
candidates.append(PROJECT_ROOT / "cli" / f"{script_name}.py")
# ...
candidates.append(meipass / "cli" / f"{script_name}.py")
```

注意：frozen 模式下 `_MEIPASS/scripts/` 也要改为 `_MEIPASS/cli/`，PyInstaller spec（Task 7）会同步。

- [ ] **Step 4: 修改 _bootstrap_resources 资源列表**

`desktop/launcher.py` 第 321 行：

```python
# 原：
"scripts", "template", "tools",

# 改为：
"cli", "template", "desktop/service", "desktop/frontend",
```

注意：frozen 模式下从 `_MEIPASS` 复制资源到数据目录，路径需同步。

- [ ] **Step 5: 修改 import config_server**

`desktop/launcher.py` 第 362 行：

```python
# 原：
import config_server  # noqa: E402  (位于 tools/)

# 改为：
import config_server  # noqa: E402  (位于 desktop/service/)
```

import 语句不变（config_server 通过 sys.path 找到），注释更新。

- [ ] **Step 6: 修改 --run 帮助文本**

`desktop/launcher.py` 第 614 行：

```python
# 原：
parser.add_argument("--run", metavar="SCRIPT", help="frozen 模式下运行 bundled scripts/<name>.py（内部用，不启动窗口）")

# 改为：
parser.add_argument("--run", metavar="SCRIPT", help="frozen 模式下运行 bundled cli/<name>.py（内部用，不启动窗口）")
```

- [ ] **Step 7: 验证桌面应用启动（dev 模式）**

```bash
python desktop/launcher.py
```

期望：
- pywebview 窗口打开（或回退到浏览器）
- Flask 后端在 5050 端口启动
- 前端能加载（如果 dist-ui 存在）

- [ ] **Step 8: Commit**

```bash
git add desktop/launcher.py
git commit -m "refactor(desktop/launcher): 适配新目录结构

- TOOLS_DIR → SERVICE_DIR (desktop/service/)
- SCRIPTS_DIR 指向 cli/（原 scripts/）
- _run_bundled_script 路径改为 cli/
- _bootstrap_resources 资源列表更新"
```

---

## Task 7: 前端构建路径修正

**目标**：`desktop/frontend/vite.config.ts` 的 outDir 对齐到 `desktop/service/dist-ui`。

**Files:**
- Modify: `desktop/frontend/vite.config.ts:18`（outDir）
- Verify: `desktop/service/config_server.py` 的 dist-ui 路径（Task 4 已改）

- [ ] **Step 1: 修改 vite.config.ts 的 outDir**

`desktop/frontend/vite.config.ts` 第 18 行：

```typescript
// 原：
outDir: '../tools/dist-ui',

// 改为：
outDir: '../service/dist-ui',
```

注意：`desktop/frontend/` 相对路径 `../service/dist-ui` 指向 `desktop/service/dist-ui`。

- [ ] **Step 2: 构建前端验证**

```bash
cd desktop/frontend
npm run build-only
```

期望：构建成功，产物在 `desktop/service/dist-ui/`。

- [ ] **Step 3: 验证产物**

```bash
ls desktop/service/dist-ui/
# 应看到 index.html、assets/ 等
```

- [ ] **Step 4: 启动 service 验证前端加载**

```bash
python desktop/service/config_server.py
```

访问 http://127.0.0.1:5050/ —— 应看到前端页面（不再是 503）。

- [ ] **Step 5: Commit**

```bash
git add desktop/frontend/vite.config.ts
git commit -m "refactor(desktop/frontend): vite outDir 改为 ../service/dist-ui

对齐 desktop/service/config_server.py 的 dist-ui 路径。"
```

---

## Task 8: server/ai_generator/ 接入 agentctl 包

**目标**：`server/ai_generator/generator.py` 删除 sys.path hack，改用 `from agentctl.lib.X import`。

**Files:**
- Modify: `server/ai_generator/generator.py:236-237,536,541,556`

- [ ] **Step 1: 修改顶层 import**

`server/ai_generator/generator.py` 第 236-237 行：

```python
# 原：
from lib.skill_market import search_skill_market
from lib.mcp_market import search_mcp_market

# 改为：
from agentctl.lib.skill_market import search_skill_market
from agentctl.lib.mcp_market import search_mcp_market
```

- [ ] **Step 2: 删除函数内 sys.path hack**

`server/ai_generator/generator.py` 第 536 行：

```python
# 原：
scripts_dir = str(Path(__file__).resolve().parent.parent.parent / "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

# 改为：删除这 3 行
```

- [ ] **Step 3: 改写函数内 import**

`server/ai_generator/generator.py` 第 541、556 行：

```python
# 原：
from lib.skill_market import search_skill_market
# ...
from lib.mcp_market import search_mcp_market

# 改为：
from agentctl.lib.skill_market import search_skill_market
# ...
from agentctl.lib.mcp_market import search_mcp_market
```

注意：第 236-237 行已有顶层 import，函数内的延迟 import 可以直接删除（用顶层的）。但如果函数内有 try/except 包裹（容错），保留延迟 import 但改路径。

- [ ] **Step 4: 验证 import 无残留**

```bash
grep -n "from lib\.\|import lib\.\|sys\.path.*scripts" server/ai_generator/generator.py
# 应无输出
```

- [ ] **Step 5: 检查 server/ 其他文件**

```bash
grep -rn "from lib\.\|import lib\.\|sys\.path.*scripts" server/
# 应无输出（如果 ai_generator 是唯一依赖 lib 的）
```

- [ ] **Step 6: 验证 server 启动**

```bash
cd server
python app.py
```

访问 http://127.0.0.1:5001/api/health —— 应返回 `{"ok": true}`。

- [ ] **Step 7: Commit**

```bash
git add server/ai_generator/generator.py
git commit -m "refactor(server/ai_generator): 接入 agentctl 包

- 删除 sys.path.insert(0, scripts_dir) hack
- from lib.X import 改为 from agentctl.lib.X import
- server/ 不再依赖 scripts/ 目录，通过 agentctl 包访问共享代码"
```

---

## Task 9: PyInstaller spec 路径修正

**目标**：`MyAgentConfig.spec` 和 `app.spec` 适配新目录结构。

**Files:**
- Modify: `MyAgentConfig.spec:30,45-49,69-70,92`
- Modify: `app.spec:63-64,74,109-110`

- [ ] **Step 1: 修改 MyAgentConfig.spec**

`MyAgentConfig.spec` 多处：

```python
# 第 30 行（hiddenimports）：
# 原：
'scripts',
# 改为：
'cli',

# 第 45-49 行（datas）：
# 原：
('tools/config_ui.html', 'tools'),
('scripts/init-env.py', 'scripts'),
('scripts/init-ide.py', 'scripts'),
('scripts/plugin-manager.py', 'scripts'),
('scripts/cleanup.py', 'scripts'),

# 改为：
('desktop/service/config_ui.html', 'desktop/service'),
('cli/init-env.py', 'cli'),
('cli/init-ide.py', 'cli'),
('cli/plugin-manager.py', 'cli'),
('cli/cleanup.py', 'cli'),

# 第 69 行（Analysis entry）：
# 原：
['app.py'],
# 改为：
['desktop/launcher.py'],

# 第 70 行（pathex）：
# 原：
pathex=['.', 'tools'],
# 改为：
pathex=['.', 'desktop/service', 'cli'],

# 第 92 行（exe name）：
# 如果 exe name 是 'MyAgentConfig'，保持不变
```

- [ ] **Step 2: 修改 app.spec**

`app.spec` 多处：

```python
# 第 63-64 行（datas）：
# 原：
datas += collect_dir('scripts', 'scripts')
datas += collect_dir('tools', 'tools')

# 改为：
datas += collect_dir('cli', 'cli')
datas += collect_dir('desktop/service', 'desktop/service')
datas += collect_dir('desktop/frontend', 'desktop/frontend')

# 第 74 行（hiddenimports）：
# 原：
hiddenimports = [
    'config_server',
    'lib', 'lib.config_io', 'lib.llm', ...
    'lib.ide', 'lib.ide.base', ...
    # AI 生成服务

# 改为：
hiddenimports = [
    'config_server',
    'agentctl', 'agentctl.lib', 'agentctl.lib.config_io', 'agentctl.lib.llm',
    'agentctl.lib.mcp', 'agentctl.lib.skills', 'agentctl.lib.plugins',
    'agentctl.lib.placeholder', 'agentctl.lib.paths', 'agentctl.lib.logging',
    'agentctl.lib.ide', 'agentctl.lib.ide.base',
    'agentctl.lib.ide.cursor', 'agentctl.lib.ide.codex',
    'agentctl.lib.ide.opencode', 'agentctl.lib.ide.trae',
    'agentctl.lib.ide.claude', 'agentctl.lib.ide.workbuddy',
    'agentctl.lib.ide.qoder', 'agentctl.lib.ide.openclaw',
    'agentctl.lib.ide.hermes', 'agentctl.lib.ide.idea',
    'agentctl.lib.ide.agents', 'agentctl.lib.ide.deepseek',
    # AI 生成服务（保留原有）

# 第 109-110 行（Analysis）：
# 原：
['app.py'],
pathex=['scripts', 'tools', 'server'],

# 改为：
['desktop/launcher.py'],
pathex=['cli', 'desktop/service', 'server'],
```

- [ ] **Step 3: 验证 spec 语法**

```bash
python -c "import ast; ast.parse(open('MyAgentConfig.spec').read()); print('OK')"
python -c "import ast; ast.parse(open('app.spec').read()); print('OK')"
```

- [ ] **Step 4: 尝试打包验证**

```bash
python build.py --skip-tests
```

期望：PyInstaller 打包成功（可能耗时较长）。

如果失败，检查：
- pathex 路径是否正确
- hiddenimports 是否遗漏
- datas 收集的目录是否存在

- [ ] **Step 5: 验证打包产物**

```bash
# Windows
dist\AgentBuddy\AgentBuddy.exe
# 或
dist\MyAgentConfig\MyAgentConfig.exe
```

启动 exe，验证：
- pywebview 窗口打开
- Flask 后端启动
- 前端加载
- API 可用

- [ ] **Step 6: Commit**

```bash
git add MyAgentConfig.spec app.spec
git commit -m "refactor(spec): PyInstaller spec 适配新目录结构

- scripts → cli, tools → desktop/service, app.py → desktop/launcher.py
- hiddenimports 从 lib.* 改为 agentctl.lib.*
- pathex 更新为 cli/, desktop/service/"
```

---

## Task 10: 构建脚本路径修正

**目标**：`build.py` / `build.cmd` / `build.sh` / `run.cmd` / `run.sh` / `release.*` / `install.*` 适配新路径。

**Files:**
- Modify: `build.py:55,157,160`
- Modify: `build.cmd:15-26,55-58`
- Modify: `build.sh`（检查路径引用）
- Modify: `run.cmd:40`
- Modify: `run.sh:58`
- Modify: `release.cmd` / `release.sh`（检查路径引用）
- Modify: `install.cmd` / `install.sh`（检查路径引用）

- [ ] **Step 1: 修改 build.py**

`build.py` 第 55、157、160 行：

```python
# 第 55 行：
# 原：
SPEC_FILE = PROJECT_ROOT / "app.spec"
# 保持不变（app.spec 仍在仓库根）

# 第 157 行（注释）：
# 原：
"""构建时写入版本信息到 tools/dist-ui/version.json，供运行时 /api/version 读取。"""
# 改为：
"""构建时写入版本信息到 desktop/service/dist-ui/version.json，供运行时 /api/version 读取。"""

# 第 160 行：
# 原：
version_file = PROJECT_ROOT / "tools" / "dist-ui" / "version.json"
# 改为：
version_file = PROJECT_ROOT / "desktop" / "service" / "dist-ui" / "version.json"
```

- [ ] **Step 2: 修改 build.cmd**

`build.cmd` 第 15-26、55-58 行：

```bat
REM 第 15-18 行：
REM 原：
if not exist "frontend\node_modules" (
    echo [build]   Installing npm dependencies...
    cd frontend && call npm install && cd ..
)
cd frontend
call npm run build-only

REM 改为：
if not exist "desktop\frontend\node_modules" (
    echo [build]   Installing npm dependencies...
    cd desktop\frontend && call npm install && cd ..\..
)
cd desktop\frontend
call npm run build-only
cd ..\..

REM 第 26 行：
REM 原：
echo [build]   OK: tools\dist-ui\
REM 改为：
echo [build]   OK: desktop\service\dist-ui\

REM 第 55-58 行：
REM 原：
if exist "dist\AgentBuddy\_internal\tools\dist-ui\index.html" (
    echo [build]   OK: _internal\tools\dist-ui\index.html
) else if exist "dist\AgentBuddy\tools\dist-ui\index.html" (
    echo [build]   OK: tools\dist-ui\index.html

REM 改为：
if exist "dist\AgentBuddy\_internal\desktop\service\dist-ui\index.html" (
    echo [build]   OK: _internal\desktop\service\dist-ui\index.html
) else if exist "dist\AgentBuddy\desktop\service\dist-ui\index.html" (
    echo [build]   OK: desktop\service\dist-ui\index.html
```

- [ ] **Step 3: 修改 build.sh**

```bash
# 检查 build.sh 里的路径引用
grep -n "scripts\|tools\|frontend\|app\.py" build.sh
```

如有，按相同规则修改（scripts→cli, tools→desktop/service, frontend→desktop/frontend, app.py→desktop/launcher.py）。

- [ ] **Step 4: 修改 run.cmd**

`run.cmd` 第 40 行：

```bat
REM 原：
python app.py --port %PORT% %2 %3 %4

REM 改为：
python desktop\launcher.py --port %PORT% %2 %3 %4
```

- [ ] **Step 5: 修改 run.sh**

`run.sh` 第 58 行：

```bash
# 原：
exec $PY app.py --port "$PORT" ${2:-} ${3:-} ${4:-}

# 改为：
exec $PY desktop/launcher.py --port "$PORT" ${2:-} ${3:-} ${4:-}
```

- [ ] **Step 6: 检查 release.* 和 install.*

```bash
grep -n "scripts\|tools\|frontend\|app\.py" release.cmd release.sh install.cmd install.sh
```

如有引用，按规则修改。

- [ ] **Step 7: 验证 build.cmd（dry run）**

```bash
# 不实际打包，只验证脚本语法
build.cmd --no-installer
# 或先看 echo 输出是否正确
```

- [ ] **Step 8: Commit**

```bash
git add build.py build.cmd build.sh run.cmd run.sh release.cmd release.sh install.cmd install.sh
git commit -m "refactor(build): 构建脚本路径适配新目录结构

- build.py: version_file 路径改为 desktop/service/dist-ui/
- build.cmd: frontend → desktop\frontend, tools\dist-ui → desktop\service\dist-ui
- run.cmd/run.sh: app.py → desktop/launcher.py
- release/install 脚本同步更新"
```

---

## Task 11: CI / hook / 文档路径修正

**目标**：CI 配置、git hook、文档引用同步更新。

**Files:**
- Modify: `.github/workflows/build-release.yml:47,49,121,123`
- Verify: `.githooks/pre-commit`（仅 pytest，无路径引用）
- Modify: `AGENTS.md:83-84,120`
- Modify: `README.md`（检查路径引用）
- Modify: `BUILD.md`（检查路径引用）
- Modify: `docs/*.md`（检查路径引用）

- [ ] **Step 1: 修改 .github/workflows/build-release.yml**

第 47-49、121-123 行：

```yaml
# 原：
- name: Build frontend
  run: |
    cd frontend
    npm run build-only

# 改为：
- name: Build frontend
  run: |
    cd desktop/frontend
    npm run build-only
```

- [ ] **Step 2: 检查 .githooks/pre-commit**

```bash
grep -n "scripts\|tools\|frontend\|app\.py" .githooks/pre-commit
```

预期无路径引用（只运行 `pytest -q`），无需修改。

- [ ] **Step 3: 修改 AGENTS.md**

第 83-84 行：

```bash
# 原：
python scripts/agentctl.py generate
python scripts/agentctl.py sync --ide All --force --scope llm,mcp,skill,rules

# 改为：
python cli/agentctl.py generate
python cli/agentctl.py sync --ide All --force --scope llm,mcp,skill,rules
```

第 120 行（提及 app.py）：

```bash
# 原：
**问题**：`app.py` 的 `_migrate_legacy_data_dir()` ...
# 改为：
**问题**：`desktop/launcher.py` 的 `_migrate_legacy_data_dir()` ...
```

- [ ] **Step 4: 检查并修改 README.md**

```bash
grep -n "scripts/\|tools/\|frontend/\|app\.py" README.md
```

按规则修改所有引用。

- [ ] **Step 5: 检查并修改 BUILD.md**

```bash
grep -n "scripts/\|tools/\|frontend/\|app\.py" BUILD.md
```

按规则修改所有引用。

- [ ] **Step 6: 检查并修改 docs/*.md**

```bash
grep -rln "scripts/\|tools/\|frontend/\|app\.py" docs/
```

对每个匹配文件，按规则修改。注意 `docs/superpowers/specs/2026-08-14-three-layer-separation-design.md` 是本设计文档，**不改**（它是历史记录）。

- [ ] **Step 7: 验证 CI YAML 语法**

```bash
# 如果有 actionlint
actionlint .github/workflows/*.yml

# 或手动检查缩进
python -c "import yaml; yaml.safe_load(open('.github/workflows/build-release.yml').read()); print('OK')"
```

- [ ] **Step 8: Commit**

```bash
git add .github/workflows/build-release.yml AGENTS.md README.md BUILD.md docs/
git commit -m "docs: CI/hook/文档路径适配新目录结构

- build-release.yml: frontend → desktop/frontend
- AGENTS.md: scripts/agentctl.py → cli/agentctl.py, app.py → desktop/launcher.py
- README.md / BUILD.md / docs/ 同步更新"
```

---

## Task 12: 全量回归 + 发布前验证

**目标**：执行 AGENTS.md 第 7 节「发布前验证清单」，确保所有功能正常。

**Files:**
- Verify: 所有改动的集成验证

- [ ] **Step 1: 安装 agentctl 包**

```bash
pip install -e cli/
```

- [ ] **Step 2: 验证 import**

```bash
python -c "from agentctl.lib.llm import load_split_env_config; print('ok')"
python -c "from agentctl.lib.ide import IDE_REGISTRY; assert 'DeepSeek' in IDE_REGISTRY; print('ok')"
python -c "from agentctl.agentctl import main; assert callable(main); print('ok')"
```

- [ ] **Step 3: 验证 CLI**

```bash
agentctl --help
agentctl generate
```

- [ ] **Step 4: 验证 sync 全流程**

```bash
python cli/agentctl.py sync --ide All --force --scope llm,mcp,skill,rules
```

- [ ] **Step 5: 检查产物无占位符残留**

```bash
grep '\${' config/ide/codex/config.toml config/ide/codex/auth.json
grep '\${' config/ide/claude/settings.json
grep '\${' config/proxy/config.yaml
# 应无输出
```

- [ ] **Step 6: 前端构建**

```bash
cd desktop/frontend
npx vite build
cd ../..
```

- [ ] **Step 7: 单元测试**

```bash
python -m pytest -q
```

期望：90 passed。

- [ ] **Step 8: 桌面应用启动**

```bash
python desktop/launcher.py
```

期望：pywebview 窗口打开，Flask 后端启动，前端加载，API 可用。

- [ ] **Step 9: 远程服务启动**

```bash
cd server
python app.py
cd ..
```

期望：远程服务在 5001 端口启动，/api/health 返回 ok。

- [ ] **Step 10: PyInstaller 打包**

```bash
python build.py --skip-tests
```

期望：打包成功。

- [ ] **Step 11: 验证打包产物**

```bash
# Windows
dist\AgentBuddy\AgentBuddy.exe
```

期望：exe 可启动，功能正常。

- [ ] **Step 12: 验证无 sys.path 残留**

```bash
grep -rn "sys\.path\.insert.*SCRIPTS_DIR\|sys\.path\.insert.*scripts" cli/ desktop/ tests/ server/
# 应无输出
```

- [ ] **Step 13: 验证无 from lib 残留**

```bash
grep -rn "^from lib\.\|^import lib\." cli/agentctl.py desktop/service/config_server.py tests/ server/
# 应无输出
```

- [ ] **Step 14: 最终 Commit（如果有未提交的修复）**

```bash
git status
# 如果有改动
git add -A
git commit -m "test: 全量回归验证通过

- pip install -e cli/ 成功
- agentctl CLI 可用
- pytest 90 passed
- 桌面应用启动正常
- 远程服务启动正常
- PyInstaller 打包成功"
```

---

## 验收标准

完成所有 Task 后，以下检查项必须全部通过：

- [ ] `pip install -e cli/` 成功
- [ ] `agentctl --help` 可用
- [ ] `python -c "from agentctl.lib.llm import load_split_env_config"` 不报错
- [ ] `python -c "from agentctl.lib.ide import IDE_REGISTRY; assert 'DeepSeek' in IDE_REGISTRY"` 通过
- [ ] `pytest -q` 全部通过（90 passed）
- [ ] `python desktop/service/config_server.py` 启动，API 可访问
- [ ] `python desktop/launcher.py` 启动，pywebview 窗口正常
- [ ] `cd desktop/frontend && npx vite build` 构建成功
- [ ] `cd server && python app.py` 远程服务启动
- [ ] `python build.py --skip-tests` 打包成功，产物可运行
- [ ] `grep -r "sys.path.insert.*SCRIPTS_DIR" cli/ desktop/ tests/ server/` 无结果
- [ ] `grep -r "^from lib\." cli/agentctl.py desktop/service/config_server.py tests/ server/` 无结果
