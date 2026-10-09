"""从市场 zip 里读出插件说明、原文地址和技能正文。"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import yaml

_REPO_RE = re.compile(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:@.+)?$")
_SKILL_MD_RE = re.compile(r"(?:^|/)skills/([^/]+)/SKILL\.md$", re.IGNORECASE)


def source_url(source: str, fallback: str = "") -> str:
    """把 skill.source / 主页收成可打开的链接。"""
    text = (source or "").strip()
    if text.startswith("ai-extracted:"):
        text = text.split(":", 1)[1].strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text
    match = _REPO_RE.match(text)
    if match:
        return f"https://github.com/{match.group(1)}/{match.group(2)}"
    fb = (fallback or "").strip()
    if fb.startswith(("http://", "https://")):
        return fb
    return ""


def homepage_of(cfg: dict) -> str:
    home = str(cfg.get("homepage") or "").strip()
    if home.startswith(("http://", "https://")):
        return home
    repo = cfg.get("repository") or ""
    if isinstance(repo, dict):
        repo = repo.get("url") or ""
    repo = str(repo or "").strip()
    if repo.startswith(("http://", "https://")):
        return repo
    return ""


def inspect_zip_bytes(data: bytes) -> dict:
    """解析插件 zip。不返回 envVars / 密钥。"""
    cfg: dict = {}
    skill_docs: dict[str, str] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = info.filename.replace("\\", "/")
                if name.endswith(".plugin.yaml") or name.endswith(".plugin.yml"):
                    try:
                        loaded = yaml.safe_load(zf.read(info))
                    except Exception:
                        loaded = None
                    if isinstance(loaded, dict) and not cfg:
                        cfg = loaded
                    continue
                match = _SKILL_MD_RE.search(name)
                if match:
                    try:
                        skill_docs[match.group(1)] = zf.read(info).decode("utf-8", errors="replace")
                    except Exception:
                        continue
    except zipfile.BadZipFile:
        return {"description": "", "homepage": "", "skills": []}

    fallback = homepage_of(cfg)
    skills = []
    for item in cfg.get("skills") or []:
        if isinstance(item, dict):
            skill_name = str(item.get("name") or item.get("skill") or "").strip()
            description = str(item.get("description") or "").strip()
            version = str(item.get("version") or "").strip()
            source = str(item.get("source") or "").strip()
            body = str(item.get("body") or "").strip() or skill_docs.get(skill_name, "")
        else:
            skill_name = str(item).strip()
            description = version = source = ""
            body = skill_docs.get(skill_name, "")
        if not skill_name:
            continue
        skills.append({
            "name": skill_name,
            "description": description,
            "version": version,
            "source": source,
            "source_url": source_url(source, fallback),
            "body": body,
        })
    if not fallback:
        for skill in skills:
            if skill["source_url"]:
                fallback = skill["source_url"]
                break
    return {
        "description": str(cfg.get("description") or "").strip(),
        "homepage": fallback,
        "skills": skills,
    }


def inspect_zip_file(path: Path) -> dict:
    if not path.is_file():
        return {"description": "", "homepage": "", "skills": []}
    return inspect_zip_bytes(path.read_bytes())
