#!/usr/bin/env python3
"""agentctl - AI 智能体配置统一 CLI。

合并 init-env.py + init-ide.py + plugin-manager.py 为单一入口。

子命令：
  generate  生成运行态配置（mcp.json + 各 IDE 模板配置）
  sync      同步 rules/mcp/skills 到各 IDE
  plugin    插件管理（install/list/uninstall/build/publish/auth）
  skill     技能管理（list-skills/generate-plugin from CSV）
  env       设置环境变量（process/user 作用域）
  shell     导出 shell 环境变量语句
  provider  切换活跃 LLM provider/protocol
  setup     一键全流程（generate + plugin install all + sync）

用法示例：
  python -m agentctl.agentctl generate
  python -m agentctl.agentctl sync --ide Cursor --force
  python -m agentctl.agentctl sync --ide All --skills tdd,mermaid
  python -m agentctl.agentctl plugin install template/plugins/core.plugin.yaml
  python -m agentctl.agentctl plugin list
  python -m agentctl.agentctl plugin build QwenLM/Qwen-MM-Plugins --skills core,api,search --mode inline
  python -m agentctl.agentctl plugin build "https://mp.weixin.qq.com/s/xxx" --ai --publish --tags vision,ocr
  python -m agentctl.agentctl plugin publish ./my-plugin.zip --scope public --tags ai,mcp
  python -m agentctl.agentctl plugin auth login --username AgentBuddy --password xxx
  python -m agentctl.agentctl provider openai
  python -m agentctl.agentctl setup

或安装后直接使用 agentctl 命令：
  agentctl generate
  agentctl sync --ide Cursor --force
  agentctl setup
"""
import argparse
import sys
from pathlib import Path

from agentctl.lib.logging import (
    COLOR_CYAN, COLOR_GREEN, COLOR_YELLOW, COLOR_RED, COLOR_DARKGRAY, COLOR_RESET,
    info, warn, error, hint, header,
)
from agentctl.lib import llm, mcp, skills, plugins
from agentctl.lib.ide import get_ide, IDE_REGISTRY
from agentctl.lib.ide._meta import get_ide_protocols as get_ide_protocols


def _resolve_project_root() -> Path:
    """Frozen-aware 项目根定位。

    macOS .app bundle 安装到 /Applications 后不可写，
    改用 ~/Library/Application Support/AgentBuddy/。
    """
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            data_root = Path.home() / "Library" / "Application Support" / "AgentBuddy"
            data_root.mkdir(parents=True, exist_ok=True)
            return data_root
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[1]


PROJECT_ROOT = _resolve_project_root()


def _append_codex_candidate_providers(config_path, env_config, active_provider):
    """在 codex config.toml 末尾追加其他启用的 provider 作为候选 model_providers。

    只同步有 responses 协议且启用的 provider。active provider 已在模板中生成。
    """
    from agentctl.lib.llm import _merge_base

    llm = env_config.get("llm", {})
    if not isinstance(llm, dict):
        return

    # 网关也是个 provider，加入候选列表
    gateway_config = env_config.get("proxy", {}).get("gateway", {})
    enable_gateway = gateway_config.get("enabled", False) if isinstance(gateway_config, dict) else False

    # 收集候选 provider，active provider 排第一
    candidates = []
    for provider_name, provider_value in llm.items():
        if provider_name.startswith("_") or provider_name == "proxy":
            continue
        if not isinstance(provider_value, dict):
            continue
        if provider_value.get("_enabled") is False:
            continue
        # active provider 已在模板中，跳过
        if provider_name == active_provider:
            continue

        merged = _merge_base(provider_value)
        # 只同步有 responses 协议的 provider
        proto_config = merged.get("responses") if isinstance(merged, dict) else None
        if not isinstance(proto_config, dict):
            continue

        base_url = str(proto_config.get("base_url", "")).strip().strip("`").strip()
        if not base_url:
            continue

        candidates.append((provider_name, base_url))

    # 网关作为候选 provider 加入（启用了且不是 active provider）
    # active_provider 为空时模板 fallback 到 agentbuddy-gateway，不需要重复加入
    if enable_gateway and active_provider:
        gw_url = str(gateway_config.get("base_url", "http://127.0.0.1:4000/v1")).strip()
        gw_name = "agentbuddy-gateway"
        if gw_url and active_provider != gw_name:
            candidates.insert(0, (gw_name, gw_url))

    lines = []
    for provider_name, base_url in candidates:
        lines.append(f"\n[model_providers.{provider_name}]")
        lines.append(f'name = "{provider_name}"')
        lines.append(f'base_url = "{base_url}"')
        lines.append('wire_api = "responses"')
        lines.append("requires_openai_auth = true")

    if lines:
        with open(config_path, "a", encoding="utf-8") as f:
            f.write("\n# --- candidate providers (enabled, non-default) ---\n")
            f.write("\n".join(lines) + "\n")


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
        # 两维度模型：网关兼容、原生仅直连。
        # 有具体 active provider 且 gateway 关闭时，生成 opencode 原生双协议 provider
        # （openai→@ai-sdk/openai, anthropic→@ai-sdk/anthropic，anthropic 不注入 models）
        llm.inject_opencode_native_providers(opencode_output, env_config,
                                             active_provider, active_protocols)

    # 3. 生成 codex auth.json + config.toml（从模板）→ config/ide/codex/
    # Codex 使用 responses 协议，需要专用 flat_config
    codex_protocols = get_ide_protocols("Codex")
    codex_flat_config = llm.flatten_env_config(env_config, active_provider, active_protocols,
                                               ide_protocols=codex_protocols)
    codex_auth_template = PROJECT_ROOT / "template" / "ide" / "codex" / "auth.template.json"
    codex_auth_output = PROJECT_ROOT / "config" / "ide" / "codex" / "auth.json"
    if codex_auth_template.exists():
        codex_auth_output.parent.mkdir(parents=True, exist_ok=True)
        mcp.invoke_generate_step(codex_flat_config, codex_auth_template, codex_auth_output)

    codex_config_template = PROJECT_ROOT / "template" / "ide" / "codex" / "config.template.toml"
    codex_config_output = PROJECT_ROOT / "config" / "ide" / "codex" / "config.toml"
    if codex_config_template.exists():
        codex_config_output.parent.mkdir(parents=True, exist_ok=True)
        mcp.invoke_generate_step(codex_flat_config, codex_config_template, codex_config_output)
        # 追加其他启用的 provider 作为候选 model_providers
        _append_codex_candidate_providers(codex_config_output, env_config, active_provider)

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
        for p in plugins.iter_plugin_files(plugins_dir):
            if p.stat().st_mtime > target_mtime:
                stale_sources.append(p.name)
                break
    if stale_sources:
        print(f"{COLOR_YELLOW}[!] mcp.json is stale ({', '.join(stale_sources)} changed). "
              f"Run `agentctl generate` before sync to include latest plugin mcpServers.{COLOR_RESET}")


def _validate_default_llm_selection(env_config, targets):
    """Codex/Claude 同步前必须明确选择唯一默认 LLM 源和模型。"""
    target_names = {getattr(target, "name", "") for target in targets}
    if not target_names.intersection({"Codex", "Claude"}):
        return None
    return llm.validate_default_llm(env_config)


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
    # 加载 env_config 用于 IDE 协议过滤配置
    _env_config_for_ide = None
    try:
        _env_config_for_ide = llm.load_split_env_config(PROJECT_ROOT, silent=True)
    except Exception:
        pass
    targets = get_ide(ide_name, project_root=PROJECT_ROOT, force=args.force,
                      include_skills=include, scope=scope,
                      env_config=_env_config_for_ide)

    if "llm" in scope:
        validation_error = _validate_default_llm_selection(_env_config_for_ide, targets)
        if validation_error:
            print(f"{COLOR_RED}[ERROR] {validation_error}{COLOR_RESET}")
            return False

    # Agents 仅承载公共 rules/mcp/skills；纯 llm 同步不应触碰 .agents/。
    agents_scopes = {"rules", "mcp", "skill"}
    if scope.intersection(agents_scopes) and ide_name not in ("All", "Agents"):
        if not any(getattr(t, 'name', '') == 'Agents' for t in targets):
            agents_targets = get_ide("Agents", project_root=PROJECT_ROOT, force=args.force,
                                     include_skills=include, scope=scope)
            targets.extend(agents_targets)

    # rules 源（多源并集，与 skills 一致）:
    #   1. config/rules/   - 用户编辑的规则（优先）
    #   2. template/rules/ - 内置预置规则
    source_rules = [PROJECT_ROOT / "config" / "rules"]
    template_rules = PROJECT_ROOT / "template" / "rules"
    if template_rules.exists():
        source_rules.append(template_rules)
    source_mcp = PROJECT_ROOT / "config" / "mcp" / "mcp.json"
    mcp_yaml_file = PROJECT_ROOT / "config" / "mcp" / "mcp.yaml"
    plugins_dir = PROJECT_ROOT / "template" / "plugins"

    # 首次运行时从模板生成 mcp.yaml / llm.yaml（与 config_server._ensure_* 一致）
    mcp_example = PROJECT_ROOT / "template" / "mcp" / "mcp-template.yaml"
    if not mcp_yaml_file.exists() and mcp_example.exists():
        mcp_yaml_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            import shutil
            shutil.copy2(mcp_example, mcp_yaml_file)
            hint(f"首次运行：已从模板生成 {mcp_yaml_file.relative_to(PROJECT_ROOT)}")
        except Exception as e:
            hint(f"[WARN] 创建 mcp.yaml 失败: {e}")
    llm_yaml_file = PROJECT_ROOT / "config" / "llm" / "llm.yaml"
    llm_example = PROJECT_ROOT / "template" / "llm" / "llm-template.yaml"
    if not llm_yaml_file.exists() and llm_example.exists():
        llm_yaml_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            import shutil
            shutil.copy2(llm_example, llm_yaml_file)
            hint(f"首次运行：已从模板生成 {llm_yaml_file.relative_to(PROJECT_ROOT)}")
        except Exception as e:
            hint(f"[WARN] 创建 llm.yaml 失败: {e}")

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

    # 始终通过唯一的 generate 入口刷新所有 LLM 产物。维护一份 IDE 列表可避免
    # OpenCode、OpenWorker 等目标在 sync 时继续复制历史配置。
    if "llm" in scope and llm_yaml_file.exists():
        cmd_generate(argparse.Namespace(provider=None, protocol=None))

    # skill 源（三源并集）:
    #   1. template/skills/   - 内置预置技能（只读）
    #   2. .agents/skills/     - 项目级安装的技能（下载/插件）
    #   3. config/skills/      - 项目级复制的技能
    source_skills = [PROJECT_ROOT / "template" / "skills"]
    agents_skills = PROJECT_ROOT / ".agents" / "skills"
    if agents_skills.exists():
        source_skills.append(agents_skills)
    project_skills = PROJECT_ROOT / "config" / "skills"
    if project_skills.exists():
        source_skills.append(project_skills)

    # 从 skill.yaml 读取启用清单（项目级），只同步启用的 skill
    skill_yaml = PROJECT_ROOT / "config" / "skills" / "skill.yaml"
    if "skill" in scope and skill_yaml.exists():
        # 数据迁移：把 sources 记录但未进 enabled 的 skill 补入 enabled
        added = skills.sync_enabled_from_sources(skill_yaml)
        if added:
            hint(f"已自动启用 {added} 个历史安装的 skill（从 sources 补入 enabled）")
        enabled_set = skills.get_enabled_skills(skill_yaml)
        if enabled_set:
            # 合并命令行 --skills 白名单和 skill.yaml 的 enabled
            if include:
                include = include & enabled_set
            else:
                include = enabled_set
            hint(f"skill.yaml enabled: {len(enabled_set)} skill(s)")

    source_agents_md = PROJECT_ROOT / "AGENTS.md"

    failures = []
    for t in targets:
        try:
            t.run(source_rules, source_mcp, source_skills, source_agents_md)
        except Exception as e:
            failures.append(t.name)
            print(f"{COLOR_RED}[ERROR] {t.name} sync failed: {e}{COLOR_RESET}")

    if failures:
        print(f"\n{COLOR_RED}[FAILED] {len(failures)} IDE(s): {', '.join(failures)}{COLOR_RESET}")
        return False

    print(f"\n{COLOR_GREEN}[DONE] Synced to {len(targets)} IDE(s){COLOR_RESET}")
    return True


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


def cmd_plugin_build(args):
    """从来源构建插件 zip（analyze → download → generate → package → 可选 publish）。"""
    from agentctl.lib import plugin_builder as pb

    builder = pb.PluginBuilder(PROJECT_ROOT)

    # 1. 分析来源
    header(f"Building plugin from: {args.source}")
    print(f"\n{COLOR_CYAN}==> Step 1/4: Analyzing source{COLOR_RESET}")
    ai_mode = getattr(args, "ai", False)
    meta = builder.analyze_source(args.source, ai=ai_mode)
    print(f"  Name: {meta.name}")
    print(f"  Description: {meta.description[:80]}")
    if meta.skills:
        print(f"  Skills: {', '.join(s.name for s in meta.skills)}")
    if meta.mcp_servers:
        print(f"  MCP Servers: {', '.join(meta.mcp_servers.keys())}")

    # 2. 命令行参数覆盖
    if args.name:
        meta.name = args.name
    if args.version:
        meta.version = args.version
    if args.description:
        meta.description = args.description
    if args.author:
        meta.author = args.author

    # 解析 --mcp 参数（名称:command:arg1:arg2:...）
    if args.mcp:
        for raw in args.mcp:
            name, config = pb.parse_mcp_arg(raw)
            meta.mcp_servers[name] = config

    # 解析 --env 参数（KEY:description:default:required）
    if args.env:
        for raw in args.env:
            key, spec = pb.parse_env_arg(raw)
            meta.env_vars[key] = spec

    # 过滤 skills
    selected_skills = None
    if args.skills:
        selected = [s.strip() for s in args.skills.split(",") if s.strip()]
        selected_skills = selected
        meta.skills = [s for s in meta.skills if s.name in selected]

    # 3. 下载 skills
    print(f"\n{COLOR_CYAN}==> Step 2/4: Downloading skills{COLOR_RESET}")
    skill_dirs = builder.download_skills(meta, selected=selected_skills)

    # 4. 生成 YAML + 打包
    print(f"\n{COLOR_CYAN}==> Step 3/4: Generating plugin.yaml & packaging{COLOR_RESET}")
    mode_label = "inline (MCP+envVars 内联)" if args.mode == "inline" else "split (mcp.yaml + keys.yaml)"
    print(f"  打包模式: {mode_label}")
    cfg = builder.generate_yaml(meta)
    output_dir = Path(args.output) if args.output else PROJECT_ROOT / "config" / "plugins"
    zip_path = builder.package(cfg, skill_dirs, mode=args.mode, output_dir=output_dir)
    print(f"\n{COLOR_GREEN}[OK] 插件打包完成: {zip_path}{COLOR_RESET}")

    # 5. 发布（可选）
    if args.publish:
        print(f"\n{COLOR_CYAN}==> Step 4/4: Publishing to marketplace{COLOR_RESET}")
        from agentctl.lib import auth as market_auth
        token = market_auth.get_token()
        if not token:
            error("未登录，请先执行: agentctl plugin auth login")
            return False
        server_url = market_auth.get_server_url()
        tags = args.tags.split(",") if args.tags else meta.tags
        try:
            result = builder.publish(
                zip_path, server_url, token,
                tags=tags, scope=args.scope, team_id=args.team_id,
            )
            info(f"[OK] 发布成功: {result.get('name', meta.name)}")
        except Exception as e:
            error(f"发布失败: {e}")
            return False
    else:
        hint(f"\n提示：如需发布，执行: agentctl plugin publish {zip_path}")

    return True


def cmd_plugin_publish(args):
    """发布已有 zip 到市场。"""
    from agentctl.lib import auth as market_auth
    from agentctl.lib import plugin_builder as pb

    zip_path = Path(args.zip_file).resolve()
    if not zip_path.exists():
        error(f"文件不存在: {zip_path}")
        return False

    token = market_auth.get_token()
    if not token:
        error("未登录，请先执行: agentctl plugin auth login")
        return False

    server_url = market_auth.get_server_url()
    tags = args.tags.split(",") if args.tags else []

    builder = pb.PluginBuilder(PROJECT_ROOT)
    try:
        result = builder.publish(
            zip_path, server_url, token,
            tags=tags, scope=args.scope, team_id=args.team_id,
        )
        info(f"[OK] 发布成功: {result.get('name', zip_path.stem)}")
        return True
    except Exception as e:
        error(f"发布失败: {e}")
        return False


def cmd_plugin_auth(args):
    """市场认证（login/register/whoami/logout）。"""
    from agentctl.lib import auth as market_auth

    sub = args.sub

    if sub == "login":
        if not args.username or not args.password:
            error("请提供 --username 和 --password")
            return False
        try:
            data = market_auth.login(args.username, args.password, args.server)
            user = data.get("user", {})
            info(f"[OK] 登录成功: {user.get('username')} (role: {user.get('role')})")
            hint(f"服务器: {data.get('server_url')}")
        except Exception as e:
            error(f"登录失败: {e}")
            return False

    elif sub == "register":
        if not args.username or not args.password:
            error("请提供 --username 和 --password")
            return False
        try:
            data = market_auth.register(
                args.username, args.password, args.email or "", args.server
            )
            user = data.get("user", {})
            info(f"[OK] 注册成功: {user.get('username')} (role: {user.get('role')})")
            hint(f"服务器: {data.get('server_url')}")
        except Exception as e:
            error(f"注册失败: {e}")
            return False

    elif sub == "whoami":
        if not market_auth.is_logged_in():
            warn("未登录")
            return False
        user = market_auth.whoami()
        if user:
            info(f"用户: {user.get('username')}")
            print(f"  ID: {user.get('id')}")
            print(f"  Email: {user.get('email', '-')}")
            print(f"  Role: {user.get('role')}")
        else:
            error("token 无效或已过期，请重新登录")
            return False

    elif sub == "logout":
        if market_auth.logout():
            info("[OK] 已退出登录")
        else:
            warn("未登录，无需退出")

    return True


def cmd_skill_list(args):
    """从 skills-index.csv 列出所有技能。"""
    csv_path = PROJECT_ROOT / args.csv
    plugins.list_skills_from_csv(csv_path)


def cmd_skill_enable(args):
    """启用技能（加入 skill.yaml 的 enabled 列表）。"""
    skill_yaml = PROJECT_ROOT / "config" / "skills" / "skill.yaml"
    added = skills.enable_skill(skill_yaml, args.skill_name)
    if added:
        print(f"{COLOR_GREEN}[OK] 已启用技能: {args.skill_name}{COLOR_RESET}")
    else:
        print(f"{COLOR_DARKGRAY}[~] 技能已启用: {args.skill_name}{COLOR_RESET}")


def cmd_skill_disable(args):
    """禁用技能（从 skill.yaml 的 enabled 列表移除）。"""
    skill_yaml = PROJECT_ROOT / "config" / "skills" / "skill.yaml"
    removed = skills.disable_skill(skill_yaml, args.skill_name)
    if removed:
        print(f"{COLOR_GREEN}[OK] 已禁用技能: {args.skill_name}{COLOR_RESET}")
    else:
        print(f"{COLOR_DARKGRAY}[~] 技能未启用: {args.skill_name}{COLOR_RESET}")


def cmd_skill_scan(args):
    """扫描本地技能，显示状态。"""
    skill_yaml = PROJECT_ROOT / "config" / "skills" / "skill.yaml"
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

    # plugin build — 从来源构建插件 zip
    p_build = p_plugin_sub.add_parser("build", help="从来源构建插件 zip（GitHub/URL/本地目录）")
    p_build.add_argument("source", help="来源：GitHub(owner/repo)、文章 URL、本地目录路径")
    p_build.add_argument("--name", default=None, help="插件名称（覆盖自动分析结果）")
    p_build.add_argument("--version", default=None, help="插件版本")
    p_build.add_argument("--description", default=None, help="插件描述")
    p_build.add_argument("--author", default=None, help="作者")
    p_build.add_argument("--skills", default=None,
                         help="指定要打包的 skill（逗号分隔），省略则全部")
    p_build.add_argument("--mcp", action="append", default=None,
                         help="MCP server 配置（名称:command:arg1:arg2:...），可多次指定")
    p_build.add_argument("--env", action="append", default=None,
                         help="环境变量声明（KEY:description:default:required），可多次指定")
    p_build.add_argument("--mode", choices=["inline", "split"], default="inline",
                         help="打包模式：inline（MCP+envVars 内联 plugin.yaml）或 split（拆分 mcp.yaml + keys.yaml）")
    p_build.add_argument("--ai", action="store_true", help="启用 AI 分析来源内容（从文章 URL 构建时推荐）")
    p_build.add_argument("--output", default=None, help="输出目录（默认 config/plugins）")
    p_build.add_argument("--publish", action="store_true", help="构建后自动发布到市场")
    p_build.add_argument("--scope", default="public", choices=["public", "team"],
                         help="发布范围（--publish 时生效）")
    p_build.add_argument("--tags", default=None, help="标签（逗号分隔，--publish 时生效）")
    p_build.add_argument("--team-id", type=int, default=None,
                         help="团队 ID（scope=team 时需要）")
    p_build.set_defaults(func=cmd_plugin_build)

    # plugin publish — 发布已有 zip
    p_pub = p_plugin_sub.add_parser("publish", help="发布 zip 到市场")
    p_pub.add_argument("zip_file", help="zip 文件路径")
    p_pub.add_argument("--scope", default="public", choices=["public", "team"], help="发布范围")
    p_pub.add_argument("--tags", default=None, help="标签（逗号分隔）")
    p_pub.add_argument("--team-id", type=int, default=None, help="团队 ID（scope=team 时需要）")
    p_pub.set_defaults(func=cmd_plugin_publish)

    # plugin auth — 市场认证
    p_auth = p_plugin_sub.add_parser("auth", help="市场认证（login/register/whoami/logout）")
    p_auth_sub = p_auth.add_subparsers(dest="sub", required=True)

    p_auth_login = p_auth_sub.add_parser("login", help="登录市场")
    p_auth_login.add_argument("--username", "-u", required=True, help="用户名")
    p_auth_login.add_argument("--password", "-p", required=True, help="密码")
    p_auth_login.add_argument("--server", default=None, help="服务器地址（默认使用已保存的）")
    p_auth_login.set_defaults(func=cmd_plugin_auth)

    p_auth_reg = p_auth_sub.add_parser("register", help="注册账号")
    p_auth_reg.add_argument("--username", "-u", required=True, help="用户名")
    p_auth_reg.add_argument("--password", "-p", required=True, help="密码（至少 8 位）")
    p_auth_reg.add_argument("--email", default="", help="邮箱")
    p_auth_reg.add_argument("--server", default=None, help="服务器地址")
    p_auth_reg.set_defaults(func=cmd_plugin_auth)

    p_auth_who = p_auth_sub.add_parser("whoami", help="查看当前登录用户")
    p_auth_who.set_defaults(func=cmd_plugin_auth)

    p_auth_out = p_auth_sub.add_parser("logout", help="退出登录")
    p_auth_out.set_defaults(func=cmd_plugin_auth)

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
    result = args.func(args)
    if result is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
