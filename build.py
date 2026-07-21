#!/usr/bin/env python3
"""AgentBuddy 跨平台打包脚本。

在当前平台生成可分发的程序包（onedir）：
  - macOS  : dist/AgentBuddy/AgentBuddy (可进一步压成 .zip / 做成 .dmg)
  - Windows: dist/AgentBuddy/AgentBuddy.exe
  - Linux  : dist/AgentBuddy/AgentBuddy (可进一步做成 .AppImage)

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
import io
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Windows CI (cp1252) 无法编码中文，强制 stdout/stderr 用 UTF-8。
# reconfigure 在某些 CI 环境不可用或无效，需兜底用 TextIOWrapper 重新包装 buffer。
def _ensure_utf8_stream(stream):
    if stream is None:
        return None
    enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
    if enc == "utf8":
        return stream
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
        return stream
    except (AttributeError, ValueError, OSError):
        pass
    buf = getattr(stream, "buffer", None)
    if buf is not None:
        return io.TextIOWrapper(buf, encoding="utf-8", errors="replace", line_buffering=True)
    return stream

sys.stdout = _ensure_utf8_stream(sys.stdout)
sys.stderr = _ensure_utf8_stream(sys.stderr)

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
    # 本地测试插件配置（含真实密钥，仅本地使用，禁止打包）
    "Plugin.plugin.yaml",
}
# 绝不允许出现的密钥明文片段（命中即失败）
# 分两类：
#   - 前缀型（以 "-" 结尾）：如 sk-or-v1- / sk-proj-，属公开文档化的 Key 前缀，
#     源码（如 provider_catalog.py 的指纹正则）合法引用前缀本身，不能仅凭前缀判泄漏。
#     需前缀后紧跟 >=16 位真实 Key 材质 [A-Za-z0-9_-] 才算泄漏。
#   - 完整密钥型：朴素子串匹配，命中即泄漏。
SENSITIVE_TOKENS = [
    "sk-or-v1-",
    "sk-proj-",
    "ark-df9d94e1",
    "tvly-dev-",
    "mg_991eddf81b0f4dbaaaebc68bf2bfe9ba",
    "ctx7sk-",
    "uclcA910DZWGnbsYOqVSac897xgZhXyOAj4gBexX",
]

# 前缀型 token 编译为「前缀 + >=16 位 Key 材质」的正则；完整密钥型用 None 表示走朴素子串
SENSITIVE_PATTERNS: list[tuple[str, "re.Pattern[str] | None"]] = [
    (
        tok,
        re.compile(re.escape(tok) + r"[A-Za-z0-9_-]{16,}") if tok.endswith("-") else None,
    )
    for tok in SENSITIVE_TOKENS
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


def generate_icns() -> None:
    """macOS: 从 app.png 生成 app.icns（如果 .icns 不存在）。

    使用 iconutil + sips 生成多分辨率 .icns：
      1. sips 生成各尺寸 png 到 .iconset/
      2. iconutil --convert icns 生成 .icns
    """
    if sys.platform != "darwin":
        return
    icns_path = PROJECT_ROOT / "assets" / "app.icns"
    png_path = PROJECT_ROOT / "assets" / "app.png"
    if icns_path.exists():
        info(f".icns 已存在: {icns_path.relative_to(PROJECT_ROOT)}")
        return
    if not png_path.exists():
        info("assets/app.png 不存在，跳过 .icns 生成")
        return

    iconset_dir = PROJECT_ROOT / "assets" / "app.iconset"
    if iconset_dir.exists():
        shutil.rmtree(iconset_dir)
    iconset_dir.mkdir(parents=True)

    # 用 sips 生成各分辨率（macOS 内置工具）
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    for sz in sizes:
        # 普通分辨率
        r = subprocess.run(
            ["sips", "-z", str(sz), str(sz), str(png_path),
             "--out", str(iconset_dir / f"icon_{sz}x{sz}.png")],
            capture_output=True, text=True,
        )
        # @2x 高分辨率
        sz2 = sz * 2
        subprocess.run(
            ["sips", "-z", str(sz2), str(sz2), str(png_path),
             "--out", str(iconset_dir / f"icon_{sz}x{sz}@2x.png")],
            capture_output=True, text=True,
        )

    # iconutil 转 .icns
    r = subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
        capture_output=True, text=True,
    )
    shutil.rmtree(iconset_dir, ignore_errors=True)
    if r.returncode == 0 and icns_path.exists():
        info(f".icns 已生成: {icns_path.relative_to(PROJECT_ROOT)}")
    else:
        info(f"iconutil 生成 .icns 失败: {r.stderr.strip()}，使用 .ico 回退")


def run_pyinstaller(windowed: bool, version: str = "1.0.0") -> None:
    # 使用 .spec 文件时，windowed 由 spec 内的 console=False 控制，
    # 不能再传 --windowed（PyInstaller 不允许 spec + --windowed 同时使用）
    # 通过环境变量 AGENTBUDDY_VERSION 把版本号传给 app.spec（写入 Info.plist）
    cmd = [sys.executable, "-m", "PyInstaller", str(SPEC_FILE), "--noconfirm"]
    info(f"执行: {' '.join(cmd)}")
    env = os.environ.copy()
    env["AGENTBUDDY_VERSION"] = version
    rc = subprocess.call(cmd, cwd=str(PROJECT_ROOT), env=env)
    if rc != 0:
        fail(f"PyInstaller 构建失败 (exit={rc})")


def verify_bundle() -> None:
    """扫描 dist/ 产物，确认无敏感文件 / 无密钥明文。

    前缀型 token（以 "-" 结尾，如 sk-or-v1-）需后跟 >=16 位真实 Key 材质才算泄漏，
    避免 provider_catalog.py 等指纹识别代码中的合法前缀引用被误判；
    完整密钥型 token 仍走朴素子串匹配。
    """
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
        for tok, pat in SENSITIVE_PATTERNS:
            if pat is None:
                # 完整密钥型：朴素子串匹配
                if tok in text:
                    leaked_tokens.append(f"{p.relative_to(PROJECT_ROOT)} (含 {tok})")
                    break
            else:
                # 前缀型：需前缀后紧跟 >=16 位 [A-Za-z0-9_-] 真实 Key 材质
                if pat.search(text):
                    leaked_tokens.append(f"{p.relative_to(PROJECT_ROOT)} (含 {tok}...)")
                    break
    if leaked_files:
        fail("发现敏感文件被打包，构建中止:\n  " + "\n  ".join(leaked_files))
    if leaked_tokens:
        fail("发现密钥明文被打包，构建中止:\n  " + "\n  ".join(leaked_tokens))
    info("密钥泄漏扫描通过：未发现 mcp.yaml/llm.yaml/密钥明文")


def check_examples_present() -> None:
    """确认模板文件已进 bundle（运行时生成依赖它们）。"""
    base = DIST_DIR / "AgentBuddy" / "_internal"
    # PyInstaller 6.x 把数据放到 _internal/；旧版放到 exe 同级
    candidates = [
        DIST_DIR / "AgentBuddy" / "template" / "llm" / "llm-env-example.yaml",
        DIST_DIR / "AgentBuddy" / "template" / "mcp" / "mcp-env-example.yaml",
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
        app_bundle = DIST_DIR / "AgentBuddy.app"
        exe = DIST_DIR / "AgentBuddy" / "AgentBuddy"
        if app_bundle.is_dir():
            print(f"  App Bundle: {app_bundle.relative_to(PROJECT_ROOT)}")
        else:
            print(f"  产物目录: dist/AgentBuddy/")
        print(f"  可执行:  {exe.relative_to(PROJECT_ROOT)}")
        dist_files = list(INSTALLER_OUT_DIR.glob("AgentBuddy-*-*")) if INSTALLER_OUT_DIR.exists() else []
        for df in dist_files:
            print(f"  分发包:  {df.relative_to(PROJECT_ROOT)}")
        if not dist_files:
            print("  分发:    压缩 dist/AgentBuddy 为 .zip，或用 create-dmg 做 .dmg")
    elif plat == "win32":
        exe = DIST_DIR / "AgentBuddy" / "AgentBuddy.exe"
        print(f"  产物目录: dist\\AgentBuddy\\")
        print(f"  可执行:  {exe.relative_to(PROJECT_ROOT)}")
        installer = list(INSTALLER_OUT_DIR.glob("AgentBuddy-Setup-*.exe")) if INSTALLER_OUT_DIR.exists() else []
        if installer:
            print(f"  安装包:  {installer[0].relative_to(PROJECT_ROOT)}")
        else:
            print("  分发:    压缩 dist\\AgentBuddy 为 .zip，或用 Inno Setup 做 .exe 安装包")
    else:
        exe = DIST_DIR / "AgentBuddy" / "AgentBuddy"
        print(f"  产物目录: dist/AgentBuddy/")
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
    """Windows: Inno Setup -> AgentBuddy-Setup-<version>-x64.exe"""
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
    installer = INSTALLER_OUT_DIR / f"AgentBuddy-Setup-{version}-x64.exe"
    if installer.is_file():
        info(f"安装包已生成: {installer.relative_to(PROJECT_ROOT)}")
    else:
        fail(f"未找到预期的安装包输出: {installer.name}")


def _build_macos_dist(version: str) -> None:
    """macOS: 生成 .dmg（拖拽安装）+ .pkg（安装器）。

    优先打包 dist/AgentBuddy.app（BUNDLE 产出），回退到 dist/AgentBuddy/（裸目录）。
    """
    INSTALLER_OUT_DIR.mkdir(parents=True, exist_ok=True)
    app_bundle = DIST_DIR / "AgentBuddy.app"
    app_dir = DIST_DIR / "AgentBuddy"

    # 确定打包源：优先 .app，回退到裸目录
    if app_bundle.is_dir():
        pkg_source = app_bundle
        pkg_source_name = "AgentBuddy.app"
        info("打包源: AgentBuddy.app (标准 .app bundle)")
    elif app_dir.is_dir():
        pkg_source = app_dir
        pkg_source_name = "AgentBuddy"
        info("打包源: AgentBuddy/ (裸目录，无 .app bundle)")
    else:
        fail(f"找不到产物: {app_bundle} 或 {app_dir}")

    # 1. 生成 .dmg（拖拽安装）
    _build_macos_dmg(version, pkg_source)

    # 2. 生成 .pkg（安装器，自动安装到 /Applications）
    _build_macos_pkg(version, pkg_source, pkg_source_name)

    # 3. 回退：如果 .dmg 和 .pkg 都没成功，生成 .zip
    dmg_files = list(INSTALLER_OUT_DIR.glob("AgentBuddy-*-macos.dmg"))
    pkg_files = list(INSTALLER_OUT_DIR.glob("AgentBuddy-*-macos.pkg"))
    if not dmg_files and not pkg_files:
        _build_macos_zip(version, pkg_source_name)


def _build_macos_dmg(version: str, app_path: Path) -> None:
    """用 create-dmg 生成 .dmg（需要 .app bundle）。

    未签名的 .app 也能生成 .dmg，但用户打开时需右键 → 打开。
    """
    create_dmg = shutil.which("create-dmg")
    if not create_dmg:
        info("未安装 create-dmg，跳过 .dmg 生成（可 brew install create-dmg）")
        return

    dmg_name = f"AgentBuddy-{version}-macos.dmg"
    dmg_path = INSTALLER_OUT_DIR / dmg_name
    info(f"使用 create-dmg 生成 .dmg...")
    cmd = [
        create_dmg,
        "--no-internet-enable",
        "--overwrite",
        "--skip-jenkins",  # 不检查 Jenkins（CI 环境）
        "--volname", "AgentBuddy",
        "--app-drop-link", "180", "200",  # 拖拽到 Applications 的快捷方式
        "--icon", "AgentBuddy.app", "60", "200",  # .app 图标位置
        str(dmg_path),
        str(app_path.parent),  # 源目录（含 .app）
    ]
    rc = subprocess.call(cmd, cwd=str(PROJECT_ROOT))
    if rc == 0 and dmg_path.is_file():
        info(f"DMG 已生成: {dmg_path.relative_to(PROJECT_ROOT)}")
    else:
        info("create-dmg 失败，稍后尝试 .zip 回退")


def _build_macos_pkg(version: str, app_path: Path, app_name: str) -> None:
    """用 pkgbuild 生成 .pkg 安装器。

    仅在打包源是 .app 时生效（pkgbuild --component 需要 .app）。
    """
    if not app_name.endswith(".app"):
        info("打包源不是 .app bundle，跳过 .pkg 生成")
        return

    pkgbuild = shutil.which("pkgbuild")
    if not pkgbuild:
        info("未找到 pkgbuild（非 macOS 或 Xcode tools 未安装），跳过 .pkg 生成")
        return

    pkg_name = f"AgentBuddy-{version}-macos.pkg"
    pkg_path = INSTALLER_OUT_DIR / pkg_name
    info(f"使用 pkgbuild 生成 .pkg 安装器...")
    cmd = [
        pkgbuild,
        "--component", str(app_path),
        "--install-location", "/Applications",
        "--identifier", "com.agentbuddy.app",
        "--version", version,
        str(pkg_path),
    ]
    rc = subprocess.call(cmd, cwd=str(PROJECT_ROOT))
    if rc == 0 and pkg_path.is_file():
        info(f"PKG 已生成: {pkg_path.relative_to(PROJECT_ROOT)}")
    else:
        info(f"pkgbuild 失败 (exit={rc})，跳过 .pkg")


def _build_macos_zip(version: str, app_name: str) -> None:
    """回退：生成 .zip。"""
    zip_name = f"AgentBuddy-{version}-macos.zip"
    zip_path = INSTALLER_OUT_DIR / zip_name
    info(f"生成 .zip: {zip_name}")
    cmd = ["zip", "-r", "-y", str(zip_path), app_name]
    rc = subprocess.call(cmd, cwd=str(DIST_DIR))
    if rc != 0:
        fail(f"zip 打包失败 (exit={rc})")
    if zip_path.is_file():
        info(f"ZIP 已生成: {zip_path.relative_to(PROJECT_ROOT)}")
    else:
        fail(f"未找到预期的 zip 输出: {zip_name}")


def _step_timer(step_name: str):
    """步骤计时上下文管理器，结束时打印耗时。"""
    from contextlib import contextmanager
    import time

    @contextmanager
    def _timer():
        t0 = time.perf_counter()
        info(f"── {step_name} 开始 ──")
        try:
            yield
        finally:
            elapsed = time.perf_counter() - t0
            if elapsed >= 60:
                info(f"── {step_name} 完成: {elapsed/60:.1f}m ──")
            else:
                info(f"── {step_name} 完成: {elapsed:.1f}s ──")
    return _timer()


def main():
    import time
    total_t0 = time.perf_counter()

    ap = argparse.ArgumentParser(description="AgentBuddy 跨平台打包")
    ap.add_argument("--windowed", action="store_true", help="无控制台（macOS 生成 .app / Windows 无黑框）")
    ap.add_argument("--clean", action="store_true", help="构建前清理 dist/ build/")
    ap.add_argument("--no-verify", action="store_true", help="跳过密钥泄漏扫描（不推荐）")
    ap.add_argument("--no-installer", action="store_true",
                    help="跳过安装包生成（macOS: .dmg/.pkg；Windows: Inno Setup .exe）。开发迭代强烈推荐")
    ap.add_argument("--version", default="1.0.0", help="安装包版本号（默认 1.0.0）")
    args = ap.parse_args()

    info(f"平台: {sys.platform} | Python: {sys.version.split()[0]} | 版本: {args.version}")
    if args.no_installer:
        info("已启用 --no-installer：跳过 .dmg/.pkg 生成（开发迭代模式）")

    ensure_pyinstaller()
    with _step_timer("写版本号"):
        write_version(args.version)
    with _step_timer("生成 icns"):
        generate_icns()
    if args.clean:
        with _step_timer("清理 dist/build"):
            clean()
    with _step_timer("PyInstaller 打包"):
        run_pyinstaller(windowed=args.windowed, version=args.version)
    if not args.no_verify:
        with _step_timer("密钥泄漏扫描"):
            verify_bundle()
            check_examples_present()
    if not args.no_installer and sys.platform in ("win32", "darwin"):
        with _step_timer("生成安装包 .dmg/.pkg"):
            build_installer(version=args.version)

    total = time.perf_counter() - total_t0
    info(f"═══ 总耗时: {total/60:.1f}m ═══" if total >= 60 else f"═══ 总耗时: {total:.1f}s ═══")
    report()


if __name__ == "__main__":
    main()
