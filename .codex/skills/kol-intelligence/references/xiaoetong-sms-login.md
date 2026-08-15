# Xiaoetong SMS Login, Slider CAPTCHA, and Muted Playback

Use this only after the bound Xiaoetong resource redirects to account login
and the user authorizes the interactive SMS login. Browser is the only UI
control path; never use Computer Use. Keep the same OpenCLI session, resource
identity, and capture job throughout. Preserve the original tab while its SMS
page session is valid; replace the bound tab only at the explicit recovery
boundaries below.

## Contents

- [One-pass path](#one-pass-path)
- [Identity and exactly-once state](#identity-and-exactly-once-state)
- [CAPTCHA visibility and authorization](#captcha-visibility-and-sms-authorization-scope)
- [Asset fallback and geometry](#asset-fallback-and-current-geometry)
- [Drag and SMS receipt](#one-browser-drag-and-authoritative-send-readback)
- [Stale Toast repair](#stale-or-duplicated-full-screen-toast)
- [OTP and playback](#otp-consent-course-password-and-muted-playback)
- [Stop/retry matrix](#stopretry-matrix)

## One-pass path

Use this sequence before taking any exceptional branch:

1. Bind the exact OpenCLI session, resource, canonical course path, and capture
   job. Before requesting an SMS, require the active tab to report
   `document.visibilityState == "visible"`; recover a hidden/minimized container
   now, while no OTP page session exists.
2. Identify the visible interactive owner for the phone, send, consent, OTP,
   and Login controls. Prefer the current send owner
   `.custom-button.login-verify-code` when present; do not click an inner label
   or accept `clicked=true` as a receipt. Prove each control-center hit target
   with `elementFromPoint()` and repair only a confirmed stale Toast interceptor.
3. Fill the already-authorized phone value without reading or exposing stored
   credentials. Click the send owner once, solve only the current CAPTCHA, and
   require the success Toast plus a positive resend countdown.
4. Keep that accepted page session unchanged. If the newest OTP is already in
   the current user message, continue immediately; otherwise ask once and wait.
   Pass the phone/OTP only once to the intended Browser input; never persist,
   log, echo, or repeat either secret in reports, memory, or repository files.
5. Enter the OTP once, check required consent once, click Login once, and read
   back the exact canonical course path. Do not resubmit while the result is
   unknown.
6. Enter `666` only at a visible course-password gate. Set page mute, start
   playback non-blockingly, and require two advancing samples from the same
   media element before returning `activated=true` to the retained runner.

## Identity and exactly-once state

Record the OpenCLI `session`, Chrome profile, current `tab_id`, Xiaoetong
`resource_id`, canonical course path, `capture_job_id`, page-attempt number,
and these separate states:

```text
SMS:   not_requested | requested | accepted | expired | invalidated
login: not_submitted | otp_submitted | authenticated
```

The tab/resource identity and the SMS page session are different boundaries.
A refresh or rebuilt login page may preserve the resource while invalidating an
already-sent OTP. Bind the accepted page session to the exact URL,
`performance.timeOrigin`, positive resend countdown, and OTP-field state; a
changed document or missing accepted-state evidence is not the same SMS
session. Never reuse an OTP across a page-session reset. Never click `获取验证码`
again while the current CAPTCHA is open or while an accepted SMS countdown
remains. An unknown send outcome requires readback, not a resend.

When the accepted countdown reaches zero and the user asks for a fresh code,
mark the old OTP `expired`, prove the OTP field is empty, and begin one new send
attempt in the same resource/session. From that transition onward, never submit
the old code. If clicking the send owner produces neither a visible current
CAPTCHA nor accepted-state readback, classify it as no effect, inspect the hit
target, and do not assume an SMS was sent.

## CAPTCHA visibility and SMS authorization scope

Text or DOM presence alone does not prove the CAPTCHA is visible. One explicit
user request to send an SMS or complete SMS login authorizes the CAPTCHA work
needed for that login attempt; do not insert an extra allow/deny prompt for an
Agent-owned geometry check, drag, or narrow DOM repair. Require all of the
following before attempting one drag on the current CAPTCHA instance:

- the root, background, puzzle piece, track, and knob exist;
- `display != none`, `visibility` is visible, and `opacity > 0`;
- the root and knob rectangles have non-zero size and intersect the viewport;
- the elements are not parked at a huge negative coordinate;
- `elementFromPoint()` at the knob center hits the knob or a descendant;
- the background and puzzle assets plus their geometry are loaded.

A root with `display:block`, `opacity:0`, or an offscreen position is hidden.
Do not drag it. A refreshed or replaced challenge is a new CAPTCHA instance;
recompute its assets and geometry, but do not ask for another confirmation while
the same user-authorized SMS login attempt remains active.

## Asset fallback and current geometry

If `Page.captureScreenshot` times out, do not loop screenshots. Use the current
tab's `pageAssets`: list once, identify the CAPTCHA background and puzzle-piece
sprite, and bundle both from the same inventory. Do not navigate to signed
asset URLs. Read the current DOM rectangles, track width, `background-size`,
and `background-position` alongside the assets.

Historical dimensions and coordinates are calibration examples only. Recompute
all values for the current challenge. Let:

```text
Wn = background natural width
Wr = background rendered width in CSS pixels
s = Wr / Wn
x_gap_px = gap-center x in natural-image pixels
bg_left = background rectangle left
piece_left, piece_width = current puzzle-piece DOM geometry

x_gap_css = x_gap_px * s
x_piece_center_css = (piece_left - bg_left) + piece_width / 2
drag_distance_css = x_gap_css - x_piece_center_css
drag_distance_css = clamp(drag_distance_css, 0, track_width - knob_width)
```

For a sprite, also verify:

```text
sprite_scale_x = css_background_size_width / sprite_natural_width
sprite_source_x = -css_background_position_x / sprite_scale_x
```

If the background and sprite scales disagree materially, the challenge changed
or the wrong assets were selected. Stop and obtain the current DOM/assets.

## One Browser drag and authoritative send readback

`tab.cua.drag()` uses tab-viewport CSS-pixel coordinates, matching
`getBoundingClientRect()`. This is the Browser tab's input primitive, not the
Computer Use skill. Do not add macOS window offsets. Start at the current knob
center and end at the computed distance:

```text
start_x = knob.left + knob.width / 2
start_y = knob.top + knob.height / 2
end_x = start_x + drag_distance_css
end_y ~= start_y
```

Use a monotonic progressive path: slow start, faster middle, slow finish, with
minor vertical variation. Never jump directly to the end and never replay an
old path. If the knob and puzzle piece do not move at all, no CAPTCHA attempt
was submitted; diagnose the current hit target and coordinates before another
action. If the challenge reports failure or is replaced, recompute from the
new instance within the same SMS authorization. Never reuse the old geometry or
add an Agent-owned repair approval prompt.

After the drag, wait for a short bounded UI stabilization window. Mark the SMS
state `accepted` only when readback proves all three:

- CAPTCHA status contains `验证成功`;
- the page contains `验证码已发送成功`;
- the send control reads `重新发送(Ns)` with `N > 0`.

The drag returning, CAPTCHA disappearance, a stale Toast string, or the send
button click alone is insufficient. On success, keep the accepted page session
unchanged. Use the newest OTP already present in the current user message; only
ask when no current code has been supplied.

## Stale or duplicated full-screen Toast

Before every SMS send/resend and immediately before the single Login click,
inspect every `[id="SpToast"]`: its
display, opacity, `pointer-events`, position, z-index, rectangle, and the
send/login-button-center hit target. Do not rely on `querySelector('#SpToast')`:
Xiaoetong can insert a second element with the same ID after a successful send,
while the first one is already hidden. The dangerous state is the exact node
returned by `elementFromPoint()` at the control center when that node is an
invisible (`opacity:0`) fixed, full-viewport Toast with `pointer-events:auto`;
it swallows normal clicks even though it looks gone. Never blind-click or treat
a forced-click return as an SMS or login receipt.

Wait for the CSS transition's bounded dismissal interval, then read the hit
target again. If the confirmed stale Toast still intercepts the control, this
is an Agent-owned repair inside the already-authorized SMS login: change only
that exact intercepting Toast node to `display:none !important` and
`pointer-events:none !important`. Do not bulk-edit all duplicate IDs. Read back
both values and prove `elementFromPoint()` at the control center now returns the
real send or login control. Do not remove other overlays or modify login fields,
and do not stop for an additional allow/deny prompt.

A refresh is the last resort. After a refresh, mark the SMS page session
`invalidated`; do not reuse the prior OTP unless the page authoritatively proves
that session remains valid.

## OTP, consent, course password, and muted playback

Before submitting, prove the same tab/resource, `SMS=accepted`, an empty OTP
field, a non-blocking Toast, and a correct login-button hit target. If a consent
checkbox is required, check it once and read back the checked state. Enter the
newest OTP once and click Login once. From then on, use URL/DOM readback only;
never submit the same OTP or click Login again while the outcome is unknown.

If `同意并继续` appears, click it once and read the next state. Account login is
successful only when the exact canonical course path for the bound resource is
reached. A redirect back to login is not success and does not authorize reuse
or resubmission of the same OTP.

Enter `666` only after reaching that exact course resource and only when a
visible course-password gate requests it. Never put `666` into an account-login
password field. If there is no visible course-password gate, try playback
without it.

Before playback, and again after every refresh, navigation, or player rebuild,
set and read back:

```javascript
video.muted = true;
video.volume = 0;
```

This is the page-level control required for activation.

Do this as soon as the bound page has a current `<video>` element; do not wait
for meaningful playback. If a visible course-password gate appears before the
element exists, submit `666` first, then mute immediately when the player is
mounted. In the Codex Browser, use the same bound tab's `cdp` capability and a
scoped `Runtime.evaluate` when custom controls are hidden. Read a CDP event
cursor before and after, and return only the current media state. Target the
current `<video>`; never replace this with system/browser mute,
cookies/storage inspection, Computer Use, or unrelated DOM changes.

`open <the-same-url>` may only reuse/focus the existing OpenCLI page; it is not
an authoritative reload. After a proven stuck player, use one real
`location.reload()` and reapply page mute. Invoke playback non-blockingly with
`video.play().catch(() => {})`; never `await video.play()` inside an OpenCLI eval,
because an unresolved promise can pin the command even when `paused` already
changed to `false`.

If the exact page reports `document.visibilityState == "hidden"` while OpenCLI
reports the session tab active, test a fresh empty `MediaSource` with a short
bounded `sourceopen` readback. When it does not open, stop rebuilding the player:
OpenCLI 1.8.6 can focus an existing minimized owned window without restoring it
to a normal visible state. Release only the same browser-session lease, launch
the exact Chrome extension profile (this capture node uses `Default`) in a new
normal foreground window at the canonical resource URL, and bind the same
OpenCLI session to that exact current tab. The bind receipt must return the
canonical URL, and DOM readback must prove `visibilityState == "visible"` before
playback activation. If `browser bind` returns `about:blank`, it bound the
reusable placeholder rather than the course; fail closed and use a no-preconnect
bind through the pinned OpenCLI transport, then repeat the exact URL/visibility
readback. Never create a second session or resend an OTP for this recovery.

Prefer this same-session window normalization before requesting the SMS. If a
tab replacement becomes unavoidable while `SMS=accepted` and before
`login=authenticated`, mark that OTP page session `invalidated` and request a
fresh code only after the replacement tab is visibly bound to the same canonical
resource. Rebinding after `authenticated` does not authorize another login or
SMS send.

Activation requires `muted == true`, `volume == 0`, `paused == false`,
`ended == false`, `readyState >= 2`, and a second `currentTime` sample 3–5
seconds later that is strictly greater than the first sample from the same media
element. System mute is only an extra safeguard; it never replaces the
page-level readback.

## Stop/retry matrix

| Stage | Stop condition | Narrow retry boundary |
|---|---|---|
| Identity | tab/resource/capture job differs | Read-only recover the original identity; never create a replacement job |
| CAPTCHA | hidden, offscreen, zero-sized, or intercepted | Re-read the current instance inside the existing SMS authorization; never click send again |
| Assets | background/piece missing or challenge changed | List/bundle assets for the current instance |
| Geometry | scale mismatch or out-of-range distance | Re-read current DOM/assets; never use historical distance |
| Drag | no submitted movement, failure, or replacement | Diagnose hit target; for a new instance recompute without another approval prompt |
| SMS | success Toast and countdown present | Stop and wait for the newest OTP |
| Expired SMS | countdown is zero and user requests a fresh code | Mark the old code expired; preflight the send owner; send once and never reuse the old OTP |
| Toast | invisible full-screen layer intercepts | Bounded wait; Agent-owned repair of only the exact `elementFromPoint()` Toast |
| OTP | Login clicked but result unknown | Read URL/DOM only; never click twice |
| Consent | consent clicked but navigation unknown | Read and wait for the exact course path |
| Course gate | no visible course-password prompt | Do not enter `666`; try direct playback |
| Playback | mute readback fails or time does not advance | Reapply mute; real reload once; recover a hidden minimized container into the same session; never mark activated early |
