"""IDE 元数据加载器。

从 ide.yaml 加载 install_meta / detect_meta，作为 install.py / detect.py 的唯一数据源。
代码只负责调用执行，配置全部在 YAML 中维护。
"""
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml  # PyYAML
except ImportError:  # pragma: no cover
    yaml = None

_YAML_PATH = Path(__file__).parent / "ide.yaml"
_cache: Optional[Dict[str, Any]] = None


def _load() -> Dict[str, Any]:
    """加载 ide.yaml 并缓存。"""
    global _cache
    if _cache is not None:
        return _cache
    if yaml is None:
        raise RuntimeError("PyYAML 未安装，请运行: pip install pyyaml")
    if not _YAML_PATH.exists():
        raise FileNotFoundError(f"IDE 元数据文件不存在: {_YAML_PATH}")
    with _YAML_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"ide.yaml 顶层必须是 dict，实际为 {type(data).__name__}")
    _cache = data
    return _cache


def get_install_meta() -> Dict[str, dict]:
    """返回 IDE_INSTALL_META（按 IDE key → 元数据 dict）。"""
    meta = _load().get("install_meta") or {}
    if not isinstance(meta, dict):
        raise ValueError("ide.yaml: install_meta 必须是 dict")
    return meta


def get_detect_meta() -> Dict[str, dict]:
    """返回 IDE_DETECT_META（按 IDE key → 检测元数据 dict）。"""
    meta = _load().get("detect_meta") or {}
    if not isinstance(meta, dict):
        raise ValueError("ide.yaml: detect_meta 必须是 dict")
    return meta


def get_ide_protocols(ide_name: str) -> list[str]:
    """返回某个 IDE 支持的 LLM 协议列表（如 ['openaiv1'] 或 ['openaiv1', 'anthropic']）。

    从 ide.yaml 的 detect_meta.<ide>.protocols 读取。
    未配置时默认返回 ['openaiv1']。
    """
    meta = get_detect_meta()
    entry = meta.get(ide_name, {})
    protocols = entry.get("protocols")
    if isinstance(protocols, list) and protocols:
        return [str(p).strip() for p in protocols if str(p).strip()]
    return ["openaiv1"]


def reload() -> None:
    """清除缓存，下次访问时重新加载（调试/热更新用）。"""
    global _cache
    _cache = None


__all__ = ["get_install_meta", "get_detect_meta", "get_ide_protocols", "reload"]
