# C_mode_rotation_k_survivors 已 PASS，但还没有进入策略消费

- mode: PROPOSAL_ONLY
- source: scripts/flywheel_selfcheck.py
- requires_confirmation: True

## 为什么需要你看
策略飞轮发现已 PASS 但未消费的证据：C_mode_rotation_k_survivors。

## 建议动作
补齐明确落地映射、不过拟合证据和回滚方案；齐了就按固定输入走 AUTO_APPLIED，否则维持提案。

## 2026-08-07 用户确认后的复验结论

- 用户已确认继续优化，但确认不替代研究护栏。
- 旧 PASS 使用理论 `net_realized_ret`；按现行 Book-B 契约改用非北交所、开盘窗口可成交的 `executable_net_ret` 后，样本为 69 笔 / 24 日，逐笔超额约 +2.70pp，Bonferroni 修正后的显著性门槛为 0.0025，而原始 p=0.00299，结论为 `REJECTED(significant)`。
- C 与现行 ★E 在共同 12 日上的直接组合日对照未通过 walk-forward，不能证明用 C 替换 ★E 会改善当前 paper 策略。
- 因此本次只修正研究口径、导出 manifest 并让 verdict ledger 反映最新证据；不改 Book-B 选择、参数、成交、账户或安全逻辑。未来新增独立样本重新 PASS 后再进入策略消费门。

## 证据包
```json
{
  "attribution": "flywheel_selfcheck 从 verdict ledger 读到 PASS；缺口是 ② 证据没有进入 ③ 策略更新。",
  "baseline_vs_variant": "当前行为只是把 PASS 证据暴露出来，没有应用到纸面/模拟策略。",
  "change_scope": "纸面/模拟策略提案",
  "evidence_artifact": "kronos_screen/HYPOTHESES.jsonl + scripts/flywheel_selfcheck.py",
  "overfit_check": "PASS 本身不等于任意改代码；自动落地需要明确映射、不过拟合说明和可回滚方案。",
  "problem_observed": "已 PASS 但没有进入策略消费：C_mode_rotation_k_survivors",
  "rollback": "git revert <commit>"
}
```
