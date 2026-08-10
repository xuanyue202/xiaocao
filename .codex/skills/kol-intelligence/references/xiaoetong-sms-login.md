# Xiaoetong SMS Login, Slider CAPTCHA, and Muted Playback

Use this only after the bound Xiaoetong resource redirects to account login
and the user authorizes the interactive SMS login. Browser is the only UI
control path; never use Computer Use. Keep the original tab, resource identity,
and capture job throughout.

## Identity and exactly-once state

Record the current `tab_id`, Xiaoetong `resource_id`, canonical course path,
`capture_job_id`, page-attempt number, and SMS state:

```text
not_requested | requested | accepted | invalidated
```

The tab/resource identity and the SMS page session are different boundaries.
A refresh or rebuilt login page may preserve the resource while invalidating an
already-sent OTP. Never reuse an OTP across a page-session reset. Never click
`获取验证码` again while the current CAPTCHA is open or while an accepted SMS
countdown remains. An unknown send outcome requires readback, not a resend.

## CAPTCHA visibility and user confirmation

Text or DOM presence alone does not prove the CAPTCHA is visible. Require all
of the following before requesting user confirmation for the current CAPTCHA
instance and attempting one drag:

- the root, background, puzzle piece, track, and knob exist;
- `display != none`, `visibility` is visible, and `opacity > 0`;
- the root and knob rectangles have non-zero size and intersect the viewport;
- the elements are not parked at a huge negative coordinate;
- `elementFromPoint()` at the knob center hits the knob or a descendant;
- the background and puzzle assets plus their geometry are loaded.

A root with `display:block`, `opacity:0`, or an offscreen position is hidden.
Do not drag it. A refreshed or replaced challenge is a new CAPTCHA instance and
requires fresh user confirmation.

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

## One CUA drag and authoritative send readback

`tab.cua.drag()` uses tab-viewport CSS-pixel coordinates, matching
`getBoundingClientRect()`; do not add macOS window offsets. Start at the current
knob center and end at the computed distance:

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
new instance and obtain fresh user confirmation.

After the drag, wait for a short bounded UI stabilization window. Mark the SMS
state `accepted` only when readback proves all three:

- CAPTCHA status contains `验证成功`;
- the page contains `验证码已发送成功`;
- the send control reads `重新发送(Ns)` with `N > 0`.

The drag returning, CAPTCHA disappearance, a stale Toast string, or the send
button click alone is insufficient. On success, stop at the empty OTP field and
ask the user for the newest SMS code.

## Stale full-screen Toast

Before OTP submission inspect `#SpToast`: its display, opacity,
`pointer-events`, position, z-index, rectangle, and the login-button-center
hit target. The dangerous state is an invisible (`opacity:0`) fixed,
full-viewport Toast with `pointer-events:auto`; it swallows normal clicks even
though it looks gone. Never blind-click or treat a forced-click return as a
login receipt.

Wait for the CSS transition's bounded dismissal interval, then read the hit
target again. If the confirmed stale Toast still intercepts the button, obtain
explicit authorization for this page-local DOM repair. With that authorization,
change only `#SpToast` to `display:none !important` and
`pointer-events:none !important`, then read back both values and prove the
button-center hit target is the real login control. Do not remove other
overlays or modify login fields. Without authorization, stop for user action.

A refresh is the last resort. After a refresh, mark the SMS page session
`invalidated`; do not reuse the prior OTP unless the page authoritatively proves
that session remains valid.

## OTP, consent, course password, and muted playback

Before submitting, prove the same tab/resource, `SMS=accepted`, an empty OTP
field, a non-blocking Toast, and a correct login-button hit target. Enter the
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

Activation requires `muted == true`, `volume == 0`, `paused == false`,
`ended == false`, adequate `readyState`, and a later `currentTime` sample
strictly greater than the earlier one. System mute is only an extra safeguard;
it never replaces the page-level readback.

## Stop/retry matrix

| Stage | Stop condition | Narrow retry boundary |
|---|---|---|
| Identity | tab/resource/capture job differs | Read-only recover the original identity; never create a replacement job |
| CAPTCHA | hidden, offscreen, zero-sized, or intercepted | Wait for the current instance; never click send again |
| Assets | background/piece missing or challenge changed | List/bundle assets for the current instance |
| Geometry | scale mismatch or out-of-range distance | Re-read current DOM/assets; never use historical distance |
| Drag | no submitted movement, failure, or replacement | Diagnose hit target; for a new instance recompute and reconfirm |
| SMS | success Toast and countdown present | Stop and wait for the newest OTP |
| Toast | invisible full-screen layer intercepts | Bounded wait; authorized repair of only confirmed `#SpToast` |
| OTP | Login clicked but result unknown | Read URL/DOM only; never click twice |
| Consent | consent clicked but navigation unknown | Read and wait for the exact course path |
| Course gate | no visible course-password prompt | Do not enter `666`; try direct playback |
| Playback | mute readback fails or time does not advance | Reapply page mute and read back; never mark activated early |
