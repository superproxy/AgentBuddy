#!/usr/bin/env python3
"""agentctl - AI 智能体配置统一 CLI。

合并 init-env.py + init-ide.py + plugin-manager.py 为单一入口。

子命令：
  generate  生成运行态配置（mcp.json + 各 IDE 模板配置）
  sync      同步 rules/mcp/skills 到各 IDE
  plugin    插件管理（install/list）
  skill     技能管理（list-skills/generate-plugin from CSV）
  env       设置环境变量（process/user 作用域）
  shell     导出 shell 环境变量语句
  provider  切换活跃 LLM provider/protocol
  setup     一键全流程（generate + plugin install all + sync）

用法示例：
  python scripts/agentctl.py generate
  python scripts/agentctl.py sync --ide Cursor --force
  python scripts/agentctl.py sync --ide All --skills tdd,mermaid
  python scripts/agentctl.py plugin install template/plugins/core.plugin.yaml
  python scripts/agentctl.py plugin list
  python scripts/agentctl.py provider openai
  python scripts/agentctl.py setup
"""
import argparse
import sys
from pathlib import Path

# 确保 scripts/ 在 sys.path 中，以便导入 lib 包
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.logging import (
    COLOR_CYAN, COLOR_GREEN, COLOR_YELLOW, COLOR_RED, COLOR_DARKGRAY, COLOR_RESET,
    info, warn, error, hint, header,
)
from lib import llm, mcp, skills, plugins
from lib.ide import get_ide, IDE_REGISTRY

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ============================================================
# 子命令实现
# ============================================================

def cmd_generate(args):
    """生成运行态配置：mcp.json + 各 IDE 模板配置（opencode/codex/claude/proxy）。"""
    env_config = llm.load_split_env_config(PROJECT_ROOT)

    # 切换 provider/protocol（如指定）
    if args.provider or args.protocol:
        if args.provider:
            env_config = llm.switch_provider(
                env_config, args.provider, args.protocol,
                PROJECT_ROOT / "config" / "llm" / "llm.yaml"
            )
        elif args.protocol:
            active = llm.get_active_provider(env_config)
            available = llm.list_protocols(env_config, active)
            current = llm.get_active_protocols(env_config)
            new_protocols = list(set(current + [args.protocol]))
            new_protocols = [p for p in new_protocols if p in available]
            if not new_protocols:
                new_protocols = [args.protocol] if args.protocol in available else available
            env_config["llm"]["_active_protocol"] = "|".join(new_protocols)
            llm.save_split_env_config(PROJECT_ROOT, env_config)
            print(f"{COLOR_GREEN}[OK] Protocol updated: {active}/{'|'.join(new_protocols)}{COLOR_RESET}")

    active_provider = llm.get_active_provider(env_config)
    active_protocols = llm.get_active_protocols(env_config)
    flat_config = llm.flatten_env_config(env_config, active_provider, active_protocols)

    header("Generate Runtime Configs")
    print(f"  {COLOR_GREEN}Active LLM: {active_provider}/{'|'.join(active_protocols)}{COLOR_RESET}")
    print()

    # 1. 生成 mcp.json（从 config/mcp/mcp.yaml + 已安装插件的 mcpServers 合并）
    mcp_yaml_file = PROJECT_ROOT / "config" / "mcp" / "mcp.yaml"
    mcp_output = PROJECT_ROOT / "config" / "mcp" / "mcp.json"
    plugins_dir = PROJECT_ROOT / "template" / "plugins"
    installed = plugins.read_installed_plugins(PROJECT_ROOT)
    mcp.invoke_mcp_generate_step(flat_config, mcp_yaml_file, mcp_output,
                                  plugins_dir=plugins_dir, installed_names=installed)

    # 2. 生成 opencode.json（从模板 + 注入模型）→ config/ide/opencode/
    opencode_template = PROJECT_ROOT / "template" / "ide" / "opencode" / "opencode.template.json"
    opencode_output = PROJECT_ROOT / "config" / "ide" / "opencode" / "opencode.json"
    if opencode_template.exists():
        opencode_output.parent.mkdir(parents=True, exist_ok=True)
        mcp.invoke_generate_step(flat_config, opencode_template, opencode_output)
        mcp._inject_opencode_models(opencode_output, env_config)

    # 3. 生成 codex auth.json + config.toml（从模板）→ config/ide/codex/
    codex_auth_template = PROJECT_ROOT / "template" / "ide" / "codex" / "auth.template.json"
    codex_auth_output = PROJECT_ROOT / "config" / "ide" / "codex" / "auth.json"
    if codex_auth_template.exists():
        codex_auth_output.parent.mkdir(parents=True, exist_ok=True)
        mcp.invoke_generate_step(flat_config, codex_auth_template, codex_auth_output)

    codex_config_template = PROJECT_ROOT / "template" / "ide" / "codex" / "config.template.toml"
    codex_config_output = PROJECT_ROOT / "config" / "ide" / "codex" / "config.toml"
    if codex_config_template.exists():
        codex_config_output.parent.mkdir(parents=True, exist_ok=True)
        mcp.invoke_generate_step(flat_config, codex_config_template, codex_config_output)

    # 4. 生成 claude settings.json（从模板）→ config/ide/claude/
    claude_template = PROJECT_ROOT / "template" / "ide" / "claude" / "settings.template.json"
    claude_output = PROJECT_ROOT / "config" / "ide" / "claude" / "settings.json"
    if claude_template.exists():
        claude_output.parent.mkdir(parents=True, exist_ok=True)
        mcp.invoke_generate_step(flat_config, claude_template, claude_output)

    # 5. 生成 proxy config.yaml（从模板，不剪枝）
    proxy_template = PROJECT_ROOT / "template" / "proxy" / "config.template.yaml"
    proxy_output = PROJECT_ROOT / "config" / "proxy" / "config.yaml"
    if proxy_template.exists():
        mcp.invoke_generate_step(flat_config, proxy_template, proxy_output, prune=False)

    print(f"{COLOR_CYAN}========================================{COLOR_RESET}")
    print(f"{COLOR_CYAN}  Generate Done.{COLOR_RESET}")
    print(f"{COLOR_CYAN}========================================{COLOR_RESET}")


def _warn_if_mcp_stale(mcp_json: Path) -> None:
    """检测 mcp.json 是否比 mcp.yaml / plugins/*.plugin.yaml 旧，是则提示先 generate。"""
    if not mcp_json.exists():
        print(f"{COLOR_YELLOW}[!] mcp.json not found, run `agentctl generate` first{COLOR_RESET}")
        return
    target_mtime = mcp_json.stat().st_mtime
    stale_sources = []
    mcp_yaml = PROJECT_ROOT / "config" / "mcp" / "mcp.yaml"
    if mcp_yaml.exists() and mcp_yaml.stat().st_mtime > target_mtime:
        stale_sources.append("config/mcp/mcp.yaml")
    plugins_dir = PROJECT_ROOT / "template" / "plugins"
    if plugins_dir.exists():
        for p in plugins_dir.glob("*.plugin.yaml"):
            if p.stat().st_mtime > target_mtime:
                stale_sources.append(p.name)
                break
    if stale_sources:
        print(f"{COLOR_YELLOW}[!] mcp.json is stale ({', '.join(stale_sources)} changed). "
              f"Run `agentctl generate` before sync to include latest plugin mcpServers.{COLOR_RESET}")


def cmd_sync(args):
    """同步 rules/mcp/skills 到各 IDE。

    sync 会自动完成：
      1. 合并 mcp.yaml + 已安装插件 mcpServers → 全局 mcp.json
      2. 合并 template/skills/ + config/skills/ → IDE skills 目录
      3. 同步 mcp.json + skills + rules 到各 IDE
    """
    # 解析 scope
    scope = set(s.strip() for s in args.scope.split(",") if s.strip())
    # 解析 skills 白名单
    include = None
    if args.skills and args.skills.strip():
        include = set(s.strip() for s in args.skills.split(",") if s.strip())
        hint(f"Skills filter: {len(include)} skill(s) selected")

    ide_name = args.ide
    targets = get_ide(ide_name, project_root=PROJECT_ROOT, force=args.force,
                      include_skills=include, scope=scope)

    source_rules = PROJECT_ROOT / "agents" / "rules"
    source_mcp = PROJECT_ROOT / "config" / "mcp" / "mcp.json"
    mcp_yaml_file = PROJECT_ROOT / "config" / "mcp" / "mcp.yaml"
    plugins_dir = PROJECT_ROOT / "template" / "plugins"

    # sync 前自动刷新 mcp.json：合并 mcp.yaml + 已安装插件 mcpServers
    # 这样 sync 就是完整的「关联 mcp + skill → 全局 → IDE」流程
    if "mcp" in scope and mcp_yaml_file.exists():
        installed = plugins.read_installed_plugins(PROJECT_ROOT)
        # 读取 flat_config 用于占位符替换
        flat_config = {}
        llm_yaml = PROJECT_ROOT / "config" / "llm" / "llm.yaml"
        if llm_yaml.exists():
            try:
                env_config = llm.load_split_env_config(PROJECT_ROOT)
                active_provider = llm.get_active_provider(env_config)
                active_protocols = llm.get_active_protocols(env_config)
                flat_config = llm.flatten_env_config(env_config, active_provider, active_protocols)
            except Exception:
                pass
        mcp.refresh_mcp_json(mcp_yaml_file, source_mcp, plugins_dir, installed, flat_config)

    # skill 源：template/skills/（源/内置）+ config/skills/（plugin 安装的，补充）
    source_skills = [PROJECT_ROOT / "template" / "skills"]
    plugin_skills = PROJECT_ROOT / "config" / "skills"
    if plugin_skills.exists():
        source_skills.append(plugin_skills)

    # 从 skill.yaml 读取启用清单，只同步启用的 skill
    skill_yaml = PROJECT_ROOT / "config" / "skills" / "skill.yaml"
    if "skill" in scope and skill_yaml.exists():
        enabled_set = skills.get_enabled_skills(skill_yaml)
        if enabled_set:
            # 合并命令行 --skills 白名单和 skill.yaml 的 enabled
            if include:
                include = include & enabled_set
            else:
                include = enabled_set
            hint(f"skill.yaml enabled: {len(enabled_set)} skill(s)")

    source_agents_md = PROJECT_ROOT / "AGENTS.md"

    for t in targets:
        t.run(source_rules, source_mcp, source_skills, source_agents_md)

    print(f"\n{COLOR_GREEN}[DONE] Synced to {len(targets)} IDE(s){COLOR_RESET}")


def cmd_env(args):
    """设置环境变量（process/user 作用域）。"""
    env_config = llm.load_split_env_config(PROJECT_ROOT)
    active_provider = llm.get_active_provider(env_config)
    active_protocols = llm.get_active_protocols(env_config)
    flat_config = llm.flatten_env_config(env_config, active_provider, active_protocols)
    llm.invoke_env_step(flat_config, args.scope, args.force)


def cmd_shell(args):
    """导出 shell 环境变量语句。"""
    env_config = llm.load_split_env_config(PROJECT_ROOT, silent=True)
    active_provider = llm.get_active_provider(env_config)
    active_protocols = llm.get_active_protocols(env_config)
    flat_config = llm.flatten_env_config(env_config, active_provider, active_protocols)
    llm.invoke_export_shell(flat_config)


def cmd_provider(args):
    """切换活跃 LLM provider/protocol。"""
    env_config = llm.load_split_env_config(PROJECT_ROOT)
    providers = llm.list_providers(env_config)

    if not args.name and not args.protocol:
        # 无参数：显示当前状态
        active = llm.get_active_provider(env_config)
        active_protocols = llm.get_active_protocols(env_config)
        print(f"{COLOR_CYAN}Current: {active}/{'|'.join(active_protocols)}{COLOR_RESET}")
        print(f"{COLOR_CYAN}Available providers: {', '.join(providers)}{COLOR_RESET}")
        for p in providers:
            protos = llm.list_protocols(env_config, p)
            print(f"  - {p}: {', '.join(protos)}")
        return

    if args.name:
        env_config = llm.switch_provider(
            env_config, args.name, args.protocol,
            PROJECT_ROOT / "llm.yaml"
        )
    elif args.protocol:
        active = llm.get_active_provider(env_config)
        available = llm.list_protocols(env_config, active)
        current = llm.get_active_protocols(env_config)
        new_protocols = list(set(current + [args.protocol]))
        new_protocols = [p for p in new_protocols if p in available]
        if not new_protocols:
            new_protocols = [args.protocol] if args.protocol in available else available
        env_config["llm"]["_active_protocol"] = "|".join(new_protocols)
        llm.save_split_env_config(PROJECT_ROOT, env_config)
        print(f"{COLOR_GREEN}[OK] Protocol updated: {active}/{'|'.join(new_protocols)}{COLOR_RESET}")


def cmd_plugin_install(args):
    """安装插件。"""
    plugin_path = Path(args.plugin_file).resolve()
    env_path = PROJECT_ROOT / args.env_file
    plugins.install_plugin(
        plugin_path, env_path, PROJECT_ROOT,
        dry_run=args.dry_run, use_symlink=args.symlink
    )


def cmd_plugin_list(args):
    """列出可用插件。"""
    plugins_dir = PROJECT_ROOT / args.plugins_dir
    plugins.list_plugins(plugins_dir)


def cmd_plugin_uninstall(args):
    """卸载插件。"""
    plugin_path = Path(args.plugin_file).resolve()
    env_path = PROJECT_ROOT / args.env_file
    plugins.uninstall_plugin(
        plugin_path, env_path, PROJECT_ROOT,
        remove_plugin_file=args.purge,
    )


def cmd_skill_list(args):
    """从 skills-index.csv 列出所有技能。"""
    csv_path = PROJECT_ROOT / args.csv
    plugins.list_skills_from_csv(csv_path)


def cmd_skill_enable(args):
    """启用技能（加入 skill.yaml 的 enabled 列表）。"""
    skill_yaml = PROJECT_ROOT / "template" / "skills" / "skill.yaml"
    added = skills.enable_skill(skill_yaml, args.skill_name)
    if added:
        print(f"{COLOR_GREEN}[OK] 已启用技能: {args.skill_name}{COLOR_RESET}")
    else:
        print(f"{COLOR_DARKGRAY}[~] 技能已启用: {args.skill_name}{COLOR_RESET}")


def cmd_skill_disable(args):
    """禁用技能（从 skill.yaml 的 enabled 列表移除）。"""
    skill_yaml = PROJECT_ROOT / "template" / "skills" / "skill.yaml"
    removed = skills.disable_skill(skill_yaml, args.skill_name)
    if removed:
        print(f"{COLOR_GREEN}[OK] 已禁用技能: {args.skill_name}{COLOR_RESET}")
    else:
        print(f"{COLOR_DARKGRAY}[~] 技能未启用: {args.skill_name}{COLOR_RESET}")


def cmd_skill_scan(args):
    """扫描本地技能，显示状态。"""
    skill_yaml = PROJECT_ROOT / "template" / "skills" / "skill.yaml"
    all_skills = skills.scan_local_skills(PROJECT_ROOT)
    enabled_set = skills.get_enabled_skills(skill_yaml)

    print(f"{COLOR_CYAN}{'=' * 40}{COLOR_RESET}")
    print(f"{COLOR_CYAN}  本地技能清单{COLOR_RESET}")
    print(f"{COLOR_CYAN}{'=' * 40}{COLOR_RESET}")
    print(f"\n共 {len(all_skills)} 个技能，{len(enabled_set)} 个已启用:\n")
    for name in all_skills:
        status = f"{COLOR_GREEN}[启用]{COLOR_RESET}" if name in enabled_set else f"{COLOR_DARKGRAY}[禁用]{COLOR_RESET}"
        print(f"  {status} {name}")


def cmd_skill_gen_plugin(args):
    """根据 skills-index.csv 生成插件配置。"""
    csv_path = PROJECT_ROOT / args.csv
    output_path = PROJECT_ROOT / args.output
    plugins.generate_plugin_from_csv(
        csv_path, output_path, args.name, args.description,
        category_filter=args.category
    )


def cmd_setup(args):
    """一键全流程：generate → sync（同步全局 agents/ 资源到 IDE）。

    agents/ 是全局基础设施（rules/commands），template/ 提供 LLM/MCP/Plugins/Skills 模板，开箱即用。
    插件（template/plugins/）是用户按需追加的扩展，不在此流程自动安装。
    用户需通过 `agentctl plugin install <file>` 单独安装插件。

    流程：
      1. generate
         - 从 mcp.yaml + template/plugins/*.plugin.yaml 合并生成 mcp.json
         - 生成各 IDE 模板配置（opencode/codex/claude）
      2. sync All
         - 同步 rules/mcp/skills 到各 IDE
    """
    header("Setup: Generate + Sync global agents/ resources")

    # Step 1: 生成运行态配置
    print(f"\n{COLOR_CYAN}==> Step 1/2: Generate runtime configs{COLOR_RESET}")
    ns_gen = argparse.Namespace(provider=None, protocol=None)
    cmd_generate(ns_gen)

    # Step 2: 同步到所有 IDE
    print(f"\n{COLOR_CYAN}==> Step 2/2: Sync to all IDEs{COLOR_RESET}")
    ns_sync = argparse.Namespace(
        ide="All", force=True, scope="llm,mcp,skill,rules", skills=""
    )
    cmd_sync(ns_sync)

    print(f"\n{COLOR_GREEN}========================================{COLOR_RESET}")
    print(f"{COLOR_GREEN}  Setup Complete!{COLOR_RESET}")
    print(f"{COLOR_GREEN}========================================{COLOR_RESET}")
    print(f"\n{COLOR_DARKGRAY}提示：如需扩展功能，可安装插件：{COLOR_RESET}")
    print(f"  {COLOR_WHITE}agentctl plugin install template/plugins/<name>.plugin.yaml{COLOR_RESET}")
    print(f"  {COLOR_WHITE}agentctl plugin list  # 查看可用插件{COLOR_RESET}")


# ============================================================
# argparse 主入口
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentctl",
        description="AI 智能体配置统一 CLI（合并 init-env + init-ide + plugin-manager）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # generate
    p_gen = sub.add_parser("generate", help="生成运行态配置（mcp.json + IDE 模板）")
    p_gen.add_argument("--provider", default=None,
                       help="切换 LLM provider（如 openai/anthropic/deepseek）")
    p_gen.add_argument("--protocol", default=None, choices=["openai", "anthropic"],
                       help="切换 LLM 协议")
    p_gen.set_defaults(func=cmd_generate)

    # sync
    p_sync = sub.add_parser("sync", help="同步 rules/mcp/skills 到 IDE")
    p_sync.add_argument("--ide", "-i", default="All",
                        help=f"目标 IDE（默认 All；可选: {', '.join(IDE_REGISTRY.keys())}）")
    p_sync.add_argument("--force", "-f", action="store_true",
                        help="强制覆盖已存在文件")
    p_sync.add_argument("--scope", default="llm,mcp,skill,rules",
                        help="同步范围，逗号分隔（默认 llm,mcp,skill,rules）")
    p_sync.add_argument("--skills", default="",
                        help="技能白名单，逗号分隔（仅同步这些技能）")
    p_sync.set_defaults(func=cmd_sync)

    # env
    p_env = sub.add_parser("env", help="设置环境变量")
    p_env.add_argument("--scope", choices=["process", "user"], default="process",
                       help="作用域：process（当前会话）或 user（持久）")
    p_env.add_argument("--force", action="store_true", help="跳过确认")
    p_env.set_defaults(func=cmd_env)

    # shell
    p_shell = sub.add_parser("shell", help="导出 shell 环境变量语句")
    p_shell.set_defaults(func=cmd_shell)

    # provider
    p_prov = sub.add_parser("provider", help="切换/查看活跃 LLM provider")
    p_prov.add_argument("name", nargs="?", default=None,
                        help="provider 名称（省略则查看当前状态）")
    p_prov.add_argument("--protocol", default=None, choices=["openai", "anthropic"],
                        help="同时切换协议")
    p_prov.set_defaults(func=cmd_provider)

    # plugin
    p_plugin = sub.add_parser("plugin", help="插件管理")
    p_plugin_sub = p_plugin.add_subparsers(dest="sub", required=True)

    p_ins = p_plugin_sub.add_parser("install", help="安装插件")
    p_ins.add_argument("plugin_file", help="插件 .plugin.yaml 文件路径")
    p_ins.add_argument("--env-file", default="config/llm/llm.yaml", help="环境变量文件（默认 config/llm/llm.yaml）")
    p_ins.add_argument("--dry-run", action="store_true", help="模拟运行")
    p_ins.add_argument("--symlink", action="store_true",
                       help="已弃用（保留兼容性，不再生效）")
    p_ins.set_defaults(func=cmd_plugin_install)

    p_lst = p_plugin_sub.add_parser("list", help="列出可用插件")
    p_lst.add_argument("--plugins-dir", default="template/plugins",
                       help="插件目录（默认 template/plugins）")
    p_lst.set_defaults(func=cmd_plugin_list)

    p_uns = p_plugin_sub.add_parser("uninstall", help="卸载插件（移除已安装的 skill 和 envVars）")
    p_uns.add_argument("plugin_file", help="插件 .plugin.yaml 文件路径")
    p_uns.add_argument("--env-file", default="config/llm/llm.yaml", help="环境变量文件（默认 config/llm/llm.yaml）")
    p_uns.add_argument("--purge", action="store_true",
                       help="同时删除插件 .plugin.yaml 文件本身")
    p_uns.set_defaults(func=cmd_plugin_uninstall)

    # skill
    p_skill = sub.add_parser("skill", help="技能管理（基于 skills-index.csv）")
    p_skill_sub = p_skill.add_subparsers(dest="sub", required=True)

    p_sl = p_skill_sub.add_parser("list", help="列出 CSV 中所有技能")
    p_sl.add_argument("--csv", default="template/skills/skills-index.csv",
                      help="技能映射文件（默认 template/skills/skills-index.csv）")
    p_sl.set_defaults(func=cmd_skill_list)

    p_sg = p_skill_sub.add_parser("gen-plugin", help="根据 CSV 生成插件配置")
    p_sg.add_argument("--csv", default="template/skills/skills-index.csv",
                      help="技能映射文件（默认 template/skills/skills-index.csv）")
    p_sg.add_argument("--output", default="template/plugins/generated.plugin.yaml",
                      help="输出文件路径")
    p_sg.add_argument("--name", default="generated", help="插件名称")
    p_sg.add_argument("--description", default="", help="插件描述")
    p_sg.add_argument("--category", default=None, help="按分类过滤")
    p_sg.set_defaults(func=cmd_skill_gen_plugin)

    p_se = p_skill_sub.add_parser("enable", help="启用技能（加入 skill.yaml enabled 列表）")
    p_se.add_argument("skill_name", help="技能名称")
    p_se.set_defaults(func=cmd_skill_enable)

    p_sd = p_skill_sub.add_parser("disable", help="禁用技能（从 skill.yaml enabled 列表移除）")
    p_sd.add_argument("skill_name", help="技能名称")
    p_sd.set_defaults(func=cmd_skill_disable)

    p_sc = p_skill_sub.add_parser("scan", help="扫描本地技能，显示启用状态")
    p_sc.set_defaults(func=cmd_skill_scan)

    # setup
    p_setup = sub.add_parser("setup", help="一键全流程：generate + sync（不含插件安装）")
    p_setup.set_defaults(func=cmd_setup)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
