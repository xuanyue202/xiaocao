# Source wait repair and exact-queue completion

Date: 2026-09-06, Asia/Shanghai.

## Acceptance

- The original image was completed at 10:00:13; its low-density no-report/no-reminder/no-trade disposition was reconciled without replay.
- Both PDFs first observed at 08:32:47 were resumed by exact identity with `refresh_listing=False`; no second hourly sweep or mailbox drain was launched.
- AI framework PDF: exact source `2541e028d427195e0b22c329c9548b20f88343473971f5d6d8609fb744a85c52`; report `kr_hz3qbitd6liwopdlbxgphekhr6ax2mv256o323zl6i4hkje3dmda` is published, no reminder is eligible, no Book row is created, and the authority-zero knowledge file is hash-bound. Final decision SHA: `fc4fb73b78dc3bfb237a76443015551c63fd9df67a4a2884841a8ceb8ae35a34`.
- Sovereign-fund conversation PDF: exact source `517fcaa0469036bb376d7a67f5f757aac3cefec00fc52646d4ed3170b02b735a`; report `kr_m4mtf7wdk4s5l2di5xo5si4mdsfpit4db2chnhivdxhioz4v6tvq` is published, one eligible reminder has an all-recipient delivery terminal, and KOL-US is paper-only/no-trade. Final decision SHA: `1fe2a2f17248b265360ee3b7d8cd14a8510cbab1e8b6019c3f03c8ddc4790c2a`.
- Both reports were read through the authenticated read-only record interface. Server content/manifest hashes passed validation; titles and complete Markdown matched their exact validated bundles.
- Both exact terminal reconciliations returned `external_business_effects_replayed=false`. Final Lv pending count is zero.

## 5 Why

1. Why was repair not completion? The earlier turn stopped after repairing a local validation path and left the durable object in a provider-style wait. Code success and an object terminal are distinct.
2. Why did the recovered queue still fail? The next PDFs exercised paths not covered by the image: mixed PDF line endings, durable-only knowledge, and published-report readback.
3. Why did the same evidence fail identity validation? Request creation used universal-newline text reads while canonical validation and the downstream TranscriptDocument decoded raw CR/CRLF. Identical raw bytes produced different segment identities. The original file contained one CR; its request exactly matched normalized-text segmentation and not raw-text segmentation.
4. Why did a legal knowledge report fail? Canonical Book validation admitted only trade/no-trade while the existing consumer contract required not-applicable for durable-only reports. Separately, promoted Lv readback called a publication identity helper without importing it; the old low-density-only test never reached that branch.
5. Why were these gaps missed? Tests checked individual stages but not the request-to-canonical-to-consumer path or both publication dispositions. Regression coverage now exercises mixed CR/CRLF across the real consumer, preserves original raw hash/bytes, admits only the narrow durable-only no-Book case, rejects current-decision misuse, and reads the existing publication receipt without effects.

## Recovery boundaries and validation

- The initial owner-cloud byte-stream failure was retried once against its existing verified transfer receipt. It succeeded; no root-cause claim is made for an unclassified transient that did not recur, and there was no second transfer.
- The first PDF report had already published before downstream segmentation failed. Recovery reused that exact publication receipt; it did not mint a replacement publication, reminder, or trade.
- `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_kol_semantic_bundle.py tests/test_kol_daily.py tests/test_kol_decisions.py tests/test_kol_lv_subscription.py`: 321 passed.
- No schedules, recipients, investment parameters, or real-capital authority changed. Unrelated worktree changes remain outside the scoped commits.
- Completion rule: own the existing object through repair, targeted validation, exact continuation, and authoritative terminal readback. A real provider deadline remains owned unfinished work; it is not a handoff to the next Automation.
