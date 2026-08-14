"""mcp_market 去重与安装 hint 单元测试（不依赖外网）。"""
import pathlib

from agentctl.lib.mcp_market import (
    _dedupe,
    _dedupe_key,
    _local_name,
    _norm_url,
    _registry_install_hint,
    _result,
)


def test_norm_url_strips_git_suffix():
    assert _norm_url("https://github.com/a/b.git") == "github.com/a/b"
    assert _norm_url("git@github.com:a/b.git") == "github.com/a/b"


def test_dedupe_prefers_first_by_repo():
    a = _result(source="registry", id="io.x/a", name="a", repo_url="https://github.com/o/r")
    b = _result(source="glama", id="o/r", name="r", repo_url="https://github.com/o/r.git")
    out = _dedupe([a, b])
    assert len(out) == 1
    assert out[0]["source"] == "registry"
    assert _dedupe_key(a) == _dedupe_key(b)


def test_dedupe_by_package_name():
    a = _result(source="registry", id="x", name="x", package_name="@scope/pkg")
    b = _result(source="pulsemcp", id="y", name="y", package_name="@scope/pkg")
    assert len(_dedupe([a, b])) == 1


def test_local_name():
    assert _local_name("io.github.foo/bar-baz") == "bar-baz"
    assert _local_name("@owner/my mcp") == "my-mcp"


def test_registry_install_hint_from_remote():
    hint = _registry_install_hint({
        "remotes": [{"type": "streamable-http", "url": "https://example.com/mcp"}],
    })
    assert hint == {"type": "streamableHttp", "url": "https://example.com/mcp"}


def test_registry_install_hint_from_npm_package():
    hint = _registry_install_hint({
        "packages": [{
            "identifier": "@modelcontextprotocol/server-filesystem",
            "runtimeHint": "npx",
            "runtimeArguments": [{"value": "-y", "type": "positional"}],
            "transport": {"type": "stdio"},
            "environmentVariables": [{"name": "API_KEY", "isRequired": True}],
        }],
    })
    assert hint["command"] == "npx"
    assert "-y" in hint["args"]
    assert "@modelcontextprotocol/server-filesystem" in hint["args"]
    assert hint["env"]["API_KEY"] == "${API_KEY}"


def test_modelscope_owner_name():
    from agentctl.lib.mcp_market import _modelscope_owner_name
    assert _modelscope_owner_name("@modelcontextprotocol/github") == (
        "modelcontextprotocol",
        "github",
    )
    assert _modelscope_owner_name("YTGX123/search") == ("YTGX123", "search")


def test_modelscope_id_candidates_preserve_at():
    from agentctl.lib.mcp_market import _modelscope_id_candidates, _modelscope_mcp_id
    assert _modelscope_id_candidates(server_id="@modelcontextprotocol/github") == [
        "@modelcontextprotocol/github"
    ]
    assert _modelscope_mcp_id(server_id="@a/b") == "@a/b"
    cands = _modelscope_id_candidates(owner="myalone", name="fetch")
    assert cands[0] == "myalone/fetch"
    assert "@myalone/fetch" in cands


def test_extract_modelscope_install_from_server_config_list():
    from agentctl.lib.mcp_market import _extract_modelscope_install
    local, cfg = _extract_modelscope_install({
        "id": "@modelcontextprotocol/github",
        "name": "GitHub",
        "server_config": [{
            "mcpServers": {
                "github": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                    "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "<YOUR_TOKEN>"},
                }
            }
        }],
    })
    assert local == "github"
    assert cfg["command"] == "npx"
    assert cfg["env"]["GITHUB_PERSONAL_ACCESS_TOKEN"] == "${GITHUB_PERSONAL_ACCESS_TOKEN}"


def test_modelscope_detail_uses_full_mcp_id(monkeypatch):
    from agentctl.lib import mcp_market as mm

    called = {}

    class FakeResp:
        def __init__(self, status=200, payload=None):
            self.status_code = status
            self._payload = payload or {
                "success": True,
                "data": {
                    "id": "@modelcontextprotocol/github",
                    "server_config": [{
                        "mcpServers": {
                            "github": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"]}
                        }
                    }],
                },
            }

        def raise_for_status(self):
            if self.status_code >= 400:
                raise mm.requests.HTTPError(f"{self.status_code}")

        def json(self):
            return self._payload

    def fake_get(url, params=None, headers=None, timeout=None):
        called["url"] = url
        called["params"] = params
        if "get_operational_url" in (params or {}):
            return FakeResp(401, {"success": False, "code": "InvalidAuthentication"})
        if "@modelcontextprotocol/github" in url:
            return FakeResp(200)
        return FakeResp(404, {"success": False})

    monkeypatch.setattr(mm.requests, "get", fake_get)
    data = mm.ModelScopeClient().detail(server_id="@modelcontextprotocol/github")
    assert "@modelcontextprotocol/github" in called["url"]
    assert called["params"] is None  # 无 token 时不带 get_operational_url
    assert data["id"] == "@modelcontextprotocol/github"


def test_modelscope_parses_mcp_server_list(monkeypatch):
    from agentctl.lib import mcp_market as mm

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "data": {
                    "mcp_server_list": [
                        {
                            "id": "@modelcontextprotocol/github",
                            "name": "GitHub",
                            "description": "GitHub MCP",
                            "categories": ["version-control"],
                        }
                    ],
                    "total_count": 1,
                },
            }

    monkeypatch.setattr(mm.requests, "put", lambda *a, **k: FakeResp())
    items = mm.ModelScopeClient().search("github", limit=5)
    assert len(items) == 1
    assert items[0]["source"] == "modelscope"
    assert items[0]["owner"] == "modelcontextprotocol"
    assert items[0]["name"] == "GitHub"


def test_glama_ns_slug_prefers_id_over_display_name():
    from agentctl.lib.mcp_market import _glama_ns_slug
    assert _glama_ns_slug(
        server_id="LauraMattz/mcp_ai_news",
        owner="LauraMattz",
        name="AI News Aggregator",
    ) == ("LauraMattz", "mcp_ai_news")
    assert _glama_ns_slug(owner="LauraMattz", name="AI News Aggregator") == ("LauraMattz", "")
    assert _glama_ns_slug(owner="acme", name="fetch-server") == ("acme", "fetch-server")


def test_glama_detail_uses_id_slug(monkeypatch):
    from agentctl.lib import mcp_market as mm

    called = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "namespace": "LauraMattz",
                "slug": "mcp_ai_news",
                "name": "AI News Aggregator",
                "repository": {"url": "https://github.com/LauraMattz/mcp_ai_news"},
            }

    def fake_get(url, headers=None, timeout=None):
        called["url"] = url
        called["timeout"] = timeout
        return FakeResp()

    monkeypatch.setattr(mm.requests, "get", fake_get)
    data = mm.GlamaClient().detail(
        namespace="LauraMattz",
        slug="AI News Aggregator",
        server_id="LauraMattz/mcp_ai_news",
    )
    assert "LauraMattz/mcp_ai_news" in called["url"]
    assert "AI%20News" not in called["url"]
    assert data["slug"] == "mcp_ai_news"


def test_glama_resolve_from_readme_without_refetching_glama(monkeypatch):
    from agentctl.lib import mcp_market as mm

    def boom(*a, **k):
        raise AssertionError("should not refetch glama detail")

    monkeypatch.setattr(mm.GlamaClient, "detail", boom)

    readme = '''
# demo
```json
{
  "mcpServers": {
    "breaking-changes": {
      "command": "npx",
      "args": ["-y", "breaking-changes-mcp"],
      "env": { "GITHUB_TOKEN": "ghp_xxx_optional" }
    }
  }
}
```
'''

    def fake_raw(owner, repo, path):
        if path.lower() == "readme.md":
            return readme
        return None

    monkeypatch.setattr(mm, "_github_raw_get", fake_raw)
    out = mm.resolve_mcp_install(
        "glama",
        id="Anicodeth/breaking-changes-mcp",
        owner="Anicodeth",
        name="breaking-changes-mcp",
        detail={
            "repository": {"url": "https://github.com/Anicodeth/breaking-changes-mcp"},
            "environmentVariablesJsonSchema": {
                "properties": {
                    "GITHUB_TOKEN": {"type": "string"},
                    "NPM_REGISTRY": {"type": "string", "default": "https://registry.npmjs.org"},
                }
            },
        },
    )
    assert out["local_name"] == "breaking-changes"
    assert out["server_config"]["command"] == "npx"
    assert out["server_config"]["args"] == ["-y", "breaking-changes-mcp"]
    assert out["server_config"]["env"]["GITHUB_TOKEN"] == "${GITHUB_TOKEN}"
    assert out["server_config"]["env"]["NPM_REGISTRY"] == "https://registry.npmjs.org"
    assert out["resolved_from"] == "repo"


def test_extract_mcp_from_readme_and_package_json():
    from agentctl.lib.mcp_market import _extract_mcp_from_readme, _cfg_from_package_json, _parse_github_repo
    assert _parse_github_repo("https://github.com/Anicodeth/breaking-changes-mcp.git") == (
        "Anicodeth", "breaking-changes-mcp"
    )
    key, cfg = _extract_mcp_from_readme(
        '```json\n{"mcpServers":{"demo":{"command":"npx","args":["-y","demo"]}}}\n```',
        preferred_name="demo",
    )
    assert key == "demo"
    assert cfg["command"] == "npx"
    key2, cfg2 = _cfg_from_package_json('{"name":"foo-mcp"}', preferred_name="foo")
    assert key2 == "foo"
    assert cfg2 == {"command": "npx", "args": ["-y", "foo-mcp"]}


def test_glama_resolve_falls_back_to_package_json(monkeypatch):
    from agentctl.lib import mcp_market as mm

    monkeypatch.setattr(mm.GlamaClient, "detail", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no")))

    def fake_raw(owner, repo, path):
        if path == "package.json":
            return '{"name":"breaking-changes-mcp"}'
        return None

    monkeypatch.setattr(mm, "_github_raw_get", fake_raw)
    out = mm.resolve_mcp_install(
        "glama",
        id="Anicodeth/breaking-changes-mcp",
        detail={"repository": {"url": "https://github.com/Anicodeth/breaking-changes-mcp"}},
    )
    assert out["server_config"]["args"][-1] == "breaking-changes-mcp"
