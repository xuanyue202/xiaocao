# Diagnose and reuse existing capture connections without WeChat activation

Baseline: 154b506. User asks to continue offline diagnosis, reuse earlier
connections/interfaces and minimize WeChat launch/clicks. The private native hold
remains active; no live provider entry, app binding/screenshot/input, PAC change,
backend restart, new download/upload or ASR execution is part of this change.

Evidence: existing backend39765 is healthy/deployed hash matches. Dynamic status
reports no Channels websocket before/after35s passive reconnect. Current original
kol-wechat-deb789c4f7d6a541c7903b35 / kol-2ba19ba5cd4d remains unbound;1766 capture
candidates include zero observations since its original publication. Source is
not inferred from unrelated old candidates. Prior accepted socket reconnect
requires its page-resident client; Channels SDK is not a Xiaoetong playback API.
The cause of WeChat protection itself cannot be reproduced safely offline.

Implement:
- One shared Python reader of the private native activation hold; malformed values
  fail closed. Preserve prior missing-field compatibility and all job/claim bytes.
- The actual Liuguan companion must reuse healthy API work even while native entry
  is held. Missing socket while held must preserve its result/artifacts, emit no
  native initialization request and do no stdin wait. Direct bootstrap must also
  reject before leases/PAC/UI, while an existing healthy socket returns unchanged.
- A `kol_yangsheng.py connections` diagnostic reads only loopback shared status
  and deployment identity/config, optionally waits up to35s for retained-page
  reconnect, and reports exact reuse/missing/held facts. It must never start a
  service, inspect/control WeChat, mutate PAC/catalogue, download or run ASR.
- Document exact source-specific capabilities and remaining evidence gap. Update
  existing Automation instructions only, not cadence/model/notifications.
- Offline regression, independent Spec and Standards review, scoped commit/push;
  run the passive diagnostic on the retained production backend. No claim of
  protection root cause fixed, new replay captured or entire backlog completed.
