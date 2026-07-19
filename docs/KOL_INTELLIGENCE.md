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
`low_density_content`. Cross-source agreements and
conflicts link claim IDs and require a written judgment; counts and majority
votes have no authority.

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
per-item receipt immediately. Notification idempotency includes the advisory
content/revision, while Book KOL-US continues to key on evidence SHA: corrected
advice can be resent without duplicating a paper trade. A process lock and a
durable pre-send claim prevent concurrent duplicate sends; an interrupted relay
call fails closed as uncertain until reconciled.

## Two output layers

Phone messages are written for a human reader, not as serialized pipeline state:
each names the company and code, explains what happened, connects the causal
chain to the likely market impact, says what it means for this household or a
new opportunity, and gives plain-language timing and reconsideration conditions.
Book KOL-US fills, gate/status enums, bucket labels, hashes, and cross-source
plumbing remain in the audit result and are never included in WeChat copy.

Reusable reasoning from every author is distilled through the same
`xiaocao-distill` governance into `reference/experience/distilled/`. New
multi-author files include `author`, `source`, and evidence path/SHA provenance;
the common candidate backlog preserves authors and source references. 小草's
A-share posture remains the dated posture SSOT, while 吕晓彤/路西法 notes can
enrich playbook and hypotheses without impersonating 小草 or overwriting that
posture. All such knowledge remains `authority=0` until the existing research
and human gates pass.

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
