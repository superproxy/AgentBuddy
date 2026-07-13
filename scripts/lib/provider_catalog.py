"""LLM Provider Catalog：从 llm-env-example.yaml 构建预设，并按 key/URL 推断厂商+协议。

对齐 OpenClaw 配置管道思路：
  Catalog（模板预设）→ Detect（Key 指纹 / URL）→（模糊时端点探测）→ Apply → Verify

Key 指纹来源（业界公开格式，2025–2026）：
  - OpenAI: sk-proj- / sk-svcacct- / sk-admin- / 遗留 sk-
  - Anthropic: sk-ant-api03- / sk-ant-oat01- / sk-ant-*
  - OpenRouter: sk-or-v1- / sk-or-
  - 智谱 BigModel / Z.ai: {32hex}.{16alnum}（无 sk- 前缀）
  - DashScope: sk- / Coding Plan: sk-sp-
  - DeepSeek / 火山 / Moonshot: 均为 sk-（需端点探测消歧）
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from lib.config_io import load_env_config_file

# ---------------------------------------------------------------------------
# API Key 指纹（按优先级；unique=True 表示可唯一锁定厂商/家族）
# ---------------------------------------------------------------------------
KEY_FINGERPRINTS: List[Dict[str, Any]] = [
    {
        "id": "anthropic",
        "pattern": re.compile(r"^sk-ant-(?:api0[13]|oat01|admin01)-[A-Za-z0-9_-]{20,}$", re.I),
        "providers": ["anthropic"],
        "protocol": "anthropic",
        "unique": True,
        "reason": "Anthropic Key 指纹 sk-ant-api03/oat01",
    },
    {
        "id": "anthropic_loose",
        "pattern": re.compile(r"^sk-ant-[A-Za-z0-9_-]{8,}$", re.I),
        "providers": ["anthropic"],
        "protocol": "anthropic",
        "unique": True,
        "reason": "Anthropic Key 前缀 sk-ant-",
    },
    {
        "id": "openrouter",
        "pattern": re.compile(r"^sk-or-v1-[A-Za-z0-9]+$", re.I),
        "providers": ["openrouter"],
        "protocol": "openai",
        "unique": True,
        "reason": "OpenRouter Key 指纹 sk-or-v1-",
    },
    {
        "id": "openrouter_loose",
        "pattern": re.compile(r"^sk-or-[A-Za-z0-9_-]+$", re.I),
        "providers": ["openrouter"],
        "protocol": "openai",
        "unique": True,
        "reason": "OpenRouter Key 前缀 sk-or-",
    },
    {
        "id": "openai_proj",
        "pattern": re.compile(r"^sk-proj-[A-Za-z0-9_-]{20,}$", re.I),
        "providers": ["openai"],
        "protocol": "openai",
        "unique": True,
        "reason": "OpenAI Project Key 指纹 sk-proj-",
    },
    {
        "id": "openai_svcacct",
        "pattern": re.compile(r"^sk-svcacct-[A-Za-z0-9_-]{20,}$", re.I),
        "providers": ["openai"],
        "protocol": "openai",
        "unique": True,
        "reason": "OpenAI Service Account Key 指纹 sk-svcacct-",
    },
    {
        "id": "dashscope_coding",
        "pattern": re.compile(r"^sk-sp-[A-Za-z0-9]+$", re.I),
        "providers": ["qwen"],
        "protocol": "openai",
        "unique": True,
        "reason": "DashScope Coding Plan Key 指纹 sk-sp-",
    },
    {
        # TruffleHog / 智谱官方：id(32hex).secret(16alnum)
        "id": "zhipu_zai",
        "pattern": re.compile(r"^[a-f0-9]{32}\.[A-Za-z0-9]{16}$"),
        "providers": ["bigmodel", "zai"],  # 同 Key 体系，端点不同 → 探测或让用户选
        "protocol": "openai",
        "unique": False,
        "family": "zhipu",
        "reason": "智谱/Z.ai Key 指纹 {32hex}.{16alnum}",
        "probe_providers": ["bigmodel", "zai", "bigmodelCoding", "zaiCoding"],
    },
    {
        # DeepSeek 官方常见 sk- + 恰好 32 hex（对齐 llm-key-validator）
        "id": "deepseek_hex",
        "pattern": re.compile(r"^sk-[a-f0-9]{32}$", re.I),
        "providers": ["deepseek"],
        "protocol": "openai",
        "unique": False,
        "reason": "疑似 DeepSeek Key（sk- + 32 hex）",
        "probe_providers": [
            "deepseek", "volcengine", "openai", "moonshot", "qwen",
        ],
    },
    {
        # OpenAI 遗留 / DeepSeek / 火山 / Moonshot / DashScope 通用 sk-
        "id": "generic_sk",
        "pattern": re.compile(r"^sk-[A-Za-z0-9_-]{16,}$", re.I),
        "providers": [],
        "protocol": "openai",
        "unique": False,
        "reason": "通用 sk- Key，需端点探测消歧",
        "probe_providers": [
            "openai", "deepseek", "volcengine", "moonshot", "qwen",
        ],
    },
]

# 模糊 Key 探测权威端点（探测一律用这里；catalog URL 仅作 Apply 写入默认值）
# alt_base_urls: 同厂商国内外/备用域名，并联探测取最高分
PROBE_ENDPOINTS: Dict[str, Dict[str, Any]] = {
    "openai": {"base_url": "https://api.openai.com/v1", "protocol": "openai"},
    "deepseek": {"base_url": "https://api.deepseek.com", "protocol": "openai"},
    "volcengine": {"base_url": "https://ark.cn-beijing.volces.com/api/v3", "protocol": "openai"},
    "volcengineCoding": {"base_url": "https://ark.cn-beijing.volces.com/api/coding/v3", "protocol": "openai"},
    "volcengineAgent": {"base_url": "https://ark.cn-beijing.volces.com/api/plan/v3", "protocol": "openai"},
    "moonshot": {
        "base_url": "https://api.moonshot.ai/v1",
        "protocol": "openai",
        "alt_base_urls": ["https://api.moonshot.cn/v1"],
    },
    "qwen": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "protocol": "openai"},
    "bigmodel": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "protocol": "openai"},
    "bigmodelCoding": {"base_url": "https://open.bigmodel.cn/api/coding/paas/v4", "protocol": "openai"},
    "zai": {"base_url": "https://api.z.ai/api/paas/v4", "protocol": "openai"},
    "zaiCoding": {"base_url": "https://api.z.ai/api/coding/paas/v4", "protocol": "openai"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "protocol": "openai"},
    "anthropic": {"base_url": "https://api.anthropic.com/v1", "protocol": "anthropic"},
    "openicu": {"base_url": "https://rehdasu.cn/v1", "protocol": "openai"},
}

# /models 返回的 model id 签名 → 用于探测二次验真打分
MODEL_SIGNATURES: Dict[str, Tuple[str, ...]] = {
    "deepseek": ("deepseek",),
    "openai": ("gpt-", "o1", "o3", "chatgpt", "text-embedding"),
    "qwen": ("qwen", "qwq", "qwen2", "qwen3"),
    "moonshot": ("moonshot", "kimi"),
    "volcengine": ("doubao", "seed-"),
    "volcengineCoding": ("doubao", "seed-"),
    "volcengineAgent": ("doubao", "seed-"),
    "bigmodel": ("glm-", "glm"),
    "bigmodelCoding": ("glm-", "glm"),
    "zai": ("glm-", "glm"),
    "zaiCoding": ("glm-", "glm"),
    "openrouter": ("/",),  # OpenRouter 模型多为 provider/model
    "anthropic": ("claude",),
}

PROBE_TIMEOUT_SEC = 4.0
PROBE_MAX_WORKERS = 6
# 探测唯一锁定：第一名 ≥ 此分且领先第二名 ≥ 此分差
PROBE_LOCK_MIN_SCORE = 95
PROBE_LOCK_MIN_MARGIN = 8

FAMILY_EXPAND_ON_AMBIGUOUS = {
    "bigmodel": ["bigmodel", "bigmodelCoding"],
    "zai": ["zai", "zaiCoding"],
    "volcengine": ["volcengine", "volcengineCoding", "volcengineAgent"],
    "zhipu": ["bigmodel", "bigmodelCoding", "zai", "zaiCoding"],
}


def classify_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    """按业界公开 Key 指纹分类。返回命中的 KEY_FINGERPRINTS 条目（拷贝）。"""
    key = (api_key or "").strip()
    if not key:
        return None
    for fp in KEY_FINGERPRINTS:
        if fp["pattern"].match(key):
            return dict(fp)
    return None


# 厂商展示名 / 家族（同家族多端点时弹出候选）
PROVIDER_META: Dict[str, Dict[str, str]] = {
    "openicu": {"label": "OpenICU", "family": "openicu"},
    "bigmodel": {"label": "BigModel（资源包/余额）", "family": "bigmodel"},
    "bigmodelCoding": {"label": "BigModel Coding Plan", "family": "bigmodel"},
    "zai": {"label": "Z.ai（资源包/余额）", "family": "zai"},
    "zaiCoding": {"label": "Z.ai Coding Plan", "family": "zai"},
    "openrouter": {"label": "OpenRouter", "family": "openrouter"},
    "openai": {"label": "OpenAI", "family": "openai"},
    "anthropic": {"label": "Anthropic", "family": "anthropic"},
    "deepseek": {"label": "DeepSeek", "family": "deepseek"},
    "volcengine": {"label": "火山方舟（通用）", "family": "volcengine"},
    "volcengineCoding": {"label": "火山方舟 Coding", "family": "volcengine"},
    "volcengineAgent": {"label": "火山方舟 Agent/Plan", "family": "volcengine"},
    "moonshot": {"label": "Moonshot / Kimi", "family": "moonshot"},
    "qwen": {"label": "通义千问 / DashScope", "family": "qwen"},
    "openai-compatible": {"label": "OpenAI Compatible", "family": "custom"},
    "custom": {"label": "自定义 Provider", "family": "custom"},
}

# 检测规则：按顺序匹配，越靠前优先级越高。
DETECT_RULES: List[Dict[str, Any]] = [
    {
        "provider": "anthropic",
        "key_prefixes": ["sk-ant-"],
        "url_includes": ["api.anthropic.com", "anthropic.com"],
        "url_requires": [],
        "url_excludes": ["openrouter", "bigmodel", "z.ai", "volces", "deepseek"],
        "key_only": True,
        "protocol": "anthropic",
    },
    {
        "provider": "openrouter",
        "key_prefixes": ["sk-or-"],
        "url_includes": ["openrouter.ai", "openrouter"],
        "url_requires": [],
        "url_excludes": [],
        "key_only": True,
        "protocol": "openai",
    },
    {
        "provider": "bigmodelCoding",
        "key_prefixes": [],
        "url_includes": ["bigmodel.cn", "bigmodel"],
        "url_requires": ["/coding/"],
        "url_excludes": [],
        "key_only": False,
    },
    {
        "provider": "bigmodel",
        "key_prefixes": [],
        "url_includes": ["bigmodel.cn", "bigmodel"],
        "url_requires": [],
        "url_excludes": ["/coding/"],
        "key_only": False,
    },
    {
        "provider": "zaiCoding",
        "key_prefixes": [],
        "url_includes": ["api.z.ai", "z.ai"],
        "url_requires": ["/coding/"],
        "url_excludes": [],
        "key_only": False,
    },
    {
        "provider": "zai",
        "key_prefixes": [],
        "url_includes": ["api.z.ai", "z.ai"],
        "url_requires": [],
        "url_excludes": ["/coding/"],
        "key_only": False,
    },
    {
        "provider": "volcengineCoding",
        "key_prefixes": [],
        "url_includes": ["volces.com", "volcengine"],
        "url_requires": ["/coding"],
        "url_excludes": [],
        "key_only": False,
    },
    {
        "provider": "volcengineAgent",
        "key_prefixes": [],
        "url_includes": ["volces.com", "volcengine"],
        "url_requires": ["/plan"],
        "url_excludes": [],
        "key_only": False,
    },
    {
        "provider": "volcengine",
        "key_prefixes": [],
        "url_includes": ["volces.com", "volcengine", "ark.cn-beijing"],
        "url_requires": [],
        "url_excludes": ["/coding", "/plan"],
        "key_only": False,
    },
    {
        "provider": "deepseek",
        "key_prefixes": [],
        "url_includes": ["deepseek.com", "deepseek.cn", "api.deepseek"],
        "url_requires": [],
        "url_excludes": [],
        "key_only": False,
    },
    {
        "provider": "moonshot",
        "key_prefixes": [],
        "url_includes": ["moonshot", "kimi"],
        "url_requires": [],
        "url_excludes": [],
        "key_only": False,
    },
    {
        "provider": "qwen",
        "key_prefixes": [],
        "url_includes": ["dashscope", "aliyuncs"],
        "url_requires": [],
        "url_excludes": [],
        "key_only": False,
    },
    {
        "provider": "openicu",
        "key_prefixes": [],
        "url_includes": ["rehdasu"],
        "url_requires": [],
        "url_excludes": [],
        "key_only": False,
    },
    {
        "provider": "openai",
        "key_prefixes": [],
        "url_includes": ["api.openai.com", "openai.com"],
        "url_requires": [],
        "url_excludes": ["openrouter", "azure"],
        "key_only": False,
        "protocol": "openai",
    },
]


def _models_url(base_url: str) -> str:
    url = (base_url or "").rstrip("/")
    if url.endswith("/v1/models") or url.endswith("/models"):
        return url
    if url.endswith("/v1") or url.endswith("/v3") or url.endswith("/v4"):
        return url + "/models"
    # bigmodel/zai paas 路径本身已含版本
    if "/paas/" in url or "/coding/" in url or "/plan" in url:
        return url + "/models" if not url.endswith("/models") else url
    return url + "/v1/models"


def _extract_model_ids(body: Any) -> List[str]:
    """从 /models JSON 抽取 model id 列表。"""
    ids: List[str] = []
    if not isinstance(body, dict):
        return ids
    data = body.get("data")
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                mid = item.get("id") or item.get("name")
                if isinstance(mid, str) and mid:
                    ids.append(mid)
            elif isinstance(item, str):
                ids.append(item)
    models = body.get("models")
    if isinstance(models, list):
        for item in models:
            if isinstance(item, dict):
                mid = item.get("id") or item.get("name")
                if isinstance(mid, str) and mid:
                    ids.append(mid)
            elif isinstance(item, str):
                ids.append(item)
    return ids


def score_model_signature(provider: str, model_ids: List[str]) -> int:
    """根据 /models 返回的 id 与厂商签名匹配程度打分增量。

    返回：
      15 → 强匹配（可抬到 98–100）
      0  → 无签名可判 / 无模型列表
     -5 → 有模型但签名明显不符（压到 ~80）
    """
    sigs = MODEL_SIGNATURES.get(provider) or ()
    if not model_ids:
        return 0
    if not sigs:
        return 0
    joined = " ".join(m.lower() for m in model_ids)
    if any(s.lower() in joined for s in sigs):
        # OpenRouter 的 "/" 太宽，要求同时像 provider/model
        if provider == "openrouter":
            if any("/" in m and not m.startswith("/") for m in model_ids):
                return 15
            return 0
        return 15
    # 有模型列表但签名不命中 → 轻微降权（避免误锁）
    return -5


def probe_endpoint(api_key: str, base_url: str, protocol: str = "openai") -> Dict[str, Any]:
    """对单个端点做轻量鉴权探测（GET models）。

    返回 {ok, status, error?, model_ids?}。
    """
    try:
        import requests as _req
    except ImportError:
        return {"ok": False, "status": 0, "error": "requests 未安装", "model_ids": []}
    url = _models_url(base_url)
    headers = {"Authorization": f"Bearer {api_key}"}
    if protocol == "anthropic":
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    try:
        r = _req.get(url, headers=headers, timeout=PROBE_TIMEOUT_SEC)
        # 200 = 有效；401/403 = 端点对但 key 无效；其它可能是路径不对
        if r.status_code == 200:
            model_ids: List[str] = []
            try:
                model_ids = _extract_model_ids(r.json())
            except Exception:
                model_ids = []
            return {"ok": True, "status": 200, "model_ids": model_ids}
        if r.status_code in (401, 403):
            return {"ok": False, "status": r.status_code, "error": "auth_failed", "model_ids": []}
        return {"ok": False, "status": r.status_code, "error": f"http_{r.status_code}", "model_ids": []}
    except Exception as e:
        return {"ok": False, "status": 0, "error": str(e)[:120], "model_ids": []}


def _probe_urls_for_provider(name: str) -> List[Tuple[str, str]]:
    """返回 [(base_url, protocol), ...]，权威端点优先，含 alt_base_urls。"""
    ep = PROBE_ENDPOINTS.get(name)
    if not ep:
        return []
    protocol = ep.get("protocol") or "openai"
    urls: List[str] = []
    primary = (ep.get("base_url") or "").strip()
    if primary:
        urls.append(primary)
    for alt in ep.get("alt_base_urls") or []:
        alt_s = (alt or "").strip()
        if alt_s and alt_s not in urls:
            urls.append(alt_s)
    return [(u, protocol) for u in urls]


def rank_probe_hits(
    hits: List[Tuple[str, str, int]],
) -> List[Tuple[str, str, int]]:
    """按 score 降序；高置信且领先明显时只保留第一名。"""
    if not hits:
        return []
    ranked = sorted(hits, key=lambda x: (-x[2], x[0]))
    # 同 provider 多 URL 时只留最高分
    best: Dict[str, Tuple[str, str, int]] = {}
    for name, proto, sc in ranked:
        prev = best.get(name)
        if not prev or sc > prev[2]:
            best[name] = (name, proto, sc)
    ranked = sorted(best.values(), key=lambda x: (-x[2], x[0]))
    if len(ranked) == 1:
        return ranked
    top_sc = ranked[0][2]
    second_sc = ranked[1][2]
    if top_sc >= PROBE_LOCK_MIN_SCORE and (top_sc - second_sc) >= PROBE_LOCK_MIN_MARGIN:
        return [ranked[0]]
    return ranked


def needs_choice_for_candidates(candidates: List[Dict[str, Any]]) -> bool:
    """是否需要用户手动选择厂商。

    单候选，或第一名高置信且明显领先第二名 → 不需要选择。
    """
    if not candidates:
        return False
    if len(candidates) == 1:
        return False
    top = candidates[0].get("score") or 0
    second = candidates[1].get("score") or 0
    try:
        top_i = int(top)
        second_i = int(second)
    except (TypeError, ValueError):
        return True
    if top_i >= PROBE_LOCK_MIN_SCORE and (top_i - second_i) >= PROBE_LOCK_MIN_MARGIN:
        return False
    return True


def probe_providers(
    api_key: str,
    provider_names: List[str],
    catalog_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Tuple[str, str, int]]:
    """并行探测多个厂商权威端点。返回 [(provider, protocol, score), ...]。

    探测 URL 一律来自 PROBE_ENDPOINTS（含 alt），不使用可能不准确的 catalog URL。
    catalog_map 仅用于确认厂商名是否已知（可选，不影响 URL 选择）。
    """
    del catalog_map  # 保留参数兼容调用方；探测不再读 catalog URL
    jobs: List[Tuple[str, str, str]] = []  # provider, base_url, protocol
    for name in provider_names:
        for base_url, protocol in _probe_urls_for_provider(name):
            jobs.append((name, base_url, protocol))

    raw_hits: List[Tuple[str, str, int]] = []
    if not jobs:
        return raw_hits

    with ThreadPoolExecutor(max_workers=min(PROBE_MAX_WORKERS, len(jobs))) as pool:
        futures = {
            pool.submit(probe_endpoint, api_key, bu, proto): (name, proto)
            for name, bu, proto in jobs
        }
        for fut in as_completed(futures):
            name, proto = futures[fut]
            try:
                res = fut.result()
            except Exception:
                continue
            if not res.get("ok"):
                continue
            # 基分 85（鉴权通过但无签名验真）；签名命中 +15 → 100；不符 -5 → 80
            base = 85
            sig_delta = score_model_signature(name, res.get("model_ids") or [])
            score = max(70, min(100, base + sig_delta))
            raw_hits.append((name, proto, score))

    return rank_probe_hits(raw_hits)

def _meta(provider: str) -> Dict[str, str]:
    return PROVIDER_META.get(provider, {"label": provider, "family": provider})


def _norm_url(url: str) -> str:
    return (url or "").strip().rstrip("/").lower()


def _url_parts(url: str) -> Tuple[str, str]:
    """返回 (host, path)，均小写、path 无尾斜杠。"""
    u = _norm_url(url)
    if not u:
        return "", ""
    if "://" not in u:
        u = "https://" + u
    try:
        p = urlparse(u)
        return (p.netloc or "", (p.path or "").rstrip("/"))
    except Exception:
        return "", ""


def infer_protocol(
    api_key: str = "",
    base_url: str = "",
    available: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """推断协议。返回 (protocol, reason)。

    优先级：
      1. key 前缀 sk-ant- → anthropic
      2. URL 路径特征（/anthropic、anthropic 域名）→ anthropic
      3. 与 catalog 各协议 base_url 精确/前缀匹配
      4. 默认 openai（若 available 含 openai，否则取第一个）
    """
    key = (api_key or "").strip().lower()
    url = _norm_url(base_url)
    avail = available or {}

    if key.startswith("sk-ant-"):
        if not avail or "anthropic" in avail:
            return "anthropic", "API Key 前缀 sk-ant-"

    if url:
        host, path = _url_parts(url)
        # 原生 Anthropic
        if "anthropic.com" in host and "openrouter" not in host:
            if not avail or "anthropic" in avail:
                return "anthropic", "URL 为 Anthropic 官方端点"
        # 路径含 /anthropic（bigmodel/zai/deepseek/volcengine/openrouter 等兼容端点）
        if "/anthropic" in path or path.endswith("anthropic"):
            if not avail or "anthropic" in avail:
                return "anthropic", "URL 路径含 /anthropic"
        # OpenRouter：/api/v1 → openai；/api（无 v1）常作 anthropic 兼容
        if "openrouter" in host or "openrouter" in url:
            if path.endswith("/api") or path.rstrip("/").endswith("/api"):
                if not avail or "anthropic" in avail:
                    return "anthropic", "OpenRouter Anthropic 兼容路径"
            if not avail or "openai" in avail:
                return "openai", "OpenRouter OpenAI 兼容路径"

        # 与 catalog 协议 base_url 比对
        if avail:
            best_proto, best_score = "", -1
            uh, up = host, path
            for proto, cfg in avail.items():
                if not isinstance(cfg, dict):
                    continue
                bh, bp = _url_parts(cfg.get("base_url") or "")
                if not bh:
                    continue
                score = 0
                if uh == bh and up == bp:
                    score = 100
                elif uh == bh and (up.startswith(bp) or bp.startswith(up)):
                    score = 90
                elif uh == bh:
                    score = 60
                if score > best_score:
                    best_score = score
                    best_proto = proto
            if best_proto and best_score >= 60:
                return best_proto, f"URL 匹配 {best_proto} 端点"

    if avail:
        if "openai" in avail:
            return "openai", "默认 OpenAI 兼容协议"
        return next(iter(avail.keys())), "取厂商首个可用协议"
    return "openai", "默认 OpenAI 兼容协议"


def load_provider_catalog(example_path: Path) -> List[Dict[str, Any]]:
    """从 llm-env-example.yaml 解析 provider 预设列表。"""
    if not example_path.exists():
        return []
    data = load_env_config_file(example_path) or {}
    llm = data.get("llm") or {}
    catalog: List[Dict[str, Any]] = []
    for name, block in llm.items():
        if name.startswith("_") or name == "proxy":
            continue
        if not isinstance(block, dict):
            continue
        protocols: Dict[str, Any] = {}
        for proto, cfg in block.items():
            if not isinstance(cfg, dict):
                continue
            if not any(k in cfg for k in ("base_url", "api_key", "models")):
                continue
            protocols[proto] = {
                "base_url": cfg.get("base_url") or "",
                "models": dict(cfg.get("models") or {}),
            }
        if not protocols:
            continue
        meta = _meta(name)
        catalog.append({
            "provider": name,
            "label": meta["label"],
            "family": meta["family"],
            "protocols": protocols,
            "suggested_protocol": _suggest_protocol(protocols),
            "active_protocol": "|".join(protocols.keys()),
        })
    return catalog


def catalog_as_map(catalog: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {c["provider"]: c for c in catalog}


def _suggest_protocol(protocols: Dict[str, Any]) -> str:
    if "openai" in protocols:
        return "openai"
    if "anthropic" in protocols:
        return "anthropic"
    return next(iter(protocols.keys()), "openai")


def _host_matches(host: str, pattern: str) -> bool:
    """host 是否匹配 pattern（精确 / 子域后缀 / 前缀标签 / DNS 标签相等）。"""
    host = (host or "").lower().rstrip(".")
    pattern = (pattern or "").lower().rstrip(".")
    if not host or not pattern or pattern.startswith("/"):
        return False
    if host == pattern:
        return True
    if host.endswith("." + pattern):
        return True
    if host.startswith(pattern + "."):
        return True
    # 单标签相等，如 pattern=volcengine 对 host 中某 label
    labels = host.split(".")
    if pattern in labels:
        return True
    return False


def _url_match(url: str, rule: Dict[str, Any]) -> bool:
    """基于 host/path 结构化匹配，避免对整段 URL 做 substring 误伤。"""
    if not url:
        return False
    host, path = _url_parts(url)
    includes = rule.get("url_includes") or []
    if includes and not any(_host_matches(host, s) for s in includes):
        return False
    requires = rule.get("url_requires") or []
    if requires and not all(s in path for s in requires):
        return False
    excludes = rule.get("url_excludes") or []
    if excludes and any(s in path for s in excludes):
        return False
    # openrouter 等规则可能用 host 关键词；无 includes 时仅靠 requires 也可
    return bool(includes or requires)


def _key_match(key: str, rule: Dict[str, Any]) -> bool:
    prefixes = rule.get("key_prefixes") or []
    return bool(prefixes) and any(key.startswith(p) for p in prefixes)


def match_catalog_endpoints(
    base_url: str,
    catalog: List[Dict[str, Any]],
) -> List[Tuple[str, str, int]]:
    """用 URL 直接匹配 catalog 中各协议端点。

    返回 [(provider, protocol, score), ...] 按 score 降序。
    """
    url = _norm_url(base_url)
    if not url:
        return []
    uh, up = _url_parts(url)
    scored: List[Tuple[str, str, int]] = []
    for entry in catalog:
        for proto, cfg in (entry.get("protocols") or {}).items():
            bh, bp = _url_parts(cfg.get("base_url") or "")
            if not bh:
                continue
            score = 0
            if uh == bh and up == bp:
                score = 100
            elif uh == bh and bp and (up.startswith(bp) or bp.startswith(up)):
                score = 92
            elif uh == bh and bp and (bp in up or up in bp):
                score = 85
            elif uh == bh:
                score = 55
            if score >= 85:
                scored.append((entry["provider"], proto, score))
    scored.sort(key=lambda x: (-x[2], x[0], x[1]))
    return scored


def _candidate_from_catalog(
    entry: Dict[str, Any],
    *,
    score: int,
    reason: str,
    base_url_override: str = "",
    detected_protocol: str = "",
    protocol_reason: str = "",
    api_key: str = "",
) -> Dict[str, Any]:
    protocols = {}
    avail = entry.get("protocols") or {}
    if detected_protocol and detected_protocol in avail:
        suggested = detected_protocol
        p_reason = protocol_reason or f"识别为 {detected_protocol}"
    else:
        suggested, p_reason = infer_protocol(api_key, base_url_override, avail)

    for proto, cfg in avail.items():
        url = cfg.get("base_url") or ""
        if base_url_override and (proto == suggested or len(avail) == 1):
            url = base_url_override
        protocols[proto] = {
            "base_url": url,
            "models": dict(cfg.get("models") or {}),
        }

    # active：识别到明确协议时用单协议；否则保留厂商全部协议
    if detected_protocol and detected_protocol in protocols:
        active = detected_protocol
    elif suggested and (api_key.startswith("sk-ant-") or "/anthropic" in _norm_url(base_url_override)):
        active = suggested
    else:
        active = "|".join(protocols.keys()) if len(protocols) > 1 else suggested

    return {
        "provider": entry["provider"],
        "label": entry["label"],
        "family": entry["family"],
        "score": score,
        "reason": reason,
        "protocols": protocols,
        "detected_protocol": suggested,
        "protocol_reason": p_reason,
        "suggested_protocol": suggested,
        "active_protocol": active,
    }


def _fallback_custom(api_key: str, base_url: str) -> Dict[str, Any]:
    provider = "openai-compatible" if api_key.startswith("sk-") else "custom"
    meta = _meta(provider)
    proto, p_reason = infer_protocol(api_key, base_url)
    return {
        "provider": provider,
        "label": meta["label"],
        "family": meta["family"],
        "score": 10,
        "reason": "未匹配已知厂商，使用兼容预设",
        "protocols": {
            proto: {
                "base_url": base_url,
                "models": {},
            }
        },
        "detected_protocol": proto,
        "protocol_reason": p_reason,
        "suggested_protocol": proto,
        "active_protocol": proto,
    }


def detect_providers(
    api_key: str,
    base_url: str = "",
    catalog: Optional[List[Dict[str, Any]]] = None,
    example_path: Optional[Path] = None,
    *,
    probe: bool = True,
) -> List[Dict[str, Any]]:
    """根据 api_key / base_url 返回候选（含识别出的协议）。

    识别顺序：
      1. URL 精确匹配 catalog 协议端点 → 厂商+协议双确定
      2. Key 指纹正则（unique → 直接锁定；家族 → 探测/候选）
      3. URL 规则匹配厂商
      4. 模糊 sk- → 并行端点探测消歧；探测失败再给精简候选
    """
    key = (api_key or "").strip()
    url = _norm_url(base_url)
    key_l = key.lower()
    user_url = (base_url or "").strip()

    if catalog is None:
        if example_path is None:
            raise ValueError("catalog 或 example_path 必须提供其一")
        catalog = load_provider_catalog(example_path)
    cmap = catalog_as_map(catalog)

    hits: List[Dict[str, Any]] = []
    seen = set()

    def add_provider(
        name: str,
        score: int,
        reason: str,
        *,
        override_url: Optional[str] = None,
        detected_protocol: str = "",
        protocol_reason: str = "",
    ) -> None:
        if name in seen:
            return
        entry = cmap.get(name)
        if not entry:
            # catalog 无此厂商时，用 PROBE_ENDPOINTS 合成最小预设
            ep = PROBE_ENDPOINTS.get(name)
            if not ep:
                return
            meta = _meta(name)
            proto = detected_protocol or ep.get("protocol") or "openai"
            entry = {
                "provider": name,
                "label": meta["label"],
                "family": meta["family"],
                "protocols": {
                    proto: {"base_url": ep["base_url"], "models": {}},
                },
                "suggested_protocol": proto,
                "active_protocol": proto,
            }
        seen.add(name)
        hits.append(_candidate_from_catalog(
            entry,
            score=score,
            reason=reason,
            base_url_override="" if override_url is None else override_url,
            detected_protocol=detected_protocol,
            protocol_reason=protocol_reason,
            api_key=key_l,
        ))

    # 0) URL 精确匹配 catalog 端点
    if url:
        endpoint_hits = match_catalog_endpoints(user_url, catalog)
        if endpoint_hits and endpoint_hits[0][2] >= 92:
            top_score = endpoint_hits[0][2]
            exact = [h for h in endpoint_hits if h[2] >= 92 and h[2] >= top_score - 5]
            best_by_provider: Dict[str, Tuple[str, int]] = {}
            for prov, proto, sc in exact:
                prev = best_by_provider.get(prov)
                if not prev or sc > prev[1]:
                    best_by_provider[prov] = (proto, sc)
            for prov, (proto, sc) in best_by_provider.items():
                add_provider(
                    prov, sc, f"端点匹配 {prov}/{proto}",
                    override_url=user_url,
                    detected_protocol=proto,
                    protocol_reason=f"URL 匹配 {proto} 端点",
                )
            if hits:
                hits.sort(key=lambda c: (-c["score"], c["provider"]))
                return hits

    # 1) Key 指纹分类（业界公开格式）
    fp = classify_api_key(key)
    if fp and fp.get("unique") and fp.get("providers"):
        for name in fp["providers"]:
            add_provider(
                name, 97, fp.get("reason") or f"Key 指纹 {fp.get('id')}",
                override_url=user_url if user_url else None,
                detected_protocol=fp.get("protocol") or "",
                protocol_reason=fp.get("reason") or "",
            )
        if hits:
            hits.sort(key=lambda c: (-c["score"], c["provider"]))
            return hits

    if fp and not fp.get("unique"):
        probe_list = list(fp.get("probe_providers") or fp.get("providers") or [])
        # 智谱/Z.ai：同 Key 体系，优先探测；探测失败再给家族候选
        if probe and probe_list:
            probed = probe_providers(key, probe_list, cmap)
            if probed:
                for name, proto, sc in probed:
                    add_provider(
                        name, sc, f"端点探测成功（{fp.get('reason') or fp.get('id')}）",
                        override_url=None,
                        detected_protocol=proto,
                        protocol_reason="端点探测鉴权通过",
                    )
                # 同家族多端点都通时保留全部（如 bigmodel + coding）
                if hits:
                    hits.sort(key=lambda c: (-c["score"], c["provider"]))
                    return hits
        # 探测无结果：给出家族/指纹候选（不再甩全量 GENERIC 列表）
        family = fp.get("family")
        names = list(fp.get("providers") or [])
        if family and family in FAMILY_EXPAND_ON_AMBIGUOUS:
            names = FAMILY_EXPAND_ON_AMBIGUOUS[family]
        elif probe_list:
            # 模糊 sk-：给精简候选，不把 openrouter/anthropic 等已有专属指纹的混进来
            names = [
                n for n in probe_list
                if n in cmap or n in PROBE_ENDPOINTS
            ][:6]
        for name in names:
            add_provider(
                name, 55, fp.get("reason") or "Key 指纹候选",
                override_url=None,
                detected_protocol=fp.get("protocol") or "openai",
                protocol_reason=fp.get("reason") or "",
            )
        if hits:
            hits.sort(key=lambda c: (-c["score"], c["provider"]))
            return hits

    # 2) URL 规则匹配厂商
    if url:
        for rule in DETECT_RULES:
            if _url_match(url, rule):
                rule_proto = rule.get("protocol") or ""
                if not rule_proto:
                    entry = cmap.get(rule["provider"])
                    rule_proto, p_reason = infer_protocol(
                        key_l, user_url, (entry or {}).get("protocols"),
                    )
                else:
                    p_reason = f"规则指定 {rule_proto}"
                add_provider(
                    rule["provider"], 100, f"URL 匹配 {rule['provider']}",
                    override_url=user_url,
                    detected_protocol=rule_proto,
                    protocol_reason=p_reason,
                )
                family = _meta(rule["provider"])["family"]
                requires = rule.get("url_requires") or []
                if not requires and family in FAMILY_EXPAND_ON_AMBIGUOUS:
                    for sib in FAMILY_EXPAND_ON_AMBIGUOUS[family]:
                        if sib == rule["provider"]:
                            continue
                        add_provider(
                            sib, 80, f"同家族候选（{family}）",
                            override_url=None,
                            detected_protocol=rule_proto,
                            protocol_reason=p_reason,
                        )
                break

    # 3) 遗留 key_prefixes（兼容旧规则，指纹未覆盖时）
    if not hits and key_l:
        for rule in DETECT_RULES:
            if not _key_match(key_l, rule):
                continue
            if rule.get("key_only") or not url:
                rule_proto = rule.get("protocol") or ""
                entry = cmap.get(rule["provider"])
                if not rule_proto:
                    rule_proto, p_reason = infer_protocol(
                        key_l, user_url, (entry or {}).get("protocols"),
                    )
                else:
                    p_reason = f"规则指定 {rule_proto}"
                add_provider(
                    rule["provider"], 90, f"API Key 前缀匹配 {rule['provider']}",
                    override_url=user_url if user_url else None,
                    detected_protocol=rule_proto,
                    protocol_reason=p_reason,
                )

    if not hits:
        if key:
            hits.append(_fallback_custom(key_l, user_url))
        return hits

    hits.sort(key=lambda c: (-c["score"], c["provider"]))
    return hits


def apply_provider_to_env(
    env_data: Dict[str, Any],
    candidate: Dict[str, Any],
    api_key: str,
    *,
    set_active: bool = True,
    base_url_override: str = "",
    protocol: str = "",
) -> Dict[str, Any]:
    """将候选 preset 写入 env_data。

    protocol: 若指定则优先作为 _active_protocol / suggested；
    否则用 candidate.detected_protocol / suggested_protocol。
    """
    if "llm" not in env_data or not isinstance(env_data["llm"], dict):
        env_data["llm"] = {}
    llm = env_data["llm"]
    provider = candidate["provider"]
    existed = provider in llm and isinstance(llm.get(provider), dict)
    block = llm.get(provider) if existed else {}
    if not isinstance(block, dict):
        block = {}

    protocols = candidate.get("protocols") or {}
    detected = (
        protocol
        or candidate.get("detected_protocol")
        or candidate.get("suggested_protocol")
        or ""
    )
    applied_protos = []
    for proto, cfg in protocols.items():
        prev = block.get(proto) if isinstance(block.get(proto), dict) else {}
        use_override = bool(base_url_override) and (
            len(protocols) == 1 or proto == detected
        )
        base_url = (base_url_override if use_override else None) or cfg.get("base_url") or prev.get("base_url") or ""
        models = cfg.get("models") or prev.get("models") or {}
        block[proto] = {
            "base_url": base_url,
            "api_key": api_key,
            "models": dict(models) if isinstance(models, dict) else {},
        }
        applied_protos.append(proto)

    llm[provider] = block

    # 明确识别到协议 → active 用单协议；否则保留多协议
    if detected and detected in (protocols or block):
        active_protocol = detected
    else:
        active_protocol = candidate.get("active_protocol") or "|".join(applied_protos)

    if set_active:
        llm["_active_provider"] = provider
        llm["_active_protocol"] = active_protocol

    resolved_urls = {
        p: (block.get(p) or {}).get("base_url") or ""
        for p in applied_protos
    }
    return {
        "provider": provider,
        "protocols": applied_protos,
        "set_active": set_active,
        "existed": existed,
        "active_protocol": active_protocol,
        "detected_protocol": detected or (applied_protos[0] if applied_protos else "openai"),
        "suggested_protocol": detected or (applied_protos[0] if applied_protos else "openai"),
        "protocol_reason": candidate.get("protocol_reason") or "",
        "base_urls": resolved_urls,
        "base_url": resolved_urls.get(active_protocol)
            or resolved_urls.get(detected)
            or next(iter(resolved_urls.values()), ""),
    }
