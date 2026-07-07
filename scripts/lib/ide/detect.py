"""IDE 检测模块。

通过 shutil.which + 已知安装路径，探测本机已安装的 AI 编程 IDE。
返回每个 IDE 的 key/label/installed/exe_path/version/config_paths/sessions_dir。

支持检测的 IDE（与 IDE_REGISTRY 对齐）：
- Claude Code（claude CLI）
- Codex（codex CLI）
- Cursor（cursor 命令 + macOS .app + Windows exe）
- Trae / Trae CN / Trae Work CN（macOS .app + CLI + Windows exe）
- OpenCode（opencode CLI）
- Qoder（macOS .app + CLI + Windows exe）
- OpenClaw（openclaw CLI）
- WorkBuddy（workbuddy CLI）
- ZCode（智谱 ADE，zcode CLI + macOS .app）
- IDEA（idea 命令 + Toolbox + Windows exe）
- Agents（通用，无独立 CLI，按配置目录存在判断）
- Kimi Code（kimi CLI，非 IDE_REGISTRY 成员但作为扩展检测）

Windows 探测说明：
- CLI：shutil.which 返回的可能是 .CMD/.BAT 包装脚本（npm 全局安装的典型情况），
  会尝试解析出同目录或邻近的真实 .exe 作为 exe_path
- App：通过 windows_apps 路径列表探测 GUI 可执行文件（Program Files / LOCALAPPDATA 等）
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path


# ===== IDE 元数据注册表 =====
# 每个 IDE 定义：
#   cli_names：CLI 命令名列表（按优先级，shutil.which 探测）
#   macos_apps：macOS .app 路径列表
#   windows_apps：Windows GUI exe 路径列表（支持 {ProgramFiles} {ProgramFiles(x86)} {LOCALAPPDATA} {APPDATA} 占位）
#   config_dirs：配置目录列表（相对 Path.home()）
#   sessions_subdir：会话子目录名
#   is_tui：CLI 是否为交互式 TUI 应用，需 TTY 才能显示界面
#   cli_to_exe_resolver：可选，自定义从 .CMD/.BAT 路径解析真实 .exe 的函数名
IDE_DETECT_META = {
    "Claude": {
        "label": "Claude Code",
        "cli_names": ["claude"],
        "macos_apps": [],
        "windows_apps": [],
        "config_dirs": [".claude"],
        "sessions_subdir": "projects",  # Claude 会话按项目哈希存于 projects/
        "is_tui": True,
    },
    "Codex": {
        "label": "Codex",
        "cli_names": ["codex"],
        "macos_apps": [],
        "windows_apps": [],
        "config_dirs": [".codex"],
        "sessions_subdir": "sessions",
        "is_tui": True,
    },
    "Cursor": {
        "label": "Cursor",
        "cli_names": ["cursor"],
        "macos_apps": [
            "/Applications/Cursor.app",
        ],
        "windows_apps": [
            "{LOCALAPPDATA}/Programs/cursor/Cursor.exe",
            "{ProgramFiles}/Cursor/Cursor.exe",
            "{ProgramFiles(x86)}/Cursor/Cursor.exe",
        ],
        "config_dirs": [".cursor"],
        "sessions_subdir": "projects",
        "is_tui": False,
    },
    "Trae": {
        "label": "Trae",
        "cli_names": ["trae", "trae-cli", "traecli"],
        "macos_apps": ["/Applications/Trae.app"],
        "windows_apps": [
            "{LOCALAPPDATA}/Programs/Trae/Trae.exe",
            "{LOCALAPPDATA}/trae-cli/bin/trae-cli.exe",
            "{ProgramFiles}/Trae/Trae.exe",
        ],
        "config_dirs": [".trae"],
        "sessions_subdir": "sessions",
        "is_tui": False,
    },
    "TraeCN": {
        "label": "Trae CN",
        "cli_names": ["trae-cn"],
        "macos_apps": ["/Applications/Trae CN.app"],
        "windows_apps": [
            "{LOCALAPPDATA}/Programs/Trae CN/Trae CN.exe",
            "{LOCALAPPDATA}/Programs/Trae CN/Trae.exe",
            "{ProgramFiles}/Trae CN/Trae CN.exe",
        ],
        "config_dirs": [".trae-cn", ".traecn"],
        "sessions_subdir": "sessions",
        "is_tui": False,
    },
    "TraeSoloCN": {
        "label": "Trae Work CN",
        "cli_names": ["trae-solo-cn"],
        "macos_apps": ["/Applications/Trae Solo CN.app"],
        "windows_apps": [
            "{LOCALAPPDATA}/Programs/Trae Solo CN/Trae Solo CN.exe",
            "{ProgramFiles}/Trae Solo CN/Trae Solo CN.exe",
        ],
        "config_dirs": [".trae-solo-cn", ".traesolocn"],
        "sessions_subdir": "sessions",
        "is_tui": False,
    },
    "OpenCode": {
        "label": "OpenCode",
        "cli_names": ["opencode"],
        "macos_apps": [],
        "windows_apps": [],
        "config_dirs": [".config/opencode", ".opencode"],
        "sessions_subdir": "sessions",
        "is_tui": True,
    },
    "Qoder": {
        "label": "Qoder",
        "cli_names": ["qoder"],
        "macos_apps": ["/Applications/Qoder.app"],
        "windows_apps": [
            "{LOCALAPPDATA}/Programs/Qoder/Qoder.exe",
            "{ProgramFiles}/Qoder/Qoder.exe",
        ],
        "config_dirs": [".qoder"],
        "sessions_subdir": "sessions",
        "is_tui": True,
    },
    "QoderCN": {
        "label": "Qoder CN",
        "cli_names": ["qoder-cn"],
        "macos_apps": ["/Applications/Qoder CN.app", "/Applications/Qoder中国版.app"],
        "windows_apps": [
            "{LOCALAPPDATA}/Programs/Qoder CN/Qoder CN.exe",
            "{ProgramFiles}/Qoder CN/Qoder CN.exe",
        ],
        "config_dirs": [".qoder-cn", ".qodercn"],
        "sessions_subdir": "sessions",
        "is_tui": True,
    },
    "OpenClaw": {
        "label": "OpenClaw",
        "cli_names": ["openclaw"],
        "macos_apps": [],
        "windows_apps": [],
        "config_dirs": [".openclaw"],
        "sessions_subdir": "sessions",
        "is_tui": True,
    },
    "WorkBuddy": {
        "label": "WorkBuddy",
        "cli_names": ["workbuddy"],
        "macos_apps": [],
        "windows_apps": [],
        "config_dirs": [".workbuddy"],
        "sessions_subdir": "sessions",
        "is_tui": True,
    },
    "IDEA": {
        "label": "IDEA",
        "cli_names": ["idea", "idea64"],
        "macos_apps": [
            "/Applications/IntelliJ IDEA.app",
            "/Applications/IntelliJ IDEA CE.app",
        ],
        "windows_apps": [
            # Toolbox 安装：{LOCALAPPDATA}/JetBrains/Toolbox/apps/IDEA-C/ch-0/<version>/bin/idea64.exe
            # 直接安装：{ProgramFiles}/JetBrains/IntelliJ IDEA <version>/bin/idea64.exe
            # 用 glob 模式，下面 _resolve_windows_app 会展开
            "{LOCALAPPDATA}/JetBrains/Toolbox/apps/IDEA-C/ch-0/*/bin/idea64.exe",
            "{LOCALAPPDATA}/JetBrains/Toolbox/apps/IDEA-U/ch-0/*/bin/idea64.exe",
            "{ProgramFiles}/JetBrains/IntelliJ IDEA*/bin/idea64.exe",
            "{ProgramFiles(x86)}/JetBrains/IntelliJ IDEA*/bin/idea64.exe",
            "D:/Program Files/JetBrains/IntelliJ IDEA*/bin/idea64.exe",
        ],
        "config_dirs": [".idea", ".jetbrains"],
        "sessions_subdir": None,  # IDEA 无 CLI 会话概念
        "is_tui": False,
    },
    "Agents": {
        "label": "Agents",
        "cli_names": [],
        "macos_apps": [],
        "windows_apps": [],
        "config_dirs": ["./config/skills"],
        "sessions_subdir": None,
        "is_tui": False,
    },
    # 扩展：Kimi Code（非 IDE_REGISTRY 成员，作为 CLI 伙伴工具检测）
    "KimiCode": {
        "label": "Kimi Code",
        "cli_names": ["kimi", "kimi-code"],
        "macos_apps": [],
        "windows_apps": [],
        "config_dirs": [".kimi-code"],
        "sessions_subdir": "sessions",
        "is_tui": True,
    },
    # 智谱 ZCode ADE（Agent Development Environment）
    "ZCode": {
        "label": "ZCode",
        "cli_names": ["zcode"],
        "macos_apps": ["/Applications/ZCode.app"],
        "windows_apps": [
            "{LOCALAPPDATA}/Programs/ZCode/ZCode.exe",
            "{ProgramFiles}/ZCode/ZCode.exe",
        ],
        "config_dirs": [".zcode"],
        "sessions_subdir": "sessions",
        "is_tui": True,
    },
}


def _which(cli_name: str) -> str | None:
    """shutil.which 封装，返回绝对路径或 None。"""
    return shutil.which(cli_name)


def _resolve_cmd_wrapper_to_exe(cmd_path: str) -> str:
    """Windows 下把 .CMD/.BAT 包装脚本路径解析为真实 .exe。

    npm 全局安装的 CLI（如 claude/codex/opencode）会在 npm 目录生成 .CMD 包装，
    真实 .exe 通常在 node_modules/<package>/bin/ 或同目录。
    Cursor/Trae 的 .CMD 在 resources/app/bin/，真实 exe 在上级目录。

    若找不到对应 .exe，返回原 .CMD 路径（保持向后兼容）。
    返回的路径会校正为磁盘上真实的文件名大小写（Windows 文件系统大小写不敏感，
    但 Path.exists 对小写路径也返回 True，需遍历目录取真实名）。
    """
    p = Path(cmd_path)
    # 仅处理 Windows 下的 .CMD/.BAT
    if sys.platform != "win32" or p.suffix.lower() not in (".cmd", ".bat"):
        return cmd_path

    name = p.stem.lower()  # 如 "cursor"
    # 1. 同目录下的 <name>.exe
    same_dir = p.with_name(f"{p.stem}.exe")
    if same_dir.exists():
        return _realpath_case(str(same_dir))

    # 2. 上级目录（cursor.CMD 在 resources/app/bin/，exe 在程序根目录）
    #    逐级向上找 <name>.exe，最多 4 层
    parent = p.parent
    for _ in range(4):
        candidate = parent / f"{p.stem}.exe"
        if candidate.exists():
            return _realpath_case(str(candidate))
        # 也试小写名（如 cursor.exe 而非 Cursor.exe）
        candidate_lower = parent / f"{name}.exe"
        if candidate_lower.exists():
            return _realpath_case(str(candidate_lower))
        if parent.parent == parent:
            break
        parent = parent.parent

    # 3. IDEA 特例：idea.BAT 同目录有 idea64.exe
    idea64 = p.with_name("idea64.exe")
    if idea64.exists():
        return _realpath_case(str(idea64))

    return cmd_path  # 找不到真实 exe，返回原路径


def _realpath_case(path: str) -> str:
    """校正 Windows 路径的大小写为磁盘上真实的文件名大小写。

    Windows 文件系统大小写不敏感，Path.exists 对小写路径也返回 True，
    但展示给用户时希望用真实大小写（如 Cursor.exe 而非 cursor.exe）。
    """
    if sys.platform != "win32":
        return path
    p = Path(path)
    if not p.exists():
        return path
    # 逐级解析真实大小写
    parts = []
    cur = p
    # 从父目录向下收集真实文件名
    anchors = []
    while cur != cur.parent:
        anchors.append(cur.name)
        cur = cur.parent
    # cur 现在是根目录（如 C:\）
    real = cur
    for name in reversed(anchors):
        try:
            # 在 real 下找匹配 name（大小写不敏感）的真实条目
            for child in real.iterdir():
                if child.name.lower() == name.lower():
                    real = child
                    break
            else:
                # 没找到匹配，保留原名继续
                real = real / name
        except (PermissionError, OSError):
            real = real / name
    return str(real)


def _expand_windows_path(template: str) -> Path:
    """展开 Windows 路径模板中的环境变量占位符。"""
    env_map = {
        "{ProgramFiles}": os.environ.get("ProgramFiles", r"C:\Program Files"),
        "{ProgramFiles(x86)}": os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        "{LOCALAPPDATA}": os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")),
        "{APPDATA}": os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")),
    }
    result = template
    for k, v in env_map.items():
        result = result.replace(k, v)
    return Path(result)


def _check_windows_app(app_template: str) -> str:
    """检查 Windows GUI exe 是否存在，支持 glob 模式（如 IDEA 多版本目录）。

    返回找到的第一个匹配路径（字符串），未找到返回空串。
    """
    if sys.platform != "win32":
        return ""
    p = _expand_windows_path(app_template)
    # 支持 glob（含 * 或 ?）
    if "*" in p.name or "?" in p.name:
        # 在父目录下查找匹配的文件
        parent = p.parent
        if not parent.exists():
            return ""
        import fnmatch
        try:
            for child in sorted(parent.iterdir(), reverse=True):
                if child.is_file() and fnmatch.fnmatch(child.name, p.name):
                    return str(child)
        except (PermissionError, OSError):
            pass
        return ""
    # 也支持目录名含 glob（如 IntelliJ IDEA*/bin/idea64.exe）
    if "*" in str(p) or "?" in str(p):
        import glob
        matches = sorted(glob.glob(str(p)), reverse=True)
        return matches[0] if matches else ""
    return str(p) if p.exists() else ""


def _check_macos_app(app_path: str) -> bool:
    """检查 macOS .app 是否存在。"""
    return sys.platform == "darwin" and Path(app_path).exists()


# ===== Windows 注册表 + 开始菜单快捷方式兜底探测 =====
# 当 windows_apps 路径列表探测失败时，回退到系统卸载注册表和开始菜单快捷方式，
# 这能识别用户安装在非默认路径、或厂商改名的 IDE（如 OpenCode 桌面版安装在
# @opencode-aidesktop 目录、Trae Work CN 注册名为 "TRAE Work CN" 等）。
_REGISTRY_CACHE: list[dict] | None = None
_STARTMENU_CACHE: dict[str, str] | None = None


def _normalize_id(s: str) -> str:
    """规范化 IDE 标识用于匹配：去空格/标点，转小写。

    例："Trae CN" -> "traecn", "TRAE Work CN (User)" -> "traeworkcnuser",
        "IntelliJ IDEA 2026.1.3" -> "intellijidea202613"
    """
    import re
    return re.sub(r"[\s\(\)\.\-_]", "", s).lower()


def _scan_registry_uninstall() -> list[dict]:
    """扫描 Windows 卸载注册表，返回 [{name, icon, location, version}] 列表（带缓存）。

    覆盖 HKLM 64/32 位和 HKCU 三个根，能识别 user-scope 安装的 IDE。
    version 来自 DisplayVersion 字段，用于 GUI 应用版本号展示（不调用 CLI）。
    """
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None:
        return _REGISTRY_CACHE
    if sys.platform != "win32":
        _REGISTRY_CACHE = []
        return _REGISTRY_CACHE
    import winreg
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    entries = []
    for root, subkey in roots:
        try:
            with winreg.OpenKey(root, subkey) as key:
                index = 0
                while True:
                    try:
                        subname = winreg.EnumKey(key, index)
                        index += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(key, subname) as sk:
                            name = winreg.QueryValueEx(sk, "DisplayName")[0]
                            icon = ""
                            try:
                                icon = winreg.QueryValueEx(sk, "DisplayIcon")[0]
                            except FileNotFoundError:
                                pass
                            location = ""
                            try:
                                location = winreg.QueryValueEx(sk, "InstallLocation")[0]
                            except FileNotFoundError:
                                pass
                            version = ""
                            try:
                                version = winreg.QueryValueEx(sk, "DisplayVersion")[0]
                            except FileNotFoundError:
                                pass
                            if name:
                                entries.append({
                                    "name": str(name),
                                    "icon": str(icon).split(",")[0].strip('"').strip(),
                                    "location": str(location).strip('"').strip(),
                                    "version": str(version).strip(),
                                })
                    except FileNotFoundError:
                        continue
        except FileNotFoundError:
            continue
    _REGISTRY_CACHE = entries
    return entries


def _scan_start_menu_shortcuts() -> dict[str, str]:
    """扫描开始菜单 .lnk 快捷方式，返回 {name_stem: target_path}（带缓存）。

    覆盖 user 和 all-users 两个 Start Menu\Programs 目录。
    多线程环境下 pywin32 COM 需要每线程 CoInitialize（detect_all 用线程池）。
    """
    global _STARTMENU_CACHE
    if _STARTMENU_CACHE is not None:
        return _STARTMENU_CACHE
    if sys.platform != "win32":
        _STARTMENU_CACHE = {}
        return _STARTMENU_CACHE
    result: dict[str, str] = {}
    paths = [
        os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(os.environ.get("ProgramData", r"C:\Program Data"), "Microsoft", "Windows", "Start Menu", "Programs"),
    ]
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except ImportError:
        pass
    try:
        import win32com.client  # pywin32
        shell = win32com.client.Dispatch("WScript.Shell")
    except ImportError:
        # pywin32 不可用时退回powershell方案（一次性、不缓存）
        try:
            import subprocess as _sp
            cmd = (
                "$paths=@('"
                + "','".join(paths)
                + "'); foreach($p in $paths){ if(Test-Path $p){"
                "Get-ChildItem -Path $p -Recurse -Filter *.lnk -ErrorAction SilentlyContinue | ForEach-Object {"
                "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($_.FullName);"
                "Write-Output ($_.BaseName+'|'+$s.TargetPath)}}}"
            )
            r = _sp.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True, text=True, timeout=10,
                creationflags=0x08000000,
            )
            for line in r.stdout.splitlines():
                if "|" in line:
                    name, target = line.split("|", 1)
                    if name and target and Path(target).exists():
                        result[name.strip()] = target.strip()
        except Exception:
            pass
        _STARTMENU_CACHE = result
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except ImportError:
            pass
        return result

    try:
        for p in paths:
            base = Path(p)
            if not base.exists():
                continue
            try:
                for lnk in base.rglob("*.lnk"):
                    try:
                        target = shell.CreateShortcut(str(lnk)).TargetPath
                        if target and Path(target).exists():
                            result[lnk.stem] = target
                    except Exception:
                        continue
            except (PermissionError, OSError):
                continue
    finally:
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except ImportError:
            pass
    _STARTMENU_CACHE = result
    return result


def _lookup_windows_app_via_system(label: str) -> tuple[str, str]:
    """通过注册表 + 开始菜单快捷方式查找 Windows GUI exe（兜底）。

    匹配规则：规范化后的 label 是否被规范化后的 DisplayName / 快捷方式名 包含。
    避免误匹配：Trae CN 不会匹配到 "TRAE Work CN"（traecn 不是 traeworkcn 的子串）。

    Returns:
        (exe_path, version) 元组。未找到返回 ("", "")。
        version 来自注册表 DisplayVersion 字段（不调用 CLI）。
    """
    if sys.platform != "win32" or not label:
        return "", ""
    norm_label = _normalize_id(label)
    if not norm_label:
        return "", ""

    # 1. 注册表：DisplayIcon 通常指向真实 exe（如 "C:\...\Trae CN.exe,0"）
    #    优先 InstallLocation + 重名 exe，其次 DisplayIcon
    reg_hits = []
    for entry in _scan_registry_uninstall():
        norm_name = _normalize_id(entry["name"])
        if norm_label in norm_name:
            reg_hits.append(entry)
    for entry in reg_hits:
        # DisplayIcon 优先（直接是 exe 路径）
        if entry["icon"] and entry["icon"].lower().endswith(".exe"):
            p = Path(entry["icon"])
            if p.exists():
                return _realpath_case(str(p)), entry.get("version", "")
    for entry in reg_hits:
        # InstallLocation 下找 <label>.exe（去掉空格的版本）
        if entry["location"]:
            loc = Path(entry["location"])
            if loc.is_dir():
                # 试多种文件名变体：原 label、去空格、首字母大写
                candidates = [
                    f"{label}.exe",
                    f"{label.replace(' ', '')}.exe",
                ]
                for cand in candidates:
                    p = loc / cand
                    if p.exists():
                        return _realpath_case(str(p)), entry.get("version", "")
                # 兜底：目录下任何与 label 同名（大小写不敏感）的 exe
                label_norm = _normalize_id(label)
                try:
                    for f in loc.iterdir():
                        if (f.is_file() and f.suffix.lower() == ".exe"
                                and label_norm == _normalize_id(f.stem)):
                            return _realpath_case(str(f)), entry.get("version", "")
                except (PermissionError, OSError):
                    pass

    # 2. 开始菜单快捷方式：BaseName 通常就是产品名（如 "Trae CN.lnk"）
    for name, target in _scan_start_menu_shortcuts().items():
        if norm_label == _normalize_id(name) or norm_label in _normalize_id(name):
            if target.lower().endswith(".exe") and Path(target).exists():
                # 快捷方式无版本号，尝试从注册表反查
                ver = _lookup_version_from_registry(name)
                return _realpath_case(target), ver

    return "", ""


def _lookup_version_from_registry(label: str) -> str:
    """通过 label 反查注册表中的 DisplayVersion。"""
    if sys.platform != "win32" or not label:
        return ""
    norm_label = _normalize_id(label)
    if not norm_label:
        return ""
    for entry in _scan_registry_uninstall():
        if norm_label == _normalize_id(entry["name"]):
            return entry.get("version", "")
    return ""


def _get_cli_version(exe_path: str) -> str:
    """尝试获取 CLI 版本（--version），失败返回空字符串。

    Windows 下用 CREATE_NO_WINDOW 避免每个 CLI 探测弹一个 cmd 黑窗。
    """
    if not exe_path:
        return ""
    # 只试 --version（绝大多数 CLI 支持），失败快速返回，避免逐个 flag 串行拖慢
    kwargs = dict(capture_output=True, text=True, timeout=2)
    if sys.platform == "win32":
        # 隐藏 cmd 窗口（subprocess.CREATE_NO_WINDOW = 0x08000000）
        kwargs["creationflags"] = 0x08000000
    try:
        r = subprocess.run([exe_path, "--version"], **kwargs)
        out = (r.stdout + r.stderr).strip()
        if out:
            return out.split("\n", 1)[0][:80]
    except Exception:
        pass
    return ""


def _resolve_config_paths(config_dirs: list[str]) -> list[str]:
    """将配置目录解析为绝对路径，返回存在的路径列表。

    路径约定：
    - 以 "/" 开头：绝对路径
    - 以 "./" 开头：项目根目录（PROJECT_ROOT，detect 模块无法获取，用 cwd 兜底）
    - 其他：相对 Path.home()
    """
    home = Path.home()
    project_root = Path.cwd()
    found = []
    for d in config_dirs:
        if d.startswith("/"):
            abs_path = Path(d)
        elif d.startswith("./"):
            abs_path = project_root / d[2:]
        else:
            abs_path = home / d
        if abs_path.exists():
            found.append(str(abs_path))
    return found


def _resolve_sessions_dir(ide_key: str, config_paths: list[str]) -> str:
    """根据 sessions_subdir 推测会话目录绝对路径。"""
    meta = IDE_DETECT_META.get(ide_key, {})
    subdir = meta.get("sessions_subdir")
    if not subdir or not config_paths:
        return ""
    # 取第一个存在的 config_path/subdir
    for cp in config_paths:
        candidate = Path(cp) / subdir
        if candidate.exists():
            return str(candidate)
    return ""


def detect_ide(ide_key: str) -> dict:
    """检测单个 IDE。

    Returns:
        {
            "key": str,
            "label": str,
            "installed": bool,       # 仅当 exe_path 或 app_path 存在才为 True（配置目录不算）
            "exe_path": str,        # CLI 可执行文件路径（Windows 下解析 .CMD/.BAT 为真实 .exe）
            "app_path": str,        # macOS .app 或 Windows GUI exe 路径（可能为空）
            "version": str,
            "config_paths": list[str],
            "sessions_dir": str,
        }
    """
    meta = IDE_DETECT_META.get(ide_key)
    if not meta:
        return {
            "key": ide_key, "label": ide_key, "installed": False,
            "exe_path": "", "app_path": "", "version": "",
            "config_paths": [], "sessions_dir": "",
        }

    # 1. CLI 探测：shutil.which + .CMD/.BAT wrapper 解析
    exe_path = ""
    version = ""
    for cli_name in meta.get("cli_names", []):
        p = _which(cli_name)
        if p:
            # Windows 下把 .CMD/.BAT 解析为真实 .exe（cursor.CMD → Cursor.exe）
            exe_path = _resolve_cmd_wrapper_to_exe(p)
            version = _get_cli_version(exe_path)
            break

    # 2. App 探测：macOS .app + Windows GUI exe
    app_path = ""
    app_version = ""
    for ap in meta.get("macos_apps", []):
        if _check_macos_app(ap):
            app_path = ap
            break
    if not app_path:
        # Windows GUI exe 探测：先按已知路径列表
        for wt in meta.get("windows_apps", []):
            hit = _check_windows_app(wt)
            if hit:
                app_path = hit
                break
        # 兜底：注册表 + 开始菜单快捷方式（识别非默认路径、改名 IDE）
        if not app_path:
            app_path, app_version = _lookup_windows_app_via_system(meta.get("label", ""))

    # 3. 配置目录（仅信息展示，不影响 installed 判定）
    config_paths = _resolve_config_paths(meta.get("config_dirs", []))
    sessions_dir = _resolve_sessions_dir(ide_key, config_paths)

    # 4. installed：必须有可执行文件（CLI 或 App），配置目录不算
    installed = bool(exe_path or app_path)

    # 5. 版本号：优先 CLI 版本，其次注册表 DisplayVersion
    if not version and app_version:
        version = app_version

    return {
        "key": ide_key,
        "label": meta["label"],
        "installed": installed,
        "exe_path": exe_path,
        "app_path": app_path,
        "version": version,
        "config_paths": config_paths,
        "sessions_dir": sessions_dir,
    }


def detect_all() -> list[dict]:
    """检测所有支持的 IDE，返回列表（并行加速，按 key 字母升序）。"""
    from concurrent.futures import ThreadPoolExecutor
    keys = sorted(IDE_DETECT_META.keys())
    with ThreadPoolExecutor(max_workers=min(len(keys), 8)) as ex:
        results = list(ex.map(detect_ide, keys))
    return results


def is_installed(ide_key: str) -> bool:
    """快速判断 IDE 是否安装。"""
    return detect_ide(ide_key)["installed"]


__all__ = ["IDE_DETECT_META", "detect_ide", "detect_all", "is_installed"]
