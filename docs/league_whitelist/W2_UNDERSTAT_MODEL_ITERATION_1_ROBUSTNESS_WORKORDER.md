# Codex 工单 · Understat 模型迭代 1 · 稳健性验证

面向:Codex 执行 + reviewer 验收。可直接下发。

## 背景(冷读者必读)

模型迭代 1(PR #193,分支 `feat/w2-understat-model-iteration-1`)已把模型从手设先验(`strategy/calibration.py`,`CALIBRATION_STATUS=BASELINE_PRIOR`)改为**离线拟合 lambda + temperature 概率校准**,在五大联赛 Understat 免费 xG 上得到:

- 样本:fixtures 1755 / xG matched 1750 / eligible walk-forward 1510;train/val = 1057/453。
- **validation(fitted+temperature):log_loss `0.9699`、Brier `0.5777`、RPS `0.2022`、ECE `0.0411`。**
- vs baseline-prior:log_loss `-0.0354`,ECE `-0.0730`。

方法学已核实干净:切分是时间序列(`free_tier_2024.py` 的 `chronological_prefix_train_suffix_validation`,按 kickoff 排序、前 train 后 validation);lambda(`_fit_offline_lambda_model`)与 temperature(`_fit_temperature`)**只在 train 上拟合**再套用到 validation;无泄漏边界已写死。

**问题:这是单折结果、逼近市场级(~0.96)。一个这么好的单折结果,必须先证它稳健、非过拟合、非单折侥幸,才能往上建或据此决定付费。**

## 目标

确认 validation log_loss `0.9699` **稳定、非过拟合、非单折侥幸**。全程 `$0`、仅 Understat、零 API-Football。

## 任务(按顺序)

1. **训练-验证 gap(过拟合检查)**
   - 并列报出 **train** 与 **validation** 的 log_loss / Brier / RPS / ECE。
   - 判据:train ≈ val(都 ~0.97)= 未过拟合;train ≪ val = 过拟合 → 加正则 / 减参数后重报。

2. **跨季外样本(泛化检查)**
   - Understat 免费提供多季历史。做 **fit 2023 → validate 2024**,以及 **fit 2024 → validate 2023**。
   - 判据:两个方向 log_loss 都能复现 ~0.97 量级,才算跨季稳。

3. **多折 walk-forward(方差检查)**
   - 不止一个 70/30 切点;做扩窗多折(rolling origin,如按月或按轮次推进 origin)。
   - 报每折 log_loss/Brier/ECE + 均值/方差。方差小才可信。

4. **对照基线(相对进步检查)**
   - 每折都对比 **baseline-prior** 与一个**简单参照**(`src/w2/models/dixon_coles.py` 已有 Dixon-Coles,或 Elo-only)。
   - 判据:拟合模型需在每折**稳定赢过**这两者,才算真进步而非噪声。

## 硬约束

- 严格时间边界:任何折的系数与 temperature **只用该折验证边界之前**的比赛拟合;as-of 滚动特征同边界。零泄漏。
- 确定性可复现(固定 seed + 固定选样)。
- `$0`:仅用已缓存 / Understat 公开数据,**零 API-Football provider call**,不读 provider key。
- 不 enable、不部署、不写生产 DB、不改 canonical `season=2026`、online lambda-fit 门保持关闭(纯离线)。
- 脱敏产出,不提交 raw payload / header / key。
- 在 #193 分支上做,保持 **Draft**,不转 Ready、不 merge。

## 完成定义

产出三张表 + 结论:
1. train vs validation gap 表;
2. 跨季(2023↔2024 双向)表;
3. 多折 walk-forward 表(每折 + 均值/方差)+ 对 baseline-prior / Dixon-Coles 的对照。

一句话结论明确:**`0.9699` 是稳健的,还是单折侥幸。**

## 若结论为"稳健"

则:模型架构方向确认成立;记录为可进入 challenger 设计的证据;八月开 Pro 后,ANALYSIS_PICK 将建立在已验证的拟合模型上,而非先验。仍不 enable、不部署,等 reviewer 决策。

## 若结论为"单折侥幸 / 过拟合"

则:回退到"改特征/正则"再迭代,不据此做任何付费或上线决定。
