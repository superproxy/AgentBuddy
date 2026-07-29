# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MyAgentPlugin 配置工具 (pywebview 桌面版)。
构建：pyinstaller MyAgentConfig.spec
输出：dist/MyAgentConfig/MyAgentConfig.exe (onedir)
"""
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# 收集 pywebview / flask 等动态依赖
hiddenimports = [
    # pywebview Windows 后端
    'webview',
    'webview.platforms.edgechromium',
    'webview.platforms.winforms',
    'clr_loader',
    'pythonnet',
    # flask / jinja2
    'flask',
    'jinja2',
    'markupsafe',
    # yaml / requests
    'yaml',
    'requests',
    'urllib3',
    'certifi',
    'charset_normalizer',
    'idna',
    # 项目内部脚本（importlib 加载，需显式声明）
    'scripts',
    # config_server 由 app.py 通过 sys.path 动态 import，需显式声明
    'config_server',
]
hiddenimports += collect_submodules('webview')
hiddenimports += collect_submodules('flask')

# 数据文件：(源, 目标目录) —— 相对 spec 文件所在的项目根
datas = []
# macOS 下 PyInstaller hook-certifi 偶发不打包 cacert.pem，
# 导致 frozen 应用 HTTPS 请求报 CERTIFICATE_VERIFY_FAILED。
# 显式收集 certifi 数据文件作为兜底。
datas += collect_data_files('certifi')

datas += [
    ('tools/config_ui.html', 'tools'),
    ('scripts/init-env.py', 'scripts'),
    ('scripts/init-ide.py', 'scripts'),
    ('scripts/plugin-manager.py', 'scripts'),
    ('scripts/cleanup.py', 'scripts'),
    ('agents/mcp/mcp.template.json', 'agents/mcp'),
    ('agents/plugins', 'agents/plugins'),
    ('agents/rules', 'agents/rules'),
    ('agents/commands', 'agents/commands'),
    ('agents/system-prompts', 'agents/system-prompts'),
    ('ide', 'ide'),
    ('llm-template.yaml', '.'),
    ('mcp-template.yaml', '.'),
    ('AGENTS.md', '.'),
    # skills 目录较大，单独打包；如有 skills-mapping.csv 也含进 plugins
]

# agents/skills 可选打包（体积大，按需启用）
import os
_skills_dir = 'agents/skills'
if os.path.isdir(_skills_dir):
    datas.append((_skills_dir, 'agents/skills'))

a = Analysis(
    ['app.py'],
    pathex=['.', 'tools'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大模块以减小体积
        'matplotlib', 'numpy', 'pandas', 'scipy', 'PIL', 'tkinter',
        'pytest', 'IPython', 'jupyter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MyAgentConfig',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # UPX 压缩减体积（需系统已装 upx，未装时 PyInstaller 会跳过）
    console=False,  # 发布模式：隐藏控制台（调试时改 True 查看日志）
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app.ico' if __import__('os').path.exists('assets/app.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MyAgentConfig',
)
