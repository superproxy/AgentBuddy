#!/usr/bin/env python3
"""BuildAgent — 构建智能体。

职责：扫描 CrawlerAgent 产出的 spec.yaml → build_plugin 打 zip → 发布到市场。
不搜索、不抓取、不抽取 skills。CrawlerAgent 负责 spec.yaml 的生成。

spec.yaml 路径约定：data/specs/<task_name>/<slug>.yaml
spec.yaml 顶层包含 build_plugin 兼容字段（name/version/description/skills/...），
BuildAgent 直接将整个 spec 内容作为 config_yaml 传给 build_plugin。

构建状态机（spec.build_status 字段，由 BuildAgent 维护）：
    pending → built → published
                 ↘ error

幂等：已 built/published 的 spec 跳过；error 的可重试。
"""
from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

SERVER_DIR = Path(__file__).resolve().parent
SPECS_DIR = SERVER_DIR / "data" / "specs"


# ============================================================
# 发布函数类型（依赖注入，避免与 PluginMarketWorker.py 循环 import）
# ============================================================

PublishFn = Callable[[Path, list], dict]
AlreadyPublishedFn = Callable[[str, str], bool]


# ============================================================
# spec.yaml 读写
# ============================================================


def iter_specs(
    specs_dir: Path | None = None,
    *,
    min_rating: int = 0,
) -> list[tuple[Path, dict]]:
    """扫描所有 spec.yaml，按 rating 降序返回 [(path, spec_dict), ...]。

    - 跳过非 yaml 文件和解析失败的文件
    - 过滤掉 rating < min_rating 的 spec（默认 0 不过滤）
    - 按 spec.rating 降序排序（高分优先构建）
    """
    root = specs_dir or SPECS_DIR
    if not root.exists():
        return []
    out: list[tuple[Path, dict]] = []
    for p in sorted(root.rglob("*.yaml")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                spec = yaml.safe_load(f) or {}
        except Exception:
            continue
        if not isinstance(spec, dict):
            continue
        # 必须包含 build_plugin 兼容字段
        if not spec.get("name") or not spec.get("skills"):
            continue
        # 评级过滤
        rating = int(spec.get("rating", 0) or 0)
        if rating < min_rating:
            continue
        out.append((p, spec))
    # 按 rating 降序（高分优先构建）
    out.sort(key=lambda x: int(x[1].get("rating", 0) or 0), reverse=True)
    return out


def save_spec(spec_path: Path, spec: dict) -> None:
    """回写 spec.yaml（更新 build_status 等）。"""
    with open(spec_path, "w", encoding="utf-8") as f:
        yaml.dump(spec, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


# ============================================================
# 构建结果
# ============================================================


@dataclass
class BuildResult:
    spec_path: str
    plugin_name: str
    status: str  # built / published / skipped / error
    zip_path: str = ""
    reason: str = ""
    skills: list[str] = field(default_factory=list)


# ============================================================
# 主流程 — BuildAgent 执行
# ============================================================


def run(
    *,
    dry_run: bool = False,
    only_task: str | None = None,
    publish_fn: PublishFn | None = None,
    already_published_fn: AlreadyPublishedFn | None = None,
    specs_dir: Path | None = None,
    min_rating: int = 0,
    max_publish: int = 0,
) -> list[BuildResult]:
    """BuildAgent 主入口：扫描 spec → 构建 → 发布。

    Args:
        dry_run: True 则只构建不发布
        only_task: 仅处理指定 task 名（spec.task 字段），None 则处理全部
        publish_fn: 发布函数 (zip_path, tags) -> dict；None 则不发布
        already_published_fn: 去重函数 (name, version) -> bool；None 则不去重
        specs_dir: spec 目录（测试用），None 则用默认 SPECS_DIR
        min_rating: 只处理 rating >= min_rating 的 spec（默认 0 不过滤）
        max_publish: 最多发布几个（含本次已发布的累计计数，0 表示不限）。
                     达到上限后剩余 spec 不再构建发布。

    Returns: [BuildResult, ...]
    """
    from plugin_build import build_plugin

    specs = iter_specs(specs_dir, min_rating=min_rating)
    if not specs:
        print("[build_agent] 无 spec.yaml 待构建（data/specs/ 为空）")
        return []

    print(f"[build_agent] 发现 {len(specs)} 个 spec"
          f"{'（dry-run）' if dry_run else ''}"
          f"{'（min_rating=%d）' % min_rating if min_rating > 0 else ''}"
          f"{'（max_publish=%d）' % max_publish if max_publish > 0 else ''}")

    results: list[BuildResult] = []
    published_count = 0  # 本次新发布的计数（max_publish 限流用）
    for spec_path, spec in specs:
        task = str(spec.get("task", "")).strip()
        if only_task and task != only_task:
            continue

        plugin_name = str(spec.get("name", "")).strip()
        version = str(spec.get("version", "1.0.0")).strip() or "1.0.0"
        build_status = str(spec.get("build_status", "pending")).strip()
        skills = [s.get("name", "") if isinstance(s, dict) else str(s)
                  for s in spec.get("skills", [])]

        # 幂等：已发布跳过
        if build_status == "published":
            print(f"  [SKIP-PUBLISHED] {plugin_name}")
            results.append(BuildResult(
                spec_path=str(spec_path), plugin_name=plugin_name,
                status="skipped", reason="already published", skills=skills,
            ))
            continue

        # 幂等：已构建且不发布 → 跳过
        if build_status == "built" and (dry_run or publish_fn is None):
            print(f"  [SKIP-BUILT] {plugin_name}")
            results.append(BuildResult(
                spec_path=str(spec_path), plugin_name=plugin_name,
                status="skipped", reason="already built", skills=skills,
            ))
            continue

        # max_publish 限流：达上限后剩余 spec 不再构建发布
        # （已 published/built 的不算在 max_publish 内，直接跳过）
        if max_publish > 0 and published_count >= max_publish:
            print(f"  [SKIP-QUOTA] {plugin_name}（已达 max_publish={max_publish}）")
            results.append(BuildResult(
                spec_path=str(spec_path), plugin_name=plugin_name,
                status="skipped", reason=f"quota full ({max_publish})", skills=skills,
            ))
            continue

        # 已构建且需要发布 → 直接走发布
        if build_status == "built" and publish_fn is not None and not dry_run:
            # 找 zip
            zip_path_str = str(spec.get("_zip_path", "")).strip()
            if not zip_path_str:
                # 重新构建（找不到上次 zip）
                print(f"  [REBUILD] {plugin_name}（_zip_path 缺失）")
            else:
                zip_path = Path(zip_path_str)
                if not zip_path.exists():
                    print(f"  [REBUILD] {plugin_name}（zip 不存在: {zip_path}）")
                else:
                    # 去重
                    if already_published_fn and already_published_fn(plugin_name, version):
                        print(f"  [SKIP-DUP] {plugin_name} 已发布")
                        spec["build_status"] = "published"
                        save_spec(spec_path, spec)
                        results.append(BuildResult(
                            spec_path=str(spec_path), plugin_name=plugin_name,
                            status="skipped", reason="already published (dup check)", skills=skills,
                        ))
                        continue
                    # 发布
                    try:
                        tags = list(spec.get("keywords", []) or [])
                        publish_fn(zip_path, tags)
                        spec["build_status"] = "published"
                        save_spec(spec_path, spec)
                        print(f"  [PUBLISHED] {plugin_name}")
                        results.append(BuildResult(
                            spec_path=str(spec_path), plugin_name=plugin_name,
                            status="published", zip_path=str(zip_path), skills=skills,
                        ))
                        published_count += 1
                        continue
                    except Exception as e:
                        spec["build_status"] = "error"
                        spec["_last_error"] = f"publish: {e}"
                        save_spec(spec_path, spec)
                        print(f"  [PUBLISH-ERR] {plugin_name}: {e}")
                        results.append(BuildResult(
                            spec_path=str(spec_path), plugin_name=plugin_name,
                            status="error", reason=f"publish: {e}", skills=skills,
                        ))
                        continue

        # pending / error → 构建
        try:
            # spec.yaml 顶层即 build_plugin 兼容字段，直接 dump 为 config_yaml
            config_yaml = yaml.dump(spec, allow_unicode=True, default_flow_style=False, sort_keys=False)
            zip_path, _meta = build_plugin(
                SERVER_DIR,
                {"config_yaml": config_yaml, "mode": "inline"},
            )
        except Exception as e:
            spec["build_status"] = "error"
            spec["_last_error"] = f"build: {e}"
            save_spec(spec_path, spec)
            print(f"  [BUILD-ERR] {plugin_name}: {e}")
            results.append(BuildResult(
                spec_path=str(spec_path), plugin_name=plugin_name,
                status="error", reason=f"build: {e}", skills=skills,
            ))
            continue

        spec["build_status"] = "built"
        spec["_zip_path"] = str(zip_path)
        save_spec(spec_path, spec)

        if dry_run or publish_fn is None:
            print(f"  [BUILT] {plugin_name} → {zip_path.name}")
            results.append(BuildResult(
                spec_path=str(spec_path), plugin_name=plugin_name,
                status="built", zip_path=str(zip_path), skills=skills,
            ))
            continue

        # 发布
        if already_published_fn and already_published_fn(plugin_name, version):
            spec["build_status"] = "published"
            save_spec(spec_path, spec)
            print(f"  [SKIP-DUP] {plugin_name} 已发布")
            results.append(BuildResult(
                spec_path=str(spec_path), plugin_name=plugin_name,
                status="skipped", reason="already published (dup check)", skills=skills,
            ))
            continue

        try:
            tags = list(spec.get("keywords", []) or [])
            publish_fn(Path(zip_path), tags)
            spec["build_status"] = "published"
            save_spec(spec_path, spec)
            print(f"  [PUBLISHED] {plugin_name}")
            results.append(BuildResult(
                spec_path=str(spec_path), plugin_name=plugin_name,
                status="published", zip_path=str(zip_path), skills=skills,
            ))
            published_count += 1
        except Exception as e:
            spec["build_status"] = "error"
            spec["_last_error"] = f"publish: {e}"
            save_spec(spec_path, spec)
            print(f"  [PUBLISH-ERR] {plugin_name}: {e}")
            results.append(BuildResult(
                spec_path=str(spec_path), plugin_name=plugin_name,
                status="error", reason=f"publish: {e}", skills=skills,
            ))

    return results


def main(argv: list[str] | None = None) -> int:
    """BuildAgent 独立 CLI 入口（也可通过 PluginMarketWorker.py --build-agent 调用）。"""
    import argparse

    parser = argparse.ArgumentParser(description="BuildAgent — 读 spec.yaml 构建并发布插件")
    parser.add_argument("--dry-run", action="store_true", help="只构建不发布")
    parser.add_argument("--task", default=None, help="仅构建指定 task 的 spec")
    parser.add_argument("--no-publish", action="store_true", help="不发布（仅构建到 zip）")
    parser.add_argument("--min-rating", type=int, default=0,
                        help="只构建 rating >= 此值的 spec（默认 0 不过滤）")
    parser.add_argument("--max-publish", type=int, default=0,
                        help="本次最多发布几个（0 表示不限）")
    args = parser.parse_args(argv)

    publish_fn: PublishFn | None = None
    already_published_fn: AlreadyPublishedFn | None = None
    if not args.no_publish and not args.dry_run:
        # 延迟 import 避免循环
        try:
            from PluginMarketWorker import publish_local, already_published_local
            publish_fn = publish_local
            already_published_fn = already_published_local
        except ImportError as e:
            print(f"[build_agent] 无法导入 PluginMarketWorker 发布函数: {e}", file=sys.stderr)
            return 1

    results = run(
        dry_run=args.dry_run,
        only_task=args.task,
        publish_fn=publish_fn,
        already_published_fn=already_published_fn,
        min_rating=args.min_rating,
        max_publish=args.max_publish,
    )

    # 统计
    built = sum(1 for r in results if r.status == "built")
    published = sum(1 for r in results if r.status == "published")
    skipped = sum(1 for r in results if r.status == "skipped")
    errors = sum(1 for r in results if r.status == "error")
    print(f"\n[build_agent] 完成：built={built} published={published} skipped={skipped} error={errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


# ============================================================
# 调试辅助（不参与主流程）
# ============================================================


def _debug_print_spec(spec_path: Path) -> None:
    """打印单个 spec 的内容（调试用）。"""
    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            print(f.read())
    except Exception as e:
        print(f"读取失败: {e}", file=sys.stderr)
        traceback.print_exc()
