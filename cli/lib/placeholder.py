"""占位符替换与未解析块剪枝。

兼容键剪枝：仅对 provider/providers/mcpServers/mcp 子项剪枝，
未填占位符的子项自动移除，避免污染最终配置。
"""
import json
import os
import re
from typing import Tuple


def _has_unresolved_placeholder(value) -> bool:
    """检测 value 是否含未解析的 ${VAR} 占位符（不含 ${VAR:-default} 形式）。"""
    if isinstance(value, str):
        for m in re.finditer(r"\$\{(\w+)(?::-.*?)?\}", value):
            if ":-" not in m.group(0):
                return True
        return False
    if isinstance(value, dict):
        return any(_has_unresolved_placeholder(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_unresolved_placeholder(v) for v in value)
    return False


PRUNE_TARGET_KEYS = ("provider", "providers", "mcpServers", "mcp")


def prune_unresolved_blocks(content: str) -> Tuple[str, dict]:
    """从 JSON 内容中剪枝含未解析占位符的容器子项。

    Returns:
        (pruned_content, pruned_map) — pruned_map 形如 {"mcpServers": ["xxx"]}
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return content, {}

    pruned: dict = {}

    def walk(node):
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if key in PRUNE_TARGET_KEYS and isinstance(value, dict):
                    for child_name in list(value.keys()):
                        if _has_unresolved_placeholder(value[child_name]):
                            pruned.setdefault(key, []).append(child_name)
                            del value[child_name]
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    if not pruned:
        return content, {}
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n", pruned


def resolve_str(text: str, env_map: dict) -> tuple:
    """解析字符串中的 ${VAR} 与 ${VAR:-default} 占位符。

    解析优先级：
      1. env_map（keys.yaml / mcp.yaml.mcp / flat_config）
      2. ${VAR:-default} 的 default 字面值
      3. 都没有 → 保留字面 ${VAR}（交由 prune 阶段处理）

    注意：不直接读取 OS 环境变量。环境变量由 keys.yaml 写入（见 llm.apply_keys_to_env），
    占位符解析时只认 keys.yaml 的值，确保配置可追溯。

    返回 (resolved_text, replaced_count)。
    """
    if not isinstance(text, str):
        return text, 0
    replaced = 0
    # 先处理 ${VAR:-default}（带默认值语法）
    for m in re.finditer(r"\$\{(\w+):-(.*?)\}", text):
        var_name = m.group(1)
        default_value = m.group(2)
        full_match = m.group(0)
        if env_map.get(var_name) is not None:
            resolved = env_map[var_name]
        else:
            resolved = default_value
        text = text.replace(full_match, resolved)
        replaced += 1
    # 再处理 ${VAR}（无默认值语法）
    for m in re.finditer(r"\$\{(\w+)\}", text):
        var_name = m.group(1)
        full_match = m.group(0)
        if env_map.get(var_name) is not None:
            text = text.replace(full_match, env_map[var_name])
            replaced += 1
        # 都没有时不替换，保留 ${VAR}（交由 prune 阶段处理）
    return text, replaced


def resolve_dict(obj, env_map: dict) -> tuple:
    """递归解析 dict/list/str 中的 ${VAR} 占位符（只认 env_map / keys.yaml）。

    返回 (resolved_obj, replaced_count)。
    """
    if isinstance(obj, str):
        return resolve_str(obj, env_map)
    if isinstance(obj, dict):
        total = 0
        for k in obj:
            obj[k], r = resolve_dict(obj[k], env_map)
            total += r
        return obj, total
    if isinstance(obj, list):
        total = 0
        for i in range(len(obj)):
            obj[i], r = resolve_dict(obj[i], env_map)
            total += r
        return obj, total
    return obj, 0


__all__ = [
    "prune_unresolved_blocks",
    "resolve_str",
    "resolve_dict",
    "_has_unresolved_placeholder",
    "PRUNE_TARGET_KEYS",
]
