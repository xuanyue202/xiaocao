# 01 — 三位 KOL 真实文稿到家庭提醒与美股模拟闭环

**What to build:** Use one real video transcript from each of Xiaocao, Lv Xiaotong, and Lucifer to deliver one source-neutral path through current-market judgment, household WeChat advice, and an idempotent Book KOL-US paper action or explicit no-trade reason. Preserve original claims separately from system synthesis and surface material cross-KOL agreement or conflict. Never call real-capital execution.

**Blocked by:** None — can start immediately.

**Status:** completed

**Progress:** Completed in commits `f892c86`, `a49462b`, and `8e92126`. Three real transcripts passed through the source-neutral decision path; the final market-outlook messages were delivered to the agreed WeChat recipient and an immediate replay returned `already_delivered`; Book KOL-US remained at one paper fill. The full suite passes with 713 tests, and final Standards and Spec reviews reported no P0/P1/P2 findings.

- [x] One real transcript from each of Xiaocao, Lv Xiaotong, and Lucifer passes through the same source-neutral contract.
- [x] Evidence, timestamps, original claims, reasoning, asset scope, horizon, confidence, and falsifiers remain distinct from system synthesis.
- [x] Current-market validation can support, qualify, conflict with, or invalidate a claim without expiring it solely because a day elapsed.
- [x] Cross-KOL agreement and conflict are visible without majority voting replacing judgment.
- [x] Non-US assets, macro signals, and risk warnings remain in household advice even when Book KOL-US cannot transact them.
- [x] The household message chooses buy, add, hold, reduce, sell, or wait and reaches the agreed WeChat path.
- [x] Book KOL-US remains isolated from Book B, Book T, and real accounts and records an eligible action or explicit no-trade reason per item.
- [x] Book KOL-US forbids margin, options, futures, direct shorts, and negative cash while allowing eligible leveraged/inverse ETFs as cash securities.
- [x] A decisive paper position records evidence, concentration risk, and exit/falsifier rather than using mechanical timidity.
- [x] Reprocessing the same evidence does not duplicate a household notification or paper transaction.
- [x] Missing context/data, ambiguous ticker mapping, and low-density content fail visibly rather than inventing advice.
- [x] The user confirms the real messages are decision-useful and the paper result is neither mechanically timid nor uncontrolled.

## Comments

- 2026-07-19: Human acceptance completed after the final messages added market-wide trend, overall portfolio strategy, current facts, author/system attribution, and concrete stock or sector actions.
