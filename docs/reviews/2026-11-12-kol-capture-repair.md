# Local KOL capture repair and visible failure handling

Baseline: `336adc31f8c71f46397da9bcea34010000870db0`.
Scope: catalogue source binding, recorded source errors, local capture result,
exact continuation progress and existing operational login notices.

The real Nov11 source `kol-wechat-10c940b3d1d51c8d69f40603` changed its
mini-program share token while retaining the exact labelled history catalogue
URL in the same message. The old implementation treated the configured share
token as recording identity and exposed that catalogue URL as another capture.
Both discovery and media proof now join the exact cached message, its original
token, configured URL, contact and timestamp. Original IDs and receipts remain.

Local repair, reconciliation and human-action results now exit nonzero with
the exact item, responsibility, stage and next action. Catalogue and unexpected
exceptions use credential-safe diagnostics; uncertain effects remain uncertain.
Exact continuation persists repair progress and an originating sweep for later
fingerprint validation. Ambiguous shared fingerprints fail closed.
Login notices retain the existing sender and exact blocker deduplication.
A generic no-update cannot clear a blocker; completed same-item or media/cloud
progress can.

Independent Standards and Spec review used the pinned baseline and scoped diff.
Review findings were reproduced and fixed: exception boundary gaps, mixed full
and split recording omission, missing repair persistence, incorrect notification
clearing, and multiple originals sharing one failure fingerprint.
Final relevant regression: **742 passed**. No APP simulation tests were run.
Unrelated Yangsheng WIP was excluded.

Actual catalogue readback contained 17 resources. The exact Nov11 item now
passes source binding and reports `recorded_course_multipart_requires_assembly`
for its two dated parts, preserving capture `kol-25e78d8fca27`. This is an
Agent-owned implementation gap, not an unpublished recording or media acceptance.
No multipart assembly, new media Handoff or remote ACK is claimed here.
Nov10's dated `盘中` title remains a source-session evidence gap; it is not
silently equated with the morning announcement.

The existing Codex Automation was updated and viewed through the app. It
retains ACTIVE status, 07/11/21 China wall time, Terra/high and the same project.
Its original prompt suffix is unchanged
(`b9c9a938a51c5ab82180be9dd750971dab4be8e683ad3b42dbf077f60b879a09`);
the new prefix requires in-task repair or a concrete human/external action.
Failure notifications are enabled through the Automation notification policy.
