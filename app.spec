# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for AgentBuddy desktop app.

安全边界（关键）：
  - agents/mcp/mcp.yaml、agents/llm/llm.yaml 含真实 API Key，绝不打包进 bundle
  - agents/mcp/mcp.json、agents/skills/skill.yaml 为本地运行态，绝不打包进 bundle
  - 仅打包 *-env-example.yaml 模板；首次运行时由 config_server._ensure_*_file()
    从模板复制生成 llm.yaml / mcp.yaml（见 desktop/launcher.py 的 _bootstrap_from_bundle）

三层分离后的目录映射：
  - cli/          -> agentctl 包（pip install -e cli/），PyInstaller 通过 import 探测收集
  - desktop/      -> 含 launcher.py（入口）+ config_server.py（Flask API）+ frontend/（Vue SPA）+ dist-ui/（构建产物）
  - template/     -> 配置模板
  - server/       -> 远程服务（marketplace + ai_generator）

构建：
  python build.py                 # 推荐（含依赖检查 + 密钥泄漏扫描）
  python -m PyInstaller app.spec  # 直接调用
"""
import fnmatch
import os
import sys
import shutil
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# ---- agentctl 包映射 ----
# PyInstaller 不理解 pyproject.toml 的 package-dir = {"agentctl" = "."} 映射，
# 它会把 cli/agentctl.py 当作 agentctl 模块（.py 文件），而非 agentctl 包（目录），
# 导致 from agentctl.lib.xxx import ... 失败（ModuleNotFoundError: No module named 'agentctl.lib'）。
# 解决：创建 build/_pkg_map/agentctl -> cli/ 符号链接，让 PyInstaller 正确识别 agentctl 为包。
_PKG_MAP = os.path.join(SPECPATH, 'build', '_pkg_map')
_AGENTCTL_LINK = os.path.join(_PKG_MAP, 'agentctl')
_CLI_SRC = os.path.join(SPECPATH, 'cli')

if not (os.path.islink(_AGENTCTL_LINK) or os.path.isdir(_AGENTCTL_LINK)):
    if os.path.exists(_PKG_MAP):
        shutil.rmtree(_PKG_MAP)
    os.makedirs(_PKG_MAP, exist_ok=True)
    if sys.platform == 'win32':
        import subprocess
        subprocess.check_call(['cmd', '/c', 'mklink', '/J', _AGENTCTL_LINK, _CLI_SRC], shell=True)
    else:
        os.symlink(_CLI_SRC, _AGENTCTL_LINK)
# 加入 sys.path，让 collect_submodules('agentctl') 能正确扫描 agentctl 包
if _PKG_MAP not in sys.path:
    sys.path.insert(0, _PKG_MAP)

# 从环境变量读取版本号（由 build.py 的 run_pyinstaller 设置）
APP_VERSION = os.environ.get("AGENTBUDDY_VERSION", "1.0.0")

# 绝不允许进入 bundle 的文件名 / glob（basename 匹配）
# 这些是运行态文件（含真实 API Key），由脚本从 *.template.* 生成
SENSITIVE = {
    'mcp.yaml', 'llm.yaml', 'mcp.json', 'skill.yaml',
    'env.yaml', 'env.local.yaml', '.DS_Store',
    # IDE 运行态配置（含真实密钥，需从对应 *.template.* 生成）
    'opencode.json',          # 模板: opencode.template.json
    'settings.json',          # claude: settings.template.json
    'auth.json',              # codex: auth.template.json
    'config.toml',            # codex: config.template.toml
    'config.yaml',            # proxy: config.template.yaml
    # 本地测试插件配置（含真实密钥，仅本地使用，禁止打包）
    'Plugin.plugin.yaml',
}


def collect_dir(root, prefix, excludes=SENSITIVE):
    """递归收集目录，返回 PyInstaller datas 的 [(src, dest_dir), ...] 二元组。

    过滤敏感文件与缓存目录，保持目录结构：root/llm/x.yaml -> prefix/llm
    """
    out = []
    if not os.path.isdir(root):
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        # 裁剪缓存目录
        dirnames[:] = [d for d in dirnames if d not in ('__pycache__', '.venv', 'build', 'dist', 'node_modules', '.vite', '.git')]
        for fn in filenames:
            if fn in excludes:
                continue
            if fnmatch.fnmatch(fn, '*.pyc') or fnmatch.fnmatch(fn, '*.log'):
                continue
            src = os.path.join(dirpath, fn)
            rel = os.path.relpath(dirpath, root)
            dest_dir = prefix if rel == '.' else prefix + '/' + rel.replace(os.sep, '/')
            out.append((src, dest_dir))
    return out


datas = []
datas += collect_dir('cli', 'cli')
# desktop/ 只打包 dist-ui（前端构建产物）+ 单文件，不打包 frontend/ 源码（85MB）和 __pycache__
datas += collect_dir('desktop/dist-ui', 'desktop/dist-ui')
datas += collect_dir('template', 'template')
datas += collect_dir('server', 'server')

# 单文件资源
for f in ('AGENTS.md', 'README.md', 'install.sh', 'install.cmd',
          'init-env.sh', 'init-env.cmd'):
    if os.path.exists(f):
        datas.append((f, '.'))

# agentctl 包（cli/）通过 _PKG_MAP 符号链接正确映射为 agentctl/ 包目录
# collect_submodules 自动收集所有子模块（agentctl.lib.*, agentctl.lib.ide.* 等）
hiddenimports = [
    'config_server',
] + collect_submodules('agentctl') + [
    # AI 生成服务
    'openai',
    'marketplace', 'marketplace.routes', 'marketplace.storage',
    'ai_generator', 'ai_generator.generator',
]

# 排除未直接使用的大依赖包，减小体积（~60MB → ~40MB）
# - numpy / PIL: openai SDK 间接依赖但 AgentBuddy 运行时不使用
# - cryptography: Flask session 加密用，但 JWT auth 不依赖（可选）
# - pydantic_core: openai SDK 间接依赖
# - pythonnet: pywebview 在 Windows 上需要 pythonnet 作为 GUI 后端，不能排除
# - Tcl/Tk: 无 GUI 需求
EXCLUDES = [
    'numpy', 'numpy.libs', 'PIL', 'Pillow',
    'pydantic_core', 'pydantic',
    'tkinter', '_tkinter',
    'matplotlib', 'scipy', 'pandas',
]

# litellm 不打包进 bundle — 运行时按需 pip install litellm[proxy]
# （打包 litellm + fastapi/uvicorn/cryptography 等依赖会使体积从 ~10MB 涨到 ~100MB）
# 用户在 LLM 网关页面点击「启动」时，后端检测 litellm 是否可用，
# 若未安装则提示运行: pip install 'litellm[proxy]'

a = Analysis(
    ['desktop/launcher.py'],
    pathex=[_PKG_MAP, 'desktop', 'server'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AgentBuddy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 无控制台（GUI 应用，pywebview 提供窗口）；Flask 日志写入 exe 目录 app.log
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=(
        os.path.join(SPECPATH, 'assets', 'app.ico')
        if os.path.isfile(os.path.join(SPECPATH, 'assets', 'app.ico'))
        else os.path.join(SPECPATH, 'assets', 'app.icns')
        if os.path.isfile(os.path.join(SPECPATH, 'assets', 'app.icns'))
        else None
    ),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AgentBuddy',
)

# macOS: 生成标准 .app bundle（BUNDLE 仅在 macOS 生效，Windows/Linux 自动忽略）
app = BUNDLE(
    coll,
    name='AgentBuddy.app',
    icon=(
        os.path.join(SPECPATH, 'assets', 'app.icns')
        if os.path.isfile(os.path.join(SPECPATH, 'assets', 'app.icns'))
        else None
    ),
    bundle_identifier='com.agentbuddy.app',
    info_plist={
        'CFBundleName': '飞翼',
        'CFBundleDisplayName': '飞翼',
        'CFBundleShortVersionString': APP_VERSION,
        'CFBundleVersion': APP_VERSION,
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.13',
    },
)
