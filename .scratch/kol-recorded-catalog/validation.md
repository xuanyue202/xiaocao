# Validation — 2026-11-04 15:00 Asia/Shanghai

- Baseline: b89d52dc6b4619df4b21f4a858c91f8742851ee4; only the catalogue module,
  CLI, focused tests and linked local SOP/PRD are in this change. ASR WIP excluded.
- 16 focused offline tests pass. They exercise pagination completeness, changed
  source/course/resource identities, ambiguous sessions, old/future originals,
  no ticket export, redirect boundaries, exact CLI original binding and NETRC
  isolation with a positive vulnerable-session control.
- Independent Standards and Spec reviews initially found NETRC inheritance and
  an original-identity mismatch. Fixed both and strengthened the NETRC regression
  after re-review detected a hostname-casing issue. Final reviews: zero remaining
  actionable findings.
- Actual CLI readback at14:59:19 bound original kol-wechat-8b4f1cf81fc606b162677e8a
  and capture kol-e407e756fa16 to catalogue candidate v_6aeac14ce4b023c0863c984c,
  title 大师班早盘直播11月4日, duration2311seconds, complete catalogue count4.
  Anonymous metadata: available1, free0, subscribe0, try0, unlock0, DRM1.
- The former idle runner was stopped on human direction and its exit guardian
  proved restoration; capture PAC readback No. No original/capture/entry receipt
  was replaced and no permanent course deferral was recorded.
- Download, entitled native recorded-course integration, finite media acceptance,
  cloud/Handoff and stable end-to-end acquisition remain unverified. The human's
  normal course/account authorization is needed for the next real source check.
  Public metadata does not establish download authority or an accepted session.
