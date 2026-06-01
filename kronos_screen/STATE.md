# Kronos × 小草 二级筛选模型 — 进度状态 (Ralph loop)

目标：得到一个**鲁棒、高收益**的组合二级筛选模型。机器 = MacBook Pro M3 (12核 6P+6E, 36GB, MPS)。

## 决策记录
- 策略口径：二级筛选 = `validated_v5` profile + `--exit-rule next_close`（买信号日开盘、卖**下一交易日**收盘）。label = returnPct，win = returnPct>0。
- 数据全部 **cache-only**（API 可达但不碰，遵守 cache-first 纪律）。缓存 `output/.cache/xiaocao.db`。
- 结构化特征覆盖 2025-01-03→2026-05-28（336日）；date_kline 覆盖 2025-06-04→2026-05-28 → 可用标注区间约 2025-06-09→2026-05-27（~240日）。
- **无未来函数**：Kronos 上下文只用 tradeDate < buyDate 的 K 线（D 开盘决策只见 ≤D-1）。结构化特征含 D 开盘竞价(xcjw 等)。
- **walk-forward** 时间切分，按交易日整块；有效独立样本 ≈ 天数(~240)而非行数。要求 train+test 同时改善。
- 模型维度：mini d=256/4层(ctx2048)、small d=512/8层(ctx512)、base d=832/12层(ctx512)。
- GBDT 用 sklearn `HistGradientBoosting`（避免 lightgbm 的 libomp 依赖）。

## 路线（gate 逐级放行）
0. **go/no-go**：mini/small 零样本预测次日，算 IC/AUC vs 实际 win。判"输入里有没有信号"。
1. **天花板检验**：base **冻结** embedding(decode_s1 的 x[:,-1]) ⊕ 结构化特征 → HGB，walk-forward。判"能否打败小草现状二级筛选"。
2. 若见 lift：base 继续预训练(A) + LoRA 头(B)。
3. 终检：walk-forward 分板块胜率/收益、鲁棒性、超过现状。

## 现状基线（已知，来自既有回测）
- 二级筛选 active：60d 52.4%/+1.13%、20d 53.2%/+0.69%、5d 36.4%/−1.88%。
- 单笔 std 7.83%，edge ~+1.1%。最近一周回撤是真实 ~2.6σ，且大盘/情绪门槛都过不了三窗口同改善。

## 进度
- [x] 环境：torch 2.12 +MPS OK；deps OK；Kronos 权重(mini/small/base+tokenizers)已下。
- [x] 全年标注集：1814 信号 → 1456 样本(358 因上下文<60丢弃)，win50.1%/+1.02%。ds/meta.parquet + contexts.pkl + emb_base/small.npz。
- [x] 天花板检验(绝对收益 target)：
      - 原始 832 维 embedding 喂 HGB = 噪声(IC~0, AUC~0.5)，hybrid 反而更差(维度灾难)。
      - **PCA8 + Ridge：embedding IC≈0.059，top20 +1.20%/55% vs 基线 +1.03%/52%** —— 弱但唯一稳定的正信号。
      - 结构化特征(4维或富化55维)都几乎无稳健信号；富化反而过拟合更重。
      - 所有配置 per-fold IC 变号 → 信号弱且 regime 依赖。
- [x] **关键转向成功**：按日横截面 target(收益减当日均值)。base frozen emb → 每fold StandardScaler → PCA8 → Ridge(α=10)：
      - **pooled within-day IC=0.110，5个fold全正 [0.107,0.148,0.026,0.038,0.239]**；对 α 完全不敏感、k=6~8 稳定。base >> small(0.046) >> mini(0.020)。**规模问题答案：base。**
      - 月度：弱市 2026-05 take-all −0.09% → 模型 top50 +1.58%（鲁棒性达标）。
- [x] **诚实的经济性检验(防"真实的谎言")**：
      - 日度等权组合 top50 +254% vs take-all +111% —— **大部分是日度等权加权假象，不作为头条**。
      - **逐笔(每笔等权)**：top50 +1.082%/笔 vs take-all +1.032%，win 53.2% vs 52.1%；**top半-底半 spread 仅 +0.098%/笔**。
      - 结论：frozen 边际**真实但经济上很小**（rank对了、幅度小）。Sharpe/回撤在日度框架有改善但幅度需谨慎陈述。
      - 固定 top-2/3/天 反而更差 → 信号是"剔除预测最差的一半"，不是"精准命中最强"。
- [x] **LoRA 微调 base 失败(诚实记录)**：单split(train前50%/750样本) frozen baseline wIC=0.075、top50+1.022%≈take-all。LoRA(末4块attn,r8,215K参数,按日Pearson损失,早停)：
      - OOS wIC=**-0.004**，top50 +1.051% —— **没超过 frozen floor**。val_wIC 在 0 附近震荡(ep10峰值0.086,其余多为负) → 750样本下微调过拟合、学不到稳定可泛化信号。
      - 结论：**当前数据规模下 frozen embedding 就是天花板**；微调/富化特征都不提升。
- [~] go/no-go 零样本生成式探针(off-the-shelf base, H=2, samples=30) 后台运行中 → zeroshot_base.log。这是论文的正牌方法基线。
- [ ] **重大方向修正(用户指出 README 有官方A股微调demo)**：论文全程 zero-shot，但 repo 提供官方微调=**继续生成式预训练**(tokenizer→predictor 走AR next-token目标)，**全参数微调(无LoRA)**，lr=4e-5，csi300 2011-2022。
      - 我之前的 LoRA 是自创的监督排序头——错误工具。
      - **Q2 答案：100M 不需要 LoRA**；作者全参微调，36GB M3 内存足够。约束是"数据少→过拟合"，靠小lr+早停+自监督目标(数据海量)解决，不是 LoRA。
      - 数据格式：{symbol: DataFrame[datetime, open/high/low/close/vol/amt]}，滑窗 lookback+predict+1，按lookback段做z-score(防泄漏)。**不需要 qlib**，从 date_kline 缓存直接造。
      - **防泄漏**：自监督微调窗口必须结束于 2025-12-22 之前(OOS 从12-23开始)。训练语料=2025-06..2025-12-22 的全A股日线。
- [x] **零样本生成式探针(off-the-shelf base, samples=30) 结果**：全样本 within-day IC=0.022；**OOS wIC=-0.006(≈0)**。论文的 zero-shot 预测**不能**对小草候选排序。
- [~] **方法对比(OOS within-day IC)**：zero-shot 生成式 -0.006 | frozen embedding 0.075(单split)/0.110(扩展folds, 最佳) | 自创LoRA -0.004。**结论：信号在"表征(embedding)"里，不在"生成式预测"里。**
- [~] ft_pretrain.py 已写并运行中：base 全参微调，46924 train/18118 val 窗口，lr4e-5，早停。→ ft_base.log / ft_base/
- [x] **官方继续预训练微调结果(真实数据验证)**：base 全参 FT，epoch0 val loss 3.014→2.492(AR目标改善)。但**embedding 排序能力反而下降**：
      - FT-base(ep0) within-day IC=**0.041** vs frozen off-the-shelf **0.110**；top50 +1.17%/50% vs +1.39%/53%。
      - 原因(第一性原理)：12B多市场预训练的通用表征，被1年A股窄数据的AR目标过度特化/灾难性遗忘，擦掉了利于横截面排序的跨资产结构。
- [x] **三种方法全部不及 frozen**：zero-shot生成式 -0.006 | 自创LoRA -0.004 | 官方继续预训练 0.041 | **frozen 0.110(冠军)**。
      → **结论(真实数据验证)：frozen off-the-shelf base embedding 就是天花板，微调任何形式都不提升甚至有害。**
- [ ] **重定目标(Ralph)**：两阶段(一级modes→二级Kronos排序)、鲁棒、高收益、真实数据全验证后才收尾。
- [x] **两阶段验证(真实OOS数据)** validate_two_stage.py：
      - within-day IC 0.110, t=2.18, **p=0.032 显著**, 56% days>0; 5/5训练fold全正; 月度4/6正(含弱市5月+1.67)。
      - 日度定额资金回测 top50 +254%cum/Sharpe4.41/maxDD-16.6% vs take-all +111%/3.04/-22.2%。
      - **诚实警告**：逐笔仅 +0.098%/笔；日度edge +0.545%/天但 **t=1.47 p=0.145 不显著**。+254%含复利与少数好日子，非稳健显著。
- [x] **Kronos vs 平凡因子(决定性)**：-vol 0.011 | -5d动量 0.082 | 1d反转 0.043 | **Kronos 0.110(唯一显著)**；去掉vol成分后 Kronos 仍 0.088。→ **Kronos 是真实横截面结构，非vol/动量代理，值得用。**
- [ ] **剩余唯一杠杆=更多数据**(每天仅~7候选→日度IC高方差)。扩到 primary 池(focus/sort_v2)做更大横截面，embed子采样，复验 IC 是否更强更显著。
- [ ] 锁定+部署 scorer + 集成 live_recommend；全验证(尤其yield显著性)通过才收尾。

- [x] **高功效广域复验(决定性, 真实数据)** build_universe.py + validate_universe.py：
      - 广域宇宙 ~398只/天 × 19 OOS天：within-day IC = **-0.0435** (t=-1.66, p=0.11)，top10-bot10 spread p=0.63 不显著。
      - 限定到小草可交易名单(~300/天)：IC = **-0.0514** (t=-1.80, p=0.089) —— 仍为负。
      - **mode候选上的 +0.110 在更高功效的广域检验下不复现，且广域偏负。**

## ★ 最优组合策略(已找到, 真实数据验证) — PIPELINE
**两阶段二级筛选 = K 过滤 + P 优选：**
- **Stage-2a (K)**: Kronos base 冻结 embedding 排序器(PCA8+Ridge, 按日去均值 target) → 剔除当天 primary 候选的**后50%**(K 是显著的广域排序器, "去掉最差")。
- **Stage-2b (P)**: 前一日分钟级微结构(尾盘强度/收盘位置/振幅/主力净流入, 来自 minute_line 历史) GBDT 排序 → 在幸存者里取 **top3-4**。
- 数据来源全部决策时可见(K线<D, 前一日完整); 今日集合竞价(call_auction)仅 latest-only→只能LIVE加成,不可回测。

**验证(OOS 2025-12-23..2026-05-27, 93天, vs take-all +0.847%/天 win50.8%)：**
| 策略 | 日收益 | win | cum | Sharpe | maxDD | 配对p |
|---|---|---|---|---|---|---|
| take-all(现状) | +0.847% | 51% | +112% | 3.04 | -22 | - |
| K top50%(去最差半) | +1.45% | 55% | +271% | 4.48 | -20 | 0.145 |
| **PIPE K50→P top3** | **+1.76%** | **58%** | **+402%** | **5.29** | -21 | **0.017** |
| PIPE top4 / top5 | +1.53/+1.44% | 55% | +305/+269% | 4.80/4.52 | -22/-20 | 0.050/0.084 |
- 跨N(3,4,5)稳健; 月度 **4/6 正**(含弱市5月+2.20, 1月+2.43; 仅12月euphoric -1.55、3月~0)。
- 板块: 边际在**主板**(85%选中, +1.74%/58%win), 非北交微盘驱动。
- **诚实警告**: 限定主板+创业 edge +0.57%/天 p=0.147(不独立显著); 全样本 p=0.017 部分靠少数北交高收益日。试了~6策略(多重比较→有效p更高)。结论: **真实、经济有意义、主板集中、鲁棒(跨N与多数月)，但统计显著性临界。**

## 迭代2更新(富化P + 显著性天花板)
- 富化 P 到23个分钟特征(三段动量/主力净流入占比/trendLine斜率/量能偏移, 从缓存分钟重抽,免API)。
- pipeline 稳定: PIPE K50→P top3 = +1.67%/天 win58% Sharpe5.02 p=0.028; 12月回吐缩小到-0.53。新显著变体 K+P rank top50% +1.72%/天 p=0.049。
- **候选扩展不可行**: 放宽 max-open-pct(12 vs 6) 候选量几乎不变(127 vs 120)——~7/天由 mode 规则决定,非过滤器。**显著性天花板是结构性的**(要更多候选须改一级筛选,超出二级筛选范畴)。
- scorer 已用富化P重存(动态特征列)。
- LIVE-only 增强(不可回测): 今日 call_auction 不平衡(buyVol2-sellVol2)/竞价涨幅 做最终 tie-break; 个股舆情(WebSearch)叠加。已在 spec.json 记录。
- **收敛结论**: 已达此数据下的最优二级筛选组合。进一步提升只能靠(a)一级筛选扩候选→显著性, 或(b)live信号(竞价/舆情, 不可回测)。

## 迭代3: 选项1(扩候选)实测 — 结论=扩候选反而稀释
- XC_JW_SCALE env 旋钮(已回滚, 默认不变)。JW_SCALE=0.33 → ~12/天(从~6/天), 3149候选(vs1814)。候选量被 mode setup 规则结构性封顶~12/天。
- **4窗口 pipeline(K50→P top3) vs take-all 边际**:
  - WIDE(~12/天): 6月+0.04 / 3月-0.56 / 1月+0.07 / 1周+1.03; 全OOS +0.61 vs +0.54 (edge+0.07, **p=0.83**)。
  - NARROW(~6/天): 6月+0.22 / 3月-0.01 / 1月+0.31 / 1周+1.70; 全OOS +1.04 vs +0.69 (edge+0.35, **p=0.33**)。
  - **扩候选稀释边际**(弱竞价票=噪声)。且换OOS窗口(12-09 vs 12-23)边际从+1.67/p.028 掉到+0.35/p.33 → **对setup敏感, 不稳健显著**。
- NARROW pipeline 真正稳的好处: **提升胜率**(各窗口 51/56/60/54% vs 50/54/53/37%)+ **缓冲坏周**(1周 -0.69% vs -2.39%, win54 vs37)。收益边际小且不显著。
- **最终诚实裁决**: 二级筛选边际真实但**小且不稳健显著**; 主要价值=胜率小幅提升+回撤缓冲; 扩候选无法买到显著性。

## 迭代4: 重审微调(新策略下) — 结论=日线FT仍否; 分钟FT低价值不推荐
- 日线FT裁决不变: K 角色变"去底半"粗筛, 但FT把 embedding IC 0.11→0.04, 排序差=筛得差, 粗筛角色救不了。
- **新角度: 喂Kronos分钟K线**(P证明日内微结构有信号)。建 ds_min: 前一日241根1分钟trade价→5分钟OHLCV(~49根)→frozen base embed。
  - **结果: minute-Kronos within-day IC = -0.011(零)**, 远不及 daily-K(0.11)。
  - 原因: (a) API分钟只有trade价无真实盘中OHLC→5分OHLC退化; (b) 上下文短(49根)而Kronos强在长真实OHLC; (c) 分钟单日截面OOD。
- **P信号分解**: 价量SHAPE特征 IC0.053(全部信号在此); 主力净流入mainIn 几乎无贡献(P_all≈P_shape)。→ 有用信号在OHLCV模态内, 但frozen minute-Kronos因输入退化/短上下文抓不到。
- **裁决**: 分钟继续预训练理论上可(信号是shape可ingest+300x数据), 但 (a)frozen基线=0(输入太差,GIGO,继续预训练救不了坏输入), (b)手工P已廉价抓到shape信号, (c)daily-K(0.11)已是最强单信号。→ **低期望价值, 不推荐再投微调。**
- **真正的杠杆 ≠ 微调Kronos, 而是低SNR的次日收盘LABEL**。换高SNR目标(多日/止盈止损出场)会同时抬升 K/P/pipeline——这才值得试。

## 迭代5: 高SNR标签 + 组合 同时试 — 结论=高SNR标签反而更差(假设证伪)
- 同一候选/特征/embedding, 只换 label 重训 K/P 跑 pipeline:
  - next_close(1d): edge +0.35/d p=0.33
  - 3d hold: edge +0.18/d p=0.71 (边际衰减,1d优势3d内反转)
  - **max_dd(v5真实止损出场, avg+3.57%): edge -0.17/d p=0.65 (pipeline 反而略差!)**
- max_dd 4窗口: 6月 -0.35 / 3月 +0.06 / 1月 +0.84 / **1周 +2.73(win54 vs31)**。
- **跨所有label一致模式**: pipeline 收益集中在**近1月/近1周**(尤其缓冲坏周/抓近期赢家), 6月维度washout或反转。
- 机理: 选"次日上涨"的信号 ≠ 选"一周跑赢"的信号; Kronos+前日分钟特征不含稳健的多日选股alpha。
- **裁决: 高SNR标签不能换来显著边际; 二级筛选对真实v5(max_dd)策略无改善(略负)。**

## ★ 全investigation 收敛裁决(真实数据, 防真实的谎言)
Kronos(任何用法) + 前日分钟特征 的二级筛选边际:
1. 真实但**弱、临界显著(p0.33)、仅限1日次日收盘**;
2. 微调(LoRA/继续预训练/分钟)均不提升甚至有害; 扩候选稀释; 高SNR标签更差;
3. 唯一**稳健正向**=近期(1月/1周)胜率提升 + 回撤缓冲(坏周 -2.4%→-0.7%, win37→54);
4. 对真实多日(max_dd)策略无增益。
→ **没有稳健高收益的二级筛选alpha可从现有信号挖出**; 可部署价值仅为"近期下行缓冲+小幅胜率提升"。瓶颈是信号内容(单票日线/前日分钟不含多日选股alpha)+次日收盘低SNR, 非模型/方法。

## 迭代6: 集成 live_recommend + 持续优化管线 + 适配 skill
- live_recommend.py 接入 K→P 防御性叠加层(fail-safe, --no-kronos/--kronos-top-n): ★=纯K→P(A/B基线), ★B=K→P+9:25竞价不平衡 tiebreak(权重0.25, 仅当日实时, 实盘建议集)。
- 采集管线(随采随存, 累积训练数据 + 前瞻A/B):
  - capture_signals.py: 每日竞价订单簿不平衡特征 + ★/★B + 快照 → output/live/signal_snapshots.jsonl。
  - eod_capture.py: 盘后 each_trade 逐笔买卖流特征(净主买/大单净额/尾盘净主买, latest-only=当日跑) + minute → output/live/eod_features.jsonl(--save-raw 存原始)。
  - forward_eval.py --live-only: 回填真实次日收盘 → A/B裁决(take-all vs ★ vs ★B + 配对显著性) + 累积 output/live/training_rows.parquet。
- 持续优化循环: 9:25 live_recommend → 盘后 eod_capture → T+1 forward_eval → 周期性用 training_rows 重训 P + 刷新 model/*.joblib。
- kronos_lib KRONOS_REPO 改为 env 可配(默认 parents[2]/Kronos), 便于移植/skill。
- **skill 适配**(/Users/bytedance/.codex/skills/xiaocao-trading/SKILL.md): flags 增 ★KP/KP↓, 新增 "Kronos Secondary Screen & Continuous Optimization" 章节(管线/依赖/每日循环/诚实定位)。bundle 为轻量baseline, 叠加层需 full checkout(已注明)。
- 数据现实: 竞价+逐笔均 latest-only → 只能当日采、前瞻验证, 不可回测; 真实盘中分钟仍只有 trade 价(无真实盘中OHLC), Kronos-on-minute 仍受限。

## 各方向排名(OOS, within-day, 真实数据)
K Kronos-emb IC0.110(p.03) top50+1.22 | P 前日分钟 IC0.052 top3+1.14(最佳top选) | S结构化~0 | D日线~0 | C全特征GBDT过拟合更差。
**互补**: K擅长广域排序(去底), P擅长选顶 → pipeline 组合最优。

## 最终诚实结论(关键, 防真实的谎言)
- mode候选 +0.11 是**小样本(每天~7只×93天, p=0.03 临界)结果，未通过高功效复验**(广域~400只/天 IC≈-0.04~-0.05)。
- 三种用法(frozen/zero-shot/LoRA/继续预训练)无一稳健为正。
- **裁决：Kronos 日线 embedding 不能提供稳健的二级筛选 alpha。** +0.11 很可能是噪声或极窄的 setup 条件信号(未证实)。
- 第一性原理：次日收盘 SNR 太低(单笔std7.8%/edge~1%)；基础模型的单票日线表征不编码"setup条件下的次日方向"；小草真正的edge在竞价/连板情绪等**分钟级微结构**，而缓存里没有分钟数据。
- **Ralph 完成判据(鲁棒+高收益+全验证) 未达成，且用现有日线数据大概率不可达成。** 不输出虚假完成。诚实上报，建议：要么提供分钟级/竞价数据，要么接受负面结论。

## 最佳模型(锁定)
**二级筛选器 = Kronos base (off-the-shelf, 冻结) 末层hidden embedding → 每fold StandardScaler → PCA8 → Ridge(α=10)，target=按日去均值收益。** walk-forward OOS within-day IC 0.110，5 fold 全正。

## 阶段性结论(诚实)
Kronos base **frozen** emb + PCA8 + Ridge + 按日横截面 target = **鲁棒但温和**的二级筛选边际：
扩展folds wIC0.110(5fold全正)、逐笔 top50 +1.082%/win53.2% vs take-all +1.032%/52.1%。
规模选 base(>>small>>mini)。微调在现有数据下无增益。**"高收益"只部分达成**——下一步只有"更多数据/分钟级数据"能突破。

## frozen floor 基准 (要被 LoRA 超过才算进步)
- within-day IC 0.110；逐笔 top50 +1.082% / win 53.2%；top-bottom spread +0.098%/笔。OOS 2025-12-23..2026-05-27 (100天/698笔)。

## 关键数 (反复出现)
- OOS 区间 2025-12-23..2026-05-27, n=698。take-all 基线 +1.03%/52.1%。
- 单笔 std 7.83%；按日中位收益~0 → 二分类 win 标签很噪。
- emb PCA8 是目前最稳的弱信号；维度务必先降到 ~8。

## 关键路径
- 数据集脚本 kronos_screen/scripts/build_dataset.py
- Kronos 仓库 /Users/bytedance/coding/xiaocao/Kronos (model/kronos.py: Kronos.decode_s1 返回 (s1_logits, x) → x 是隐藏表征)
- 跑全年 backtest 命令见 fullyear_backtest.log 头部
