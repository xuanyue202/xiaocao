# 回归测试：保留有效故障信号

判断一个测试是否值得保留，要能说明：它触发什么实际错误、错误会造成什么后果、断言为什么能识别该错误。用例数和覆盖率不是保留理由。

## 常用入口

安装开发依赖：`.venv/bin/python -m pip install -e '.[test]'`。

完整离线回归（包含方正 Python/Swift 行为验证，不访问 APP 或行情 API）：

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q -m 'not e2e' -n 2 --dist loadfile
```

只用两个进程，同一文件中的测试留在同一进程，避免重复创建模块级编译夹具（[pytest-xdist 分组说明](https://pytest-xdist.readthedocs.io/en/stable/distribution.html)）。各进程有独立的临时根目录、APP 测试锁和环境变量；各用例有独立临时目录。进程/线程争用测试仍创建真正的并发调用来验证锁和崩溃恢复，不用 mock 替代。

单项调试使用普通串行 pytest。专项覆盖率使用 `PYTHONPATH=src .venv/bin/python scripts/test_foundersc_reliability.py`，仍保持串行；不要给 `coverage run -m pytest` 直接追加 `-n 2`，否则只采到控制进程，不能代表工作进程的覆盖率。

行情 API e2e 继续单独串行运行 `PYTHONPATH=src .venv/bin/python -m pytest tests/e2e -q`，保持接口限流。APP 专项回归、实际 APP 仿真和手动压力测试的时间窗口保持不变，见 [APP 测试时段](FOUNDER_NATIVE_AX.md#测试时段2026-09-13)。若出现时段跳过或缺依赖跳过，必须如实报告，不能算完整通过。实际 APP 测试不加入两个进程的离线回归。

## 保留和删减依据

- 保留订单/账户身份、重复提交与撤单、金额与账本、UNKNOWN 后恢复、权限与凭据保护、部署入口及断链检查。这些错误会造成错单、重复效果、错账或流程无法继续。
- 保留通过 Node/Swift 实际执行生产函数的正常、歧义和拒绝场景；数据格式的不同边界不是因数量多就应该合并的重复测试。
- 删除锁死说明文字、缩进、版本数字、变量名、字符串出现次数的检查。字符串存在不能证明条件正确、代码可达或外部操作只发生一次。
- 不用重复进程启动证明普通分支；进程隔离、启动参数、崩溃后锁释放等本身是被测行为时保留真实进程。
- 外部服务已经被替身替代时，通过生产已有的 `sleep` 注入接口记录等待请求并断言重试时序；没有必要真的睡到超时。不可全局禁用 sleep 或削弱生产重试策略。

## 2026-09-13 清理与实测

原串行回归：3250 passed、12 个行情 API e2e deselected，pytest 40.50 秒、整条命令 41.39 秒。用户此前同条命令为 38.70 秒。

删除 29 个源码/文案用例：

| 文件 | 删除数量 | 原检查及处理 |
| --- | ---: | --- |
| `test_foundersc_opencli_templates.py` | 20 | 旧 Web 路线的源码片段、README、版本及缩进断言；保留凭据相关静态检查，实际 JS 行为测试完整保留 |
| `test_foundersc_native_ax.py` | 3 | Swift 源码坐标、函数名、关键字符串及调用文本计数；保留实际编译执行、客户端和适配器行为测试 |
| `test_kol_subscription_video.py` | 4 | 扫描、目录编辑器、搜索、转存脚本字符串；保留服务状态机的正常、失败、恢复与未知效果用例 |
| `test_kol_remote_task_candidates.py` | 1 | 指南中的固定文案和换行；保留实际候选发现与 peer-gate 行为验证 |
| `test_kol_netdisk_opencli_templates.py` | 1 | 对固定“历史案例”JSON 中的字符串清单逐项搜索源码；连同无人使用的清单删除，保留模板参数转义等检查 |

这不是宣称被删源码断言涉及的全部 UI 分支都已被端到端覆盖；源码字符串本来就不能证明那些行为。独立 APP 仿真证据仍以相应回执为准。

另外，三个服务测试真实等待共约 12 秒，改为记录并断言 `[5]` 或 `[1, 1]` 秒等待请求。pytest 每例编号目录的累计扫描改为原子创建随机目录，保留逐例隔离和会话目录回收。生产代码、重试时间及交易策略均未修改。

串行清理后：3221 passed、12 deselected，pytest 25.04 秒、命令 25.70 秒。两个进程执行相同的 3221 个离线用例，连续两次 pytest 为 15.66 / 15.33 秒、整条命令为 16.05 / 15.67 秒；没有靠增加 deselect 或 skip 达标。该耗时为本机已有编译工具链环境下实测，首次安装依赖或编译不能算在日常回归速度内。串行命令仍需约 25 秒，20 秒内的全库入口是上方显式两个进程的命令。

方正专项串行覆盖率复验：684 passed、10.93 秒。计量仍为 5385 行、2034 分支，未覆盖 731 行、部分覆盖 443 分支，与本次删减前完全相同；源码字符串断言的删除没有减少该范围的行为触达。日志：`output/research/pytest_perf_reliability_20260913.log`。

本地诊断日志：`output/research/pytest_perf_baseline_20260913.log`、`pytest_perf_iteration1_20260913.log`、`pytest_perf_parallel_20260913.log`、`pytest_perf_final_20260913.log`；逐项删减清单：`output/research/pytest_removed_20260913.txt`。这些运行产物不提交。
