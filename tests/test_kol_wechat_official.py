from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.kol_daily import _persisted_validated_bundle
from xiaocao.kol.enrichment_types import (
    EnrichmentDiagnosticError,
    EnrichmentError,
)
from xiaocao.kol.wechat_official import (
    DEFAULT_PUBLISHERS,
    OfficialAccountInbox,
    OfficialAccountOpenCliAcquirer,
    OfficialAccountSubscription,
    WechatCliOfficialAccountReader,
    parse_official_account_articles,
    validate_official_account_capsule,
)


def _article(
    article_id: str,
    publisher: str,
    title: str,
    published_at: str,
) -> dict:
    return {
        "id": article_id,
        "publisher": publisher,
        "title": title,
        "description": "本地发现摘要不得作为远端正文证据",
        "published_at": published_at,
        "received_at": published_at,
        "url": (
            "http://mp.weixin.qq.com/s?"
            f"__biz={article_id[:8]}&mid=2247483945&idx=1&sn={article_id[:32]}"
            "&chksm=tracking&scene=0&xtrack=1#rd"
        ),
    }


def _payload() -> dict:
    return {
        "update_count": 4,
        "failures": [],
        "updates": [
            _article(
                "a" * 64,
                "A也叫艾利克斯",
                "旧文章",
                "2026-08-03T15:00:00+08:00",
            ),
            _article(
                "b" * 64,
                "A也叫艾利克斯",
                '第一缕"光"',
                "2026-08-04T15:52:23+08:00",
            ),
            _article(
                "c" * 64,
                "刘少狙击营",
                "业绩炸裂",
                "2026-08-04T16:57:14+08:00",
            ),
            _article(
                "d" * 64,
                "名字相近但不是目标公众号",
                "不应进入 KOL",
                "2026-08-04T17:00:00+08:00",
            ),
        ],
    }


def _capture_one(tmp_path: Path, *, payload: dict | None = None) -> dict:
    captured: list[dict] = []

    def exchange(
        capsule: dict,
        *,
        object_kind: str,
        title: str,
    ) -> dict:
        assert object_kind == "article"
        assert title == capsule["title"]
        captured.append(validate_official_account_capsule(capsule))
        return {
            "status": "Handoff完成",
            "handoff_id": capsule["handoff_id"],
            "mailbox_outcome": "created",
            "content_sha256": "f" * 64,
        }

    OfficialAccountSubscription(
        tmp_path / "local",
        reader=lambda: payload
        or {"updates": [_payload()["updates"][2]], "failures": []},
        handoff_exchange=exchange,
    ).run_once()
    assert len(captured) == 1
    return captured[0]


def _opencli_runner(
    *,
    markdown: str,
    title: str,
    author: str,
    publish_time: str,
    with_image: bool = True,
):
    calls: list[tuple[list[str], dict]] = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        output_root = Path(command[command.index("--output") + 1])
        article_dir = output_root / "article"
        article_dir.mkdir(parents=True, exist_ok=True)
        if with_image:
            image_dir = article_dir / "images"
            image_dir.mkdir()
            (image_dir / "image-1.png").write_bytes(b"\x89PNG\r\narticle-image")
        saved = article_dir / "article.md"
        saved.write_text(markdown, encoding="utf-8")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                [{
                    "title": title,
                    "author": author,
                    "publish_time": publish_time,
                    "status": "success",
                    "size": "2.4 KB",
                    "saved": str(saved.resolve()),
                }],
                ensure_ascii=False,
            ),
            stderr="",
        )

    return runner, calls


def _long_body() -> str:
    return (
        "这是完整文章正文，用于确认抓取结果不是摘要、验证码页"
        "或空模板。"
        "正文包含足够多的连续信息、完整句子和自然收束，验证 Markdown "
        "在进入模型前已经作为文件落盘。"
    ) * 3


def test_official_account_parser_uses_exact_publishers_and_url_only_metadata():
    items = parse_official_account_articles(_payload())

    assert [item["publisher"] for item in items] == [
        "A也叫艾利克斯",
        "A也叫艾利克斯",
        "刘少狙击营",
    ]
    assert items[1]["kol_id"] == "kol-a-alex"
    assert items[2]["kol_id"] == "kol-liushao-jujiying"
    assert all(item["source_url"].startswith("https://mp.weixin.qq.com/s?") for item in items)
    assert all("scene=" not in item["source_url"] for item in items)
    assert all("xtrack=" not in item["source_url"] for item in items)
    assert all("description" not in item and "evidence_text" not in item for item in items)
    assert all(len(item["discovery_version"]) == 64 for item in items)


def test_official_account_parser_fails_closed_on_incomplete_scan():
    with pytest.raises(
        EnrichmentDiagnosticError,
        match="official-account scan is incomplete",
    ):
        parse_official_account_articles(
            {"updates": [], "failures": [{"database": "biz_message_0.db"}]}
        )


def test_official_account_reader_calls_one_stateless_combined_window(tmp_path):
    executable = tmp_path / "wechat-cli"
    executable.write_text("placeholder", encoding="utf-8")
    calls: list[tuple[list[str], dict]] = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout=json.dumps(_payload(), ensure_ascii=False))

    reader = WechatCliOfficialAccountReader(
        DEFAULT_PUBLISHERS,
        executable=executable,
        within="48h",
        runner=runner,
    )

    assert reader()["update_count"] == 4
    assert calls == [(
        [
            str(executable.resolve()),
            "subscription-updates",
            "--within",
            "48h",
            "--publisher",
            "刘少狙击营",
            "--publisher",
            "A也叫艾利克斯",
            "--format",
            "json",
        ],
        {
            "check": True,
            "capture_output": True,
            "text": True,
            "timeout": 30,
        },
    )]


def test_first_hour_baselines_older_articles_and_hands_off_latest_url_per_kol(tmp_path):
    requests: list[dict] = []
    capsules: list[dict] = []

    def exchange(
        capsule: dict,
        *,
        object_kind: str,
        title: str,
    ) -> dict:
        requests.append({"object_kind": object_kind, "title": title})
        capsules.append(validate_official_account_capsule(capsule))
        return {
            "status": "Handoff完成",
            "handoff_id": capsule["handoff_id"],
            "mailbox_outcome": "created",
            "content_sha256": "f" * 64,
        }

    subscription = OfficialAccountSubscription(
        tmp_path / "official",
        reader=_payload,
        handoff_exchange=exchange,
        clock=lambda: datetime.fromisoformat("2026-08-05T10:00:00+08:00"),
    )

    first = subscription.run_once()
    second = subscription.run_once()

    assert first["status"] == "no_update"
    assert first["handoff_dispatched_count"] == 2
    assert second["handoff_dispatched_count"] == 0
    assert [capsule["title"] for capsule in capsules] == ['第一缕"光"', "业绩炸裂"]
    assert all(capsule["content_transport"] == "public_url_only" for capsule in capsules)
    assert all(
        field not in capsule
        for capsule in capsules
        for field in ("description", "evidence_text", "markdown", "local_path")
    )
    assert all(request["object_kind"] == "article" for request in requests)
    manifest = json.loads((tmp_path / "official" / "manifest.json").read_text(encoding="utf-8"))
    assert sorted(item["status"] for item in manifest["items"].values()) == [
        "completed",
        "completed",
        "historical_baseline",
    ]


def test_handoff_publishes_capsule_to_mailbox_without_remote_task_injection(
    tmp_path,
):
    published: list[dict] = []

    def exchange(
        capsule: dict,
        *,
        object_kind: str,
        title: str,
    ) -> dict:
        published.append(capsule)
        assert object_kind == "article"
        assert title == "业绩炸裂"
        return {
            "status": "Handoff完成",
            "handoff_id": capsule["handoff_id"],
            "mailbox_outcome": "created",
            "content_sha256": "f" * 64,
        }

    OfficialAccountSubscription(
        tmp_path / "official",
        reader=lambda: {"updates": [_payload()["updates"][2]], "failures": []},
        handoff_exchange=exchange,
    ).run_once()

    [capsule] = published
    assert capsule["content_transport"] == "public_url_only"
    assert all(
        field not in capsule
        for field in ("local_path", "capsule_path", "remote_thread_id")
    )


def test_remote_import_is_idempotent_and_contains_no_article_evidence(tmp_path):
    capsule = _capture_one(tmp_path)
    inbox = OfficialAccountInbox(tmp_path / "remote")

    first = inbox.import_capsule(capsule)
    second = inbox.import_capsule(capsule)
    [item] = inbox.pending_items()

    assert first["status"] == "accepted"
    assert second["status"] == "already_present"
    assert item["status"] == "imported"
    assert "evidence_path" not in item
    assert "description" not in item


def test_remote_import_rejects_tampered_url_capsule(tmp_path):
    capsule = _capture_one(tmp_path)
    tampered = {**capsule, "title": "被篡改"}

    with pytest.raises(EnrichmentError, match="handoff binding is invalid"):
        OfficialAccountInbox(tmp_path / "remote").import_capsule(tampered)


def test_opencli_acquisition_materializes_complete_markdown_and_images(tmp_path):
    capsule = _capture_one(tmp_path)
    inbox = OfficialAccountInbox(tmp_path / "remote")
    inbox.import_capsule(capsule)
    [item] = inbox.pending_items()
    markdown = (
        "# 业绩炸裂\n\n公众号：刘少狙击营\n\n"
        + _long_body()
        + "\n\n![关键图](images/image-1.png)\n"
    )
    runner, calls = _opencli_runner(
        markdown=markdown,
        title="业绩炸裂",
        author="刘少狙击营",
        publish_time="2026年8月4日 16:57",
    )
    acquirer = OfficialAccountOpenCliAcquirer(
        tmp_path / "remote" / "opencli",
        runner=runner,
    )

    acquired = inbox.acquire(item, acquirer=acquirer)
    replay = inbox.acquire(acquired, acquirer=lambda _item: pytest.fail("must not refetch"))

    assert acquired["status"] == "acquired"
    assert acquired["image_count"] == 1
    assert replay["raw_markdown_sha256"] == acquired["raw_markdown_sha256"]
    assert Path(acquired["raw_markdown_path"]).is_file()
    [command_call] = calls
    command, kwargs = command_call
    assert command[:3] == ["opencli", "weixin", "download"]
    assert command[command.index("--download-images") + 1] == "true"
    assert command[command.index("--window") + 1] == "background"
    assert command[command.index("--site-session") + 1] == "persistent"
    assert command[command.index("--keep-tab") + 1] == "true"
    assert {
        key: kwargs[key]
        for key in ("check", "capture_output", "text", "timeout")
    } == {
        "check": False,
        "capture_output": True,
        "text": True,
        "timeout": 120,
    }
    assert kwargs["env"]["OPENCLI_BROWSER_COMMAND_TIMEOUT"] == "110"


def test_opencli_accepts_page_time_bound_to_received_at_after_discovery_drift(
    tmp_path,
):
    capsule = _capture_one(tmp_path)
    inbox = OfficialAccountInbox(tmp_path / "remote")
    inbox.import_capsule(capsule)
    [item] = inbox.pending_items()
    item["published_at"] = "2026-08-04T16:51:40+08:00"
    item["received_at"] = "2026-08-04T16:57:40+08:00"
    markdown = "# 业绩炸裂\n\n公众号：刘少狙击营\n\n" + _long_body()
    runner, _calls = _opencli_runner(
        markdown=markdown,
        title="业绩炸裂",
        author="刘少狙击营",
        publish_time="2026年8月4日 16:57",
        with_image=False,
    )

    acquired = OfficialAccountOpenCliAcquirer(
        tmp_path / "remote" / "opencli",
        runner=runner,
    )(item)

    assert acquired["page_publish_time"] == "2026-08-04T16:57:00+08:00"
    assert acquired["publish_time_delta_seconds"] == 320
    assert acquired["publish_time_match_basis"] == "received_at"


def test_opencli_rejects_page_time_far_from_both_discovery_anchors(tmp_path):
    capsule = _capture_one(tmp_path)
    inbox = OfficialAccountInbox(tmp_path / "remote")
    inbox.import_capsule(capsule)
    [item] = inbox.pending_items()
    item["published_at"] = "2026-08-04T16:51:40+08:00"
    item["received_at"] = "2026-08-04T16:57:40+08:00"
    markdown = "# 业绩炸裂\n\n公众号：刘少狙击营\n\n" + _long_body()
    runner, _calls = _opencli_runner(
        markdown=markdown,
        title="业绩炸裂",
        author="刘少狙击营",
        publish_time="2026年8月4日 17:15",
        with_image=False,
    )

    with pytest.raises(EnrichmentDiagnosticError) as captured:
        OfficialAccountOpenCliAcquirer(
            tmp_path / "remote" / "opencli",
            runner=runner,
        )(item)

    assert captured.value.diagnostic_code == (
        "wechat_official_publish_time_mismatch"
    )


def test_opencli_profile_is_bound_to_official_account_download(tmp_path):
    capsule = _capture_one(tmp_path)
    inbox = OfficialAccountInbox(tmp_path / "remote")
    inbox.import_capsule(capsule)
    [item] = inbox.pending_items()
    markdown = "# 业绩炸裂\n\n公众号：刘少狙击营\n\n" + _long_body()
    runner, calls = _opencli_runner(
        markdown=markdown,
        title="业绩炸裂",
        author="刘少狙击营",
        publish_time="2026年8月4日 16:57",
        with_image=False,
    )

    inbox.acquire(
        item,
        acquirer=OfficialAccountOpenCliAcquirer(
            tmp_path / "remote" / "opencli",
            runner=runner,
            opencli_profile="du6r9r44",
        ),
    )

    [command_call] = calls
    command, _kwargs = command_call
    assert command[:5] == [
        "opencli",
        "--profile",
        "du6r9r44",
        "weixin",
        "download",
    ]


def test_opencli_failure_recovers_complete_materialized_article(tmp_path):
    capsule = _capture_one(tmp_path)
    inbox = OfficialAccountInbox(tmp_path / "remote")
    inbox.import_capsule(capsule)
    [item] = inbox.pending_items()
    source_root = tmp_path / "remote" / "opencli" / item["handoff_id"]
    article_dir = source_root / item["title"]
    article_dir.mkdir(parents=True)
    saved = article_dir / f"{item['title']}.md"
    saved.write_text(
        f"# {item['title']}\n"
        f"> 公众号: {item['publisher']}\n"
        "> 发布时间: 2026年8月4日 16:57\n"
        f"> 原文链接: {item['source_url']}\n\n"
        + _long_body(),
        encoding="utf-8",
    )

    def runner(_command, **_kwargs):
        return SimpleNamespace(returncode=75, stdout="", stderr="TIMEOUT")

    acquired = inbox.acquire(
        item,
        acquirer=OfficialAccountOpenCliAcquirer(
            tmp_path / "remote" / "opencli",
            runner=runner,
            opencli_profile="du6r9r44",
        ),
    )

    assert acquired["status"] == "acquired"
    assert acquired["opencli_recovery"] == "materialized_after_opencli_failure"
    assert acquired["raw_markdown_path"] == str(saved.resolve())


def test_opencli_reuses_materialized_article_after_recorded_failure(tmp_path):
    capsule = _capture_one(tmp_path)
    inbox = OfficialAccountInbox(tmp_path / "remote")
    inbox.import_capsule(capsule)
    [item] = inbox.pending_items()
    source_root = tmp_path / "remote" / "opencli" / item["handoff_id"]
    article_dir = source_root / item["title"]
    article_dir.mkdir(parents=True)
    saved = article_dir / f"{item['title']}.md"
    saved.write_text(
        f"# {item['title']}\n"
        f"> 公众号: {item['publisher']}\n"
        "> 发布时间: 2026年8月4日 16:57\n"
        f"> 原文链接: {item['source_url']}\n\n"
        + _long_body(),
        encoding="utf-8",
    )
    item["last_acquisition_failure"] = {
        "category": "source_error",
        "code": "wechat_official_opencli_failed",
        "stage": "wechat_official_opencli",
    }

    def runner(*_args, **_kwargs):
        pytest.fail("must reuse the validated same-handoff artifact")

    result = OfficialAccountOpenCliAcquirer(
        tmp_path / "remote" / "opencli",
        runner=runner,
        opencli_profile="du6r9r44",
    )(item)

    assert result["opencli_recovery"] == "materialized_after_opencli_failure"
    assert result["raw_markdown_path"] == str(saved.resolve())


def test_opencli_recovers_bound_type_10_text_share_without_refetching_mailbox(
    tmp_path,
):
    capsule = _capture_one(
        tmp_path,
        payload={
            "updates": [
                _article(
                    "c" * 64,
                    "刘少狙击营",
                    _long_body(),
                    "2026-08-04T16:57:14+08:00",
                )
            ],
            "failures": [],
        },
    )
    inbox = OfficialAccountInbox(tmp_path / "remote")
    inbox.import_capsule(capsule)
    [item] = inbox.pending_items()
    calls: list[list[str]] = []

    def runner(command, **_kwargs):
        calls.append(command)
        if command[1:3] == ["weixin", "download"]:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps([{
                    "title": "Error",
                    "author": "-",
                    "publish_time": "-",
                    "status": "failed — no title",
                    "size": "-",
                    "saved": "-",
                }], ensure_ascii=False),
                stderr="",
            )
        if "eval" in command:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({
                    "url": item["source_url"],
                    "ready_state": "complete",
                    "item_show_type": "10",
                    "title": item["title"],
                    "author": item["publisher"],
                    "publish_time": "2026-08-04 16:57",
                    "body": item["title"],
                    "image_urls": [],
                    "verification_required": False,
                }, ensure_ascii=False),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    acquired = inbox.acquire(
        item,
        acquirer=OfficialAccountOpenCliAcquirer(
            tmp_path / "remote" / "opencli",
            runner=runner,
        ),
    )

    assert acquired["status"] == "acquired"
    assert acquired["opencli_recovery"] == "text_share_page"
    assert acquired["image_count"] == 0
    assert acquired["publish_time_delta_seconds"] == 14
    assert Path(acquired["raw_markdown_path"]).read_text(encoding="utf-8").endswith(
        f"{item['title']}\n"
    )
    assert calls[1][:4] == ["opencli", "browser", "site:weixin", "open"]
    assert calls[2][:4] == ["opencli", "browser", "site:weixin", "eval"]
    assert calls[3] == ["opencli", "browser", "site:weixin", "close"]


def test_opencli_text_share_recovery_rejects_non_text_page(tmp_path):
    capsule = _capture_one(tmp_path)
    inbox = OfficialAccountInbox(tmp_path / "remote")
    inbox.import_capsule(capsule)
    [item] = inbox.pending_items()

    def runner(command, **_kwargs):
        if command[1:3] == ["weixin", "download"]:
            payload = [{
                "title": "Error",
                "author": "-",
                "publish_time": "-",
                "status": "failed — no title",
                "size": "-",
                "saved": "-",
            }]
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(payload, ensure_ascii=False),
                stderr="",
            )
        if "eval" in command:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({
                    "ready_state": "complete",
                    "item_show_type": "0",
                    "title": item["title"],
                    "author": item["publisher"],
                    "publish_time": "2026-08-04 16:57",
                    "body": item["title"],
                    "image_urls": [],
                    "verification_required": False,
                }, ensure_ascii=False),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    with pytest.raises(EnrichmentDiagnosticError) as captured:
        inbox.acquire(
            item,
            acquirer=OfficialAccountOpenCliAcquirer(
                tmp_path / "remote" / "opencli",
                runner=runner,
            ),
        )

    assert captured.value.diagnostic_category == "source_error"
    assert (
        captured.value.diagnostic_code
        == "wechat_official_text_share_recovery_invalid"
    )


def test_opencli_challenge_is_user_action_and_does_not_create_evidence(tmp_path):
    capsule = _capture_one(tmp_path)
    inbox = OfficialAccountInbox(tmp_path / "remote")
    inbox.import_capsule(capsule)
    [item] = inbox.pending_items()

    def runner(_command, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps([{
                "title": "-",
                "author": "-",
                "publish_time": "-",
                "status": "failed — verification required in WeChat browser page",
                "size": "-",
                "saved": "-",
            }], ensure_ascii=False),
            stderr="",
        )

    acquirer = OfficialAccountOpenCliAcquirer(tmp_path / "remote" / "opencli", runner=runner)

    with pytest.raises(EnrichmentDiagnosticError) as captured:
        inbox.acquire(item, acquirer=acquirer)

    assert captured.value.diagnostic_category == "user_action"
    assert captured.value.diagnostic_code == "wechat_official_captcha_required"
    assert inbox.pending_items()[0]["status"] == "verification_required"
    assert not (tmp_path / "remote" / "evidence").exists()


def test_image_notes_are_markdown_covered_then_analysis_is_idempotent(tmp_path):
    capsule = _capture_one(tmp_path)
    inbox = OfficialAccountInbox(tmp_path / "remote")
    inbox.import_capsule(capsule)
    [item] = inbox.pending_items()
    markdown = (
        "# 业绩炸裂\n\n公众号：刘少狙击营\n\n"
        + _long_body()
        + "\n\n![关键图](images/image-1.png)\n"
    )
    runner, _calls = _opencli_runner(
        markdown=markdown,
        title="业绩炸裂",
        author="刘少狙击营",
        publish_time="2026年8月4日 16:57",
    )
    acquired = inbox.acquire(
        item,
        acquirer=OfficialAccountOpenCliAcquirer(
            tmp_path / "remote" / "opencli", runner=runner
        ),
    )
    image_request = inbox.prepare_image_request(acquired)
    assert image_request is not None
    assert image_request["required_output"].startswith(
        "Write UTF-8 Markdown headed `# 图片信息转写`."
    )
    image_sha = image_request["images"][0]["sha256"]
    notes_path = tmp_path / "image-notes.md"
    notes_path.write_text(
        "# 图片信息转写\n\n"
        "## 图片 1\n\n"
        f"- SHA-256：`{image_sha}`\n"
        "- 信息属性：包含正文增量。\n"
        "- 转写：图中表格给出了完整的业绩数据、单位和同比关系。\n"
        "- 边界：小字号脚注仍需谨慎核对。\n",
        encoding="utf-8",
    )
    ready = inbox.materialize_evidence(acquired, image_notes_path=notes_path)
    request = inbox.prepare_analysis_request(ready)

    assert ready["status"] == "evidence_ready"
    assert ready["evidence_scope"] == "complete_article_markdown_with_image_notes"
    evidence = Path(ready["evidence_path"]).read_text(encoding="utf-8")
    assert "业绩炸裂" in evidence
    assert "图片证据文字化" in evidence
    assert image_sha in evidence
    assert request["evidence_sha256"] == hashlib.sha256(
        Path(ready["evidence_path"]).read_bytes()
    ).hexdigest()
    assert request["captured_at"] == ready["received_at"]
    assert "longitudinal_projection" in request[
        "required_longitudinal_projection"
    ]

    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "items": [{
                    "source": ready["source"],
                    "author": ready["author"],
                    "title": ready["title"],
                    "published_at": ready["published_at"],
                    "evidence_path": ready["evidence_path"],
                    "evidence_sha256": ready["evidence_sha256"],
                }]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class FakePipeline:
        book = SimpleNamespace(account={"book": "KOL-US", "paper_only": True})

        @staticmethod
        def process(_bundle):
            return {
                "status": "processed",
                "items": [{"daily_terminal": {"kind": "source_event"}}],
            }

        @staticmethod
        def deliver_wechat(_result, *, sender):
            assert callable(sender)
            return {"status": "suppressed"}

    decided = inbox.decide(
        ready,
        bundle_path=bundle_path,
        pipeline=FakePipeline(),
        sender=lambda _title, _body: {},
    )
    replay = inbox.decide(
        ready,
        bundle_path=bundle_path,
        pipeline=FakePipeline(),
        sender=lambda _title, _body: {},
    )

    assert decided["idempotent_replay"] is False
    assert replay["idempotent_replay"] is True
    assert inbox.status()["pending_count"] == 0


def test_official_analysis_artifacts_are_namespaced_per_handoff(tmp_path):
    inbox = OfficialAccountInbox(tmp_path / "remote")
    shared_dir = (tmp_path / "remote" / "analysis_requests").resolve()
    shared_dir.mkdir(parents=True)
    (shared_dir / "validated_bundle.json").write_text(
        "stale bundle from another handoff",
        encoding="utf-8",
    )

    def ready_item(handoff_id: str, title: str) -> dict:
        evidence_path = tmp_path / "remote" / "evidence" / f"{handoff_id}.md"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(f"# {title}\n\n正文证据。", encoding="utf-8")
        return {
            "status": "evidence_ready",
            "handoff_id": handoff_id,
            "source_identity": f"wechat-official:{handoff_id}",
            "publication_version": f"version-{handoff_id}",
            "kol_id": "kol-a-alex",
            "author": "A也叫艾利克斯",
            "source": "微信公众号",
            "publisher": "A也叫艾利克斯",
            "title": title,
            "published_at": "2026-08-24T16:32:35+08:00",
            "received_at": "2026-08-24T16:33:21+08:00",
            "page_publish_time": "2026年8月24日 16:32",
            "evidence_path": str(evidence_path),
            "evidence_sha256": hashlib.sha256(
                evidence_path.read_bytes()
            ).hexdigest(),
            "evidence_scope": "complete_article_markdown_with_image_notes",
        }

    first = inbox.prepare_analysis_request(
        ready_item("a" * 64, "第一篇")
    )
    second = inbox.prepare_analysis_request(
        ready_item("b" * 64, "第二篇")
    )

    assert first["artifact_dir"] == str((shared_dir / ("a" * 64)).resolve())
    assert second["artifact_dir"] == str((shared_dir / ("b" * 64)).resolve())
    assert first["artifact_dir"] != second["artifact_dir"]
    assert _persisted_validated_bundle(first) is None
    assert _persisted_validated_bundle(second) is None


def test_official_analysis_request_migrates_legacy_shared_artifact_dir(tmp_path):
    inbox = OfficialAccountInbox(tmp_path / "remote")
    handoff_id = "c" * 64
    item = {
        "status": "evidence_ready",
        "handoff_id": handoff_id,
        "source_identity": f"wechat-official:{handoff_id}",
        "publication_version": "version-c",
        "kol_id": "kol-a-alex",
        "author": "A也叫艾利克斯",
        "source": "微信公众号",
        "publisher": "A也叫艾利克斯",
        "title": "旧请求",
        "published_at": "2026-08-24T16:32:35+08:00",
        "received_at": "2026-08-24T16:33:21+08:00",
        "page_publish_time": "2026年8月24日 16:32",
        "evidence_scope": "complete_article_markdown_with_image_notes",
    }
    evidence_path = tmp_path / "remote" / "evidence" / f"{handoff_id}.md"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("# 旧请求\n\n正文证据。", encoding="utf-8")
    item["evidence_path"] = str(evidence_path)
    item["evidence_sha256"] = hashlib.sha256(
        evidence_path.read_bytes()
    ).hexdigest()

    request = inbox.prepare_analysis_request(item)
    legacy_artifact_dir = (
        tmp_path / "remote" / "analysis_requests"
    ).resolve()
    legacy = {**request, "artifact_dir": str(legacy_artifact_dir)}
    Path(request["analysis_request_path"]).write_text(
        json.dumps(legacy, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    migrated = inbox.prepare_analysis_request(item)

    assert migrated["artifact_dir"] == str(
        (legacy_artifact_dir / handoff_id).resolve()
    )
    persisted = json.loads(
        Path(request["analysis_request_path"]).read_text(encoding="utf-8")
    )
    assert persisted["artifact_dir"] == migrated["artifact_dir"]
    events = [
        json.loads(line)
        for line in (tmp_path / "remote" / "inbox_events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert events[-1] == {
        "schema_version": 2,
        "event": "official_account_analysis_request_artifact_migrated",
        "handoff_id": handoff_id,
        "from_artifact_dir": str(legacy_artifact_dir),
        "to_artifact_dir": migrated["artifact_dir"],
    }


def test_image_notes_must_cover_every_image_sha(tmp_path):
    capsule = _capture_one(tmp_path)
    inbox = OfficialAccountInbox(tmp_path / "remote")
    inbox.import_capsule(capsule)
    [item] = inbox.pending_items()
    markdown = (
        "# 业绩炸裂\n\n公众号：刘少狙击营\n\n"
        + _long_body()
        + "\n\n![关键图](images/image-1.png)\n"
    )
    runner, _calls = _opencli_runner(
        markdown=markdown,
        title="业绩炸裂",
        author="刘少狙击营",
        publish_time="2026年8月4日 16:57",
    )
    acquired = inbox.acquire(
        item,
        acquirer=OfficialAccountOpenCliAcquirer(
            tmp_path / "remote" / "opencli", runner=runner
        ),
    )
    notes_path = tmp_path / "incomplete-notes.md"
    notes_path.write_text(
        "# 图片信息转写\n\n"
        "## 图片 1\n\n图片看起来包含一些业务信息和表格，"
        "但这份故意不完整的说明没有绑定图片哈希，"
        "也不能通过覆盖验收。",
        encoding="utf-8",
    )

    with pytest.raises(EnrichmentError, match="cover every image"):
        inbox.materialize_evidence(acquired, image_notes_path=notes_path)


def test_image_notes_must_start_with_required_heading(tmp_path):
    capsule = _capture_one(tmp_path)
    inbox = OfficialAccountInbox(tmp_path / "remote")
    inbox.import_capsule(capsule)
    [item] = inbox.pending_items()
    markdown = (
        "# 业绩炸裂\n\n公众号：刘少狙击营\n\n"
        + _long_body()
        + "\n\n![关键图](images/image-1.png)\n"
    )
    runner, _calls = _opencli_runner(
        markdown=markdown,
        title="业绩炸裂",
        author="刘少狙击营",
        publish_time="2026年8月4日 16:57",
    )
    acquired = inbox.acquire(
        item,
        acquirer=OfficialAccountOpenCliAcquirer(
            tmp_path / "remote" / "opencli", runner=runner
        ),
    )
    image_request = inbox.prepare_image_request(acquired)
    assert image_request is not None
    image_sha = image_request["images"][0]["sha256"]
    notes_path = tmp_path / "wrong-heading-notes.md"
    notes_path.write_text(
        "# 错误标题\n\n"
        "图片信息转写应当出现在正文中，但不是标题。\n"
        f"- SHA-256：`{image_sha}`\n"
        "- 信息属性：包含正文增量。\n"
        "- 边界：小字号脚注仍需谨慎核对。\n",
        encoding="utf-8",
    )

    with pytest.raises(EnrichmentError, match="required heading"):
        inbox.materialize_evidence(acquired, image_notes_path=notes_path)


def test_decided_item_completion_requires_hash_bound_daily_terminal(tmp_path):
    inbox = OfficialAccountInbox(tmp_path / "remote")
    handoff_id = "a" * 64
    result_path = tmp_path / "remote" / "decisions" / handoff_id / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps({"items": [{"daily_terminal": {"kind": "source_event"}}]}),
        encoding="utf-8",
    )
    result_sha256 = hashlib.sha256(result_path.read_bytes()).hexdigest()
    inbox.manifest_path.write_text(
        json.dumps({
            "schema_version": 2,
            "items": {
                handoff_id: {
                    "handoff_id": handoff_id,
                    "status": "decided",
                    "decision_result_path": str(result_path),
                    "decision_result_sha256": result_sha256,
                },
            },
        }),
        encoding="utf-8",
    )

    completed = inbox.verify_completed(handoff_id)
    assert completed["decision_result_sha256"] == result_sha256

    result_path.unlink()
    with pytest.raises(EnrichmentError, match="decision result changed"):
        inbox.verify_completed(handoff_id)


def test_no_image_article_materializes_markdown_without_agent_input(tmp_path):
    capsule = _capture_one(tmp_path)
    inbox = OfficialAccountInbox(tmp_path / "remote")
    inbox.import_capsule(capsule)
    [item] = inbox.pending_items()
    markdown = "# 业绩炸裂\n\n公众号：刘少狙击营\n\n" + _long_body() + "\n"
    runner, _calls = _opencli_runner(
        markdown=markdown,
        title="业绩炸裂",
        author="刘少狙击营",
        publish_time="2026年8月4日 16:57",
        with_image=False,
    )
    acquired = inbox.acquire(
        item,
        acquirer=OfficialAccountOpenCliAcquirer(
            tmp_path / "remote" / "opencli", runner=runner
        ),
    )

    assert inbox.prepare_image_request(acquired) is None
    ready = inbox.materialize_evidence(acquired)
    assert ready["image_count"] == 0
    assert "正文没有需要逐图读取的图片" in Path(ready["evidence_path"]).read_text(
        encoding="utf-8"
    )
