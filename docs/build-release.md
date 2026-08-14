# AgentBuddy — 构建、发布与运维

## 发布流程（Release）
- **触发机制**：打 git tag `v<version>` 并推送 origin → GitHub Actions 自动构建 macOS + Windows 并发布 Release
- **版本号单一来源**：项目无 version.txt / CHANGELOG，版本号仅由 git tag 维护
- **前置条件**：工作区必须干净（`git diff --quiet` 无变更），否则先提交
- **版本号判定**（语义化版本，基于自上个 tag 以来的提交性质）：

  | 提交性质 | 版本动作 | 示例 |
  |---|---|---|
  | `fix:` 修复 | patch +1 | v1.2.2 → v1.2.3 |
  | `feat:` 新功能 / 能力增强 | minor +1 | v1.2.2 → v1.3.0 |
  | 不兼容变更 | major +1 | v1.2.2 → v2.0.0 |

- **标准流程**：
  1. `git log <last-tag>..HEAD --oneline` 核对自上个 tag 以来的提交
  2. 按上表判定版本号（**版本号属大决策，需用户确认**）
  3. `git tag -a v<x.y.z> -m "Release v<x.y.z>"`（带注解 tag，附变更摘要）
  4. `git push origin v<x.y.z>` 推送触发 Actions
  5. 仓库 Actions 页面查看构建进度
- **工具**：`release.cmd [version] [-p]` 封装了上述流程（交互式确认 / 自动 patch +1 推断 / `-p` 跳过确认）
- **注意**：打 tag 推送不可逆且对外发布，推送前务必确认版本号与 tag 注解内容

## 安装更新（升级覆盖）
升级时**保留用户数据，替换程序资源**——两侧自动成立，无需额外操作。

### 保留 vs 替换矩阵
| 目录/文件 | 升级时 | 机制 |
|---|---|---|
| `config/`（llm.yaml/mcp.yaml/ide 配置/含密钥） | **保留** | 不在安装包 `dist\AgentBuddy\` 内，安装器不触及；bootstrap `resources` 列表不含它 |
| `.agents/`（技能/插件安装目标） | **保留** | 同上，不在安装包内 |
| `AgentBuddy.exe` + `_internal/` | **替换** | 安装器 `ignoreversion recursesubdirs` 覆盖到 `{app}` |
| `cli/` `template/` `desktop/` `AGENTS.md` | **替换** | bootstrap 每次启动从 `_internal/` 覆盖到顶层（`dirs_exist_ok=True`） |
| `app.log` `.bundle_bootstrapped` | 替换/清理 | `[UninstallDelete]` 卸载时清理 |

### Windows（Inno Setup）
- **安装器**：`installer.iss`，产物 `AgentBuddy-Setup-<version>-x64.exe`
- **升级方式**：装新版本时，若 Inno 提示"已检测到旧版本，是否替换"，**选择替换**
  - 原理：`AppName=AgentBuddy` 固定、`DefaultDirName={autopf}\AgentBuddy` 固定路径，识别为同名升级
  - `[Files]` 用 `ignoreversion recursesubdirs`，把 `dist\AgentBuddy\*`（仅 exe + `_internal/`）覆盖到 `{app}`；`config/`、`.agents/` 不在包内，自然保留
  - `[UninstallDelete]` 仅清 `app.log` 与 `.bundle_bootstrapped`，**不删 `config/`、`.agents/`**
- **不要做的**：不要卸载后重装（权限/路径漂移）；不要装到并行目录（产生重复卸载项）

### macOS（dmg 目录覆盖）
- **产物**：`AgentBuddy-<version>-macos.dmg`（`create-dmg` 生成，失败回退 `.zip`）
- **升级**：挂载 `.dmg` → 将 `AgentBuddy/` 目录拖入 `/Applications` 覆盖旧版（普通目录覆盖，非 .app 包覆盖）
- **配置保留**：`config/` 和 `.agents/` 在 `AgentBuddy/` 目录内，dmg 里不含这俩目录，拖拽覆盖不删除已存在文件
- **Gatekeeper**：首次启动若被拦截，右键 → 打开 → 确认（未签名时的标准处理）

### Bootstrap 覆盖机制（desktop/launcher.py `_bootstrap_from_bundle`）
- frozen 模式每次启动，从 `_MEIPASS`（=`_internal/`）把 `cli/`、`template/`、`desktop/`、`AGENTS.md` 覆盖到 exe 所在目录（`dirs_exist_ok=True`）
- 保证升级后顶层程序资源与 bundle 一致；`config/`、`.agents/` 不在 `resources` 列表，始终保留
- `.bundle_bootstrapped` 写 `"1"` 仅作诊断标记，不读回、不参与版本比较

## Windows 批处理脚本规范
- **行尾必须 CRLF**：`.cmd` / `.bat` 用 LF 行尾会导致 `if (...)` 多行块报"命令语法不正确"；由 `.gitattributes` 强制 `*.cmd` / `*.bat` `text eol=crlf`
- **注释用纯英文**：REM 注释行内的 UTF-8 中文字节，在 `chcp 65001` 切换前的解析阶段会与代码页不匹配，导致 REM 关键字识别错位、行内 `#` 被当命令执行（曾命中系统 `patch.exe` 报 `strip count '#' is not a number`）；批处理脚本注释一律用英文，中文输出放 `echo` 里（`chcp 65001` 后输出正常）
- **`#` 字符危险**：REM 行内出现 `#` 时风险最高；`::` 注释对 `#` 更稳健但 `::` 不能用在 `if (...)` 块内（会被当标签出错）；最稳妥是注释不含 `#` 且用英文
- **测试方式**：改完 `.cmd` 用 `cmd.exe //c "script.cmd args"` 验证，勿只在 PowerShell/MSYS 里跑
