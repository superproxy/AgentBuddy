# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for AgentBuddy desktop app.

安全边界（关键）：
  - agents/mcp/mcp.yaml、agents/llm/llm.yaml 含真实 API Key，绝不打包进 bundle
  - agents/mcp/mcp.json、agents/skills/skill.yaml 为本地运行态，绝不打包进 bundle
  - 仅打包 *-env-example.yaml 模板；首次运行时由 config_server._ensure_*_file()
    从模板复制生成 llm.yaml / mcp.yaml（见 app.py 的 _bootstrap_from_bundle）

构建：
  python build.py                 # 推荐（含依赖检查 + 密钥泄漏扫描）
  python -m PyInstaller app.spec  # 直接调用
"""
import fnmatch
import os

block_cipher = None

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
        dirnames[:] = [d for d in dirnames if d not in ('__pycache__', '.venv', 'build', 'dist')]
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
datas += collect_dir('scripts', 'scripts')
datas += collect_dir('tools', 'tools')
datas += collect_dir('template', 'template')

# 单文件资源
for f in ('AGENTS.md', 'README.md', 'install.sh', 'install.cmd',
          'init-env.sh', 'init-env.cmd'):
    if os.path.exists(f):
        datas.append((f, '.'))

# config_server 位于 tools/，lib.* 位于 scripts/，需显式声明 + pathex
hiddenimports = [
    'config_server',
    'lib', 'lib.config_io', 'lib.llm', 'lib.mcp', 'lib.skills',
    'lib.plugins', 'lib.placeholder', 'lib.paths', 'lib.logging',
    'lib.ide', 'lib.ide.base', 'lib.ide.cursor', 'lib.ide.codex',
    'lib.ide.opencode', 'lib.ide.trae', 'lib.ide.claude',
    'lib.ide.workbuddy', 'lib.ide.qoder', 'lib.ide.openclaw',
    'lib.ide.hermes',
    'lib.ide.idea', 'lib.ide.agents',
]

a = Analysis(
    ['app.py'],
    pathex=['scripts', 'tools'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
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
    icon=str(PROJECT_ROOT / 'assets' / 'app.ico') if (PROJECT_ROOT / 'assets' / 'app.ico').exists() else None,
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
