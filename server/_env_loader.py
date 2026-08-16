"""轻量级 .env 加载器（零依赖，不引入 python-dotenv）。

加载规则：
1. 查找 SERVER_DIR/.env（server 目录为根）
2. 解析 KEY=VALUE 行，跳过空行与 # 注释
3. 自动去除键值两侧空白；VALUE 两侧的单/双引号会被剥离
4. **不覆盖**已存在的环境变量（shell/system 注入优先级最高）
5. 加载失败（文件不存在/格式错误）静默忽略，仅打印简短日志

使用方式：
    # 在入口文件顶部（读取 os.environ 之前）
    from _env_loader import load_env_file
    load_env_file()  # 返回成功加载的变量数
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
ENV_FILE = SERVER_DIR / ".env"


def _parse_line(line: str) -> tuple[str, str] | None:
    """解析单行 KEY=VALUE，返回 (key, value) 或 None（空行/注释/格式错误）。"""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "=" not in line:
        return None
    key, _, value = line.partition("=")
    key = key.strip()
    if not key or not key.replace("_", "").isalnum():
        return None
    value = value.strip()
    # 剥离两侧匹配的单/双引号
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1]
    return key, value


def load_env_file(path: Path | None = None, *, verbose: bool = True) -> int:
    """加载 .env 文件，已存在的环境变量不被覆盖。

    Args:
        path: 自定义 .env 路径；默认 SERVER_DIR/.env
        verbose: 是否打印加载日志

    Returns: 成功加载的变量数（不含被跳过的已存在变量）
    """
    env_path = path or ENV_FILE
    if not env_path.exists():
        if verbose:
            print(f"[env] 未找到 {env_path.name}，跳过自动加载（使用 shell/system 环境变量）",
                  file=sys.stderr)
        return 0

    loaded = 0
    skipped = 0
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            parsed = _parse_line(line)
            if parsed is None:
                continue
            key, value = parsed
            if os.environ.get(key, "").strip():
                skipped += 1
                continue
            os.environ[key] = value
            loaded += 1
    except Exception as e:
        if verbose:
            print(f"[env] 加载 {env_path.name} 失败：{e}", file=sys.stderr)
        return 0

    if verbose and (loaded or skipped):
        print(f"[env] 已加载 {env_path.name}：{loaded} 个变量注入，{skipped} 个被已有环境变量覆盖",
              file=sys.stderr)
    return loaded


if __name__ == "__main__":
    n = load_env_file()
    print(f"已加载 {n} 个环境变量")
