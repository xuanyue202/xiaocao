from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from xiaocao.kol.enrichment import (
    BaiduAasrClient,
    EnrichmentError,
    S3AudioPublisher,
    VideoEnrichmentService,
)


def test_corrupt_event_ledger_fails_closed(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "events.jsonl").write_text(
        '{"event":"audio_prepared","job_id":"job-1"}\nnot-json\n',
        encoding="utf-8",
    )

    with pytest.raises(EnrichmentError, match="line 2"):
        VideoEnrichmentService(output_dir).status("job-1")


def test_baidu_token_network_failure_is_sanitized():
    class Session:
        def post(self, *_args, **_kwargs):
            raise requests.ConnectionError("https://secret-host/?client_secret=secret")

    with pytest.raises(EnrichmentError, match="access-token request failed") as caught:
        BaiduAasrClient.from_env(
            {
                "BAIDU_AASR_API_KEY": "api-secret",
                "BAIDU_AASR_SECRET_KEY": "client-secret",
            },
            session=Session(),
        )

    assert "secret-host" not in str(caught.value)
    assert "client-secret" not in str(caught.value)


def test_prepare_converts_runtime_named_video_once_and_records_verified_audio(tmp_path):
    video = tmp_path / "runtime-title-compressed.mp4"
    video.write_bytes(b"real-video-fixture")
    calls: list[list[str]] = []

    def runner(command, **_kwargs):
        calls.append([str(value) for value in command])
        if command[0] == "ffprobe" and str(command[-1]).endswith(".mp4"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({
                    "format": {"duration": "624.082474", "size": str(video.stat().st_size)},
                    "streams": [{"codec_type": "audio", "sample_rate": "44100", "channels": 2}],
                }),
                stderr="",
            )
        if command[0] == "ffmpeg":
            Path(command[-1]).write_bytes(b"prepared-wave")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "format": {"duration": "624.080000", "size": "13"},
                "streams": [{
                    "codec_type": "audio",
                    "codec_name": "pcm_s16le",
                    "sample_rate": "16000",
                    "channels": 1,
                    "bits_per_sample": 16,
                }],
            }),
            stderr="",
        )

    service = VideoEnrichmentService(tmp_path / "out", runner=runner)

    first = service.prepare(video)
    second = service.prepare(video)

    assert first["status"] == "prepared"
    assert first["provider"] == "baidu_aasr"
    assert first["video_sha256"] == hashlib.sha256(b"real-video-fixture").hexdigest()
    assert first["audio_sha256"] == hashlib.sha256(b"prepared-wave").hexdigest()
    assert first["audio_spec"] == {
        "codec_name": "pcm_s16le",
        "sample_rate": 16000,
        "channels": 1,
        "bits_per_sample": 16,
    }
    assert Path(first["audio_path"]).name == "runtime-title-compressed.wav"
    assert second["idempotent_replay"] is True
    assert sum(command[0] == "ffmpeg" for command in calls) == 1
    events = (tmp_path / "out" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(events) == 1
    assert json.loads(events[0])["event"] == "audio_prepared"


def test_prepare_normalizes_a_legacy_relative_audio_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    video = tmp_path / "runtime-title-compressed.mp4"
    video.write_bytes(b"real-video-fixture")
    audio = tmp_path / "out" / "artifact.wav"
    audio.parent.mkdir()
    audio.write_bytes(b"prepared-wave")
    prior = {
        "event": "audio_prepared",
        "status": "prepared",
        "job_id": f"kol-enrich-{hashlib.sha256(video.read_bytes()).hexdigest()[:16]}",
        "audio_path": "out/artifact.wav",
        "audio_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
    }
    (tmp_path / "out" / "events.jsonl").write_text(
        json.dumps(prior) + "\n", encoding="utf-8"
    )

    result = VideoEnrichmentService(tmp_path / "out").prepare(video)

    assert result["idempotent_replay"] is True
    assert result["audio_path"] == str(audio.resolve())
    events = (tmp_path / "out" / "events.jsonl").read_text().splitlines()
    assert len(events) == 2
    assert json.loads(events[-1])["audio_path"] == str(audio.resolve())


def test_prepare_replay_returns_latest_advanced_state(tmp_path):
    video = tmp_path / "runtime-title-compressed.mp4"
    video.write_bytes(b"real-video-fixture")

    def runner(command, **_kwargs):
        if command[0] == "ffprobe" and str(command[-1]).endswith(".mp4"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({
                    "format": {"duration": "10.0"},
                    "streams": [{"codec_type": "audio"}],
                }),
                stderr="",
            )
        if command[0] == "ffmpeg":
            Path(command[-1]).write_bytes(b"prepared-wave")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "format": {"duration": "10.0"},
                "streams": [{
                    "codec_type": "audio",
                    "codec_name": "pcm_s16le",
                    "sample_rate": "16000",
                    "channels": 1,
                    "bits_per_sample": 16,
                }],
            }),
            stderr="",
        )

    service = VideoEnrichmentService(tmp_path / "out", runner=runner)
    prepared = service.prepare(video)
    advanced = {
        **prepared,
        "event": "content_verified",
        "status": "verified",
    }
    service._append(advanced)

    replay = service.prepare(video)

    assert replay["status"] == "verified"
    assert replay["event"] == "content_verified"
    assert replay["idempotent_replay"] is True


def test_baidu_submit_uses_verbatim_asr_contract_without_returning_secrets():
    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "log_id": 123,
                "task_status": "Created",
                "task_id": "provider-task-1",
            }

    class Session:
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

    client = BaiduAasrClient(access_token="access-secret", session=Session())
    result = client.submit(
        "https://private.example/audio.wav?signature=signed-secret"
    )

    assert result == {"task_id": "provider-task-1", "task_status": "Created"}
    assert calls == [(
        "https://aip.baidubce.com/rpc/2.0/aasr/v1/create",
        {
            "params": {"access_token": "access-secret"},
            "json": {
                "speech_url": "https://private.example/audio.wav?signature=signed-secret",
                "format": "wav",
                "pid": 80006,
                "rate": 16000,
                "smooth_text": 0,
                "filter_sensitive": 0,
            },
            "timeout": 30,
        },
    )]
    assert "access-secret" not in json.dumps(result)
    assert "signed-secret" not in json.dumps(result)


def test_submit_is_idempotent_and_persists_a_five_minute_secret_free_poll_gate(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    audio = tmp_path / "source.wav"
    audio.write_bytes(b"wave")
    prepared = {
        "event": "audio_prepared",
        "status": "prepared",
        "job_id": "kol-enrich-real",
        "provider": "baidu_aasr",
        "audio_path": str(audio),
        "audio_sha256": hashlib.sha256(b"wave").hexdigest(),
    }
    (output_dir / "events.jsonl").write_text(
        json.dumps(prepared) + "\n", encoding="utf-8"
    )
    calls = []

    class Client:
        def submit(self, speech_url):
            calls.append(speech_url)
            return {"task_id": "provider-task-7", "task_status": "Created"}

    service = VideoEnrichmentService(
        output_dir,
        aasr_client=Client(),
        now=lambda: datetime.fromisoformat("2026-07-19T20:00:00+08:00"),
    )
    signed_url = "https://private.example/source.wav?signature=never-persist"

    first = service.submit(
        "kol-enrich-real",
        speech_url=signed_url,
        publication_reference="s3://private-bucket/kol/source.wav",
    )
    second = service.submit(
        "kol-enrich-real",
        speech_url=signed_url,
        publication_reference="s3://private-bucket/kol/source.wav",
    )

    assert first["status"] == "submitted"
    assert first["provider_task_id"] == "provider-task-7"
    assert first["next_poll_at"] == "2026-07-19T20:05:00+08:00"
    assert first["aasr_request"] == {
        "format": "wav",
        "pid": 80006,
        "rate": 16000,
        "smooth_text": 0,
        "filter_sensitive": 0,
    }
    assert second["idempotent_replay"] is True
    assert calls == [signed_url]
    ledger = (output_dir / "events.jsonl").read_text(encoding="utf-8")
    assert "never-persist" not in ledger
    assert "https://private.example" not in ledger


def test_poll_enforces_initial_delay_and_backoff_then_saves_raw_success(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    current_time = [datetime.fromisoformat("2026-07-19T20:04:59+08:00")]
    submitted = {
        "event": "transcription_submitted",
        "status": "submitted",
        "job_id": "kol-enrich-real",
        "provider": "baidu_aasr",
        "provider_task_id": "provider-task-7",
        "poll_count": 0,
        "next_poll_at": "2026-07-19T20:05:00+08:00",
    }
    (output_dir / "events.jsonl").write_text(
        json.dumps(submitted) + "\n", encoding="utf-8"
    )
    responses = [
        {
            "log_id": 1,
            "tasks_info": [{
                "task_id": "provider-task-7",
                "task_status": "Running",
            }],
        },
        {
            "log_id": 2,
            "tasks_info": [{
                "task_id": "provider-task-7",
                "task_status": "Success",
                "task_result": {
                    "audio_duration": 624_000,
                    "result": ["开头原文中段原文结尾原文"],
                    "detailed_result": [
                        {"begin_time": 0, "end_time": 20_000, "res": ["开头原文"]},
                        {"begin_time": 300_000, "end_time": 320_000, "res": ["中段原文"]},
                        {"begin_time": 610_000, "end_time": 624_000, "res": ["结尾原文"]},
                    ],
                },
            }],
        },
    ]
    calls = []

    class Client:
        def query(self, task_id):
            calls.append(task_id)
            return responses.pop(0)

    service = VideoEnrichmentService(
        output_dir,
        aasr_client=Client(),
        now=lambda: current_time[0],
    )

    with pytest.raises(EnrichmentError, match="not due"):
        service.poll("kol-enrich-real")
    assert calls == []

    current_time[0] = datetime.fromisoformat("2026-07-19T20:05:00+08:00")
    running = service.poll("kol-enrich-real")
    assert running["status"] == "running"
    assert running["poll_count"] == 1
    assert running["next_poll_at"] == "2026-07-19T20:15:00+08:00"

    current_time[0] = datetime.fromisoformat("2026-07-19T20:14:59+08:00")
    with pytest.raises(EnrichmentError, match="not due"):
        service.poll("kol-enrich-real")
    assert calls == ["provider-task-7"]

    current_time[0] = datetime.fromisoformat("2026-07-19T20:15:00+08:00")
    success = service.poll("kol-enrich-real")
    replay = service.poll("kol-enrich-real")

    assert success["status"] == "transcribed"
    assert success["raw_response_sha256"] == hashlib.sha256(
        Path(success["raw_response_path"]).read_bytes()
    ).hexdigest()
    assert json.loads(Path(success["raw_response_path"]).read_text())[
        "tasks_info"
    ][0]["task_status"] == "Success"
    assert replay["idempotent_replay"] is True
    assert calls == ["provider-task-7", "provider-task-7"]


def test_poll_failure_is_audited_and_backed_off_before_retry(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    current_time = datetime.fromisoformat("2026-07-19T20:05:00+08:00")
    submitted = {
        "event": "transcription_submitted",
        "status": "submitted",
        "job_id": "kol-enrich-real",
        "provider": "baidu_aasr",
        "provider_task_id": "provider-task-7",
        "poll_count": 0,
        "next_poll_at": "2026-07-19T20:05:00+08:00",
    }
    (output_dir / "events.jsonl").write_text(
        json.dumps(submitted) + "\n", encoding="utf-8"
    )

    class Client:
        def query(self, _task_id):
            raise EnrichmentError("Baidu AASR query request failed")

    service = VideoEnrichmentService(
        output_dir,
        aasr_client=Client(),
        now=lambda: current_time,
    )

    with pytest.raises(EnrichmentError, match="query request failed"):
        service.poll("kol-enrich-real")

    latest = service.status("kol-enrich-real")
    assert latest["event"] == "transcription_poll_failed"
    assert latest["status"] == "running"
    assert latest["poll_count"] == 1
    assert latest["next_poll_at"] == "2026-07-19T20:15:00+08:00"
    assert latest["provider_error"] == "Baidu AASR query request failed"


def test_render_and_verify_preserve_all_segments_and_require_three_position_audit(tmp_path):
    output_dir = tmp_path / "out"
    artifact_dir = output_dir / "artifacts" / "kol-enrich-real"
    artifact_dir.mkdir(parents=True)
    raw = {
        "log_id": 2,
        "tasks_info": [{
            "task_id": "provider-task-7",
            "task_status": "Success",
            "task_result": {
                "audio_duration": 624_000,
                    "result": [
                        "开头不追高。第一段补充。第二段补充。中段数字是四十。"
                        "第三段补充。第四段补充。结尾北特科技继续等。"
                    ],
                    "detailed_result": [
                        {"begin_time": 0, "end_time": 20_000, "res": ["开头不追高。"]},
                        {"begin_time": 110_000, "end_time": 130_000, "res": ["第一段补充。"]},
                        {"begin_time": 220_000, "end_time": 240_000, "res": ["第二段补充。"]},
                        {"begin_time": 260_000, "end_time": 280_000, "res": ["中段数字是四十。"]},
                        {"begin_time": 390_000, "end_time": 410_000, "res": ["第三段补充。"]},
                        {"begin_time": 500_000, "end_time": 520_000, "res": ["第四段补充。"]},
                        {"begin_time": 610_000, "end_time": 624_000, "res": ["结尾北特科技继续等。"]},
                ],
            },
        }],
    }
    raw_bytes = (json.dumps(raw, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    raw_path = artifact_dir / "baidu_aasr_response.json"
    raw_path.write_bytes(raw_bytes)
    transcribed = {
        "event": "transcription_completed",
        "status": "transcribed",
        "job_id": "kol-enrich-real",
        "provider": "baidu_aasr",
        "provider_task_id": "provider-task-7",
        "video_basename": "runtime-title-compressed.mp4",
        "video_sha256": "video-sha",
        "audio_sha256": "audio-sha",
        "raw_response_path": str(raw_path),
        "raw_response_sha256": hashlib.sha256(raw_bytes).hexdigest(),
    }
    (output_dir / "events.jsonl").write_text(
        json.dumps(transcribed) + "\n", encoding="utf-8"
    )
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(
        json.dumps({
            "video_sha256": "video-sha",
            "checks": [
                {
                    "position": "opening",
                    "timestamp_ms": 5_000,
                    "transcript_excerpt": "不追高",
                    "heard_text": "不追高",
                    "categories": ["direction_or_negation"],
                    "passed": True,
                },
                {
                    "position": "middle",
                    "timestamp_ms": 270_000,
                    "transcript_excerpt": "四十",
                    "heard_text": "四十",
                    "categories": ["number"],
                    "passed": True,
                },
                {
                    "position": "ending",
                    "timestamp_ms": 615_000,
                    "transcript_excerpt": "北特科技",
                    "heard_text": "北特科技",
                    "categories": ["proper_name"],
                    "passed": True,
                },
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    service = VideoEnrichmentService(output_dir)

    rendered = service.render("kol-enrich-real")
    verified = service.verify("kol-enrich-real", audit_path=audit_path)
    replay = service.verify("kol-enrich-real", audit_path=audit_path)

    transcript = Path(rendered["transcript_path"]).read_text(encoding="utf-8")
    assert transcript.index("开头不追高") < transcript.index("中段数字是四十")
    assert transcript.index("中段数字是四十") < transcript.index("结尾北特科技")
    assert rendered["rendered_segment_count"] == 7
    assert verified["status"] == "verified"
    assert verified["coverage"] == {
        "opening": True,
        "middle": True,
        "ending": True,
        "raw_render_parity": True,
        "result_detail_parity": True,
        "max_gap_within_limit": True,
    }
    assert verified["audit_categories"] == [
        "direction_or_negation",
        "number",
        "proper_name",
    ]
    assert replay["idempotent_replay"] is True


def test_verify_rejects_audit_position_that_does_not_match_timestamp(tmp_path):
    output_dir = tmp_path / "out"
    artifact_dir = output_dir / "artifacts" / "kol-enrich-real"
    artifact_dir.mkdir(parents=True)
    raw = {
        "tasks_info": [{
            "task_id": "provider-task-7",
            "task_status": "Success",
            "task_result": {
                "audio_duration": 100_000,
                "result": ["开头中间结尾"],
                "detailed_result": [
                    {"begin_time": 0, "end_time": 10_000, "res": ["开头"]},
                    {"begin_time": 40_000, "end_time": 45_000, "res": ["中间"]},
                    {"begin_time": 90_000, "end_time": 100_000, "res": ["结尾"]},
                ],
            },
        }],
    }
    raw_bytes = (json.dumps(raw, ensure_ascii=False) + "\n").encode()
    raw_path = artifact_dir / "baidu_aasr_response.json"
    raw_path.write_bytes(raw_bytes)
    (output_dir / "events.jsonl").write_text(
        json.dumps({
            "event": "transcription_completed",
            "status": "transcribed",
            "job_id": "kol-enrich-real",
            "provider_task_id": "provider-task-7",
            "video_basename": "runtime-title-compressed.mp4",
            "video_sha256": "video-sha",
            "raw_response_path": str(raw_path),
            "raw_response_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        }) + "\n",
        encoding="utf-8",
    )
    service = VideoEnrichmentService(output_dir)
    service.render("kol-enrich-real")
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(
        json.dumps({
            "video_sha256": "video-sha",
            "checks": [
                {
                    "position": "opening",
                    "timestamp_ms": 42_000,
                    "transcript_excerpt": "中间",
                    "heard_text": "中间",
                    "categories": ["direction_or_negation"],
                    "passed": True,
                },
                {
                    "position": "middle",
                    "timestamp_ms": 42_000,
                    "transcript_excerpt": "中间",
                    "heard_text": "中间",
                    "categories": ["number"],
                    "passed": True,
                },
                {
                    "position": "ending",
                    "timestamp_ms": 95_000,
                    "transcript_excerpt": "结尾",
                    "heard_text": "别的内容",
                    "categories": ["proper_name"],
                    "passed": True,
                },
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(EnrichmentError, match="unverified spot check"):
        service.verify("kol-enrich-real", audit_path=audit_path)


def test_s3_publisher_uploads_with_hash_verification_and_returns_ephemeral_url(tmp_path):
    audio = tmp_path / "runtime-title.wav"
    audio.write_bytes(b"wave-audio")
    audio_sha = hashlib.sha256(b"wave-audio").hexdigest()
    calls = []

    def runner(command, **_kwargs):
        calls.append([str(value) for value in command])
        if command[1:3] == ["s3api", "get-public-access-block"]:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({
                    "BlockPublicAcls": True,
                    "IgnorePublicAcls": True,
                    "BlockPublicPolicy": True,
                    "RestrictPublicBuckets": True,
                }),
                stderr="",
            )
        if command[1:3] == ["s3api", "head-object"]:
            return SimpleNamespace(returncode=0, stdout=audio_sha + "\n", stderr="")
        if command[1:3] == ["s3api", "get-object-acl"]:
            return SimpleNamespace(returncode=0, stdout="[]\n", stderr="")
        if command[1:3] == ["s3", "presign"]:
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "https://private-bucket.s3.example/kol/"
                    f"{audio_sha[:16]}/runtime-title.wav?signature=ephemeral-secret\n"
                ),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    published = S3AudioPublisher(runner=runner).publish(
        audio,
        s3_prefix="s3://private-bucket/kol",
        audio_sha256=audio_sha,
    )

    assert published.publication_reference == (
        f"s3://private-bucket/kol/{audio_sha[:16]}/runtime-title.wav"
    )
    assert published.speech_url.endswith("signature=ephemeral-secret")
    assert calls[0][:3] == ["aws", "s3api", "get-public-access-block"]
    assert calls[1][:3] == ["aws", "s3", "cp"]
    assert f"xiaocao-sha256={audio_sha}" in calls[1]
    assert calls[2][:3] == ["aws", "s3api", "head-object"]
    assert calls[3][:3] == ["aws", "s3api", "get-object-acl"]
    assert calls[4][:3] == ["aws", "s3", "presign"]
    assert "ephemeral-secret" not in published.publication_reference


def test_s3_publisher_rejects_credentials_embedded_in_prefix(tmp_path):
    audio = tmp_path / "runtime-title.wav"
    audio.write_bytes(b"wave-audio")

    with pytest.raises(EnrichmentError, match="stable s3"):
        S3AudioPublisher().publish(
            audio,
            s3_prefix="s3://user:password@private-bucket/kol",
            audio_sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),
        )


def test_s3_publisher_rejects_bucket_without_full_public_access_block(tmp_path):
    audio = tmp_path / "runtime-title.wav"
    audio.write_bytes(b"wave-audio")

    def runner(command, **_kwargs):
        assert command[1:3] == ["s3api", "get-public-access-block"]
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": False,
                "RestrictPublicBuckets": True,
            }),
            stderr="",
        )

    with pytest.raises(EnrichmentError, match="full S3 public-access block"):
        S3AudioPublisher(runner=runner).publish(
            audio,
            s3_prefix="s3://private-bucket/kol",
            audio_sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),
        )


def test_verified_transcript_routes_to_household_and_book_once(tmp_path):
    output_dir = tmp_path / "enrichment"
    artifact_dir = output_dir / "artifacts" / "kol-enrich-real"
    artifact_dir.mkdir(parents=True)
    transcript = artifact_dir / "runtime-title-compressed.md"
    transcript.write_text("完整逐字稿：等待成交量放大再行动。\n", encoding="utf-8")
    verified = {
        "event": "content_verified",
        "status": "verified",
        "job_id": "kol-enrich-real",
        "provider": "baidu_aasr",
        "video_sha256": "video-sha",
        "transcript_path": str(transcript),
        "transcript_sha256": hashlib.sha256(transcript.read_bytes()).hexdigest(),
    }
    (output_dir / "events.jsonl").write_text(
        json.dumps(verified) + "\n", encoding="utf-8"
    )
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps({
            "household_context_provider": {"type": "lianghui_mcp"},
            "items": [{
                "source": "baidu_aasr",
                "author": "小草",
                "title": "runtime-title-compressed",
                "evidence_path": str(transcript),
            }],
            "cross_source": {"agreements": [], "conflicts": []},
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    process_calls = []
    delivery_calls = []

    class Pipeline:
        def process(self, bundle):
            process_calls.append(bundle)
            return {
                "status": "completed",
                "items": [{
                    "notification": {
                        "idempotency_key": "notification-1",
                        "status": "pending",
                    },
                    "book_kol_us": {
                        "status": "no_trade",
                        "book": "KOL-US",
                        "paper_only": True,
                        "reason": "观点只涉及A股。",
                    },
                }],
            }

        def deliver_wechat(self, result, *, sender):
            delivery_calls.append((result, sender))
            result["items"][0]["notification"].update({
                "status": "delivered",
                "receipt": "wecom-relay://ok/notification-1",
            })
            return {"status": "delivered"}

    pipeline = Pipeline()
    service = VideoEnrichmentService(output_dir)

    with pytest.raises(EnrichmentError, match="decision bundle not found"):
        service.decide(
            "kol-enrich-real",
            bundle_path=tmp_path / "missing-bundle.json",
            decision_output_dir=tmp_path / "decisions",
            pipeline=pipeline,
            sender=lambda _title, _body: {"wecom": "ok"},
        )
    failed = service.status("kol-enrich-real")
    assert failed["event"] == "decision_failed"
    assert failed["failure_stage"] == "bundle_not_found"

    first = service.decide(
        "kol-enrich-real",
        bundle_path=bundle_path,
        decision_output_dir=tmp_path / "decisions",
        pipeline=pipeline,
        sender=lambda _title, _body: {"wecom": "ok"},
    )
    replay = service.decide(
        "kol-enrich-real",
        bundle_path=bundle_path,
        decision_output_dir=tmp_path / "decisions",
        pipeline=pipeline,
        sender=lambda _title, _body: {"wecom": "ok"},
    )

    assert first["status"] == "decided"
    assert first["household_notification"] == {
        "idempotency_key": "notification-1",
        "status": "delivered",
        "receipt": "wecom-relay://ok/notification-1",
    }
    assert first["book_kol_us"] == {
        "status": "no_trade",
        "book": "KOL-US",
        "paper_only": True,
        "reason": "观点只涉及A股。",
    }
    assert replay["idempotent_replay"] is True
    assert len(process_calls) == 1
    assert len(delivery_calls) == 1


def test_decision_pipeline_failure_is_audited_without_leaking_exception_text(tmp_path):
    output_dir = tmp_path / "enrichment"
    artifact_dir = output_dir / "artifacts" / "kol-enrich-real"
    artifact_dir.mkdir(parents=True)
    transcript = artifact_dir / "runtime-title-compressed.md"
    transcript.write_text("完整逐字稿。\n", encoding="utf-8")
    (output_dir / "events.jsonl").write_text(
        json.dumps({
            "event": "content_verified",
            "status": "verified",
            "job_id": "kol-enrich-real",
            "transcript_path": str(transcript),
            "transcript_sha256": hashlib.sha256(transcript.read_bytes()).hexdigest(),
        }) + "\n",
        encoding="utf-8",
    )
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps({"items": [{"evidence_path": str(transcript)}]}),
        encoding="utf-8",
    )

    class Pipeline:
        def process(self, _bundle):
            raise RuntimeError("household-token-must-not-enter-ledger")

    service = VideoEnrichmentService(output_dir)

    with pytest.raises(EnrichmentError, match="decision pipeline failed"):
        service.decide(
            "kol-enrich-real",
            bundle_path=bundle_path,
            decision_output_dir=tmp_path / "decisions",
            pipeline=Pipeline(),
            sender=lambda _title, _body: {},
        )

    latest = service.status("kol-enrich-real")
    assert latest["event"] == "decision_failed"
    assert latest["status"] == "verified"
    assert latest["error_type"] == "RuntimeError"
    assert "household-token" not in (output_dir / "events.jsonl").read_text()
