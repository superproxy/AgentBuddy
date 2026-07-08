#!/usr/bin/env python3
"""AdeBuddy 跨平台打包脚本。

在当前平台生成可分发的程序包（onedir）：
  - macOS  : dist/AdeBuddy/AdeBuddy (可进一步压成 .zip / 做成 .dmg)
  - Windows: dist/AdeBuddy/AdeBuddy.exe
  - Linux  : dist/AdeBuddy/AdeBuddy (可进一步做成 .AppImage)

安全保证：
  - mcp.yaml / llm.yaml / mcp.json / skill.yaml 绝不打包（由 app.spec 的 Tree.excludes 过滤）
  - 构建完成后自动扫描 dist/ 产物，若发现任何敏感文件则构建失败
  - 首次运行时 app 自动从 *-env-example.yaml 生成 llm.yaml / mcp.yaml

用法：
  python build.py                 # 当前平台，onedir，保留控制台
  python build.py --windowed      # 无控制台（macOS 生成 .app，Windows 无黑框）
  python build.py --clean         # 先清理 dist/ build/
  python build.py --no-verify     # 跳过密钥泄漏扫描（不推荐）

环境要求：
  Python 3.10+
  依赖见 requirements-build.txt（pyinstaller）+ 运行时依赖（flask/pyyaml/requests/pywebview）
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Windows CI (cp1252) 无法编码中文，强制 stdout/stderr 用 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent
SPEC_FILE = PROJECT_ROOT / "app.spec"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
INSTALLER_ISS = PROJECT_ROOT / "installer.iss"
INSTALLER_OUT_DIR = DIST_DIR / "installer"

# 绝不允许出现在产物中的文件名（ basename 匹配）
# 这些是运行态文件（含真实 API Key），由脚本从 *.template.* 生成
SENSITIVE_FILES = {
    "mcp.yaml", "llm.yaml", "mcp.json", "skill.yaml",
    "env.yaml", "env.local.yaml",
    # IDE 运行态配置（含真实密钥，需从对应 *.template.* 生成）
    "opencode.json",     # 模板: opencode.template.json
    "settings.json",     # claude: settings.template.json
    "auth.json",         # codex: auth.template.json
    "config.toml",       # codex: config.template.toml
    "config.yaml",       # proxy: config.template.yaml
}
# 绝不允许出现的密钥明文片段（命中即失败）
SENSITIVE_TOKENS = [
    "sk-or-v1-",
    "sk-proj-",
    "ark-df9d94e1",
    "tvly-dev-",
    "mg_991eddf81b0f4dbaaaebc68bf2bfe9ba",
    "ctx7sk-",
    "uclcA910DZWGnbsYOqVSac897xgZhXyOAj4gBexX",
]


def info(msg: str) -> None:
    print(f"[build] {msg}")


def fail(msg: str) -> None:
    print(f"[build][ERROR] {msg}", file=sys.stderr)
    sys.exit(1)


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
        return
    except ImportError:
        pass
    info("PyInstaller 未安装，正在安装...")
    rc = subprocess.call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    if rc != 0:
        fail("安装 PyInstaller 失败，请手动执行: pip install pyinstaller")


def clean() -> None:
    for d in (DIST_DIR, BUILD_DIR):
        if d.exists():
            info(f"清理 {d.name}/")
            shutil.rmtree(d, ignore_errors=True)


def write_version(version: str) -> None:
    """构建时写入版本信息到 tools/dist-ui/version.json，供运行时 /api/version 读取。"""
    import json
    from datetime import datetime, timezone
    version_file = PROJECT_ROOT / "tools" / "dist-ui" / "version.json"
    data = {
        "version": version,
        "build_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    version_file.parent.mkdir(parents=True, exist_ok=True)
    with open(version_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    info(f"版本信息已写入: {version_file.relative_to(PROJECT_ROOT)} (v{version})")


def run_pyinstaller(windowed: bool) -> None:
    # 使用 .spec 文件时，windowed 由 spec 内的 console=False 控制，
    # 不能再传 --windowed（PyInstaller 不允许 spec + --windowed 同时使用）
    cmd = [sys.executable, "-m", "PyInstaller", str(SPEC_FILE), "--noconfirm"]
    info(f"执行: {' '.join(cmd)}")
    rc = subprocess.call(cmd, cwd=str(PROJECT_ROOT))
    if rc != 0:
        fail(f"PyInstaller 构建失败 (exit={rc})")


def verify_bundle() -> None:
    """扫描 dist/ 产物，确认无敏感文件 / 无密钥明文。"""
    if not DIST_DIR.exists():
        fail("dist/ 不存在，构建未产出")
    leaked_files = []
    leaked_tokens = []
    for p in DIST_DIR.rglob("*"):
        if not p.is_file():
            continue
        if p.name in SENSITIVE_FILES:
            leaked_files.append(str(p.relative_to(PROJECT_ROOT)))
            continue
        # 仅扫描小文本文件，避免二进制误报与性能问题
        if p.stat().st_size > 2 * 1024 * 1024:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for tok in SENSITIVE_TOKENS:
            if tok in text:
                leaked_tokens.append(f"{p.relative_to(PROJECT_ROOT)} (含 {tok})")
                break
    if leaked_files:
        fail("发现敏感文件被打包，构建中止:\n  " + "\n  ".join(leaked_files))
    if leaked_tokens:
        fail("发现密钥明文被打包，构建中止:\n  " + "\n  ".join(leaked_tokens))
    info("密钥泄漏扫描通过：未发现 mcp.yaml/llm.yaml/密钥明文")


def check_examples_present() -> None:
    """确认模板文件已进 bundle（运行时生成依赖它们）。"""
    base = DIST_DIR / "AdeBuddy" / "_internal"
    # PyInstaller 6.x 把数据放到 _internal/；旧版放到 exe 同级
    candidates = [
        DIST_DIR / "AdeBuddy" / "template" / "llm" / "llm-env-example.yaml",
        DIST_DIR / "AdeBuddy" / "template" / "mcp" / "mcp-env-example.yaml",
        base / "template" / "llm" / "llm-env-example.yaml",
        base / "template" / "mcp" / "mcp-env-example.yaml",
    ]
    found = [c for c in candidates if c.exists()]
    if not found:
        fail("未在产物中找到 *-env-example.yaml，运行时无法生成配置")
    info(f"模板已就位: {found[0].relative_to(PROJECT_ROOT)}")


def report() -> None:
    print("\n========================================")
    print("  Build Complete")
    print("========================================")
    plat = sys.platform
    if plat == "darwin":
        exe = DIST_DIR / "AdeBuddy" / "AdeBuddy"
        print(f"  产物目录: dist/AdeBuddy/")
        print(f"  可执行:  {exe.relative_to(PROJECT_ROOT)}")
        dist_pkg = list(INSTALLER_OUT_DIR.glob("AdeBuddy-*-*.*")) if INSTALLER_OUT_DIR.exists() else []
        if dist_pkg:
            print(f"  分发包:  {dist_pkg[0].relative_to(PROJECT_ROOT)}")
        else:
            print("  分发:    压缩 dist/AdeBuddy 为 .zip，或用 create-dmg 做 .dmg")
    elif plat == "win32":
        exe = DIST_DIR / "AdeBuddy" / "AdeBuddy.exe"
        print(f"  产物目录: dist\\AdeBuddy\\")
        print(f"  可执行:  {exe.relative_to(PROJECT_ROOT)}")
        installer = list(INSTALLER_OUT_DIR.glob("AdeBuddy-Setup-*.exe")) if INSTALLER_OUT_DIR.exists() else []
        if installer:
            print(f"  安装包:  {installer[0].relative_to(PROJECT_ROOT)}")
        else:
            print("  分发:    压缩 dist\\AdeBuddy 为 .zip，或用 Inno Setup 做 .exe 安装包")
    else:
        exe = DIST_DIR / "AdeBuddy" / "AdeBuddy"
        print(f"  产物目录: dist/AdeBuddy/")
        print(f"  可执行:  {exe.relative_to(PROJECT_ROOT)}")
        print("  分发:    压缩为 .tar.gz，或用 appimagetool 做 .AppImage")
    print("\n  首次运行会自动从模板生成 config/llm/llm.yaml 与 config/mcp/mcp.yaml")
    print("  用户在 UI 中填入真实 API Key 即可。\n")


def find_iscc() -> str | None:
    """查找 Inno Setup 编译器 ISCC.exe。返回路径或 None。"""
    # 1) PATH
    from shutil import which
    p = which("ISCC") or which("ISCC.exe")
    if p:
        return p
    # 2) 默认安装路径
    candidates = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe",
    ]
    import os
    for c in candidates:
        expanded = os.path.expandvars(c)
        if Path(expanded).is_file():
            return expanded
    return None


def build_installer(version: str = "1.0.0") -> None:
    """生成平台安装包。
    - Windows: 调用 Inno Setup 编译 installer.iss 生成 .exe 安装包
    - macOS:   优先用 create-dmg 生成 .dmg，回退到 .zip
    """
    if sys.platform == "win32":
        _build_windows_installer(version)
    elif sys.platform == "darwin":
        _build_macos_dist(version)


def _build_windows_installer(version: str) -> None:
    """Windows: Inno Setup -> AdeBuddy-Setup-<version>-x64.exe"""
    if not INSTALLER_ISS.is_file():
        fail(f"找不到 {INSTALLER_ISS.name}")
    iscc = find_iscc()
    if not iscc:
        info("未找到 Inno Setup (ISCC.exe)，跳过安装包生成")
        info("  安装 Inno Setup 6: https://jrsoftware.org/isdl.php")
        return
    INSTALLER_OUT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [iscc, f"/DAPP_VERSION={version}", str(INSTALLER_ISS)]
    info(f"执行: {' '.join(cmd)}")
    rc = subprocess.call(cmd, cwd=str(PROJECT_ROOT))
    if rc != 0:
        fail(f"Inno Setup 编译失败 (exit={rc})")
    installer = INSTALLER_OUT_DIR / f"AdeBuddy-Setup-{version}-x64.exe"
    if installer.is_file():
        info(f"安装包已生成: {installer.relative_to(PROJECT_ROOT)}")
    else:
        fail(f"未找到预期的安装包输出: {installer.name}")


def _build_macos_dist(version: str) -> None:
    """macOS: 优先 create-dmg 生成 .dmg，回退到 .zip"""
    INSTALLER_OUT_DIR.mkdir(parents=True, exist_ok=True)
    app_dir = DIST_DIR / "AdeBuddy"
    if not app_dir.is_dir():
        fail(f"找不到产物目录: {app_dir}")

    # 尝试用 create-dmg 生成 .dmg
    create_dmg = shutil.which("create-dmg")
    if create_dmg:
        dmg_name = f"AdeBuddy-{version}-macos.dmg"
        dmg_path = INSTALLER_OUT_DIR / dmg_name
        info(f"使用 create-dmg 生成 .dmg...")
        # --no-internet-enable: 不添加 Internet Enable 属性
        # --overwrite: 覆盖已有 dmg
        cmd = [
            create_dmg,
            "--no-internet-enable",
            "--overwrite",
            "--app-name", "AdeBuddy",
            str(dmg_path),
            str(app_dir),
        ]
        rc = subprocess.call(cmd, cwd=str(PROJECT_ROOT))
        if rc == 0 and dmg_path.is_file():
            info(f"DMG 已生成: {dmg_path.relative_to(PROJECT_ROOT)}")
            return
        else:
            info("create-dmg 失败，回退到 .zip")

    # 回退：生成 .zip
    zip_name = f"AdeBuddy-{version}-macos.zip"
    zip_path = INSTALLER_OUT_DIR / zip_name
    info(f"生成 .zip: {zip_name}")
    cmd = ["zip", "-r", "-y", str(zip_path), "AdeBuddy"]
    rc = subprocess.call(cmd, cwd=str(DIST_DIR))
    if rc != 0:
        fail(f"zip 打包失败 (exit={rc})")
    if zip_path.is_file():
        info(f"ZIP 已生成: {zip_path.relative_to(PROJECT_ROOT)}")
    else:
        fail(f"未找到预期的 zip 输出: {zip_name}")


def main():
    ap = argparse.ArgumentParser(description="AdeBuddy 跨平台打包")
    ap.add_argument("--windowed", action="store_true", help="无控制台（macOS 生成 .app / Windows 无黑框）")
    ap.add_argument("--clean", action="store_true", help="构建前清理 dist/ build/")
    ap.add_argument("--no-verify", action="store_true", help="跳过密钥泄漏扫描（不推荐）")
    ap.add_argument("--no-installer", action="store_true", help="跳过 Inno Setup 安装包生成（仅 Windows）")
    ap.add_argument("--version", default="1.0.0", help="安装包版本号（默认 1.0.0）")
    args = ap.parse_args()

    info(f"平台: {sys.platform} | Python: {sys.version.split()[0]} | 版本: {args.version}")
    ensure_pyinstaller()
    write_version(args.version)
    if args.clean:
        clean()
    run_pyinstaller(windowed=args.windowed)
    if not args.no_verify:
        verify_bundle()
        check_examples_present()
    if not args.no_installer and sys.platform in ("win32", "darwin"):
        build_installer(version=args.version)
    report()


if __name__ == "__main__":
    main()
