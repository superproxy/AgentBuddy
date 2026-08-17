"""从本地 plugin-builds/*.zip + specs/*.yaml 重建 plugins 表数据。

适用场景：
    升级到 MySQL 后 plugins 表数据缺失，但本地 data/plugin-builds/ 下的 zip
    和 data/specs/ 下的 yaml 仍然存在。本脚本扫描这些本地资源，重建 plugins
    表记录（INSERT ... ON DUPLICATE KEY UPDATE，幂等）。

数据源优先级：
    zip 内 .plugin.yaml → 权威元数据（name / version / description / author）
    data/specs/<task>/<spec-name>.yaml → 补充（keywords→tags、homepage）

用法：
    python3 scripts/rebuild_plugins_from_local.py
    python3 scripts/rebuild_plugins_from_local.py --dry-run
    python3 scripts/rebuild_plugins_from_local.py \\
        --builds-dir data/plugin-builds \\
        --specs-dir data/specs \\
        --marketplace-dir data/marketplace

前置条件：
    1. .env 中已配置 AGENTBUDDY_DB_BACKEND 和 AGENTBUDDY_DB_URL（如用 MySQL）
    2. app.py 至少启动过一次（已自动建表）

输出：
    1. 同步 zip 到 marketplace/packages/（若目标不存在）
    2. 写入 plugins 表（author_id=NULL，downloads=0，likes=0）
"""
import argparse
import json
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# 让 server/ 加入 sys.path
SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))

# 加载 .env
from _env_loader import load_env_file
load_env_file()

import yaml
from auth.models import plugin_save, set_marketplace_dir


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_plugin_yaml_from_zip(zip_path: Path) -> dict | None:
    """从 zip 中读取 .plugin.yaml，返回 dict。无则返回 None。"""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = info.filename
                if name.endswith((".plugin.yaml", ".plugin.yml", "plugin.yaml", "plugin.yml")):
                    try:
                        data = yaml.safe_load(zf.read(name).decode("utf-8"))
                        if isinstance(data, dict):
                            return data
                    except Exception:
                        pass
                    break
    except zipfile.BadZipFile:
        return None
    return None


def find_spec_yaml(specs_dir: Path, spec_name: str) -> Path | None:
    """在 specs_dir 下递归找 <spec_name>.yaml。"""
    if not specs_dir.exists():
        return None
    for p in specs_dir.rglob(f"{spec_name}.yaml"):
        return p
    return None


def safe_plugin_name(name: str) -> str:
    """生成 zip 文件名安全形式：仅字母数字和 -_。"""
    return "".join(c for c in str(name) if c.isalnum() or c in ("-", "_"))


def mtime_to_iso(path: Path) -> str:
    """文件 mtime 转 ISO 字符串。"""
    try:
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return now_iso()


def rebuild_one(zip_path: Path, specs_dir: Path, marketplace_dir: Path,
                service_author: str = "crawler-agent") -> dict | None:
    """重建一个 plugin 条目。返回 entry dict 或 None（失败）。"""
    ydata = parse_plugin_yaml_from_zip(zip_path)
    if not ydata:
        return None

    plugin_name = str(ydata.get("name") or zip_path.stem).strip()
    version = str(ydata.get("version") or "1.0.0").strip() or "1.0.0"
    description = str(ydata.get("description") or "").strip()
    author = str(ydata.get("author") or "").strip() or service_author

    # 同名 spec yaml 补充 keywords → tags、homepage
    tags: list = []
    homepage = ""
    spec_name = plugin_name
    spec_path = find_spec_yaml(specs_dir, spec_name)
    if spec_path:
        try:
            spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
            if isinstance(spec, dict):
                kws = spec.get("keywords") or []
                if isinstance(kws, list):
                    tags = [str(k) for k in kws if k]
                homepage = str(spec.get("homepage") or "")
                # spec.description 通常更完整，优先用 spec 的
                spec_desc = str(spec.get("description") or "").strip()
                if spec_desc and len(spec_desc) > len(description):
                    description = spec_desc
        except Exception:
            pass

    safe_name = safe_plugin_name(plugin_name)
    pkg_name = f"{safe_name or 'plugin'}-{version}.zip"

    # 1. 同步 zip 到 marketplace/packages/
    packages_dir = marketplace_dir / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)
    target_pkg = packages_dir / pkg_name
    if not target_pkg.exists():
        target_pkg.write_bytes(zip_path.read_bytes())

    # 2. 构造 entry
    entry = {
        "id": f"{plugin_name}-{version}",
        "name": plugin_name,
        "version": version,
        "description": description[:500],
        "author": author,
        "author_id": None,  # crawler-agent 非真实用户，无 author_id
        "file": f"packages/{pkg_name}",
        "size": target_pkg.stat().st_size,
        "published_at": mtime_to_iso(zip_path),
        "tags": tags,
        "downloads": 0,  # 旧计数无法恢复
        "likes": 0,
        "scope": "public",
        "team_id": None,
    }
    return entry


def main():
    parser = argparse.ArgumentParser(description="从本地 zip + spec yaml 重建 plugins 表")
    parser.add_argument("--builds-dir", type=Path,
                        default=SERVER_DIR / "data" / "plugin-builds",
                        help="plugin-builds 目录（zip 源）")
    parser.add_argument("--specs-dir", type=Path,
                        default=SERVER_DIR / "data" / "specs",
                        help="specs 目录（yaml 补充源）")
    parser.add_argument("--marketplace-dir", type=Path,
                        default=SERVER_DIR / "data" / "marketplace",
                        help="marketplace 目录（packages 目标）")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅扫描和打印将重建的条目，不写库不同步文件")
    parser.add_argument("--service-author", type=str, default="crawler-agent",
                        help="无 author 字段时的默认值")
    args = parser.parse_args()

    if not args.builds_dir.exists():
        print(f"[ERROR] builds-dir 不存在: {args.builds_dir}")
        sys.exit(1)

    # 设置 marketplace_dir（auth.models.plugin_save 内部不用，但保持一致性）
    args.marketplace_dir.mkdir(parents=True, exist_ok=True)
    set_marketplace_dir(args.marketplace_dir)

    zips = sorted(args.builds_dir.glob("*.zip"))
    print(f"[1/3] 扫描 {args.builds_dir}: {len(zips)} 个 zip")
    if not zips:
        print("[ERROR] 没找到 zip，确认 --builds-dir 正确")
        sys.exit(1)

    print(f"[2/3] 解析 zip 内 .plugin.yaml + 补充 specs")
    entries = []
    skipped = []
    for zp in zips:
        entry = rebuild_one(zp, args.specs_dir, args.marketplace_dir,
                            service_author=args.service_author)
        if entry:
            entries.append(entry)
            print(f"  OK   {zp.name} → {entry['id']}")
        else:
            skipped.append(zp.name)
            print(f"  SKIP {zp.name} (无 .plugin.yaml 或 zip 损坏)")

    print(f"\n  合计: 可重建 {len(entries)}，跳过 {len(skipped)}")

    if args.dry_run:
        print("\n[dry-run] 不写库，仅打印前 3 个 entry 示例：")
        for e in entries[:3]:
            print(json.dumps(e, ensure_ascii=False, indent=2))
        return

    if not entries:
        print("[ERROR] 没有可重建的条目")
        sys.exit(1)

    print(f"\n[3/3] 写入 plugins 表（INSERT ... ON DUPLICATE KEY UPDATE，幂等）")
    ok = 0
    fail = 0
    for e in entries:
        try:
            plugin_save(e)
            ok += 1
        except Exception as ex:
            fail += 1
            print(f"  FAIL {e['id']}: {ex}")

    print(f"\n[OK] 重建完成: ok={ok} fail={fail}")
    print("\n下一步：")
    print("  1. 重启服务: ./run.sh restart")
    print("  2. 验证: mysql -u agentbuddy -p agentbuddy -e 'SELECT id, name, author FROM plugins;'")


if __name__ == "__main__":
    main()
