# [RFC]: vLLM-Omni Ascend 310P Optimization Roadmap (2026 Q4 – 2027 Q1)

> **状态：本地草稿，尚未提交。**
> 目标仓库：`vllm-project/vllm-omni`
> 提交模板：`[RFC]` issue + [官方设计文档模板](https://docs.google.com/document/d/1jcgR3cDaUQH3VczD4ZcKaJAoYWHjCmnYzHkCNyz-9fk/edit?usp=sharing) + ≥1 周反馈期
> 建议标签：`RFC`、`NPU`、`Hardware Plugin`、`roadmap`
> 关联：Q4 roadmap [#8264](https://github.com/vllm-project/vllm-omni/issues/8264)、310P/A5 CI [#6806](https://github.com/vllm-project/vllm-omni/issues/6806)、MRv2 NPU [#9446](https://github.com/vllm-project/vllm-omni/issues/9446)、310P 安装版本 [#5251](https://github.com/vllm-project/vllm-omni/issues/5251)
> 本地依据：[300I-DUO-适配与优化分析.md](300I-DUO-适配与优化分析.md) §A.4-§A.8、[vLLM-Omni-架构与技术报告.md](vLLM-Omni-架构与技术报告.md) 第 II 部分 §13
> PR 拆分：[300I-DUO-30PR计划.md](300I-DUO-30PR计划.md)（30 个可独立提交、独立验证的 PR）

---

## Motivation

Atlas 300I DUO（Ascend 310P3）是成本敏感的边端推理目标：单 chip 48 GB、FP16 约 24 TFLOPS、实测带宽约 185 GB/s、无 HCCS、无 BF16、无 Triton/Ascend C 的常用高性能路径。当前 vLLM-Omni 的 310P 支持以 Qwen3-TTS 为中心，已经跨过“功能成立”门槛，但还没有形成可发布、可回归、可度量的产品能力：

- 310P 只有 CPU mock 的 patch 测试，没有真机 E2E/accuracy/perf CI（[#6806](https://github.com/vllm-project/vllm-omni/issues/6806) 仍 open）；
- 没有 310P 性能基线（RTF、首包、tok/s、s/image、显存峰值）；
- 没有 310P 量化路径（W8A8/INT8 KV 未接入 omni 模型）；
- 扩散模型没有 310P 适配，DiT attention 回退到 `TORCH_SDPA`，VAE/DiT 算子未验证；
- 没有多 chip/TP 验证，也没有 V2 runner（[#9446](https://github.com/vllm-project/vllm-omni/issues/9446) 尚在推进）；
- 310P 的 ATB/NNAL 算子缺口（`ReshapeAndCache`、`MoeGatingTopKSoftmax`、paged attention/splitfuse 等）目前以 torch fallback 形式存在，性能和归属都未定。

本 RFC 定义一个**有边界、可拆分、可验收**的 310P 优化 roadmap，把“能跑”推进到“可发布、可回归、可度量”，并明确哪些工作属于 vLLM-Omni、哪些应上游到 vLLM-Ascend。

---

## Proposed Change

### 0. 当前状态与基线

**已有能力（已验证或已合入）**

| 能力 | 状态 | 参考 |
| --- | --- | --- |
| 310P 平台检测/worker/runner 路由 | 已合入 | #4283、#4841、#4852、#9246 |
| Qwen3-TTS Talker/CodePredictor/Code2Wav 310P patch | 已合入 | #4283、#4841 |
| FP16 强制、JIT 关闭、310P sampler、参考音频/Mel 下沉 CPU | 已合入 | `vllm_omni/platforms/npu/_310p/` |
| CPU 侧 310P patch 契约测试 | 已合入 | `tests/platforms/npu/test_310p_patches.py` |
| 310P/A5 CI RFC | open | #6806 |

**主要缺口**

| 缺口 | 影响 |
| --- | --- |
| 无 310P 真机 E2E CI | 无法阻止回归，发布无 gate |
| 无 accuracy/perf 基线 | 无法判断优化是否有效 |
| 无 W8A8/INT8 KV | 带宽瓶颈下吞吐和显存收益未兑现 |
| 扩散零适配 | 图像/视频能力不可用 |
| 无多 chip/TP 验证 | 双 chip 只能做 stage 拆分，不能做 TP |
| 无 V2 runner | MRv2 特性在 310P 不可用 |
| ATB/NNAL 算子缺口 | torch fallback 慢，且 patch 归属 vllm-omni/vllm-ascend 未定 |

**版本基线（2026-11）**

| 组件 | 验证值 | 备注 |
| --- | --- | --- |
| 硬件 | Atlas 300I DUO，48 GB/chip，无 HCCS | 实测 3 卡 × 2 chip = 6 device |
| CANN | 8.3.RC1 / 9.0.1 | 两套记录并存 |
| torch / torch_npu | 2.9 / 2.10 | 需锁定与 CANN 匹配 |
| vLLM | 0.30.0（310P 验证）/ 0.33.0（omni main） | main 与 310P wheel 存在版本差 |
| vLLM-Ascend | 0.30.0（310P wheel）/ 0.32.0rc1（最新） | 310P wheel 可用性是关键依赖 |
| vLLM-Omni | v0.30.0 tree / main | 本 RFC 以 main 为最终目标，允许 release/v0.30.0 过渡验证 |

---

### 1. Goals

- **G1（P0）**：建立 310P 真机 E2E + accuracy + perf 的最小 CI gate。
- **G2（P1）**：Qwen3-TTS 0.6B/1.7B 达到可交付性能：1.7B RTF ≤ 0.3、首包 ≤ 300 ms；0.6B 支持高并发。
- **G3（P1）**：TTS 关键路径 W8A8 量化落地，吞吐约 2×、权重减半。
- **G4（P2）**：形成 310P TTS 模型矩阵（CosyVoice3 0.5B、Kokoro-82M、MOSS/IndexTTS/Fish 中选 1–2 个）。
- **G5（P3）**：Qwen2.5-Omni-3B 在 310P 上完成语音问答/语音输出的最小闭环。
- **G6（P4）**：Z-Image / FLUX.2-klein 4B 在 512–768 分辨率完成图像生成闭环。
- **G7（持续）**：每个 release 发布 310P validated model list、recipe、support matrix 与版本矩阵。

### 2. Non-goals

- 不在 310P 上支持 ≥20B 模型：Qwen3-Omni 30B-A3B、Qwen-Image 20B、HunyuanImage3 80B、MiniMax-H3、LTX-2.5、大视频。
- 不把 310P 当作 CUDA 性能对等目标；以“单位成本可用”为目标。
- 不做 310P 训练/RL、全双工 8B 级模型、VLA 大规模落地。
- 不在本 RFC 内解决 vLLM-Ascend 的所有 310P 算子缺口；只定义归属与验收。

---

### 3. 模型覆盖矩阵

| 优先级 | 模型 | 量级 | 目标 | 主要工作 |
| --- | --- | --- | --- | --- |
| **P0** | Qwen3-TTS 0.6B/1.7B | 0.6–1.7B | 生产可用 | E2E CI、图安全采样、参考音频/Mel NPU、W8A8、双 chip stage 拆分 |
| **P1** | CosyVoice3 0.5B | 0.5B | 高并发语音 | 移植 `cosyvoice3_graph.py` 到 310P；FP16；FIA mask；HiFT 图 |
| **P1** | Kokoro-82M | 82M | 高并发 TTS 样板 | 算子核查（LSTM/iSTFT）、图捕获、批处理 |
| **P2** | MOSS-TTS-Nano / IndexTTS-2 / Fish Speech S2（选 1–2） | 小–中 | 复用 codec 图设施 | CodePredictor/Code2Wav 图复用 |
| **P3** | Qwen2.5-Omni-3B | 3B | 边缘多模态 | FP16、音频/视觉编码器算子、stage 拆分、流式 |
| **P4** | Z-Image / FLUX.2-klein 4B / SDXL | 4–6B | 512–768 文生图 | 310P DiT attention、VAE Conv FRACTAL_Z、ACLGraph、FP16 精度 |
| **Watch** | MiniCPM-o 4.5 | ~8B | 全双工 | 等 3B Omni 跑通后评估 |
| **Watch** | Wan2.2-TI2V-5B / SANA-Video 2B | 2–5B | 480p 实验 | 仅低帧率实验 |
| **Watch** | pi0 / GR00T N1.7 3B | 3B | 边缘策略 | 场景明确后再做 |
| **Not recommended** | Qwen3-Omni 30B-A3B、Qwen-Image 20B、HunyuanImage3 80B、MiniMax-H3、LTX-2.5 | ≥20B | — | 算力/内存/带宽不匹配 |

> 选型依据与量级测算见本地报告 [300I-DUO-适配与优化分析.md](300I-DUO-适配与优化分析.md) §A.4-§A.5。

---

### 4. 工作流（Workstreams）

> 每个工作流对应到 [300I-DUO-30PR计划.md](300I-DUO-30PR计划.md) 中的具体 PR；括号内为 PR 编号。

#### W1 · CI 与基线（P0，PR-01 – PR-06）

- [ ] **PR-01** 在 #6806 基础上落地 310P ready job：`pytest -m 'core_model and npu and 310P'`，`mirror_hardwares: 310p_npu_1`。
- [ ] **PR-02** Qwen3-TTS 0.6B/1.7B 真机 smoke：启动、单请求、输出非空、退出码。
- [ ] **PR-03** accuracy gate：WER/CER（ASR/TTS 文本）、SIM（音色）。
- [ ] **PR-04** perf 基线：RTF、首包、tok/s、显存峰值；每个 device 一条。
- [ ] **PR-05** 310P 版本矩阵文档：CANN / torch_npu / vLLM / vLLM-Ascend / vLLM-Omni。
- [ ] **PR-06** `is_310p` 检测回归测试。

**验收**：310P ready job 在 PR 上稳定绿色；基线报告随 release 更新。

#### W2 · TTS 正确性与性能（P1a/P1b/P2，PR-07 – PR-22）

- [ ] **PR-07 – PR-13** 运行时正确性：能力探测、fallback 显式配置、ReshapeAndCache/MoE 向量化、MoE router、kwargs 过滤、attention 选择与指标。
- [ ] **PR-14 – PR-15** **图安全采样**：预生成 uniform，图内确定性 top-k + inverse-CDF/Gumbel，把 Talker-MTP 从 eager 变 ACLGraph；补单测。
- [ ] **PR-16 – PR-17** **参考音频/Mel NPU 化**：按 1s/3s/5s/10s 分桶 padding，Mimi encoder 回 NPU；mel 预计算缓存。
- [ ] **PR-18 – PR-19** **W8A8**：Talker/Code2Wav 线性层量化；TTS 质量校准与 gate。
- [ ] **PR-20** **双 chip stage 拆分**：Talker chip0 / Code2Wav chip1，stage 间只传 codec chunk。
- [ ] **PR-21 – PR-22** **批处理 + bucket 图 / 前缀缓存**：扩 CodePredictor/Code2Wav batch bucket；固定 prompt/音色描述开启 prefix cache。

**验收**：1.7B RTF ≤ 0.3、首包 ≤ 300 ms；0.6B 在目标并发下 RTF < 1；连续 1 小时无 OOM/图捕获失败。

#### W3 · TTS 模型矩阵（P2，PR-23 – PR-25）

- [ ] **PR-23** CosyVoice3 0.5B：Flow Euler + HiFT 精确图移植到 310P。
- [ ] **PR-24** Kokoro-82M：算子核查、图捕获、批处理，做高并发样板。
- [ ] **PR-25** MOSS-TTS-Nano：复用 CodePredictor/Code2Wav 图设施。
- [ ] 后续 wave：IndexTTS-2 / Fish Speech S2。

**验收**：每个模型有 recipe、E2E CI、RTF/首包基线。

#### W4 · 量化（P1，PR-18 – PR-19）

- [ ] **PR-18** W8A8 Linear 接入 vLLM-Ascend 310P 量化路径。
- [ ] **PR-19** 量化后 accuracy：TTS WER/SIM。
- [ ] 后续 wave：KV cache INT8 评估（先测量收益，再决定是否落地）。
- [ ] 文档：量化配置、校准数据、已知精度损失。

#### W5 · 小 Omni（P3，PR-26 – PR-27）

- [ ] **PR-26** Qwen2.5-Omni-3B：FP16、音频/视觉编码器算子验证。
- [ ] **PR-27** Talker + Code2Wav 复用 Qwen3-TTS 的 code2wav 图与 chunk 流式；stage 拆分与流式验证。
- [ ] 先做 ASR/语音问答，再做语音输出。

**验收**：单 chip 3B、短回复 ≥15 tok/s、语音问答端到端可接受。

#### W6 · 扩散/图像（P4，PR-28 – PR-29）

- [ ] **PR-28** 310P DiT attention 后端：SDPA 或 aclnn fused attention；VAE Conv FRACTAL_Z、ACLGraph、FP16 数值验证。
- [ ] **PR-29** Z-Image / FLUX.2-klein 4B @512–768。
- [ ] 后续 wave：SDXL 对照、Cache-DiT/TeaCache 减少 NFE。

**验收**：512² × 8 步 ≤ 5 s、768² ≤ 10 s；CLIP/FID 与 910B 基线在容差内。

#### W7 · 文档、recipe 与发布（PR-05、PR-30）

- [ ] **PR-05** 版本矩阵与安装文档（对齐 #5251）。
- [ ] **PR-30** 310P support matrix：模型 × 状态（Experimental/Supported/Unmaintained）。
- [ ] **PR-30** 每个 validated 模型一份 recipe + 可复现命令。
- [ ] **PR-30** 每个 release 发布 validated model list 与 release checklist。

---

### 5. 里程碑

| 阶段 | 时间 | PR | 目标 | 交付物 |
| --- | --- | --- | --- | --- |
| **P0 基线** | 2026-11 – 2026-12 | PR-01 – PR-06 | 310P 真机 CI + Qwen3-TTS E2E + 基线 | ready job、accuracy/perf 报告、版本矩阵 |
| **P1a 运行时** | 2026-12 – 2027-01 | PR-07 – PR-13 | 能力探测、fallback 显式化、算子向量化、kwargs/attention | 可诊断、可度量的运行时 |
| **P1b TTS 性能** | 2026-12 – 2027-01 | PR-14 – PR-20 | 图安全采样、参考音频/Mel NPU、W8A8、双 chip stage | 1.7B RTF ≤ 0.3；0.6B 高并发 |
| **P2 TTS 矩阵** | 2027-01 – 2027-02 | PR-21 – PR-25 | batch/prefix、CosyVoice3 0.5B、Kokoro-82M、MOSS-TTS-Nano | 多模型 recipe + CI |
| **P3 小 Omni** | 2027-02 – 2027-03 | PR-26 – PR-27 | Qwen2.5-Omni-3B 语音问答/语音输出 | 单 chip 3B、流式 |
| **P4 图像** | 2027-03 – 2027-04 | PR-28 – PR-29 | Z-Image/FLUX.2-klein 4B @512–768 | 310P DiT 后端、s/image 基线 |
| **Release** | 2027-04 | PR-30 | validated model list、recipes、release checklist | 发布文档 |
| **P5 观望** | 2027-04+ | 后续 wave | MiniCPM-o 4.5 / 小视频 / VLA | 仅在 P3 证明 3B Omni 可行后启动 |

---

### 6. PR 交付计划

完整的 30 个 PR（标题、仓库归属、文件范围、依赖、验证、规模、风险）见 **[300I-DUO-30PR计划.md](300I-DUO-30PR计划.md)**。本节只保留阶段摘要：

| 阶段 | PR | 数量 | 重点 |
| --- | --- | --- | --- |
| P0 | PR-01 – PR-06 | 6 | CI、accuracy/perf 基线、版本矩阵、`is_310p` 回归 |
| P1a | PR-07 – PR-13 | 7 | 能力探测、fallback 显式化、算子向量化、kwargs/attention |
| P1b | PR-14 – PR-20 | 7 | 图安全采样、参考音频/Mel、W8A8、双 chip stage |
| P2 | PR-21 – PR-25 | 5 | batch/prefix、CosyVoice3、Kokoro、MOSS-TTS-Nano |
| P3 | PR-26 – PR-27 | 2 | Qwen2.5-Omni-3B 编码器 + talker/流式 |
| P4 | PR-28 – PR-29 | 2 | DiT attention/VAE、Z-Image/FLUX.2-klein |
| Release | PR-30 | 1 | validated list + recipes + release checklist |

每个 PR 保持可独立 review、可独立测试；目标 300–800 行（不含测试/配置/文档），超过 1,000 行需拆分。所有 PR 必须包含测试、配置与文档，符合 DCO、AI 使用披露和 `precheck-pr` 要求。

> 310P 的 ATB/NNAL 算子 fallback（`ReshapeAndCache`、`MoeGatingTopKSoftmax`、paged attention/splitfuse）优先上游到 `vllm-ascend`；vLLM-Omni 侧只保留平台接线与模型级 patch。该归属需在 RFC 反馈期内确认。

#### 6.1 上游归属与可合入性（结论）

**不能把 30 个 PR 的代码全部合入 vllm-omni。** 推荐按仓库拆分：

| 类别 | PR | 数量 | 目标仓库 |
| --- | --- | --- | --- |
| A1 · omni 直接合入 | PR-01 – PR-06、PR-12、PR-15、PR-17、PR-19 – PR-22、PR-30 | 14 | vllm-omni |
| A2 · omni 有条件合入 | PR-07、PR-14、PR-16、PR-23 – PR-27、PR-29 | 9 | vllm-omni（依赖 vllm-ascend） |
| B · 仅 vllm-ascend | PR-09、PR-10、PR-11 | 3 | vllm-ascend |
| C · 拆分 | PR-08、PR-13、PR-18、PR-28 | 4 | vllm-ascend + vllm-omni |
| **合计** | | **30** | |

**不能全部进 omni 的原因**：

1. 310P 的 ATB/NNAL 算子、attention 后端、量化、VAE/DiT 内核属于 vllm-ascend；长期放在 `vllm_omni/platforms/npu/_310p/` 会与上游内部实现耦合。
2. 纯文本 Qwen3-MoE 单 stage pipeline 不在 vllm-omni 已列支持范围，需先确认 scope。
3. vllm-omni main 对齐 vLLM 0.33，而 310P 的 vllm-ascend wheel 目前是 0.30，main 上无法完整验证。
4. 310P 真机 CI 依赖 #6806；没有 gate 的硬件 PR 很难被接受。
5. 模型专用 `examples/**/*.py` 是 blocking；必须走共享入口 + recipe。
6. Qwen3-ASR 在 vllm-ascend v0.30.0 已标记 Unmaintained，不能作为 omni 新模型贡献。

**不应提交到上游的本地代码**：`tools/310p_compat/sitecustomize.py`（0.30 import cycle）、纯文本 Qwen3-MoE 注册、模型专用示例、Qwen3-ASR 310P、`reports/**` 本地分析、0.30 版本 workaround。

**合入前置条件**：

- [ ] RFC 通过（#8264 / 本 roadmap）。
- [ ] 310P CI 队列与机器可用（#6806）。
- [ ] 目标 vLLM 版本有 310P 的 vllm-ascend wheel。
- [ ] NPU owner 与 model owner 同意 scope/归属。
- [ ] 每个 PR 有 310P 真机 accuracy/perf 证据。
- [ ] 文档/recipe/support matrix 同步；DCO、AI 披露、precheck-pr 通过。

> 详细分类、每个 PR 的归属和风险见 [300I-DUO-30PR计划.md](300I-DUO-30PR计划.md) §7。

---

### 7. 验证与指标

**CI**

- PR gate：`pytest -m 'core_model and npu and 310P'`，Buildkite `310p_npu_1`。
- Nightly：Qwen3-TTS 0.6B/1.7B accuracy + perf；后续每接入一个模型加一条。
- 稳定性：连续 1 小时高并发无 OOM、无图捕获失败、无 worker 崩溃。

**Accuracy**

- TTS：WER/CER、SIM；与 910B BF16/FP16 基线比较。
- 图像：CLIP/FID；与 910B 基线比较。
- Omni：语音问答关键词/语义相似度；短回复时延。

**Performance**

| 指标 | 目标 |
| --- | --- |
| Qwen3-TTS 1.7B RTF | ≤ 0.30 |
| Qwen3-TTS 首包 | ≤ 300 ms |
| Qwen3-TTS 0.6B 并发 | 目标并发下 RTF < 1 |
| Qwen2.5-Omni-3B | ≥ 15 tok/s（短回复） |
| 图像 512² × 8 步 | ≤ 5 s |
| 图像 768² × 8 步 | ≤ 10 s |
| 显存峰值 | 记录并随 release 对比 |

---

### 8. 依赖与风险

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| vLLM-Ascend 无 vLLM 0.33 的 310P wheel | main 无法完整验证 | 先以 release/v0.30.0 验证，推动 vllm-ascend 发布 0.33 310P wheel |
| CANN/torch_npu 版本漂移 | 算子/图行为变化 | 版本矩阵 + CI 锁定 |
| 310P 算子缺口归属未定 | patch 长期留在 omni，难维护 | RFC 明确：优先上游 vllm-ascend |
| 无 HCCS、双 chip 只能 PCIe | TP 通信昂贵 | 采用 stage 拆分而非 TP |
| FP16 精度损失 | TTS/图像质量下降 | 单独 accuracy baseline + 容差 |
| 310P CI 硬件不可用 | 无法建立 gate | 先复用 #6806 队列；必要时 nightly 代替 ready |
| Qwen3-ASR 在 vllm-ascend v0.30.0 被标记 Unmaintained | ASR 路线不可用 | 本 roadmap 不含 Qwen3-ASR；如需，先在 vllm-ascend 恢复支持 |

---

### 9. Open Questions

1. **目标分支**：310P 工作最终以 `main` 为准，还是先以 `release/v0.30.0` 交付？
2. **归属**：310P 的 ATB/NNAL 算子 fallback 应上游到 `vllm-ascend`，还是允许长期留在 `vllm_omni/platforms/npu/_310p/`？
3. **P1 模型**：CosyVoice3 0.5B 与 Kokoro-82M 哪个优先？是否需要先做高并发 TTS 样板？
4. **量化**：W8A8 是 Q4 必须项，还是 Q1 目标？
5. **CI 硬件**：#6806 的 310P 队列由谁维护？是否可提供 nightly 机器？
6. **发布状态**：310P 在 support matrix 中应标记 Experimental 还是 Supported？按模型分别标记是否更合适？
7. **MRv2**：310P 是否跟随 #9446 的 MRv2 计划，还是长期停留在 V1 runner？

---

## Feedback Period

建议 **2026-11-13 – 2026-11-20**（至少 1 周）。反馈期内请在本 issue 下讨论；需要设计文档的意见请直接评论在 RFC 设计文档上。

## CC List

@gcanlin @tjtanaa @xuechendi @hsliuustc0106 @yenuo26 @ywang96

## Any Other Things

- 本 RFC 是 310P 的总览与排序，不替代具体 PR 的设计讨论；每个 PR 仍需独立说明动机、测试和性能/精度证据。
- 与本 RFC 相关的已有工作：#4283、#4841、#4852、#9246、#6685、#6806、#9446、#5251。
- 若维护者认为 310P 应继续以“实验性”维护，而不是进入正式 roadmap，请在反馈期内明确；本 RFC 可降级为 tracking issue。

---

## 附：提交到社区的步骤（本地操作说明）

1. **先搜索**：确认 #6806、#8264、#9446、#5251 及 310P 相关 PR 没有重复 roadmap。
2. **开 RFC issue**：使用 `.github/ISSUE_TEMPLATE/750-RFC.yml`，标题：
   ```text
   [RFC]: vLLM-Omni Ascend 310P Optimization Roadmap (2026 Q4 – 2027 Q1)
   ```
   将本文的 `Motivation` / `Proposed Change` / `Feedback Period` / `CC List` 粘贴到对应字段。
3. **附设计文档**：按模板提供的 Google Doc 格式补充架构图、阶段依赖、PR 拆分与验收指标。
4. **Slack 同步**：在 `#sig-omni` 发一条短消息，@gcanlin、@tjtanaa、@xuechendi、@hsliuustc0106、@yenuo26，说明 310P roadmap 已开 RFC。
5. **反馈期**：至少 1 周；根据反馈修订，必要时拆成“已同意 / 待讨论 / 不在范围”三张表。
6. **通过后建 tracking issue**：参考 #6494 的形式，逐项列出 PR、owner、状态、依赖，每 2–3 天更新一次。
7. **提 PR**：遵守标题前缀、DCO `Signed-off-by`、AI 使用披露、`precheck-pr`、5 个 open PR 限制；每个 PR 附测试/性能/精度证据。

## 附：本地依据

| 内容 | 位置 |
| --- | --- |
| 310P 硬件画像与能力边界 | [300I-DUO-适配与优化分析.md](300I-DUO-适配与优化分析.md) §A.1-§A.2 |
| 当前适配清单与测试覆盖 | [300I-DUO-适配与优化分析.md](300I-DUO-适配与优化分析.md) §A.3 |
| 算法量级与模型选型 | [300I-DUO-适配与优化分析.md](300I-DUO-适配与优化分析.md) §A.4-§A.5 |
| 特性/优化清单与路线图 | [300I-DUO-适配与优化分析.md](300I-DUO-适配与优化分析.md) §A.6-§A.7 |
| 风险与验证清单 | [300I-DUO-适配与优化分析.md](300I-DUO-适配与优化分析.md) §A.8 |
| 310P 变体（Qwen3-TTS 视角） | [vLLM-Omni-架构与技术报告.md](vLLM-Omni-架构与技术报告.md) 第 II 部分 §13 |
| 平台层与 NPU 钩子 | [vLLM-Omni-架构与技术报告.md](vLLM-Omni-架构与技术报告.md) 第 I 部分 §7 |
| 30 个 PR 的拆分、依赖与验证 | [300I-DUO-30PR计划.md](300I-DUO-30PR计划.md) |


