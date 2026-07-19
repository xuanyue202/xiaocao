# KOL Intelligence Decision Slice

This slice begins with already-transcribed material. It deliberately excludes
video enrichment, OpenCLI, and live capture.

## Input boundary

Convert the real Word exports with the existing local converter:

```bash
bash /Users/bytedance/Downloads/小草/convert_original_doc_to_markdown.sh \
  /Users/bytedance/Downloads/小草/original_doc \
  /Users/bytedance/Downloads/小草
```

The decision pipeline consumes UTF-8 Markdown or text. A decision bundle is a
JSON object with one source-neutral `items[]` entry per transcript. Each entry
contains source metadata, evidence-anchored KOL claims, concrete
`actionable_signals[]`, a frozen current-market validation, separate system
synthesis, one household advisory action, and one Book KOL-US trade or explicit
no-trade decision. Every actionable signal must name an asset/ticker or explicit
theme, action, horizon, execution, trigger, falsifiers, current validation, and
separate event/fundamental/trading rationales. Framework-only content fails as
`low_density_content`. Cross-source agreements and conflicts link claim IDs
from at least two distinct authors and require a written judgment; counts and
majority votes have no authority. Relevant multi-author conclusions are part of
the reader-facing message, not audit-only plumbing.

The candidate universe is the market, not the current household holdings.
Fresh 亮灰 positions are used to label held/unheld opportunities, size risk, and
state a funding/rotation plan. They must not filter out an opportunity merely
because the family does not already own it.

`household_context_provider` selects the authoritative 亮灰 `lianghui_mcp` source.
Every processing run freshly reads `user://current`,
`get_portfolio_decision_view`, and `get_portfolio_reconciliation_view`. The
resulting family id, timestamp, positions, and decision facts are hashed and
linked to that run's audit/message. They are never reused as the next run's
input. Credentials remain in the 亮灰 project's local `LiangHuiProject` MCP
configuration and are
not copied into this repository or an output ledger.

Claims must contain an exact excerpt from the referenced transcript. Market
validation must use one of `support`, `qualify`, `conflict`, or `invalidate` and
must include timestamped facts with evidence references. Age alone is not an
invalidation rule.

Run a bundle with:

```bash
PYTHONPATH=src python3 scripts/kol_decisions.py path/to/bundle.json
```

To process with a fresh 亮灰 portfolio read and deliver each still-pending item
to the recipient already configured in `output/live/notify.env`, use:

```bash
PYTHONPATH=src python3 scripts/kol_decisions.py path/to/bundle.json --send-wechat
```

The sender reuses `src/xiaocao/live/notify.py`. A relay `ok` is persisted as a
per-item receipt immediately. Notification idempotency includes the market
outlook, advisory, relevant cross-source judgment, and revision, so a material
change from defense to trial positioning creates a new reader notification.
Book KOL-US keys on evidence plus
the material paper intent: replaying the same decision is idempotent, while a
later `no_trade -> trade` or target change can be recorded after new market
facts. Legacy evidence-only decisions remain replay-compatible. A process lock and a
durable pre-send claim prevent concurrent duplicate sends; an interrupted relay
call fails closed as uncertain until reconciled.

## Two output layers

Phone messages are written for a human reader, not as serialized pipeline state.
When the source contains a market-wide or portfolio-wide judgment, the normalized
item carries an evidence-linked `market_outlook` with the current phase, base
case, overall strategy, turning points, horizon, confidence, falsifiers, and its
own scope-matched current-market validation. The message renders this as a
standalone `大盘与整体策略` section before individual stocks or themes. It shows
the linked KOL quotes first, then labels current-market validation and every
forward path/strategy statement as system judgment, including validation time
and whether facts support, qualify, conflict with, or invalidate the view. Key
facts are rendered in reader language with their observation time; raw evidence
references remain in the audit output instead of cluttering the phone message. It
must not be inferred from holdings or invented when the source has no such view.
Each subsequent signal names the company and code,
explains what happened, connects the causal chain to the likely market impact,
says what it means for this household or a new opportunity, and gives
plain-language timing and reconsideration conditions.
Book KOL-US fills, gate/status enums, bucket labels, and hashes remain in the
audit result and are never included in WeChat copy. Relevant cross-author
agreement or tension is rendered in plain language.

Reusable reasoning from every author is distilled through the same
`xiaocao-distill` governance into `reference/experience/distilled/`. New
multi-author files include `author`, `source`, and evidence path/SHA provenance;
the common candidate backlog preserves authors and source references. This
issue does not rewrite the global current A-share posture; all three authors'
notes enrich hypotheses and reusable judgment with `authority=0` until the
existing research and human gates pass.

Committed acceptance bundles contain transcript claims, market evidence, and
redacted routing intent only. The actual family holdings and personalized
held/unheld assessment stay under ignored `output/live/kol_intelligence/`.

Use `--preflight` to validate all transcript quotes, market facts, cross-source
links, and Book KOL-US intents without writing any notification or trade. Once
an external WeChat send is confirmed, record its receipt idempotently:

```bash
PYTHONPATH=src python3 scripts/kol_decisions.py \
  --output-dir output/live/kol_intelligence \
  --mark-delivered <IDEMPOTENCY_KEY> --receipt <WECHAT_RECEIPT>
```

Outputs live under `output/live/kol_intelligence/` by default:

- `latest_result.json` and `events.jsonl`: auditable analysis results;
- `latest_household_message.md` and `household_outbox.jsonl`: deterministic
  WeChat-ready advisory messages, pending until an agreed delivery adapter
  records an external receipt;
- `book_kol_us/account.json`, `decisions.jsonl`, and `trades.jsonl`: an isolated,
  paper-only, cash-only US equity/ETF book.

The pipeline fails visibly before side effects when household context or market
facts are missing, a ticker is ambiguous, content is low-density, evidence does
not contain the quoted claim, or a proposed paper instrument breaches the book
rules. It never imports or calls a real-capital execution interface.
