# Review and validation

Baseline: `95a3b69e209369b87c722bf7b2881df00051a409`.

Independent Standards review: initial P1 proxy-owner race and resume-without-listener, then P2 lease gap during human confirmation. Fixed exclusive owner before snapshot, inherited guardian lock, no-change proxy restoration, exact listener/PAC recovery without re-launch, and lease coverage limited to waiting/observation. Final review: pass; no new reproducible blocker.

Independent Spec review: initial P1 unknown-source misbinding, transient transport ending the wait, and lifecycle self-conflict; follow-up real status-transport classification and preparation/confirmation lease gaps. Fixed exact human confirmation for an opaque original's first source, fresh finite lineage checks before binding, persistent transport backoff, precise status failure classification, and short lease scopes that end before downstream cleanup. Final review: pass; reviewer independently ran 21 related regression cases.

Implementer validation: 618 tests passed across human playback, WeChat subscription, local runner, live capture and shared capture; `git diff --check` passed. Actual macOS test notification submission returned exit 0, banner display is unverified.

Real acceptance remains pending: retained original course must be opened/allowed/played by the human, then the real candidate/download/cloud/handoff receipts must pass existing acceptance. No test result, notification submission, or interface existence substitutes for that.

Final notification correction: the human rejected a custom persistent dialog and enabled ChatGPT notification permission. The uncommitted dialog experiment was withdrawn. The final implementation emits one exact-course action event; the owning chat uses `request_user_input_async` and normal Codex question notifications, keeping HTTP polling alive. Both reviewers passed this final increment; 229 affected tests passed and the Spec reviewer independently ran 6 related cases. Actual native notification display remains unverified until a real human-action question. User-confirmed first real 26 October course has a fresh ended-state/finite playlist and is downloading in the retained original capture; prior 145 task IDs are preserved. Full file/cloud/mailbox acceptance is still pending.
