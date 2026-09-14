# 02 — 稳定 writer 启动与来源取证

**What to build:** 让唯一远端 writer 从控制面排重到路西法小媒体取证都能可靠收敛：控制面抖动不会重复启动或永久误阻塞，历史版本可以审计式退休，未来 eligible 小媒体仍能在 exact claim 约束下下载或进入当前任务修复。

**Blocked by:** 01 — 建立统一自修复状态模型

**Status:** ready-for-agent

- [ ] Peer gate 以列表发现候选、以权威 task readback 判定当前 task 和真实 peer；陈旧 active 快照不能单独阻止 writer。
- [ ] Deterministic 回放覆盖 list 悬挂、app-server/handler 错误、陈旧 active 候选和真实 peer；gate 通过前 mailbox/runner 调用为零，任一恢复序列的 runner 启动次数不超过一次。
- [ ] 控制面尝试、耗时、credential-safe failure code 和最终 gate result 可审计；持续内部故障进入当前任务 `repair_required`，不要求用户，也不伪装成成功 no-op。
- [ ] 审阅确认的路西法历史 identity/version 以 eligibility migration 退休，记录 source watermark、cutoff 和集合摘要；既有 claim/receipt 保持不变，不写伪造的完成状态。
- [ ] 同一历史 version 不再进入 pending，新 version 仍按正常 watermark 重新评估，migration 遇到并发 writer 时 fail closed 且不覆盖新状态。
- [ ] `blocked_download_frame_missing` 的同 session、同 target、无重复 click 恢复具备独立 capability 回归；修复不能以历史 pending 清零作为通过依据。
- [ ] 同 fingerprint 不再扇出为多个普通 waiting；bounded reconciliation 失败后停止处理同类 item，并返回 agent-owned `repair_required`。
- [ ] 开发验证不调用真实 Automation、OpenCLI 或 provider 副作用，不下载源视频，并保持远端 source-video bytes 为零。
