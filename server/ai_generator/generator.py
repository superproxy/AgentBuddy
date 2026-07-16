"""AI 插件生成器核心逻辑。

使用 LangChain + LLM 根据用户需求描述生成完整 plugin.yaml。
从 config/llm/llm.yaml 读取 API Key 和 provider 配置。
"""
import sys
import os
import json
import yaml
from pathlib import Path
from typing import Generator


def _load_llm_config(project_root: Path) -> dict:
    """从 config/llm/llm.yaml 加载 LLM provider 配置。"""
    llm_file = project_root / "config" / "llm" / "llm.yaml"
    if not llm_file.exists():
        return {}
    try:
        with open(llm_file, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _get_active_provider(llm_config: dict, preferred_model: str = "") -> dict:
    """获取当前活跃的 LLM provider 配置。

    Args:
        preferred_model: 优先选择包含此模型的 provider（如 "glm-5-2-260617"）
    """
    llm = llm_config.get("llm", {})
    active = llm.get("_active_provider", "")

    def _try_provider(name: str) -> dict:
        val = llm.get(name)
        if not isinstance(val, dict):
            return {}
        for proto in ("openai", "anthropic"):
            if proto in val and isinstance(val[proto], dict):
                cfg = val[proto]
                if not cfg.get("api_key"):
                    continue
                models = cfg.get("models")
                if isinstance(models, dict):
                    model_keys = list(models.keys())
                elif isinstance(models, list):
                    model_keys = models
                else:
                    model_keys = []
                # 优先匹配 preferred_model
                if preferred_model and preferred_model in model_keys:
                    model = preferred_model
                elif model_keys:
                    model = model_keys[0]
                else:
                    model = "gpt-4o"
                return {
                    "provider": name,
                    "protocol": proto,
                    "base_url": cfg.get("base_url", ""),
                    "api_key": cfg.get("api_key", ""),
                    "model": model,
                }
        return {}

    # 1. 如果有 preferred_model，遍历所有 provider 找包含该模型的
    if preferred_model:
        for name in llm:
            if name.startswith("_"):
                continue
            result = _try_provider(name)
            if result and preferred_model in result.get("model", ""):
                return result
        # 没找到精确匹配，尝试部分匹配
        for name in llm:
            if name.startswith("_"):
                continue
            result = _try_provider(name)
            if result:
                # 检查 provider 的 model 列表是否包含 preferred_model
                val = llm.get(name, {})
                for proto in ("openai", "anthropic"):
                    cfg = val.get(proto, {})
                    models = cfg.get("models")
                    if isinstance(models, dict) and preferred_model in models:
                        result["model"] = preferred_model
                        return result
                    if isinstance(models, list) and preferred_model in models:
                        result["model"] = preferred_model
                        return result

    # 2. 使用活跃 provider
    if active and active in llm:
        result = _try_provider(active)
        if result:
            return result

    # 3. 回退：遍历找第一个有 api_key 的
    for name in llm:
        if name.startswith("_"):
            continue
        result = _try_provider(name)
        if result:
            return result
    return {}


def _load_local_skills(project_root: Path) -> list[dict]:
    """加载本地技能列表（扫描三个目录 + skills-index.csv）。"""
    skills = []
    seen = set()
    # 从 skills-index.csv 加载
    csv_file = project_root / "template" / "skills" / "skills-index.csv"
    if csv_file.exists():
        import csv as _csv
        try:
            with open(csv_file, encoding="utf-8") as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    name = row.get("skill_name", "").strip()
                    if not name or name in seen:
                        continue
                    seen.add(name)
                    skills.append({
                        "name": name,
                        "category": row.get("category", "").strip(),
                        "description": row.get("description", "").strip(),
                        "source_type": row.get("source_type", "local").strip(),
                        "source": row.get("source", "").strip(),
                    })
        except Exception:
            pass
    # 扫描磁盘上存在但不在 CSV 中的技能目录
    for scan_dir in [
        project_root / "template" / "skills",
        project_root / "config" / "skills",
        project_root / ".agents" / "skills",
    ]:
        if not scan_dir.exists():
            continue
        for item in sorted(scan_dir.iterdir()):
            if not item.is_dir() or item.name.startswith(".") or item.name in seen:
                continue
            # 检查是否有 SKILL.md
            skill_md = item / "SKILL.md"
            desc = ""
            if skill_md.exists():
                try:
                    content = skill_md.read_text(encoding="utf-8")[:500]
                    # 从 frontmatter 或第一行提取描述
                    for line in content.split("\n"):
                        line = line.strip()
                        if line.startswith("description:"):
                            desc = line.split(":", 1)[1].strip().strip('"').strip("'")
                            break
                        if line and not line.startswith("#") and not line.startswith("---"):
                            desc = line
                            break
                except Exception:
                    pass
            seen.add(item.name)
            skills.append({
                "name": item.name,
                "category": "",
                "description": desc,
                "source_type": "local",
                "source": item.name,
            })
    return skills


def _load_mcp_servers(project_root: Path) -> list[dict]:
    """加载本地 MCP 服务器配置。"""
    mcp_file = project_root / "config" / "mcp" / "mcp.yaml"
    if not mcp_file.exists():
        return []
    try:
        data = yaml.safe_load(mcp_file.read_text(encoding="utf-8"))
        servers = data.get("mcpServers", {}) if isinstance(data, dict) else {}
        result = []
        for name, cfg in servers.items():
            if not isinstance(cfg, dict):
                continue
            if cfg.get("disabled"):
                continue
            entry = {"name": name, "type": cfg.get("type", "stdio")}
            if cfg.get("command"):
                cmd = cfg["command"]
                args = cfg.get("args", [])
                entry["command"] = f"{cmd} {' '.join(args)}" if args else cmd
            if cfg.get("url"):
                entry["url"] = cfg["url"]
            result.append(entry)
        return result
    except Exception:
        return []


# ============================================================
# 外部市场联网搜索
# ============================================================
# 停用词，提取关键词时过滤
_STOP_WORDS = {
    "的", "了", "和", "是", "在", "我", "有", "一个", "需要", "给我",
    "打包", "相关", "技能", "智能体", "创建", "生成", "插件", "工具", "级别",
    "the", "a", "an", "need", "want", "create", "build", "plugin", "agent",
}


def _extract_keywords(prompt: str) -> list[str]:
    """从用户需求描述中提取搜索关键词。

    简单分词：中英文混合，按空格/标点分词，过滤停用词。
    """
    import re
    # 中英文分词：空格 + 标点
    tokens = re.split(r'[\s,，。、；;:：！!？?（）()\[\]【】]+', prompt.strip())
    keywords = []
    for t in tokens:
        t = t.strip()
        if not t or len(t) < 2:
            continue
        if t.lower() in _STOP_WORDS:
            continue
        keywords.append(t)
    return keywords[:3]  # 最多3个关键词


def _search_external_resources(prompt: str) -> dict:
    """搜索外部市场（skill market + mcp market）。

    Returns:
        {"skills": [...], "mcps": [...], "errors": [...]}
    """
    from lib.skill_market import search_skill_market
    from lib.mcp_market import search_mcp_market

    keywords = _extract_keywords(prompt)
    if not keywords:
        # 用整个 prompt 作为搜索词
        keywords = [prompt[:30]]

    skills = []
    mcps = []
    errors = []

    for kw in keywords[:2]:  # 最多搜2个关键词避免太慢
        # 搜索 skills
        try:
            sk = search_skill_market(kw, limit_per_source=5)
            if sk.get("ok"):
                for item in sk.get("data", [])[:8]:
                    skills.append({
                        "name": item.get("name", ""),
                        "description": item.get("description", ""),
                        "source": item.get("source_label", ""),
                        "install": item.get("install_command", ""),
                    })
        except Exception as e:
            errors.append(f"skill search ({kw}): {e}")

        # 搜索 MCP
        try:
            mc = search_mcp_market(kw, limit_per_source=5)
            if mc.get("ok"):
                for item in mc.get("data", [])[:8]:
                    mcps.append({
                        "name": item.get("name", ""),
                        "description": item.get("description", ""),
                        "source": item.get("source_label", ""),
                        "homepage": item.get("homepage", ""),
                    })
        except Exception as e:
            errors.append(f"mcp search ({kw}): {e}")

    # 去重
    skills = _dedupe_by_key(skills, "name")
    mcps = _dedupe_by_key(mcps, "name")

    return {"skills": skills[:20], "mcps": mcps[:15], "errors": errors}


def _dedupe_by_key(items: list[dict], key: str) -> list[dict]:
    """按指定 key 去重，保留第一个。"""
    seen = set()
    result = []
    for item in items:
        val = item.get(key, "")
        if val and val not in seen:
            seen.add(val)
            result.append(item)
    return result


def _build_system_prompt(project_root: Path, external_resources: dict | None = None, level: str = "") -> str:
    """构建 system prompt，包含所有本地资源 + 外部搜索结果 + 级别指导。

    Args:
        project_root: 项目根目录
        external_resources: 外部市场搜索结果 {skills, mcps, errors}
        level: 工具集级别 basic/standard/expert
    """
    skills_dir = Path(__file__).parent / "skills"
    parts = []
    # 1. 加载 skill 定义（设计指令 + 输出规范）
    for md in sorted(skills_dir.glob("*.md")):
        parts.append(md.read_text(encoding="utf-8"))

    parts.append("\n\n## 当前项目可用资源\n")
    parts.append("根据用户需求，从以下资源中搜索、选择、融合最合适的组合。\n")
    parts.append("只选择与需求相关的资源，不要全选。\n\n")

    # 2. 本地 Skills
    skills = _load_local_skills(project_root)
    if skills:
        parts.append(f"### 可用 Skills（{len(skills)} 个）\n")
        for s in skills:
            cat = f" [{s['category']}]" if s.get("category") else ""
            desc = f" — {s['description']}" if s.get("description") else ""
            parts.append(f"- skill: {s['name']}{cat}{desc}\n")
        parts.append("\n")

    # 3. MCP 服务
    mcps = _load_mcp_servers(project_root)
    if mcps:
        parts.append(f"### 可用 MCP 服务（{len(mcps)} 个）\n")
        for m in mcps:
            cmd = m.get("command", m.get("url", ""))
            parts.append(f"- mcp: {m['name']} ({m.get('type', 'stdio')}) — {cmd}\n")
        parts.append("\n")

    # 4. Subagent 角色（含描述）
    sa_file = project_root / "config" / "subagent" / "subagent.yaml"
    if sa_file.exists():
        try:
            data = yaml.safe_load(sa_file.read_text(encoding="utf-8"))
            sa_list = data.get("subagents") or []
            if sa_list:
                parts.append(f"### 可用 Subagent（{len(sa_list)} 个）\n")
                for s in sa_list:
                    name = s.get("name", "")
                    role = s.get("role", "")
                    desc = s.get("desc", "")
                    parts.append(f"- subagent: {name} [{role}] — {desc}\n")
                parts.append("\n")
        except Exception:
            pass

    # 5. Rules（含描述和分类）
    parts.append("### 可用 Rules\n")
    rules_count = 0
    for rules_dir in [project_root / "config" / "rules", project_root / "template" / "rules"]:
        if not rules_dir.exists():
            continue
        for md in sorted(rules_dir.rglob("*.md")):
            rel = md.relative_to(rules_dir)
            # 尝试从 frontmatter 提取 description
            desc = ""
            try:
                content = md.read_text(encoding="utf-8")[:300]
                for line in content.split("\n"):
                    line = line.strip()
                    if line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip().strip('"').strip("'")
                        break
            except Exception:
                pass
            parts.append(f"- rule: {rel}" + (f" — {desc}" if desc else "") + "\n")
            rules_count += 1
    parts.append(f"（共 {rules_count} 条）\n\n")

    # 6. Commands（含描述）
    cmd_file = project_root / "config" / "cmd" / "cmd.yaml"
    if cmd_file.exists():
        try:
            data = yaml.safe_load(cmd_file.read_text(encoding="utf-8"))
            cmd_list = data.get("commands") or []
            if cmd_list:
                parts.append(f"### 可用 Commands（{len(cmd_list)} 个）\n")
                for c in cmd_list:
                    name = c.get("name", "")
                    desc = c.get("description", "")
                    parts.append(f"- command: {name} — {desc}\n")
                parts.append("\n")
        except Exception:
            pass

    # 7. LLM Providers
    llm_cfg = _load_llm_config(project_root)
    llm = llm_cfg.get("llm", {})
    providers = [name for name in llm
                 if not name.startswith("_") and isinstance(llm[name], dict)]
    if providers:
        parts.append(f"### 可用 LLM Providers: {', '.join(providers)}\n")

    # 8. 外部市场搜索结果
    if external_resources and (external_resources.get("skills") or external_resources.get("mcps")):
        ext_skills = external_resources.get("skills", [])
        ext_mcps = external_resources.get("mcps", [])
        parts.append("\n## 外部市场搜索结果（联网搜索）\n")
        parts.append("以下是从外部市场搜索到的可用资源，可以引用到插件配置中。\n\n")

        if ext_skills:
            parts.append(f"### 外部市场 Skills（{len(ext_skills)} 个）\n")
            for s in ext_skills:
                name = s.get("name", "")
                desc = s.get("description", "")[:80]
                src = s.get("source", "")
                install = s.get("install", "")
                parts.append(f"- skill: {name} ({src}) — {desc}")
                if install:
                    parts.append(f" | install: {install[:80]}")
                parts.append("\n")
            parts.append("\n")

        if ext_mcps:
            parts.append(f"### 外部市场 MCP 服务（{len(ext_mcps)} 个）\n")
            for m in ext_mcps:
                name = m.get("name", "")
                desc = m.get("description", "")[:80]
                src = m.get("source", "")
                parts.append(f"- mcp: {name} ({src}) — {desc}\n")
            parts.append("\n")

    # 9. 工具集级别指导
    if level:
        level_guides = {
            "basic": (
                "\n## 工具集级别：基础（basic）\n"
                "- 选择 1-3 个最核心的 skill\n"
                "- 不配置 MCP 服务（除非用户明确要求）\n"
                "- 配置 1 个 subagent 角色\n"
                "- 选择 1-2 条最相关的 rules\n"
                "- 配置 commit 命令\n"
                "- hooks: false\n"
            ),
            "standard": (
                "\n## 工具集级别：进阶（standard）\n"
                "- 选择 3-6 个相关 skill\n"
                "- 配置 1-2 个 MCP 服务（按需）\n"
                "- 配置 2-3 个 subagent 角色协作\n"
                "- 选择多类 rules（编码+测试+安全等）\n"
                "- 配置 commit, review, test 等命令\n"
                "- hooks: false\n"
            ),
            "expert": (
                "\n## 工具集级别：专家（expert）\n"
                "- 选择 6+ 个相关 skill（覆盖全流程）\n"
                "- 配置 2+ 个 MCP 服务\n"
                "- 配置所有相关 subagent 角色\n"
                "- 选择全部相关类别的 rules\n"
                "- 配置所有相关命令\n"
                "- hooks: true（启用自动化行为）\n"
            ),
        }
        guide = level_guides.get(level.lower(), "")
        if guide:
            parts.append(guide)

    return "\n".join(parts)


# ============================================================
# Agent 工具函数（供 LLM function calling）
# ============================================================

def _load_tavily_key(project_root: Path) -> str:
    """从 config/mcp/mcp.yaml 读取 Tavily API Key。"""
    mcp_file = project_root / "config" / "mcp" / "mcp.yaml"
    if not mcp_file.exists():
        return ""
    try:
        data = yaml.safe_load(mcp_file.read_text(encoding="utf-8"))
        servers = data.get("mcpServers", {}) if isinstance(data, dict) else {}
        tavily = servers.get("tavily-mcp", {})
        env = tavily.get("env", {}) if isinstance(tavily, dict) else {}
        return env.get("TAVILY_API_KEY", "")
    except Exception:
        return ""


def _tavily_search(query: str, tavily_key: str) -> list[dict]:
    """通过 Tavily REST API 进行 Google 搜索。

    Returns:
        [{title, url, content}, ...] 最多 5 条
    """
    if not tavily_key:
        return [{"error": "Tavily API Key 未配置"}]
    import requests
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            headers={
                "Authorization": f"Bearer {tavily_key}",
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "search_depth": "basic",
                "max_results": 5,
                "include_answer": True,
            },
            timeout=15,
        )
        if r.status_code != 200:
            return [{"error": f"Tavily API 错误: {r.status_code}"}]
        data = r.json()
        results = []
        # AI 摘要
        answer = data.get("answer", "")
        if answer:
            results.append({"title": "AI 摘要", "url": "", "content": answer[:300]})
        # 搜索结果
        for item in data.get("results", [])[:5]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", "")[:200],
            })
        return results
    except Exception as e:
        return [{"error": f"搜索失败: {e}"}]


def _search_market(query: str, search_type: str = "both") -> dict:
    """搜索本地+外部 skill/mcp 市场。

    Args:
        query: 搜索关键词
        search_type: "skill" | "mcp" | "both"
    """
    scripts_dir = str(Path(__file__).resolve().parent.parent.parent / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    result = {"skills": [], "mcps": []}
    if search_type in ("skill", "both"):
        try:
            from lib.skill_market import search_skill_market
            sk = search_skill_market(query, limit_per_source=5)
            if sk.get("ok"):
                for item in sk.get("data", [])[:8]:
                    result["skills"].append({
                        "name": item.get("name", ""),
                        "description": item.get("description", "")[:100],
                        "source": item.get("source_label", ""),
                        "install": item.get("install_command", "")[:100],
                    })
        except Exception as e:
            result["skills"].append({"error": str(e)})

    if search_type in ("mcp", "both"):
        try:
            from lib.mcp_market import search_mcp_market
            mc = search_mcp_market(query, limit_per_source=5)
            if mc.get("ok"):
                for item in mc.get("data", [])[:8]:
                    result["mcps"].append({
                        "name": item.get("name", ""),
                        "description": item.get("description", "")[:100],
                        "source": item.get("source_label", ""),
                        "homepage": item.get("homepage", ""),
                    })
        except Exception as e:
            result["mcps"].append({"error": str(e)})

    return result


# 工具定义（OpenAI function calling 格式）
_AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索互联网获取最新信息、最佳实践、推荐的工具和技能。用于了解某项技术的推荐技能、MCP 服务或开发规范。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询，如 'Vue 3 best practices skills' 或 'Java Spring Boot MCP server'"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_market",
            "description": "搜索本地和外部市场的 Skills 和 MCP 服务。用于查找可用的技能和工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "type": {"type": "string", "enum": ["skill", "mcp", "both"], "description": "搜索类型，默认 both"}
                },
                "required": ["query"]
            }
        }
    },
]


def generate_plugin(
    prompt: str,
    project_root: Path,
    preferred_model: str = "",
    level: str = "",
) -> Generator[str, None, None]:
    """根据用户需求描述生成 plugin.yaml，流式输出。

    Args:
        prompt: 用户需求描述
        project_root: 项目根目录
        preferred_model: 优先使用的模型 ID（如 "glm-5-2-260617"）
        level: 工具集级别 basic/standard/expert（可选）

    Yields:
        LLM 生成的文本片段（SSE 行内容）。
    """
    llm_cfg = _load_llm_config(project_root)
    provider = _get_active_provider(llm_cfg, preferred_model=preferred_model)

    if not provider.get("api_key"):
        yield "[ERROR] 未找到已配置的 LLM provider（需要 api_key），请在 LLM 配置 tab 设置"
        yield "[DONE]"
        return

    # 读取 Tavily API Key
    tavily_key = _load_tavily_key(project_root)

    # 构建 system prompt（含本地资源 + 级别指导）
    system_prompt = _build_system_prompt(project_root, level=level)

    yield f"[INFO] 使用 {provider['provider']}/{provider['protocol']} ({provider['model']}) 生成中..."
    if level:
        yield f"[INFO] 工具集级别: {level}"
    if tavily_key:
        yield "[INFO] 已启用联网搜索（Tavily）"
    yield f"[INFO] 需求: {prompt}"
    yield ""

    try:
        from openai import OpenAI

        base_url = provider["base_url"] or "https://api.openai.com/v1"
        client = OpenAI(api_key=provider["api_key"], base_url=base_url)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请根据以下需求生成完整的 plugin.yaml 配置：\n\n{prompt}\n\n"
              "你可以使用工具搜索相关信息：\n"
              "1. web_search: 搜索互联网获取最佳实践、推荐技能和 MCP 服务\n"
              "2. search_market: 搜索本地和外部市场的 Skills 和 MCP\n"
              "搜索完成后，直接输出 plugin.yaml 配置。"},
        ]

        max_rounds = 5
        for round_num in range(max_rounds):
            # 非流式调用（支持 function calling）
            response = client.chat.completions.create(
                model=provider["model"],
                messages=messages,
                tools=_AGENT_TOOLS,
                tool_choice="auto",
                temperature=0.7,
            )

            msg = response.choices[0].message

            # 检查是否有工具调用
            if msg.tool_calls:
                # 将 assistant 消息（含 tool_calls）加入历史
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                })

                for tc in msg.tool_calls:
                    func_name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except Exception:
                        args = {}

                    yield f"[SEARCH] 调用 {func_name}({args.get('query', '')[:50]})"

                    # 执行工具
                    if func_name == "web_search":
                        results = _tavily_search(args.get("query", ""), tavily_key)
                        summary = f"{len(results)} 条结果"
                        yield f"[SEARCH] web_search 完成: {summary}"
                    elif func_name == "search_market":
                        results = _search_market(args.get("query", ""), args.get("type", "both"))
                        summary = f"{len(results.get('skills', []))} skills, {len(results.get('mcps', []))} mcps"
                        yield f"[SEARCH] search_market 完成: {summary}"
                    else:
                        results = [{"error": f"未知工具: {func_name}"}]
                        yield f"[SEARCH] 未知工具: {func_name}"

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(results, ensure_ascii=False),
                    })

                continue  # 继续下一轮

            # 没有工具调用，LLM 输出最终结果
            if msg.content:
                yield msg.content
            yield ""
            yield "[DONE]"
            return

        # 达到最大轮次
        yield "[WARN] 达到最大搜索轮次（5轮），输出当前结果"
        # 最后一轮不带工具调用
        response = client.chat.completions.create(
            model=provider["model"],
            messages=messages,
            temperature=0.7,
        )
        content = response.choices[0].message.content or ""
        yield content
        yield "[DONE]"

    except ImportError:
        yield "[ERROR] openai SDK 未安装，请执行: pip install openai"
        yield "[DONE]"
    except Exception as e:
        yield f"[ERROR] 生成失败: {e}"
        yield "[DONE]"


# ============================================================
# 多轮对话会话管理
# ============================================================
import uuid as _uuid

# 内存会话存储：{session_id: {"messages": [...], "level": "...", "config": "...", "project_root": Path}}
_sessions: dict[str, dict] = {}


def create_session(level: str = "") -> str:
    """创建新会话，返回 session_id。"""
    sid = _uuid.uuid4().hex[:12]
    _sessions[sid] = {
        "messages": [],
        "level": level,
        "config": "",
        "project_root": None,
    }
    return sid


def get_session(sid: str) -> dict | None:
    return _sessions.get(sid)


def clear_session(sid: str) -> bool:
    if sid in _sessions:
        del _sessions[sid]
        return True
    return False


def get_session_config(sid: str) -> str:
    """获取会话中最新的生成的 YAML 配置。"""
    session = _sessions.get(sid)
    return session.get("config", "") if session else ""


def generate_plugin_chat(
    session_id: str,
    user_message: str,
    project_root: Path,
    preferred_model: str = "",
) -> Generator[str, None, None]:
    """多轮对话生成插件，携带历史消息。

    每次调用追加一条 user 消息，运行 Agent 循环，输出回复。
    支持用户后续优化请求（如"增加一个 MCP"、"减少 skills"）。

    SSE 标记协议：
        [TURN] N          — 轮次开始
        [TOOL] name(args) — 工具调用
        [TOOL_RESULT] N条 — 工具结果摘要
        [CONFIG]          — YAML 配置内容开始
        [DONE]            — 本轮结束
    """
    session = _sessions.get(session_id)
    if not session:
        yield "[ERROR] 会话不存在，请重新开始"
        yield "[DONE]"
        return

    level = session.get("level", "")
    llm_cfg = _load_llm_config(project_root)
    provider = _get_active_provider(llm_cfg, preferred_model=preferred_model)

    if not provider.get("api_key"):
        yield "[ERROR] 未找到已配置的 LLM provider（需要 api_key），请在 LLM 配置 tab 设置"
        yield "[DONE]"
        return

    tavily_key = _load_tavily_key(project_root)

    # 首次对话：构建 system prompt
    if not session["messages"]:
        system_prompt = _build_system_prompt(project_root, level=level)
        session["messages"].append({"role": "system", "content": system_prompt})
        yield f"[INFO] 使用 {provider['provider']}/{provider['protocol']} ({provider['model']})"
        if level:
            yield f"[INFO] 工具集级别: {level}"
        if tavily_key:
            yield "[INFO] 已启用联网搜索（Tavily + 市场搜索）"

    # 追加用户消息
    session["messages"].append({"role": "user", "content": user_message})

    yield f"[TURN] {len([m for m in session['messages'] if m['role'] == 'user'])}"
    yield f"[USER] {user_message}"
    yield ""

    try:
        from openai import OpenAI

        base_url = provider["base_url"] or "https://api.openai.com/v1"
        client = OpenAI(api_key=provider["api_key"], base_url=base_url)

        max_rounds = 5
        final_content = ""

        for round_num in range(max_rounds):
            response = client.chat.completions.create(
                model=provider["model"],
                messages=session["messages"],
                tools=_AGENT_TOOLS,
                tool_choice="auto",
                temperature=0.7,
            )

            msg = response.choices[0].message

            if msg.tool_calls:
                # 记录 assistant 消息（含 tool_calls）
                session["messages"].append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                })

                for tc in msg.tool_calls:
                    func_name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except Exception:
                        args = {}

                    query = args.get("query", "")[:50]
                    yield f"[TOOL] {func_name}({query})"

                    # 执行工具
                    if func_name == "web_search":
                        results = _tavily_search(args.get("query", ""), tavily_key)
                        summary = f"{len(results)} 条结果"
                    elif func_name == "search_market":
                        results = _search_market(args.get("query", ""), args.get("type", "both"))
                        summary = f"{len(results.get('skills', []))} skills, {len(results.get('mcps', []))} mcps"
                    else:
                        results = [{"error": f"未知工具: {func_name}"}]
                        summary = "未知工具"

                    yield f"[TOOL_RESULT] {summary}"

                    session["messages"].append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(results, ensure_ascii=False),
                    })

                continue  # 继续下一轮

            # 没有工具调用，LLM 输出文本
            final_content = msg.content or ""
            session["messages"].append({
                "role": "assistant",
                "content": final_content,
            })

            # 检查是否是问询模式（包含 [QUESTION]）
            if "[QUESTION]" in final_content:
                yield "[PHASE] interview"
                # 提取问题和推荐答案
                for line in final_content.split("\n"):
                    line = line.strip()
                    if line.startswith("[QUESTION]"):
                        yield line
                    elif line.startswith("[RECOMMEND]"):
                        yield line
                    elif line and not line.startswith("["):
                        yield line
                yield "[DONE]"
                return  # 等待用户回答后继续

            # 检查用户是否说"完成"/"直接生成"
            user_lower = user_message.lower()
            if any(kw in user_lower for kw in ["完成", "直接生成", "可以了", "生成吧", "done", "finish", "skip"]):
                # 用户要求生成，强制输出 YAML
                # 如果当前回复没有 YAML，再做一次不带工具的调用
                yaml_content = _extract_yaml(final_content)
                if not yaml_content:
                    gen_response = client.chat.completions.create(
                        model=provider["model"],
                        messages=session["messages"] + [
                            {"role": "user", "content": "请直接输出最终的 plugin.yaml 配置，不要提问。"}
                        ],
                        temperature=0.5,
                    )
                    final_content = gen_response.choices[0].message.content or ""
                    session["messages"].append({"role": "assistant", "content": final_content})
                    yaml_content = _extract_yaml(final_content)

                if yaml_content:
                    session["config"] = yaml_content
                    yield "[PHASE] generate"
                    yield "[CONFIG]"
                    yield yaml_content
                else:
                    yield final_content
                yield "[DONE]"
                return

            # 尝试提取 YAML（直接生成模式）
            yaml_content = _extract_yaml(final_content)
            if yaml_content:
                session["config"] = yaml_content
                yield "[PHASE] generate"
                yield "[CONFIG]"
                yield yaml_content
            else:
                yield final_content

            yield "[DONE]"
            return

        # 达到最大轮次
        yield "[WARN] 达到最大搜索轮次（5轮），强制生成"
        gen_response = client.chat.completions.create(
            model=provider["model"],
            messages=session["messages"] + [
                {"role": "user", "content": "请直接输出最终的 plugin.yaml 配置，不要再提问。"}
            ],
            temperature=0.5,
        )
        final_content = gen_response.choices[0].message.content or ""
        session["messages"].append({"role": "assistant", "content": final_content})
        yaml_content = _extract_yaml(final_content)
        if yaml_content:
            session["config"] = yaml_content
            yield "[PHASE] generate"
            yield "[CONFIG]"
            yield yaml_content
        else:
            yield final_content
        yield "[DONE]"

    except ImportError:
        yield "[ERROR] openai SDK 未安装，请执行: pip install openai"
        yield "[DONE]"
    except Exception as e:
        yield f"[ERROR] 生成失败: {e}"
        yield "[DONE]"


def _extract_yaml(text: str) -> str:
    """从 LLM 输出中提取 YAML 配置。"""
    # 1. 优先提取 ```yaml ... ``` 代码块
    import re
    match = re.search(r'```ya?ml?\n([\s\S]*?)```', text)
    if match:
        return match.group(1).strip()
    # 2. 找 name: 开头的 YAML
    lines = text.split("\n")
    filtered = [l for l in lines if not l.startswith("[") and not l.startswith("#")]
    for i, line in enumerate(filtered):
        if line.strip().startswith("name:"):
            # 向后扫描到非 YAML 行
            end = len(filtered)
            for j in range(i + 1, len(filtered)):
                trimmed = filtered[j].strip()
                if trimmed and not filtered[j].startswith(" ") and not filtered[j].startswith("\t") and not filtered[j].startswith("-"):
                    if not re.match(r'^[a-zA-Z_]+:', trimmed):
                        end = j
                        break
            return "\n".join(filtered[i:end]).strip()
    return ""
