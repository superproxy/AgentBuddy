"""服务端「根据文章创建插件」全链路测试。

覆盖两条文章分析路径的一致性对比 + 生成质量锁定：
1. crawler_agent.extract_skills_from_article：LLM 输出解析鲁棒性
   （标准 JSON / ```json 代码围栏 / 非法 JSON / 空 skills / 异常兜底 / 名称清洗 / 去重）
2. source 字段规范化（github 仓库 / npm:pip 包 / 空 / 未知单段 → ai-extracted:<文章 URL>）
3. crawler_agent.write_spec：spec.yaml 结构（name/version/description/skills/source_article/rating）
4. crawler_agent.run_task 端到端（mock 搜索 + LLM，临时目录）：
   高分出 spec / 低分跳过且不调 LLM / 无 skills 跳过 / 已 seen 跳过 / GitHub 来源免抓取
5. 对比：crawler.extract_skills_from_article 与 plugin_build.analyze_with_ai
   对同一篇文章是否产出一致的 skill 集合（防止两条路径漂移）。
"""
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import crawler_agent  # noqa: E402
from plugin_build import PluginMeta  # noqa: E402

# 一篇足够长（>2000 字符）、含代码块、命中 trending 信号的文章
LONG_ARTICLE = (
    "# TOP 10 Claude Code Skills 推荐\n\n"
    + "本文盘点最受欢迎的 Claude Code skills，含代码审查、PRD 生成等实战能力。" * 45
    + "\n```python\nprint('hello')\n```\n"
    + "\n```yaml\nname: demo\n```\n"
)
ARTICLE_URL = "https://github.com/acme/awesome-claude-skills"


def _skills_json(raw: list[dict]) -> str:
    return json.dumps({"skills": raw}, ensure_ascii=False)


class TestExtractSkillsParsing(unittest.TestCase):
    """extract_skills_from_article 对 LLM 各种输出的解析鲁棒性。"""

    def _call(self, text: str, content: str = LONG_ARTICLE):
        with mock.patch("crawler_agent.llm_chat", return_value=text):
            skills, _plugin_name = crawler_agent.extract_skills_from_article(
                "TOP 10 Claude Code Skills 推荐", content, ARTICLE_URL)
            return skills

    def test_clean_json(self):
        text = _skills_json([
            {"name": "code-review-prompt", "description": "代码审查 prompt",
             "version": "1.0.0", "source": "github.com/acme/repo"},
        ])
        skills = self._call(text)
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0].name, "code-review-prompt")
        self.assertEqual(skills[0].source, "github.com/acme/repo")

    def test_json_wrapped_in_markdown_fence(self):
        """LLM 用 ```json 代码围栏包裹 JSON —— 当前必须能解析（回归：曾因 json.loads 直解失败返回空）。"""
        text = "```json\n" + _skills_json([
            {"name": "prd-gen", "description": "PRD 生成 skill",
             "version": "1.0.0", "source": "npm:create-vite"},
        ]) + "\n```"
        skills = self._call(text)
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0].name, "prd-gen")
        self.assertEqual(skills[0].source, "npm:create-vite")

    def test_json_wrapped_in_bare_fence(self):
        """LLM 用不带语言标记的 ``` 包裹 JSON。"""
        text = "```\n" + _skills_json([
            {"name": "commit-lint", "description": "commit 规范",
             "version": "1.0.0", "source": ""},
        ]) + "\n```"
        skills = self._call(text)
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0].name, "commit-lint")

    def test_invalid_json_returns_empty(self):
        """LLM 返回非 JSON（纯文本/截断）→ 返回空列表，不抛异常。"""
        self.assertEqual(self._call("这不是 JSON，只是一段话"), [])
        self.assertEqual(self._call(""), [])

    def test_empty_skills_returns_empty(self):
        self.assertEqual(self._call('{"skills": []}'), [])

    def test_llm_exception_returns_empty(self):
        """LLM 调用抛异常 → 返回空列表（run_task 中对应 no skills 跳过）。"""
        with mock.patch("crawler_agent.llm_chat", side_effect=RuntimeError("boom")):
            skills, _ = crawler_agent.extract_skills_from_article("t", LONG_ARTICLE, ARTICLE_URL)
        self.assertEqual(skills, [])

    def test_content_too_short_skips_llm(self):
        """正文 <100 字符 → 直接返回空，且不发起 LLM 调用。"""
        with mock.patch("crawler_agent.llm_chat") as m:
            skills, _ = crawler_agent.extract_skills_from_article("t", "太短了", ARTICLE_URL)
        self.assertEqual(skills, [])
        m.assert_not_called()

    def test_name_sanitized_to_kebab_case(self):
        """名称清洗：转小写、特殊字符转连字符、去除首尾连字符。"""
        text = _skills_json([
            {"name": "Code Review!  Prompt_2", "description": "d",
             "version": "1.0.0", "source": ""},
        ])
        skills = self._call(text)
        self.assertEqual(skills[0].name, "code-review-prompt-2")

    def test_duplicate_names_deduped(self):
        text = _skills_json([
            {"name": "Code-Review", "description": "a", "version": "1.0.0", "source": ""},
            {"name": "code-review", "description": "b", "version": "1.0.0", "source": ""},
        ])
        self.assertEqual(len(self._call(text)), 1)

    def test_description_truncated_to_500(self):
        text = _skills_json([
            {"name": "long-desc", "description": "x" * 800, "version": "1.0.0", "source": ""},
        ])
        self.assertEqual(len(self._call(text)[0].description), 500)

    def test_version_default_1_0_0(self):
        text = _skills_json([
            {"name": "no-version", "description": "d", "version": "", "source": ""},
        ])
        self.assertEqual(self._call(text)[0].version, "1.0.0")

    def test_body_parsed(self):
        """LLM 返回 body（操作说明）→ 透传到 DiscoveredSkill.body（供 SKILL.md 生成）。"""
        text = json.dumps({"name": "claude-code-skills-curated", "skills": [
            {"name": "demo-skill", "description": "d", "version": "1.0.0",
             "source": "", "body": "先读 diff，再逐条检查。"},
        ]}, ensure_ascii=False)
        skills = self._call(text)
        self.assertEqual(skills[0].body, "先读 diff，再逐条检查。")

    def test_plugin_name_extracted_from_llm(self):
        """LLM 返回顶层 name → 提炼为插件名（ASCII kebab-case）。"""
        text = json.dumps({"name": "  Claude Code Skills Curated  ", "skills": []},
                          ensure_ascii=False)
        with mock.patch("crawler_agent.llm_chat", return_value=text):
            _skills, plugin_name = crawler_agent.extract_skills_from_article(
                "TOP 10 Claude Code Skills 推荐", LONG_ARTICLE, ARTICLE_URL)
        self.assertEqual(plugin_name, "claude-code-skills-curated")

    def test_plugin_name_empty_when_missing(self):
        """LLM 未返回顶层 name → 插件名为空（write_spec 兜底标题 slug）。"""
        with mock.patch("crawler_agent.llm_chat", return_value=_skills_json([])):
            _skills, plugin_name = crawler_agent.extract_skills_from_article(
                "TOP 10 Claude Code Skills 推荐", LONG_ARTICLE, ARTICLE_URL)
        self.assertEqual(plugin_name, "")


class TestSourceNormalization(unittest.TestCase):
    """extract_skills_from_article 的 source 字段规范化。"""

    def _one_source(self, src: str) -> str:
        text = _skills_json([
            {"name": "demo-skill", "description": "d", "version": "1.0.0", "source": src},
        ])
        with mock.patch("crawler_agent.llm_chat", return_value=text):
            skills, _ = crawler_agent.extract_skills_from_article("t", LONG_ARTICLE, ARTICLE_URL)
        return skills[0].source

    def test_repo_kept(self):
        self.assertEqual(self._one_source("github.com/owner/repo"), "github.com/owner/repo")

    def test_https_prefix_stripped(self):
        self.assertEqual(self._one_source("https://github.com/owner/repo/"), "github.com/owner/repo")

    def test_npm_package_kept(self):
        self.assertEqual(self._one_source("npm:create-vite@2.0.0"), "npm:create-vite@2.0.0")

    def test_pip_package_kept(self):
        self.assertEqual(self._one_source("pip:fastapi"), "pip:fastapi")

    def test_empty_falls_back_to_ai_extracted(self):
        """LLM 未解析出任何来源 → ai-extracted:<文章 URL>，标记为 AI 推断而非真实安装源。"""
        self.assertEqual(self._one_source(""), f"ai-extracted:{ARTICLE_URL}")

    def test_unknown_single_segment_falls_back_to_ai_extracted(self):
        """非仓库、非包名形式的单段字符串 → ai-extracted:<文章 URL>。"""
        self.assertEqual(self._one_source("randomstring"), f"ai-extracted:{ARTICLE_URL}")


class TestWriteSpec(unittest.TestCase):
    """write_spec 生成的 spec.yaml 结构完整性。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.object(crawler_agent, "SPECS_DIR", Path(self.tmp.name) / "specs")
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def _spec(self) -> dict:
        path = crawler_agent.write_spec(
            task_name="claude-skills",
            article_url=ARTICLE_URL,
            article_title="TOP 10 Claude Code Skills 推荐",
            article_content=LONG_ARTICLE,
            skills=[
                crawler_agent.DiscoveredSkill(
                    name="code-review-prompt", description="代码审查 prompt",
                    version="1.0.0", source="github.com/acme/repo"),
                crawler_agent.DiscoveredSkill(name="prd-gen", description="PRD 生成 skill"),
            ],
            tags=["skills"],
            rating={"score": 75, "breakdown": {}},
        )
        self.assertTrue(path.exists(), f"spec 应写出到 {path}")
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def test_required_fields_present(self):
        spec = self._spec()
        for key in ("name", "version", "description", "skills", "source_article",
                    "rating", "spec_version", "task", "build_status"):
            self.assertIn(key, spec, f"spec 缺少字段 {key}")
        self.assertEqual(spec["version"], "1.0.0")
        self.assertEqual(spec["rating"], 75)
        self.assertEqual(spec["source_article"]["url"], ARTICLE_URL)
        self.assertEqual(spec["source_article"]["title"], "TOP 10 Claude Code Skills 推荐")
        self.assertEqual(spec["build_status"], "pending")

    def test_skills_serialized_with_conditional_source(self):
        spec = self._spec()
        self.assertEqual(len(spec["skills"]), 2)
        # 有 source 的写入 source；无 source 的不写该键
        self.assertIn("source", spec["skills"][0])
        self.assertNotIn("source", spec["skills"][1])

    def test_plugin_name_falls_back_to_title_slug_without_task_prefix(self):
        spec = self._spec()
        # 未传 plugin_name → 兜底文章标题 slug（不再拼 task 前缀，避免 skills-daily-... 这类名字）
        self.assertEqual(spec["name"], "top-10-claude-code-skills", spec["name"])
        self.assertFalse(spec["name"].startswith("claude-skills"), spec["name"])

    def test_plugin_name_uses_llm_extracted_name(self):
        """传 plugin_name → 优先用 LLM 提炼的简洁名。"""
        path = crawler_agent.write_spec(
            task_name="claude-skills",
            article_url=ARTICLE_URL,
            article_title="TOP 10 Claude Code Skills 推荐",
            article_content=LONG_ARTICLE,
            skills=[crawler_agent.DiscoveredSkill(name="demo-skill", description="d")],
            tags=["skills"],
            plugin_name="claude-code-skills-curated",
        )
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(spec["name"], "claude-code-skills-curated")

    def test_skills_serialized_with_body(self):
        """skills 含 body → 写入 spec（供 package_config 生成 SKILL.md）。"""
        path = crawler_agent.write_spec(
            task_name="claude-skills",
            article_url=ARTICLE_URL,
            article_title="TOP 10 Claude Code Skills 推荐",
            article_content=LONG_ARTICLE,
            skills=[crawler_agent.DiscoveredSkill(
                name="code-review-prompt", description="代码审查 prompt",
                source="github.com/acme/repo", body="先读 diff，再按规范逐条检查。")],
            tags=["skills"],
        )
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(spec["skills"][0]["body"], "先读 diff，再按规范逐条检查。")


class TestRunTaskEndToEnd(unittest.TestCase):
    """run_task 端到端：搜索 → 抓取 → 评级 → 抽 skills → 写 spec（全部 mock，临时目录）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        patchers = [
            mock.patch.object(crawler_agent, "SPECS_DIR", root / "specs"),
            mock.patch.object(crawler_agent, "SEEN_URLS_FILE", root / "seen.json"),
            mock.patch.object(crawler_agent, "_load_channel_weights",
                              return_value={"github.com": 20, "mp.weixin.qq.com": 15}),
            mock.patch.object(crawler_agent, "_channel_weight_cache", {}),
        ]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)
        self.task_cfg = {
            "name": "claude-skills", "intent": "trending",
            "max_results": 5, "min_rating": 40, "workers": 1,
        }
        self.channels = [
            {"id": "github", "domain": "github.com", "weight": 20},
            {"id": "tavily", "domain": "mp.weixin.qq.com", "weight": 15},
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, hits, llm_text=None):
        with mock.patch("crawler_agent.generate_queries", return_value=["claude code skills"]), \
             mock.patch("crawler_agent.aggregate_search", return_value=hits), \
             mock.patch("crawler_agent.llm_chat",
                        return_value=llm_text if llm_text is not None else
                        _skills_json([
                            {"name": "code-review-prompt", "description": "代码审查 prompt",
                             "version": "1.0.0", "source": "github.com/acme/repo"},
                        ])):
            return crawler_agent.run_task(self.task_cfg, self.channels)

    def test_good_article_writes_spec(self):
        hits = [{"url": ARTICLE_URL, "title": "TOP 10 Claude Code Skills 推荐",
                 "content": LONG_ARTICLE, "source": "github"}]
        results = self._run(hits)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r.status, "spec")
        self.assertEqual(r.rating, 75)  # 20+10+25+20
        self.assertEqual(r.skills, ["code-review-prompt"])
        # spec 已落盘且可解析
        spec = yaml.safe_load(Path(r.spec_path).read_text(encoding="utf-8"))
        self.assertEqual(spec["rating"], 75)
        self.assertEqual(spec["source_article"]["title"], "TOP 10 Claude Code Skills 推荐")
        self.assertEqual(spec["skills"][0]["name"], "code-review-prompt")

    def test_low_rating_skips_without_llm(self):
        hits = [{"url": "https://unknown-domain-xyz.com/x", "title": "无关标题",
                 "content": "太短了", "source": "tavily"}]
        with mock.patch("crawler_agent.generate_queries", return_value=["claude code skills"]), \
             mock.patch("crawler_agent.aggregate_search", return_value=hits), \
             mock.patch("crawler_agent.llm_chat") as llm:
            results = crawler_agent.run_task(self.task_cfg, self.channels)
        self.assertEqual(results[0].status, "skip")
        self.assertEqual(results[0].reason, "low rating 10 < 40")
        llm.assert_not_called()  # 低分不调 LLM 抽 skills（省钱）

    def test_no_skills_skips(self):
        hits = [{"url": ARTICLE_URL, "title": "TOP 10 Claude Code Skills 推荐",
                 "content": LONG_ARTICLE, "source": "github"}]
        results = self._run(hits, llm_text='{"skills": []}')
        self.assertEqual(results[0].status, "skip")
        self.assertEqual(results[0].reason, "no skills")

    def test_seen_url_skipped(self):
        # 预置 seen 状态：同一 URL 已处理过
        (Path(self.tmp.name) / "seen.json").write_text(
            '{"' + ARTICLE_URL + '": {"ts": 0, "status": "ok"}}', encoding="utf-8")
        hits = [{"url": ARTICLE_URL, "title": "TOP 10 Claude Code Skills 推荐",
                 "content": LONG_ARTICLE, "source": "github"}]
        results = self._run(hits)
        self.assertEqual(results[0].status, "skip")
        self.assertEqual(results[0].reason, "seen")

    def test_github_source_uses_snippet_without_fetch(self):
        """GitHub 来源直接使用搜索 snippet，不调用 fetch_article。"""
        hits = [{"url": ARTICLE_URL, "title": "TOP 10 Claude Code Skills 推荐",
                 "content": LONG_ARTICLE, "source": "github"}]
        with mock.patch("crawler_agent.generate_queries", return_value=["q"]), \
             mock.patch("crawler_agent.aggregate_search", return_value=hits), \
             mock.patch("crawler_agent.llm_chat", return_value=_skills_json([
                 {"name": "code-review-prompt", "description": "d",
                  "version": "1.0.0", "source": ""}])), \
             mock.patch("crawler_agent.fetch_article") as fetch:
            results = crawler_agent.run_task(self.task_cfg, self.channels)
        self.assertEqual(results[0].status, "spec")
        fetch.assert_not_called()


class TestCompareCrawlerVsPluginBuild(unittest.TestCase):
    """对比两条文章分析路径：crawler.extract_skills_from_article vs plugin_build.analyze_with_ai。

    同一篇文章 + 同一 skill 集合，两条路径应产出完全一致的 skill name（防止漂移）。
    """

    def test_same_article_produces_same_skill_names(self):
        base_meta = PluginMeta(
            name="claude-skills", description="TOP 10 Claude Code Skills",
            homepage=ARTICLE_URL, source_type="url", source_url=ARTICLE_URL,
        )
        skill_names = ["code-review-prompt", "prd-gen", "commit-lint"]

        # crawler 路径：LLM 返回 skills JSON
        crawler_json = _skills_json([
            {"name": n, "description": f"{n} 的说明", "version": "1.0.0", "source": ""}
            for n in skill_names
        ])
        with mock.patch("crawler_agent.llm_chat", return_value=crawler_json):
            crawler_skills, _ = crawler_agent.extract_skills_from_article(
                "TOP 10 Claude Code Skills 推荐", LONG_ARTICLE, ARTICLE_URL)
        crawler_names = [s.name for s in crawler_skills]

        # plugin_build 路径：LLM 返回 plugin.yaml
        yaml_text = (
            "name: claude-skills\nversion: '1.0.0'\n"
            "description: TOP 10 Claude Code Skills\n"
            "skills:\n"
            + "".join(
                f"  - name: {n}\n    description: {n} 的说明\n    version: '1.0.0'\n"
                f"    source: ai-extracted:{ARTICLE_URL}\n"
                for n in skill_names
            )
        )
        with mock.patch("plugin_build.generate_plugin_with_direct_llm", return_value=yaml_text):
            from plugin_build import analyze_with_ai
            meta = analyze_with_ai(Path(self.tmp.name), ARTICLE_URL, base_meta,
                                   llm_config={"base_url": "https://x/v1",
                                               "api_key": "k", "model": "m"})
        build_names = [s.name for s in meta.skills]

        self.assertEqual(crawler_names, skill_names)
        self.assertEqual(build_names, skill_names)
        # 对比：两条路径对同一文章产出的 skill 集合一致
        self.assertEqual(sorted(crawler_names), sorted(build_names))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()


class TestPackageSkillMd(unittest.TestCase):
    """body→SKILL.md 链路：plugin_build 打包时把含 body 的技能写为 skills/<name>/SKILL.md。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.tmp.name) / "builds"

    def tearDown(self):
        self.tmp.cleanup()

    def _package(self, skills: list[dict]) -> zipfile.ZipFile:
        from plugin_build import generate_config, meta_from_config, package_config
        meta = meta_from_config({"name": "curated-skills", "skills": skills})
        cfg = generate_config(meta)
        zip_path = package_config(cfg, mode="inline", output_dir=self.output_dir)
        return zipfile.ZipFile(zip_path)

    def test_body_skill_writes_skill_md(self):
        with self._package([
            {"name": "code-review-prompt", "description": "代码审查 prompt",
             "version": "1.0.0", "source": "github.com/acme/repo",
             "body": "先读 diff，再按规范逐条检查。"},
        ]) as zf:
            names = set(zf.namelist())
            self.assertIn("skills/code-review-prompt/SKILL.md", names)
            md = zf.read("skills/code-review-prompt/SKILL.md").decode("utf-8")
            self.assertIn("# code-review-prompt", md)
            self.assertIn("先读 diff，再按规范逐条检查。", md)
            self.assertIn("github.com/acme/repo", md)

    def test_no_body_skill_skips_skill_md(self):
        with self._package([
            {"name": "plain-skill", "description": "无 body 的 skill",
             "version": "1.0.0", "source": "github.com/acme/repo"},
        ]) as zf:
            names = set(zf.namelist())
            self.assertNotIn("skills/plain-skill/SKILL.md", names)

    def test_config_preserves_body_for_install(self):
        """plugin.yaml 中 skills 保留 body 字段，供安装方生成 SKILL.md。"""
        from plugin_build import generate_config, meta_from_config
        meta = meta_from_config({"name": "curated-skills", "skills": [
            {"name": "demo-skill", "description": "d", "version": "1.0.0",
             "source": "", "body": "操作步骤。"},
        ]})
        cfg = generate_config(meta)
        self.assertEqual(cfg["skills"][0]["body"], "操作步骤。")


if __name__ == "__main__":
    unittest.main()
