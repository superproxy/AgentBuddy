# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for agentctl CLI — 独立命令行工具。

与 app.spec（桌面应用）的区别：
  - 入口: cli/agentctl.py（非 desktop/launcher.py）
  - console=True（CLI 需要终端输出）
  - 不打包 Flask / pywebview / 前端（CLI 不需要）
  - 仅打包 template/（配置模板）+ cli/（agentctl 包数据）
  - 体积约 15-20MB（桌面应用 ~40MB）

安全边界（与 app.spec 一致）：
  - mcp.yaml / llm.yaml 等运行态文件绝不打包
  - 仅打包 *-template.* / *-env-example.* 模板

构建：
  python build.py --cli              # 同时构建桌面应用 + CLI
  python build.py --cli-only         # 仅构建 CLI
  python -m PyInstaller cli.spec     # 直接调用
"""
import fnmatch
import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

APP_VERSION = os.environ.get("AGENTBUDDY_VERSION", "1.0.0")

# 绝不允许进入 bundle 的文件名（与 app.spec 一致）
SENSITIVE = {
    'mcp.yaml', 'llm.yaml', 'mcp.json', 'skill.yaml',
    'env.yaml', 'env.local.yaml', '.DS_Store',
    'opencode.json', 'settings.json', 'auth.json',
    'config.toml', 'config.yaml',
    'Plugin.plugin.yaml',
}


def collect_dir(root, prefix, excludes=SENSITIVE):
    """递归收集目录，返回 PyInstaller datas 的 [(src, dest_dir), ...]。"""
    out = []
    if not os.path.isdir(root):
        return out
    for dirpath, dirnames, filenames in os.walk(root):
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
# CLI 只需要 template/（配置模板）和 cli/ 包数据（.yaml 等）
datas += collect_dir('template', 'template')
datas += collect_dir('cli', 'cli')

# agentctl 包子模块（自动收集，避免手动列举遗漏）
hiddenimports = collect_submodules('agentctl')

# CLI 不需要桌面端依赖，排除以减小体积
EXCLUDES = [
    'flask', 'flask_cors', 'werkzeug', 'jinja2', 'markupsafe',
    'pywebview', 'webview',
    'numpy', 'numpy.libs', 'PIL', 'Pillow',
    'pydantic_core', 'pydantic',
    'tkinter', '_tkinter',
    'matplotlib', 'scipy', 'pandas',
    'litellm', 'fastapi', 'uvicorn',
    'openai',  # CLI 不调用 AI 生成
    'PIL',
]

a = Analysis(
    ['cli/agentctl.py'],
    pathex=['cli'],
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
    name='agentctl',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # CLI 必须有控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # CLI 无图标
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='agentctl',
)
