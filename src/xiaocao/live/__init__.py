"""xiaocao.live — the deterministic spine.

Pure, zero-LLM domain logic for the live/paper trading loop: the capital-action
safety boundary, exit policy, account accounting, and the structured contexts the
agent cortex consumes. Code here is shared by both the live loop and backtests so
that "回测 = 实盘" holds by construction. See docs/OPERATING_CONTRACT.md.
"""
