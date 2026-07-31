# C_mode_rotation_k_survivors 已 PASS，但还没有进入策略消费

- mode: PROPOSAL_ONLY
- source: scripts/flywheel_selfcheck.py
- requires_confirmation: True

## 为什么需要你看
策略飞轮发现已 PASS 但未消费的证据：C_mode_rotation_k_survivors。

## 建议动作
补齐明确落地映射、不过拟合证据和回滚方案；齐了就按固定输入走 AUTO_APPLIED，否则维持提案。

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
