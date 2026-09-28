# 吕晓彤云端转存的提交与对账修复

Status: fixed — scoped regression and native input verification passed;
第 137 课的精确转存回执已完成。历史两次点击的具体输入失效原因仍无法从旧日志还原。

## 问题与证据

- 第 137 课的 source identity 为
  `62c5b4f1c7d1d73319b827b65a7bf898465d3b871599f33209831412a0e4ed3e`，
  version 为 `747c9f9fe32a22d8d3940204340d315987c64bbe0151dec8878b0a7ba4aff653`。
- 2026-09-14 两次记录都只有原生点击 selector 命中；
  `provider_request_observed=false`、`provider_response_observed=false`，
  没有 `/share/transfer` 网络记录。两次动作不能称为服务端转存失败。
- 2026-09-28 重新读取目标目录与已完成的全局精确搜索，文件名和
  364,863,315 字节的匹配数均为零。
- 当前页面同时有 `.save-path` 与 `bottomShareSave`；旧代码只识别旧版
  `shareSave`，并把所有弹窗“确定”都作为同一种保存确认。
- 执行生产 DOM 脚本的最小复现：常规提交弹窗通过，目录选择弹窗没有发出
  请求。复现命令：
  `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_kol_share_transfer_dom.py`。
- 真实页面进一步否定了“当前 .save-path 弹窗一定只选择目录”的初始推断：
  当前标题实际是“保存到”，其确定按钮会提交保存。两类弹窗必须分别处理。
- 原始只读对账 CLI 在文件已经出现后仍报
  `source effect readback target is not active`：另一对象的最新终态遮住了
  这个旧对象；运行时绑定又错误地只允许没有 observer 字段的旧 claim。

## 根因

1. 自动化把 selector 命中、可信输入到达、服务端请求、精确文件落位四个
   独立事实压成了“点击一次”。请求从未被证明时仍消耗转存等待和重试，
   最后将可修的控制面故障作为人工阻塞。
2. 弹窗用途没有建模。“保存到”可以提交，“选择保存路径”只改目录；
   后者还需要页面级保存按钮。旧实现无法完成后者的提交步骤。
3. 已安装的页面网络 observer 会保留前一个对象的记录；旧响应可能被
   下一个对象复用。旧日志不足以证明此问题就是第 137 课两次失效的触发因素。
4. 只读恢复依赖来源总状态和 observer 字段的有无，没有以精确对象的
   durable claim 为恢复入口。因此人工保存成功也可能无法经该入口关闭旧未决状态。

## 修复

- 以弹窗标题区分目录选择与服务端提交；未知标题停止在 Agent 修复。
- 两个阶段都使用原生 OpenCLI 输入；目录阶段完成后核验可信输入、
  弹窗消失、完整目标路径及唯一来源选择，再绑定 `bottomShareSave`
  或旧版页面保存按钮。整个流程只产生一次 provider attempt。
- 提交前验证按钮中心命中本身或后代，记录匹配控件的可信 click。
  输入探针和网络 observer 同时证明没有输入、没有请求时，持久化
  `failed_pretrigger` / `lv_native_click_not_delivered`，由 Agent 修控制面；
  已发请求或输入送达但响应不确定时仍只对账。
- 每次准备清空旧观测，采用 generation 排除上一请求的迟到响应。
- 只读对账由精确 pending identity/version 和原始 claim 绑定；同来源另一
  对象的终态不阻塞该读取。保留 claim、拒绝未知 ID，也不新增转存权限。
- 同步 `kol-intelligence/references/full-contract.md`；既有 Automation 已
  引用该契约，日程、模型、通知对象和经济权限未改变。

## 实际恢复与验证边界

调查中一次准备探测错误地把当前“保存到”的确定按钮当作纯目录操作，
通过 DOM click 触发了真实保存。保护检查发现请求后没有再点页面保存按钮。
这是调查中的非预期提交，不能包装成修复后原生流程的成功证明。
原有 claim 保持不变；没有为该探测另行预先记录新的提交 claim。这个缺口
保留在 `137_diagnostic_effect_audit.json`，不事后编造提交前凭证。
新代码已移除这条 DOM 确认路径，所有确认均由原生 OpenCLI 执行。

该次请求返回 HTTP 200 / errno=0；精确目标文件随后出现，字节数匹配，
`target_provider_identity_sha256` 为
`086b5f06bffb359768236a8c074930491e501d63f4046c5542fb16292e5cbcb0`。
服务的 `readback_only=True` 已生成完成回执；修复后的
`reconcile-source-effect` 又通过原始 claim 完成只读对账，未重放保存。

修复后的真实“保存到”控件采用捕获阶段阻断服务端 handler 的原生测试：
原生输入和生产探针都证明可信事件命中，provider 请求数为零。
探测 handler 已移除，页面已回到目标目录。该检查证明原生端口与目标绑定，
避免重复保存已存在的文件；不声称修复后重新做过真实提交。

现场证据仅在本机 `output/automation_audit/kol-transfer-20260928/`：
`137_absence_readback.json`、`137_preparation_effect.json`、
`137_reconciled_transfer.json`、`original_confirmation_geometry.json`、
`native_confirmation_dry_probe.json`、
`137_effect_reconciliation_after_repair.json`。不提交凭证、分享 URL 或运行账本。

回归覆盖目录选择后提交、确认即提交、输入丢失、按钮遮挡、目标路径错误、
多个保存控件、旧记录、迟到响应、意外请求不重放、claim-before-click、
同一次 provider attempt，以及另一对象终态下的精确旧 claim 对账。
最终四个受影响测试文件共 300 passed；`git diff --check` 通过。
课程转存完成与课程语义分析/发布是不同阶段；本修复未启动另一次完整扫描。
