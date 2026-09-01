# Xiaocao WeChat mini-program automation safety research

Date: 2026-09-01 (Asia/Shanghai)

## Question

Is there a public, reliable timing rule or supported way to bypass WeChat's
protection when an Agent opens the Xiaoetong mini-program replay, and what
should the Xiaocao automation do after the recent automatic logout?

## Findings

1. No authoritative public source found a safe delay, request interval, or
   reliable bypass formula. Therefore timing is not promoted as a guarantee.
   The route should use event-based waits and a bounded retry policy, not a
   guessed sleep or repeated refresh.
2. Tencent's security research describes hooking/plugins as a security risk,
   so Xiaocao must not evade protection through injection, protocol hooking,
   database access, credential extraction, or similar hidden interfaces:
   [Tencent Xuanwu research on WeChat plugin risks](https://xlab.tencent.com/cn/2018/10/23/weixin-cheater-risks/).
3. Public macOS automation projects that document a safer operating posture
   use visible UI/accessibility control and avoid network-protocol
   interception or reverse engineering. These are engineering precedents, not
   a WeChat guarantee: [wechat-assistant](https://github.com/jzjzzzzzzz/wechat-assistant)
   and [wechat-desktop-mcp](https://github.com/Wirkflow/wechat-desktop-mcp).
4. The recent logout has no observed evidence proving whether WeChat's risk
   control, an app transition, or an automation/UI failure caused it. The
   correct response is therefore fail-closed: do not probe repeatedly with the
   re-authenticated account, and surface only a genuine login/OTP/CAPTCHA/
   consent/protection-screen boundary to the user.

## Decision for Xiaocao

The native WeChat mini-program remains the download route; the old H5 route
remains identity-only compatibility code. The active Automation owns the
visible WeChat action and must not ask the user to open/select the replay. Each
activation uses one foreground session, one action followed by fresh state
readback, no clipboard retry loop or global shortcut while state is uncertain,
and no hidden instrumentation. A media request is not enough by itself: the
singleton sniffer and source job must bind the exact `live_id` and finite VOD
playlist before the existing compressed capture task starts.

This research does not claim that the new UI policy has passed a live
end-to-end replay test. The 2026-08-31 local MP4 is existing evidence of a
download side effect, but it must not be used to fabricate a missing Xiaocao
completion receipt.
