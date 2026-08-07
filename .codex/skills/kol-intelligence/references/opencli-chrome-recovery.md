# OpenCLI and Chrome Self-Recovery

Use this only on the local capture node after a prepared Netdisk job hits an
OpenCLI timeout, missing foreground tab, or disconnected Browser Bridge. Do not
use Computer Use. Exhaust safe self-recovery before asking the user to act.

1. Read the exact capture and Netdisk ledgers. Bind the existing capture ID,
   Netdisk job ID, target folder, and upload claim state. Never retry an
   uncertain upload or create another session/job.
2. Run `opencli daemon status` and `opencli doctor`. A browser command timeout
   is not a user blocker by itself.
3. Foreground the existing target through Chrome browser control. If that
   selector is unavailable, use the user's standing authorization to launch
   Chrome and the target URL with `open -a "Google Chrome" "<target_url>"`.
   This setup-only fallback is allowed; it does not authorize Computer Use.
4. Restart the OpenCLI daemon at most once, then poll `opencli doctor` for a
   bounded interval. After connectivity returns, reuse the same OpenCLI
   session with `open <target_url> --window foreground`, read `state`, and
   require the target folder plus credentialed `/api/list` readback with
   `errno=0` before resuming the exact prepared job.
5. If the installed OpenCLI extension is disabled, resolve its current ID from
   the installed manifest and open its exact `chrome://extensions/?id=...`
   page automatically. When the user has explicitly authorized enabling this
   installed extension, Computer Use is allowed only for the minimum Chrome UI
   sequence required to click **Keep**, enable Developer mode, and enable
   OpenCLI. Immediately validate the result with `opencli doctor`; do not use
   Computer Use for any other page or workflow. Without that explicit
   authorization, ask only for the final enable action. Never edit Chrome
   Preferences/Secure Preferences, close/restart the user's Chrome, clone
   profiles, or install an extension without confirmation.
6. For Baidu Netdisk authentication, prefer **账号登录** over QR or SMS. The
   user has standing authorization to use Chrome's already-saved Baidu
   credential through the normal browser autofill/login control. Never inspect,
   export, echo, copy, or persist the password value in the skill, ledger,
   automation memory, or chat. If autofill is unavailable or Baidu requires an
   OTP, consent, or CAPTCHA, ask only for that irreducible user action.
7. Ask for user action only for authentication that the saved-account flow
   cannot complete, consent, CAPTCHA, or a final enable action that has not
   been explicitly authorized. Afterward resume the same job; never duplicate
   capture, upload, session, or handoff side effects.
