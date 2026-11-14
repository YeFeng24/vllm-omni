# [RFC] vLLM-Omni Ascend 300I Duo(310p) 优化roadmap（2026 Q4）

## 硬件基线

**表 1. Atlas 300I Duo 与 Atlas 800I A2 平台规格对比**

| 属性 | Atlas 300I Duo 整卡（2×310P3） | 单芯（每颗 310P3） | Atlas 800I A2（每模组） | 对本路线图的影响 |
| --- | --- | --- | --- | --- |
| AI 算力 FP16 | 140 TFLOPS | 70 TFLOPS（本机实测 Cube 峰值 69.5 TFLOPS） | 280 TFLOPS | 单芯约为 1/4，整卡约 1/2 |
| AI 算力 INT8 | 280 TOPS | 140 TOPS | 560 TOPS | 同样为 1/4 与 1/2 |
| 内存 | LPDDR4X 96 GB 或 48 GB，支持 ECC | 48 GB 或 24 GB | HBM 64 GB（可选 32 GB），支持 ECC | 单芯容量与参照模组相当，但带宽差约 8 倍；96 GB 整卡正好容纳两芯分片 |
| 内存带宽 | 408 GB/s（本机实测约 185 GB/s/芯） | 204 GB/s | 1.6 TB/s | decode 受带宽约束，必须靠批处理与多芯放置 |
| BF16 | 不支持 | 不支持 | 支持 | 所有模型以 FP16 为基线 |
| 算力 / 显存比 | 1.46 TFLOPS per GB（140/96） | 1.46 TFLOPS per GB（70/48） | 4.38 TFLOPS per GB（280/64） | 约为参照的 1/3：显存相对算力非常富裕，这是 310P 的核心特征 |
| 算力 / 带宽比 | 343 FLOP/byte（140/408） | 343 FLOP/byte（70/204） | 175 FLOP/byte（280/1600） | 打满算力所需的算术强度约为参照的 2 倍，实际更易落在带宽受限区 |
| 互联与拓扑 | 卡内双芯互联（实测有效带宽约 60 GB/s）；卡间 PCIe 4.0 x16（实测约 16 GB/s） | — | 支持 NPU 全互联，整机互联带宽 392 GB/s | 310P 没有 HCCS 级互联，跨芯并行代价高，优先阶段拆分而非 TP |
| 功耗 / 形态 | 150 W；单槽全高全长（10.5 英寸），PCIe 4.0 x16 | — | 整机 4U、8 模组、4×2.6 kW 电源；单模组功耗未单列 | 310P 单卡 150 W，功耗与部署密度预算明显更宽裕；每瓦吞吐按实测吞吐 ÷ 功耗核算 |

> 数据来源：[Atlas 300I Duo 推理卡](https://e.huawei.com/cn/products/computing/ascend/atlas-300i-duo) · [Atlas 800I A2](https://e.huawei.com/cn/products/computing/ascend/atlas-800i-a2) · [Atlas 300I A2](https://e.huawei.com/cn/products/computing/ascend/atlas-300i-a2)

### 硬件特殊性：算力偏弱、显存偏大

一句话概括：**每单位算力对应的显存非常富裕，每单位显存对应的带宽严重不足。** 这决定了 300I Duo 的定位与优化重点，三条推论如下。

- **权重放得下，就不必分片或换出。** 单芯 48 GB 足以让 10B 以下的 FP16 模型整块常驻；96 GB 双芯可容纳约 19B 的 Boogu-Image 执行图与 30B-A3B 的 MoE 总权重。显存容量是这张卡最有价值、也最难被同价位替代的资源，因此"能不能整块装下"应当作为模型选型的第一判据。
- **算力不够，就选"单步计算少、常驻权重多"的负载。** MoE（总参 30B / 激活 3B）、扩散模型的逐步去噪、LLM decode 阶段的单 token 生成，都属于单步计算量小但需要大权重常驻的形态，与这组硬件特性正好互补；prefill 主导、长视频生成、算力密集的视觉 encoder 堆叠则相反，不是它擅长的场景。
- **真正的瓶颈是 204 GB/s 带宽，吞吐要靠 batch 而非算子峰值。** 70 TFLOPS 配 204 GB/s，打满算力需要的算术强度约 343 FLOP/byte，是参照平台（175 FLOP/byte）的两倍，绝大多数算子在 310P 上都会先撞带宽。因此优化手段的优先级是：并发批处理（摊薄权重读取）> 减少数据搬运（NPU 常驻预处理、融合算子、避免 D2H/H2D）> 图执行开销（graph capture）> 算子微观效率。
- **显存大 ⇒ 可以开大 KV 池与长上下文。** 同级算力更强但显存更小的卡做不了这件事；对检索、rerank、长音频转写、长对话这类"上下文长、单步计算轻"的负载尤其合适。

---

## 背景

**定位：显存型推理档位，与 Atlas 800I A2 分工而非替代。** 上一节已说明算力与显存的失配——算力约为参照单模组的 1/4，显存多 50%。因此 300I Duo 的价值不在单请求跑得快，而在同等成本下能装下更大的模型、开更大的 KV 池、承载更高的并发。与之对应的甜点区有三类：10B 以下的稠密模型（语音、VLA、rerank、小型扩散），单芯 48 GB 即可整块常驻；"总参大、激活小"的 MoE（如 Qwen3-Omni-30B-A3B，总参 30B / 激活 3B），权重吃显存而单步计算轻，96 GB 双芯正好容纳；decode 主导的长上下文负载（长音频转写、长对话、检索），KV 池越大、并发越高，显存优势越明显。prefill 主导的大模型、长视频生成、精度基准与回退方案，仍由 Atlas 800I A2 承担。

**优化目标与手段顺序。** 目标是服务级吞吐与单位成本，不是单请求时延。手段顺序由 343 FLOP/byte 的算力/带宽比决定：并发批处理摊薄权重读取 > 减少数据搬运 > 压低图执行开销 > 算子微观效率。这些手段都不改变模型语义；单请求时延落后属于预期，只要吞吐与单位成本占优就不必追平。

**当前状态与本文范围。** vLLM-Omni 的 310P 支持目前只覆盖 Qwen3-TTS：路径可用，有 CPU mock 契约测试与真机接线测试，但不构成产品能力——没有多芯部署路径，语音识别、VLA、图像、视频、检索、omni 全部空白。本 RFC 给出一条可评审的补齐路线：按"能否整块装下、单步是否轻"排序的模型矩阵、逐模型的适配与优化 PR、两个超出单芯模型的"卡内双芯 + 跨卡 PP"部署方案，以及基于数据集的精度与性能证据。

---

## 总体方案

### 1. 设计原则

| 原则 | 约定 |
| --- | --- |
| **显存优先（Memory-First）** | 选型与优化都以显存容量为第一判据：能整块常驻的模型就把 batch 与 KV 池开到带宽与显存允许的上限；装不下的才切分。显存是这张卡最不可替代的资源。 |
| **单卡双芯部署：CP/SP/TP 走卡内，PP 走卡间** | 部署的基本单位是一张 300I Duo（两颗 310P3，合计 96 GB）。需要并行时，CP/SP/TP 这类要频繁交换激活或序列分块的切分放在卡内双芯上，靠卡内互联（实测约 60 GB/s）承担；卡与卡之间只有 PCIe 4.0 x16（实测约 16 GB/s），只承载 PP 这种通信仅发生在阶段边界的切分。单卡双芯仍放不下时，再向上扩展为多卡 PP。原则是：通信越密集的并行，越要留在卡内。 |
| **FP16 优先** | 310P 无 BF16，每个模型都必须有一条正确的 FP16 路径。量化不是前提，但也不排除：FP16 下达不到吞吐目标时，可以评估 W8A8 作为备选。 |
| **复用 Atlas 800I A2 的 NPU 路径** | 与 Atlas 800I A2 共享流水线、算子和图工具，310P 特化逻辑收在 `is_310p()` 与平台钩子之后（见 [#6691](https://github.com/vllm-project/vllm-omni/issues/6691)）。算子与 attention backend 归 vLLM-Ascend，模型与流水线归 vLLM-Omni。 |
| **吞吐优先于时延对齐** | 优化批处理、graph capture、prefix cache 与阶段重叠。单流时延因模型而异，不要求与 Atlas 800I A2 对齐。 |
| **每个模型保证功能与性能** | 每个模型必须同时交付两点：功能可用（E2E 跑通、数据集精度达标），以及在 300I Duo 上做到硬件允许的最优性能（吞吐贴近显存与带宽上限，而不是"能跑就行"）。两者都要附 recipe 与数据集数字。会改变精度目标或失败模式的模式（双工 vs 轮次制、纯文本 vs 视频输入、理解 vs 语音输出）各拆独立 PR。 |

### 2. 现状

**已可用**

- 310P 检测、worker 与 model-runner 路由：[#4283](https://github.com/vllm-project/vllm-omni/pull/4283)、[#4841](https://github.com/vllm-project/vllm-omni/pull/4841)、[#9246](https://github.com/vllm-project/vllm-omni/pull/9246)。
- Qwen3-TTS 的 talker、code predictor、Code2Wav 310P 路径：[#4283](https://github.com/vllm-project/vllm-omni/pull/4283)、[#4841](https://github.com/vllm-project/vllm-omni/pull/4841)。
- FP16 强制、JIT 关闭、310P sampler、CPU 侧参考音频与 mel：`vllm_omni/platforms/npu/_310p/`。
- CPU mock 契约测试与真机接线测试：`tests/platforms/npu/test_310p_patches.py`、`tests/platforms/npu/test_310p_real_device.py`。
- vLLM-Ascend 的 310P wheel 与 SIT 配置：`Dockerfile.310p`、`tests/e2e/*_310p`。

**进行中**

Model Runner V2 上 Ascend NPU（[#9446](https://github.com/vllm-project/vllm-omni/issues/9446)）、in-tree 平台归属（[#6691](https://github.com/vllm-project/vllm-omni/issues/6691)）、Boogu-Image Ascend BF16 支持（[#6665](https://github.com/vllm-project/vllm-omni/issues/6665)、[#6787](https://github.com/vllm-project/vllm-omni/issues/6787)）、310P 安装与版本配对（[#5251](https://github.com/vllm-project/vllm-omni/issues/5251)）。

**缺口**

- 语音识别、VLA、图像、视频、检索、omni 均无覆盖，310P 矩阵实际上只有一个模型。
- Boogu-Image 与 Qwen3-Omni-30B-A3B 没有卡内双芯并行（CP/SP/TP）与跨卡 PP 的验证。

### 3. 目标

- 矩阵内每个模型在真实 310P 上跑通，并在该模型自己的评测数据集上达到容差内精度。
- 每个已适配模型在同一数据集上完成吞吐优化，至少有一项实测提升，且精度不回退。
- 为 Boogu-Image 与 Qwen3-Omni-30B-A3B 验证部署路径：卡内双芯以 CP/SP/TP 切分，跨卡以 PP 扩展，并按实测给出每级扩展的收益。
- 为每个模型定级：Supported、Experimental 或 Stretch，并以 recipe 与数据集证据为准。

### 4. 模型覆盖

下表即优先级顺序。排序同时看两件事：部署需求与负载间的依赖，以及与这组硬件特性的匹配度——能否整块装进 48 GB/芯，单步计算是否足够轻。这不代表每个模型都能达到同一支持等级。

| 优先级 | 模型 | 类别 | 规模 | FP16 下的 310P 适配性 |
| ---: | --- | --- | --- | --- |
| 1 | Qwen3-ASR-1.7B | TTS / ASR | 1.7B | 权重约 3.4 GB；单次 encoder-decoder 前向，单芯算力需求低 |
| 2 | Qwen3-TTS-1.7B | TTS / ASR | 1.7B + codec | 权重约 3.4 GB 加 codec；已有 310P 路径可依托 |
| 3 | MiniCPM-o 4.5 | TTS / ASR（全双工 omni） | 约 8–9B + codec | 权重约 16–18 GB 加 codec 与阶段缓冲，仔细排布后可放进单芯（48 GB） |
| 4 | Pi0.5 | VLA | 3.62B | 权重约 7.3 GB；无状态、时延敏感，单芯 |
| 5 | Boogu-Image Turbo | 图像生成 | 约 19B 执行图（DiT + Qwen3-VL-8B + VAE） | batch 1 下 4-step DMD；权重与激活峰值约 36–41 GB；单卡双芯（96 GB）内以 CP/SP/TP 切分，仍不足时跨卡 PP |
| 6 | Z-Image-Turbo | 图像生成 | 6B DiT + 约 4B 文本编码器 | 8-NFE 调度；总权重约 20.5 GB（6B DiT、4B 文本编码器、VAE），prompt 编码后释放文本编码器可再省；单芯仍有充足余量 |
| 7 | Qwen3-Reranker 0.6B | Embedding / Reranker | 0.6B | 权重约 1.2 GB；单芯高吞吐 |
| 8 | Qwen3-Reranker 8B | Embedding / Reranker | 8B | 权重约 16 GB，可放进单芯 |
| 9 | LFM3-Omni-2B | Omni | 2B + codec | 权重约 4 GB 加 codec，单芯余量充足 |
| 10 | Qwen3-Omni-30B-A3B | Omni | 30B 总参 / 3B 活跃 | FP16 下约 60 GB；单卡双芯（96 GB）内以 CP/SP/TP 切分；两卡四芯（192 GB）通过 PP 扩展 |
| 11 | Wan2.1-T2V-1.3B | 视频生成 | 1.3B | 权重约 2.6 GB；视频激活主导单芯的内存与算力 |

**选择依据**

- **语音（ASR、TTS、MiniCPM-o）。** 模型最小，生产需求最明确。ASR 与 TTS 建立音频前端、codec 和流式原语，后续每个语音或 omni 模型都要复用；MiniCPM-o 在此之上加了全双工编排和约 8–9B 的内存压力，所以排在它们之后而非之前。
- **VLA（Pi0.5）。** 边缘机器人的参考策略：3.6B、无状态、时延敏感。与音频栈独立，可并行推进。
- **图像（Boogu-Image Turbo、Z-Image-Turbo）。** Boogu 是高价值生成系列，有活跃的 Ascend 线，且卡内双芯并行与跨卡 PP 的扩展路径清晰；Z-Image 更小、吞吐更高，作为补充。两者都基于各自蒸馏出的 Turbo 权重排期。Boogu 若未达成多芯目标，Z-Image 转为第一图像目标。
- **检索（Qwen3-Reranker 0.6B 与 8B）。** 小、吞吐高，在 310P 上经济性好。vLLM-Ascend 已停用该路径，本次适配即把它迁入 vLLM-Omni。
- **Omni（LFM3-Omni-2B、Qwen3-Omni-30B-A3B）。** LFM3 是最小的真正 omni 模型，复用音频 codec 路径；Qwen3-Omni 是唯一因 3B 活跃参数而让 310P 尚存可行性的 MoE 候选，属于以多芯吞吐为前提的 stretch 目标。
- **视频（Wan2.1-T2V-1.3B）。** 最小的 Wan 模型，用于验证时序 attention 与 VAE 解码。视频对带宽和算力要求最高，所以排最后。

### 5. 技术方案

各分支遵循同一顺序：先保证权重整块常驻、batch 与 KV 池开得出来，再削减数据搬运。

- **语音。** 加载时强制 FP16，预处理与 detokenization 留在 NPU 上；用 graph-safe sampling 与 batch 档位对 talker、code predictor、Code2Wav 子图做 capture。补上长音频 VAD 切分、forced alignment、首包时延，以及 CustomVoice / VoiceDesign 变体。MiniCPM-o 把 thinker 与 talker/Code2Wav 拆到两颗芯，只让 codec chunk 跨芯，同时保持流式、取消和长输入语义不变。
- **VLA。** 在 NPU 上启用 OpenPI realtime 路径，含多相机预处理、proprioceptive state 与 flow-matching action expert。策略保持无状态，batch 1 下对 vision tower 与 action expert 做 graph capture，并对照参考实现校验 action-chunk 一致性。
- **图像。** 验证 DiT attention（先用 `TORCH_SDPA`，有融合 aclnn 时优先用）、VAE 布局与 tiling，以及 ACLGraph 下的去噪循环（含动态 shape 回退）。两个模型都用 Turbo 权重：Boogu-Image Turbo 走 4-step DMD、batch 1，Z-Image-Turbo 走 8-NFE。Boogu-Image Turbo 不支持请求批处理，其图像吞吐来自更短的调度和更低的单图时延，而非批量化去噪。Boogu 侧先在卡内双芯上比较 CP/SP/TP 的切分方式，仍不足时才扩到跨卡 PP，均以实测吞吐为判据。
- **检索。** 把 pooling/reranker 流水线从已停用的 vLLM-Ascend 实现迁入 vLLM-Omni，范围限定在该模型与 pooling 路径。验证长上下文打分与动态批处理，报告 nDCG/MRR 与每秒文档数。
- **Omni。** LFM3 侧启用时序模型、depth decoder 与 LiquidCodec，对 depth 整体循环做 capture，验证静音视频输入路径。Qwen3-Omni 侧先验证 encoder 与 thinker，再把 talker 与 Code2Wav 作为独立交付物，并量化 MoE gating 中的 torch 回退。
- **视频。** 复用图像的 DiT/VAE 工作，加时序 attention 与帧批处理，目标为短低分辨率片段。质量与稳定性门禁建立之前，视频保持 experimental。

---

## CC

cc @Gaohan123 @hsliuustc0106 @ywang96 @gcanlin @tjtanaa @xuechendi @FayeSpica @yenuo26 @haic0 @linyueqian

## 其他说明

- 本文是路线图与优先级文档，不替代任何单个 PR 的设计讨论；每个 PR 仍需自己的动机、测试与精度/性能证据。
- 若 maintainer 更倾向把 310P 保持为实验性、尽力而为的目标而非完整支持的档位，本 RFC 可降级为 tracking issue，技术内容与模型优先级不变。
- 贡献者需遵守仓库的 DCO、AI 使用披露、`precheck-pr` 与 open-PR 上限要求。
- 相关工作：[#4283](https://github.com/vllm-project/vllm-omni/pull/4283)、[#4841](https://github.com/vllm-project/vllm-omni/pull/4841)、[#4852](https://github.com/vllm-project/vllm-omni/pull/4852)、[#9246](https://github.com/vllm-project/vllm-omni/pull/9246)、[#8264](https://github.com/vllm-project/vllm-omni/issues/8264)、[#9446](https://github.com/vllm-project/vllm-omni/issues/9446)、[#5251](https://github.com/vllm-project/vllm-omni/issues/5251)、[#6665](https://github.com/vllm-project/vllm-omni/issues/6665)、[#6787](https://github.com/vllm-project/vllm-omni/issues/6787)、[#6691](https://github.com/vllm-project/vllm-omni/issues/6691)。
