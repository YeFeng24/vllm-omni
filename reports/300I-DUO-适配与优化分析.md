# 300I DUO（Ascend 310P）适配优化与社区贡献方案

> 合并日期：2026-11-12
> 内容：300I DUO 硬件画像、适配清单、算法量级、模型建议、路线图、风险清单；vLLM-Omni Issue/PR 规范、分支 gap、PR 拆分方案、Qwen3-MoE/Qwen3-ASR 310P 贡献方案。
> 通用架构与 Ascend 执行路径见 [vLLM-Omni-架构与技术报告.md](vLLM-Omni-架构与技术报告.md)。

---

## 目录

- **Part A · 300I DUO 适配与优化全景**：硬件画像、能力边界、适配清单、算法量级、模型建议、特性优化、路线图、风险清单。
- **Part B · 社区贡献规范与 310P 贡献方案**：Issue/PR 规范、分支 gap、PR 拆分路线、Qwen3-MoE 与 Qwen3-ASR 310P 方案。

---

<a id="part-iii"></a>
# 300I DUO 专项：适配、优化与贡献方案

> 合并自两篇本地调研文档，基准为本仓库 `main` 分支 `5ed7e8887`（2026-11-10）；Part B 的 Qwen3-ASR 专项补充于 2026-11-12。
>
> 本文档是技术资料合并版，**不属于上游 PR 内容**，不要随代码一起提交。

---

### 本篇合并说明

| # | 来源文件 | 原行数 | 并入位置 | 合并/删除说明 |
|---|---|---|---|---|
| 1 | `300I-DUO-适配与优化分析.md` | 492 | **Part A**（A.0–A.8、附录 A/附录 B、结语） | 全文保留。仅将开头独立目录替换为下方统一"合并目录"；所有表格、`file:line` 引用、实测命令、原始输出均保留。 |
| 2 | `vllm-omni-贡献指南与Qwen3-MoE-310P贡献方案.md` | 545 | **Part B**（B.0–B.8） | 全文保留。Issue/PR 规范、模板草稿、分支 gap 表、PR 拆分路线、Qwen3-ASR 专项均保留。 |

**删除项（已在此登记，正文未删减）**

- Source 1 开头的独立目录（11 个锚点）已由下方"合并目录"统一替代；Source 2 无目录。除此之外没有任何段落、表格、代码块、命令或引用被删除。
- 两篇文档中重复出现的 `tests/platforms/npu/test_310p_patches.py`、`.buildkite/npu/test-npu-ready.yml`、`is_310p`/PR #9246 等事实未删去任一处正文，改为双向交叉引用（见 A.2、A.3.8、A.6.3、A.8、B.0、B.3.7、B.4）。

**重叠事实的合并方式**

| 重叠主题 | 保留策略 | 交叉引用位置 |
|---|---|---|
| `is_310p` 检测与上游回归 | Part A 保留 commit `86c44bf30` 与运行期路由细节；Part B 保留 PR #9246 的修复结论与分支处理 | A.2、A.6.3 第 15 条 ↔ B.0、B.4 |
| 310P 测试资产（`test_310p_patches.py`、`test-npu-ready.yml`） | Part A 保留"覆盖内容/局限"表；Part B 保留测试 mark、E2E 放置位置与 Buildkite step 写法 | A.3.8、附录 A ↔ B.3.7、B.7 |
| 无 HCCS / PCIe 多 chip | Part A 保留实测拓扑与性能含义；Part B 保留验证环境记录 | A.1.1、A.2、A.7 ↔ B.2.4、B.8.4 |
| 310P 无 BF16、只能 FP16 | Part A 保留能力边界表与 Qwen3-TTS FP16 patch；Part B 保留 issue 草稿中的算子缺口 | A.2、A.3.2 ↔ B.2.4 |
| 310P 算子缺失 / torch fallback | Part A 从能力边界描述；Part B 从上游归属与代码位置描述 | A.2 ↔ B.4、B.5 PR C |
| 工具链/版本 | Part A 记 CANN 8.3.RC1 + torch_npu 2.9.0；Part B 记 CANN 9.0.1 + torch_npu 2.10.0 + vLLM/vllm-ascend 0.30.0 | A.1.1、A.8 ↔ B.2.4、B.8.4、B.8.5 |

**已记录但不强行统一的冲突**：Part A 实测为 3 张卡 × 每卡 2 chip = **6 个 device**（A.1.1）；Part B 的验证环境写作 **"4 chips"**（B.2.4、B.8.4）。两者是不同机器/不同时间的记录，均原样保留。

---

### 本篇目录

**Part A：300I DUO（Ascend 310P）适配与优化全景**

- A.0 结论摘要
- A.1 硬件画像与实测数据
  - A.1.1 实测硬件
  - A.1.2 300I DUO 的定位
- A.2 为什么"910B 能跑"不等于"300I DUO 能跑"
- A.3 当前 300I DUO 适配与优化清单
  - A.3.1 平台与运行时层
  - A.3.2 Qwen3-TTS Talker（AR 生成 codec token）
  - A.3.3 Prompt-embeds builder（参考音频/音色前处理）
  - A.3.4 CodePredictor（310P 优化的核心）
  - A.3.5 Code2Wav（codec → 波形）
  - A.3.6 Tokenizer 解码器
  - A.3.7 部署形态
  - A.3.8 CI/测试覆盖
  - A.3.9 明确没做的部分
- A.4 300I DUO 的算法量级判断
  - A.4.1 AR / TTS / Omni
  - A.4.2 扩散 / 图像 / 视频
  - A.4.3 量级结论
- A.5 下一批适配模型建议
  - A.5.1 筛选标准
  - A.5.2 优先级矩阵
  - A.5.3 重点推荐理由
- A.6 可基于 300I DUO 做的特性与优化
  - A.6.1 性能类
  - A.6.2 功能类
  - A.6.3 工程类
- A.7 建议路线图
- A.8 风险与验证清单
- 附录 A：关键代码索引
- 附录 B：实测方法与原始数据
- 结语

**Part B：vLLM-Omni 社区贡献规范与 Qwen3-MoE / Qwen3-ASR 310P 贡献方案**

- B.0 结论摘要
- B.1 社区贡献渠道
- B.2 Issue 规范
  - B.2.1 基本要求
  - B.2.2 模板与标题前缀
  - B.2.3 本项目的 issue 规划
  - B.2.4 New Model issue 草稿
  - B.2.5 先例核查：PR #4841 没有关联 issue
- B.3 PR 规范
  - B.3.1 标题前缀
  - B.3.2 PR 描述模板
  - B.3.3 DCO / Signed-off-by
  - B.3.4 AI Usage Policy
  - B.3.5 PR 数量限制
  - B.3.6 提交前本地检查
  - B.3.7 测试要求
  - B.3.8 新模型 PR 额外要求
  - B.3.9 Review 流程
- B.4 当前分支逐项 gap
- B.5 推荐提交路线
  - Step 0：先沟通（1-3 天）
  - Step 1：重建干净分支
  - Step 2：拆成 3 个 PR
  - Step 3：验证并提交
- B.6 最容易踩的 5 个坑
- B.7 关键参考
- B.8 Qwen3-ASR-310P 专项（2026-11-12 调研）
  - B.8.1 关键结论
  - B.8.2 按目标选择提交对象
  - B.8.3 推荐操作顺序
  - B.8.4 vllm-ascend issue 草稿
  - B.8.5 版本提醒

---

# Part A：300I DUO（Ascend 310P）适配与优化全景

> 文档状态：基于 `main` 分支 `5ed7e8887`（2026-11-10）源代码与真机实测整理。
>
> 分析范围：vLLM-Omni 当前仓库对 Atlas 300I Duo / Ascend 310P 的适配、优化、模型支持边界，以及下一阶段可投入的模型与特性方向。
>
> 说明：文中"实测"数据来自本机 `npu-smi` 与 `torch_npu` 微基准；"公开规格"仅用于量级参考；所有性能数字为一阶估算，不代表模型级最终性能。

---

## A.0 结论摘要

1. **300I DUO 不是"降频版 910B"**。它在精度（无 BF16）、算子（无 Triton-Ascend、无 `torch.stft`）、图捕获（ACLGraph 受限）、互联（无 HCCS）上都是另一套能力边界。引擎层功能大多可复用，但模型层存在"功能不成立"而不仅是"慢"。
2. **仓库当前只对 Qwen3-TTS 做了 310P 深度适配**：Talker、CodePredictor、Code2Wav、Tokenizer 都有 310P 专属 patch；其他 Omni / TTS / 扩散模型只走通用 NPU 路径，**没有 310P 适配，也没有 310P E2E 验证**。
3. **310P 的甜点区**：TTS ≤ 2B、Omni ≤ 3B、图像 ≤ 6B（≤768 分辨率）、视频 ≤ 2B（480p，实验性）。7B 级 AR 属边缘可用，20B+ 图像、30B+ MoE、大视频不具备投入价值。
4. **下一阶段最优路径**：Qwen3-TTS 工程化 → 0.5B 级 TTS 矩阵（CosyVoice3 / Kokoro / MOSS-TTS-Nano）→ Qwen2.5-Omni-3B → 4–6B 图像模型（Z-Image / FLUX.2-klein 4B）。
5. **五件最值得先做的事**：310P E2E CI、图安全采样、W8A8 量化、双 chip stage 拆分、CPU 回退消除。

---

## A.1 硬件画像与实测数据

### A.1.1 实测硬件

本机通过 `npu-smi` 与 `torch_npu` 读取：

| 项目 | 实测值 |
|---|---|
| 板卡 | IT21PD2G10（Atlas 300I Duo），3 张卡 |
| 芯片 | 每卡 2 × Ascend 310P3，共 **6 个 device** |
| 单 chip 内存 | DDR 49152 MB，**可用 44,280 MB（约 43.2 GiB）** |
| DDR 频率 | 2131 MHz |
| 计算核 | **8 Cube + 7 Vector**，L2 16 MB |
| 互联 | **无 HCCS**；跨卡为 PCIe SYS/PHB，跨 chip 也无高带宽互联 |
| 实测拷贝带宽 | **184.8 GB/s**（1 GB FP16 张量 `copy_`） |
| 实测 FP16 Matmul | **24.0 TFLOPS**（4096³，单算子） |
| 公开峰值参考 | 约 70 TFLOPS FP16 / 140 TOPS INT8 per chip |
| 软件栈 | CANN 8.3.RC1（V100R001C23B149）、driver 25.3.rc1.b030、torch_npu 2.9.0 |

两个关键含义：

1. **单 chip 43 GB、双 chip 86 GB，但双 chip 走 PCIe。** 两张卡/两个 chip 拼大模型的 TP 效率远低于 910B 的 HCCS；**多阶段按 stage 拆分（Talker 在 chip0、Code2Wav 在 chip1）比 TP 更划算**。
2. **实际可达算力约 24 TFLOPS、带宽约 185 GB/s。** 这两个数字基本决定了 310P 的模型量级甜点区。

> 运行注意：实测时 NPU 96 那张卡有其他人的 `mem_probe` 进程；32768/32896 两张卡基本空闲。后续跑基准应避开被占用的卡，并避免假设独占。

> 交叉引用：Part B 的 New Model issue 草稿（B.2.4）与其 vllm-ascend issue 草稿（B.8.4）把验证机记为 "4 chips"；那是另一个验证环境的记录，不是本节的 6 device 实测。两处均原样保留，见"合并说明"。

### A.1.2 300I DUO 的定位

- 推理卡，不支持训练/微调。
- 优势：单卡 96 GB 级内存（双 chip）、INT8 吞吐高、功耗/成本低，适合**小模型、高并发、私有化部署**。
- 劣势：LPDDR4X 带宽低、无 BF16、无 Triton、ACLGraph 能力受限、多 chip 无 HCCS。

---

## A.2 为什么"910B 能跑"不等于"300I DUO 能跑"

引擎层（调度器、PagedAttention、OpenAI API、OmniConnector、async chunk、流式输出）是 Python 层、硬件无关的，**理论上可以跑**。真正卡住的是模型层算子与运行路径：

| 能力 | 910B / A2 / A3 | 310P3 | 影响 |
|---|---|---|---|
| BF16 | 支持 | **不支持，只能 FP16** | 模型需整体转 FP16；数值敏感模型质量/稳定性变化 |
| Triton-Ascend | 支持 | **不支持** | penalty/rejection sampler、融合算子需回退原生实现 |
| `torch.stft` | 支持 | **不支持** | Qwen3-TTS mel 前端被迫放 CPU |
| ACLGraph | 成熟 | **受限** | 随机采样算子不可捕获，Talker-MTP 只能 eager |
| FlashAttention | 910 系列签名 | **310P token-major FP16 + 16 token 对齐 + FRACTAL_NZ mask** | 需单独适配 attention |
| 互联 | HCCS | **PCIe** | 多 chip TP/EP 通信代价高 |
| vLLM-Ascend 后端 | 完整路径 | **独立 `_310p` worker/runner + 算子子集** | 大量功能未实现或未验证 |
| 内存带宽 | HBM，TB/s 级 | **LPDDR4X，实测 185 GB/s** | 解码吞吐差一个数量级 |

代码中可直接看到这些约束：

- `is_310p()` 判定后切换 `NPUWorker310` / `NPUModelRunner310`：[worker/base.py:10-13](../vllm_omni/platforms/npu/worker/base.py#L10-L13)、[npu_model_runner.py:35-38](../vllm_omni/platforms/npu/worker/npu_model_runner.py#L35-L38)
- 310P 关闭 JIT、用 `AscendSampler310` 并把 penalty 换回 vLLM 原生实现：[patch/worker.py:22-32](../vllm_omni/platforms/npu/_310p/patch/worker.py#L22-L32)
- Qwen3-TTS 310P patch 强制 FP16：[`_310p/patch/qwen3_tts.py:28`](../vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py#L28)
- 采样算子不可图捕获，Talker-MTP 置 eager：[`qwen3_tts.py:39-44`](../vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py#L39-L44)
- mel 频谱放 CPU：[`qwen3_tts.py:83-86`](../vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py#L83-L86)
- MoE 在 310P 上走 AllGather：[fused_moe.py:91-92](../vllm_omni/platforms/npu/layers/fused_moe.py#L91-L92)

另外，**310P 当前只走 V1 runner**：V2 runner 直接继承 vLLM-Ascend 的 `NPUModelRunner`，没有 310P 选择分支（[npu_omni_v2_model_runner.py:20](../vllm_omni/platforms/npu/worker/npu_omni_v2_model_runner.py#L20)、[:225](../vllm_omni/platforms/npu/worker/npu_omni_v2_model_runner.py#L225)），Qwen3-TTS 的 NPU 部署配置也固定 `model_runner: v1`（[qwen3_tts.yaml:161-170](../vllm_omni/deploy/qwen3_tts.yaml#L161-L170)）。因此依赖 MRv2 的性能特性在 310P 上不可用。

> 交叉引用：Part B B.4 进一步列出了仓库分支里针对 310P 缺失 ATB/NNAL 算子（`ReshapeAndCache`、`MoeGatingTopKSoftmax`、`_npu_flash_attention`/`_npu_paged_attention`/`splitfuse`）的 torch fallback 及其归属争议；本节从"能力边界"角度描述同一组限制。

> 交叉引用：Part B B.0/B.4 记录的 `is_310p` 检测回归（上游 PR #9246 修复）就是本节"vLLM-Ascend 版本对齐"风险的一个实例；vllm-ascend 曾移动 `is_310p`（commit `86c44bf30`），见 A.6.3 第 15 条。

---

## A.3 当前 300I DUO 适配与优化清单

### A.3.1 平台与运行时层

| 内容 | 具体做法 | 目的/限制 | 位置 |
|---|---|---|---|
| SoC 识别 | `is_310p()` 包一层 vLLM-Ascend 的检测 | 运行期正确路由 | [_310p/\_\_init\_\_.py:11-21](../vllm_omni/platforms/npu/_310p/__init__.py#L11-L21) |
| Worker/Runner 切换 | `NPUWorker310`、`NPUModelRunner310` | 走 310P 专用执行路径 | [worker/base.py:10-13](../vllm_omni/platforms/npu/worker/base.py#L10-L13)、[npu_model_runner.py:35-38](../vllm_omni/platforms/npu/worker/npu_model_runner.py#L35-L38) |
| JIT 关闭 | `torch_npu.npu.set_compile_mode(jit_compile=False)` | 310P 无 Triton-Ascend，避免 JIT 路径 | [_310p/\_\_init\_\_.py:23-26](../vllm_omni/platforms/npu/_310p/__init__.py#L23-L26) |
| Sampler | `AscendSampler310` + 原生 `Sampler.apply_penalties` | 310P 上 Triton penalty 不可用 | [patch/worker.py:30-31](../vllm_omni/platforms/npu/_310p/patch/worker.py#L30-L31) |
| 权重布局 | Linear→NZ、Conv→FRACTAL_Z、`allow_internal_format=True` | 匹配 310P 融合算子布局 | [models/qwen3_tts.py:47-77](../vllm_omni/platforms/npu/models/qwen3_tts.py#L47-L77) |
| MoE 通信 | 310P 分支固定 `ALLGATHER` | 310P 不支持 A3 的 AllToAll 路径 | [fused_moe.py:91-92](../vllm_omni/platforms/npu/layers/fused_moe.py#L91-L92) |
| 补丁入口 | 只有 `Qwen3TTSTalkerForConditionalGeneration` / `Qwen3TTSCode2Wav` 两个架构会分发 310P 补丁 | **其他模型没有 310P 模型级补丁** | [patch/\_\_init\_\_.py:27-35](../vllm_omni/platforms/npu/_310p/patch/__init__.py#L27-L35) |

### A.3.2 Qwen3-TTS Talker（AR 生成 codec token）

| 优化 | 做法 | 解决什么 | 位置 |
|---|---|---|---|
| FP16 强制 | `_embedding_dtype = torch.float16`，prompt builder 同步覆盖 | 310P 无 BF16 | [`qwen3_tts.py:34-38`](../vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py#L34-L38) |
| Talker-MTP 强制 eager | `talker_mtp_graph_safe = False`；`talker_mtp_accepts_per_row_generators = True` | 310P 随机采样算子不能被 ACLGraph 捕获；把图机会让给 CodePredictor | [`qwen3_tts.py:39-44`](../vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py#L39-L44) |
| Mimi 参考音频编码器放 CPU | `encoder.to(cpu, fp32)` + 自定义 `_encode_ref_audio_batch` | 310P 对参考音频动态 shape 敏感，避免 NPU 上的 shape 抖动/算子问题 | [`qwen3_tts.py:46-76`](../vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py#L46-L76) |
| 共享优化 | stacked codec embedding gather、`_tts_pad_embed` 预计算、silence mask 预计算、streaming decoder graphs | 减少每帧 kernel/投影/CPU 往返 | [qwen3_tts_talker.py:1549-1772](../vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_talker.py#L1549-L1772) |

### A.3.3 Prompt-embeds builder（参考音频/音色前处理）

- `_mel_spectrogram_on_cpu = True`：310P 不支持 `torch.stft`，mel 频谱放 CPU 计算，再回传 NPU（[`qwen3_tts.py:83-86`](../vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py#L83-L86)）。
- 代价：每请求/每段参考音频多一次 CPU 计算与 H2D；参考音频长、并发高时会成为首包延迟瓶颈。

### A.3.4 CodePredictor（310P 优化的核心）

Qwen3-TTS 每帧要生成 `Q-1` 个残差 codebook；序列固定且很短，天然适合图捕获。310P patch 做了这些：

| 优化 | 做法 | 收益 | 位置 |
|---|---|---|---|
| 融合 QKV + NZ | 把 `qkv_proj` 预打包成 310P matmul 布局，每步只做一次 `F.linear` | 减少 3 次 matmul/布局转换 | [`qwen3_tts.py:105-149`](../vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py#L105-L149) |
| 融合 RoPE | `torch_npu.npu_apply_rotary_pos_emb`，BSND，head_dim 64/128 | ACLGraph 可捕获 | [`qwen3_tts.py:150-172`](../vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py#L150-L172) |
| 310P FlashAttention | token-major FP16、**16 token 对齐**、`_npu_flash_attention` | 绕开通用 attention 的 layout 限制 | [`qwen3_tts.py:174-207`](../vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py#L174-L207) |
| 缓存 NZ 因果 mask | `AttentionMaskBuilder310` + `nd_to_nz_2d` + FRACTAL_NZ，固定短序列只建一次 | 避免每步重建 mask | [`qwen3_tts.py:230-270`](../vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py#L230-L270) |
| 融合 Add+RMSNorm | `torch_npu.npu_add_rms_norm` | 减少算子数 | [`qwen3_tts.py:210-228`](../vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py#L210-L228) |
| 预计算 codec embedding 投影 | `_projected_codec_embed_weight` 一次性堆叠 | 每步省掉 `small_to_mtp_projection` | [`qwen3_tts.py:300-325`](../vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py#L300-L325) |
| 按 batch bucket 捕获 + prefix graph | `_device_graphs[(padded_bsz, step+1)]` 复用；padding 到 bucket | 固定 shape 重放，减少 ACLGraph 捕获次数 | [`qwen3_tts.py:360-430`](../vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py#L360-L430) |
| 采样放在图外 | top-k/top-p + `random_sample` 在 graph replay 后执行 | 规避"随机采样算子不可捕获" | [`qwen3_tts.py:400-450`](../vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py#L400-L450) |

> 这套 CodePredictor 是 310P 上最完整的"图层 + 融合算子 + layout + bucket"组合，也是后续给其他 TTS 模型复用的基础。

### A.3.5 Code2Wav（codec → 波形）

| 优化 | 做法 | 位置 |
|---|---|---|
| FP16 运行时 | `_npu_decoder_runtime_dtype()` 返回 FP16，覆盖 stage dtype | [`qwen3_tts.py:93-102`](../vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py#L93-L102) |
| 权重布局 | Linear→NZ、Conv1d/ConvTranspose1d→FRACTAL_Z，并 `precompute_snake_caches()` | [models/qwen3_tts.py:47-77](../vllm_omni/platforms/npu/models/qwen3_tts.py#L47-L77) |
| 运行时模式 | `allow_internal_format=False` + `jit_compile=False`，走 ACLNN Conv | [models/qwen3_tts.py:32-45](../vllm_omni/platforms/npu/models/qwen3_tts.py#L32-L45) |
| 外层 PIECEWISE | deploy 配置 `cudagraph_mode: PIECEWISE` | [qwen3_tts.yaml:161-170](../vllm_omni/deploy/qwen3_tts.yaml#L161-L170) |
| 内层 exact-shape 图 | `NPUGraphDecoderWrapper` + `NPUExactGraphRunner`，按 `(batch, frames)` 捕获，warmup 后 freeze | [code2wav_graph.py:1-80](../vllm_omni/platforms/npu/models/code2wav_graph.py#L1-L80) |

### A.3.6 Tokenizer 解码器

- fused RoPE（`npu_rotary_mul`）+ fused RMSNorm（`npu_rms_norm`），所有 NPU 共用，310P 也受益：[qwen3_tts_tokenizer_v2.py:21-45](../vllm_omni/platforms/npu/models/qwen3_tts_tokenizer_v2.py#L21-L45)。

### A.3.7 部署形态

- Qwen3-TTS 两阶段（Talker → Code2Wav）通过 `SharedMemoryConnector` 传 chunk，`async_chunk: true`，NPU 用 `model_runner: v1`（[qwen3_tts.yaml:1-10](../vllm_omni/deploy/qwen3_tts.yaml#L1-L10)）。
- 默认两个 stage 都放 `devices: "0"`，每 stage `gpu_memory_utilization: 0.3`（[qwen3_tts.yaml:80-94](../vllm_omni/deploy/qwen3_tts.yaml#L80-L94)、[:129-141](../vllm_omni/deploy/qwen3_tts.yaml#L129-L141)）。
- 在 300I DUO 上更合理的做法是 **stage 拆分到两个 chip**（Talker chip0 / Code2Wav chip1），因为双 chip 走 PCIe，stage 间只传 chunk 比 TP 频繁通信便宜。

### A.3.8 CI/测试覆盖

| 测试 | 覆盖内容 | 局限 |
|---|---|---|
| `test_310p_real_device.py` | 真机检测、`NPUWorker310`/`NPUModelRunner310` 接线、patch 生效 | **只验证平台接线，不跑模型** |
| `test_310p_patches.py` | 用 fake 依赖在 CPU 上验证 Qwen3-TTS patch 契约 | 不验证真机算子/精度 |
| `test_activation.py` | 310P FP16 激活层单测 | 只覆盖扩散单层 |
| Buildkite 310P job | 构建 310P 镜像 + 上述测试 | **没有 E2E 模型任务** |

见 [test-npu-ready.yml:79-97](../.buildkite/npu/test-npu-ready.yml#L79-L97)。

> 交叉引用：Part B B.3.7 给出了 310P 测试 mark、真机 E2E 放置位置与 Buildkite step（`mirror_hardwares: 310p_npu_1`）的具体写法；两处描述的是同一套测试资产。

### A.3.9 明确没做的部分

- **扩散模型零 310P 适配**：没有 `_310p` 分支；没有 MindIE-SD 时 diffusion attention 回退 `TORCH_SDPA`（[platform.py:354-362](../vllm_omni/platforms/npu/platform.py#L354-L362)），DiT/VAE 算子未验证。
- **其他 Omni/TTS/ASR 模型没有 310P 补丁**：Qwen2.5-Omni、MiniCPM-o、CosyVoice、MOSS、Fish 等只走通用 NPU 路径。
- **没有 310P 量化路径**：W8A8/INT8 KV 未接入 omni 模型。
- **没有 310P 多 chip/TP 验证**。
- **没有 310P E2E 精度/性能基线**。
- **没有 V2 runner**。

---

## A.4 300I DUO 的算法量级判断

用实测 185 GB/s 和 24 TFLOPS 做估算。AR 解码是**带宽瓶颈**：

```text
理论 tok/s ≈ 带宽 / 权重字节数
```

DiT 是**算力瓶颈**：

```text
每步时间 ≈ 2 × 参数量 × token 数 / 算力
```

### A.4.1 AR / TTS / Omni

| 模型量级 | FP16 权重 | 理论 tok/s（185 GB/s） | 现实估计（50–70%） | 判断 |
|---|---|---|---|---|
| 82M（Kokoro） | 0.16 GB | >1000 | 很高 | **非常适合** |
| 0.5–0.6B（TTS/小模型） | 1.0–1.2 GB | 150–185 | 50–100 | **甜点** |
| 1.7B（Qwen3-TTS） | 3.4 GB | ~54 | 20–35 | **适合实时 TTS**（12Hz 帧率，RTF 约 0.3–0.6） |
| 3B（Qwen2.5-Omni-3B） | 6 GB | ~31 | 12–20 | **可用**，适合非实时/短回复 |
| 7B | 14 GB | ~13 | 5–9 | **边缘**，实时对话吃力，离线可用 |
| 8B（MiniCPM-o 4.5 级） | 16 GB | ~11.5 | 4–8 | **偏慢**，全双工体验风险高 |
| 20B | 40 GB | ~4.6 | 2–3 | 单 chip 勉强放下，**不推荐** |
| 30B-A3B MoE | ~60 GB FP16 | 需双 chip | 通信+内存双杀 | **不推荐** |

> Qwen3-TTS 12Hz 意味着每秒音频约 12 个 Talker token。1.7B 在 20–35 tok/s 下约 0.3–0.6 RTF，单路可实时；0.6B 可做到 0.1–0.2 RTF，适合高并发。

### A.4.2 扩散 / 图像 / 视频

以 24 TFLOPS 实测算力估算（512² 约 1k latent token，1024² 约 4k）：

| 模型量级 | 512² × 8 步 | 1024² × 8 步 | 判断 |
|---|---|---|---|
| 0.6B DiT | ~0.5–1 s | ~2–3 s | **很适合** 512–768 |
| 4B（FLUX.2-klein） | ~3–5 s | ~12–20 s | **可用**，建议 ≤768 |
| 6B（Z-Image Turbo） | ~4–8 s | ~16–30 s | **可用**，低分辨率优先 |
| 20B（Qwen-Image） | ~20–30 s | >1 min | **不推荐** |
| 80B MoE（HunyuanImage3） | — | — | **不可行** |
| 5B 视频（Wan2.2-TI2V） | 480p 多帧 | 数十秒到分钟级 | **实验性**，非实时 |
| 2B 视频（SANA-Video） | 480p | 可能数十秒 | **可试**，低帧率 |

> 以上是一阶估算，实际取决于算子效率、步数、分辨率、量化和图捕获。310P 的扩散算子栈目前没有 omni 侧优化，先用 `TORCH_SDPA` 的话会明显低于这个估算。

### A.4.3 量级结论

- **TTS ≤ 2B**：310P 的主战场。
- **Omni ≤ 3B**：可做边缘多模态；7B 只能离线/低实时。
- **图像 ≤ 6B，分辨率 ≤ 768**：可做低成本文生图。
- **视频 ≤ 2B 且 480p**：实验性。
- **20B+ 图像、30B+ MoE、大视频**：不建议投入 310P。

---

## A.5 下一批适配模型建议

### A.5.1 筛选标准

1. **单 chip 43 GB 能放下 FP16**（或 W8A8 后能放下）。
2. **算子 FP16 友好**：不依赖 BF16/Triton/`torch.stft`/CUDA 专用 kernel。
3. **能复用现有 NPU 图设施**：`NPUExactGraphRunner`、CodePredictor bucket graph、Code2Wav 图。
4. **社区热度高**：仓库近半年持续投入的方向。
5. **有明确边缘/私有化价值**：TTS、语音克隆、小 Omni、低分辨率图像。

### A.5.2 优先级矩阵

| 优先级 | 模型 | 量级 | 310P 适配性 | 社区热度 | 可复用性 | 主要工作 |
|---|---|---|---|---|---|---|
| **A1** | **Qwen3-TTS 0.6B/1.7B** | 0.6–1.7B | 已适配，需补 E2E/量化/批量 | 极高 | — | 310P E2E CI、图安全采样、W8A8、参考音频 NPU bucket、双 chip stage 拆分 |
| **A2** | **CosyVoice3 0.5B** | 0.5B | 好：已有 `cosyvoice3_graph.py` / DiT attention patch | 高（语音克隆/流式） | 高 | 把 A2/A3 的 graph patch 移植到 310P；FP16；FIA mask；HiFT 图 |
| **A3** | **Kokoro-82M** | 82M | 极好：极小、非 AR、易并发 | 中高（高并发 TTS） | 中 | 算子核查、图捕获、批处理；做 310P 高并发样板 |
| **A4** | **Z-Image / FLUX.2-klein 4B / SDXL** | 4–6B | 中：需 DiT attention + VAE 适配 | 高（图像生成） | 中 | 310P DiT attention 后端、FP16、ACLGraph、VAE Conv FRACTAL_Z、512–768 |
| **B1** | **Qwen2.5-Omni-3B** | 3B | 较好：Qwen2.5 backbone 是 310P 最成熟 LLM 路径 | 高（实时多模态） | 高（Talker/Code2Wav 可复用 Qwen3-TTS） | FP16、音频/视觉编码器算子、stage 拆分、流式 |
| **B2** | **MOSS-TTS-Nano / IndexTTS-2 / Fish Speech S2** | 小–中 | 中：TTS 结构相似，可复用 codec 图 | 中高 | 高 | 选 1–2 个，复用 CodePredictor/Code2Wav 图设施 |
| **B3** | **LongCat-Image / ERNIE-Image / Boogu-Image** | 中 | 中 | 中 | 中 | 图像 DiT 适配，和 A4 共用后端 |
| **C1** | **MiniCPM-o 4.5** | 约 8B 级 | 差–中：模型大、全双工延迟敏感，但 NPU patch 最丰富 | 很高（全双工） | 很高 | 先做 Qwen2.5-Omni-3B 验证 3B 级 Omni 后再评估 |
| **C2** | **Wan2.2-TI2V-5B / SANA-Video 2B** | 2–5B | 差：视频 token 多、算力不够 | 高 | 中 | 仅 480p/低帧率实验 |
| **C3** | **pi0 / GR00T N1.7 3B** | 3B | 中 | 中（机器人） | 低 | 边缘策略推理，场景明确再做 |
| **不建议** | Qwen3-Omni 30B-A3B、Qwen-Image 20B、HunyuanImage3 80B、MiniMax-H3、LTX-2.5、大视频 | ≥20B | 差 | 高但硬件不匹配 | — | 算力/内存/带宽均不划算 |

### A.5.3 重点推荐理由

#### ① Qwen3-TTS 继续做深（不是换模型，而是补工程化）

这是当前唯一已经跨过"功能成立"门槛的 310P 模型，继续投入的边际收益最高：

- 补 **310P 真机 E2E**：0.6B/1.7B 三种任务（CustomVoice/VoiceDesign/Base）的 WER/SIM/首包/RTF。
- **图安全采样**：现在 Talker-MTP 因随机采样不可捕获被迫 eager。可以把采样改成"预生成 uniform + 图内确定性 top-k/Gumbel"，把整个 Talker-MTP 变成可捕获图。CUDA 侧已有 `sample_code_topk_gumbel` 和 `sample_uniforms` 管线（[qwen3_tts_talker.py:1657-1736](../vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_talker.py#L1657-L1736)），310P 可移植。
- **参考音频 bucket**：现在 Mimi encoder 在 CPU（[`qwen3_tts.py:46-51`](../vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py#L46-L51)）。按 1s/3s/5s/10s 分桶 padding 后放回 NPU，可消除每请求 CPU 往返；mel 也可预计算缓存。
- **W8A8 量化**：310P INT8 吞吐约为 FP16 的 2 倍，权重减半；对 1.7B Talker 和 Code2Wav 线性层收益直接。
- **双 chip stage 拆分**：Talker 和 Code2Wav 各占一个 chip，stage 间只传 codec chunk，避免 PCIe 上的 TP 通信。
- **批处理 + bucket 图**：310P 带宽瓶颈，batch 能摊薄权重读取；CodePredictor 已有 bucket，可继续扩 bucket 和 Code2Wav batch。

#### ② CosyVoice3 0.5B / Kokoro-82M：310P 的"高并发语音"组合

- CosyVoice3 0.5B：两阶段（LLM + Flow + HiFT），模型小；仓库已有 `cosyvoice3_graph.py`（Flow Euler + HiFT 精确图）和 CosyVoice2 的 NPU attention 适配（[cosyvoice3_graph.py:83-124](../vllm_omni/platforms/npu/models/cosyvoice3_graph.py#L83-L124)、[cosyvoice2_dit_attn.py](../vllm_omni/platforms/npu/models/cosyvoice2_dit_attn.py)）。把这些从 A2/A3 移植到 310P，主要是 FP16、FIA mask、Conv 布局。
- Kokoro-82M：极致小，适合做"单卡 6 个 device、每 device 多并发"的语音服务样板；但它是非 AR 的 StyleTTS2 类结构，需要核查 LSTM/iSTFT 等算子在 310P 的可用性，必要时 CPU/自定义算子。

#### ③ Qwen2.5-Omni-3B：3B 级 Omni 的最优起点

- Qwen2.5 的 dense LLM backbone 是 vLLM-Ascend 310P 最成熟的路径；3B FP16 约 6 GB，单 chip 轻松放下。
- Talker + Code2Wav 可以复用 Qwen3-TTS 的 code2wav 图和 chunk 流式设施。
- 主要风险在音频/视觉编码器算子（Whisper 类 conv/attention）和 FP16 数值；建议先做 ASR/语音问答，再做语音输出。
- 相比 Qwen3-Omni 30B-A3B，3B 是 310P 唯一现实的 Omni 入口。

#### ④ Z-Image / FLUX.2-klein 4B：图像生成的 310P 甜点

- Z-Image Turbo 6B、FLUX.2-klein 4B 都属于"少步数 + 中等参数量"，512–768 分辨率下 4–8 步可落在一张 chip 上。
- 需要补：310P 可用的 DiT attention 后端（MindIE-SD 不支持就用 SDPA/aclnn 融合 attention）、VAE Conv 的 FRACTAL_Z、ACLGraph 捕获、FP16 数值验证。
- 不建议直接上 Qwen-Image 20B/HunyuanImage3 80B：算力和带宽都不匹配。

#### ⑤ MiniCPM-o 4.5：先观望

它是仓库里 NPU 适配最全的模型（static-shape decode、ragged CFM batching、Code2Wav 图、duplex），但约 8B 级 dense + 视觉/音频编码器 + 全双工 TTS，在 310P 上延迟风险很大。建议等 Qwen2.5-Omni-3B 跑通后，再用同一套 stage/graph 设施评估。

---

## A.6 可基于 300I DUO 做的特性与优化

### A.6.1 性能类

1. **图安全采样（最高优先级）**
   - 目标：把 Talker-MTP 从 eager 变成 ACLGraph。
   - 做法：预生成 `sample_uniforms`，图内做确定性的 top-k + inverse-CDF/Gumbel；把采样从图外搬回图内。
   - 复用：`sample_code_topk_gumbel`、`sample_uniforms` 管线；310P 需确认 `apply_top_k_top_p`/`random_sample` 的 ACLNN 版本可捕获，或替换成纯 tensor 实现。

2. **W8A8 / INT8 量化**
   - 310P INT8 吞吐约为 FP16 2×；对 1.7B TTS 和 4–6B DiT 收益最大。
   - 接入点：vLLM-Ascend 310P 的量化 Linear；omni 的 `quantization` 配置；需要 TTS 质量/扩散相似度校准。

3. **批处理 + bucket 图**
   - 310P 是带宽瓶颈，batch 能摊薄权重读取；CodePredictor 已有 `_bucket_sizes`，继续扩 Code2Wav/DiT 的 batch bucket。
   - 高并发 TTS 场景优先。

4. **参考音频/Mel 前端 NPU 化**
   - 按长度分桶 + padding，Mimi encoder 回 NPU；mel 频谱预计算缓存；消除每请求 CPU 往返。

5. **双 chip stage 拆分**
   - 300I DUO 双 chip 无 HCCS，stage 间只传 chunk 比 TP 便宜；把 Talker/Code2Wav 或 Thinker/Talker 分到两个 device。

6. **前缀缓存/长上下文**
   - Qwen3-TTS 当前 `enable_prefix_caching: false`；长文本/固定 system prompt/音色描述场景可开 prefix cache，降低 prefill 成本。

7. **扩散专用优化**
   - 310P DiT attention 后端（SDPA 或 aclnn fused FA）；VAE Conv FRACTAL_Z；TeaCache/Cache-DiT 减少 NFE；ACLGraph 捕获 DiT block。
   - 先做 512–768，不做 1024+。

### A.6.2 功能类

8. **高并发流式 TTS 服务**：0.6B + batch + async chunk + shared memory connector，单卡双 chip 做多路实时语音。
9. **私有化声音克隆**：1.7B Base + 参考音频缓存，43 GB 单 chip 可完全本地。
10. **小 Omni 边缘助手**：Qwen2.5-Omni-3B 做离线语音/图像问答，必要时只输出文本；语音输出用 Qwen3-TTS/Code2Wav。
11. **低成本文生图**：Z-Image/FLUX.2-klein 4B，512–768，适合批量海报/素材生成。
12. **多租户/休眠**：sleep mode、prefix cache、per-stage 内存回收，在 6 个 device 上做资源池化。

### A.6.3 工程类

13. **310P E2E CI**：当前只有平台接线测试，建议加 Qwen3-TTS 0.6B/1.7B 的 accuracy + perf job；后续每接入一个模型加一条。
14. **310P 性能基线**：RTF、首包、tok/s、s/image、显存峰值；按 device 记录。
15. **is_310p 回归测试**：vLLM-Ascend 移动过 `is_310p`（commit `86c44bf30`），这类检测回归会导致静默走错 worker，需持续覆盖。

> 交叉引用：上游修复见 Part B B.0、B.4 的 PR #9246；另见 A.8。

---

## A.7 建议路线图

| 阶段 | 时间（建议） | 目标 | 交付物 |
|---|---|---|---|
| **P0 基线** | 1–2 周 | 把 Qwen3-TTS 0.6B/1.7B 真正跑出 310P E2E 数据 | RTF/首包/显存/精度；310P CI job |
| **P1 TTS 性能** | 2–4 周 | Qwen3-TTS 图安全采样 + 参考音频 NPU + W8A8 + 双 chip stage | 1.7B RTF < 0.3；0.6B 高并发 |
| **P2 TTS 矩阵** | 1–2 月 | CosyVoice3 0.5B / Kokoro-82M / MOSS-TTS-Nano 选 2 个 | 共享 CodePredictor/Code2Wav 图设施；多模型 recipe |
| **P3 小 Omni** | 2–3 月 | Qwen2.5-Omni-3B 语音问答/语音输出 | 单 chip 3B、流式、FP16 精度 |
| **P4 图像** | 2–3 月 | Z-Image / FLUX.2-klein 4B @512–768 | 310P DiT attention 后端；s/image 基线 |
| **P5 观望** | 按需 | MiniCPM-o 4.5 / 小视频 / VLA | 仅在 P3 证明 3B Omni 可行后启动 |

**验收指标建议**：

- TTS：1.7B RTF ≤ 0.3、首包 ≤ 300 ms、WER/SIM 不低于 910B 的合理容差。
- Omni-3B：短回复 ≥ 15 tok/s、语音问答端到端可接受。
- 图像：512² × 8 步 ≤ 5 s、768² ≤ 10 s。
- 稳定性：连续 1 小时高并发无 OOM/图捕获失败。

---

## A.8 风险与验证清单

- **vLLM-Ascend 版本对齐**：310P 的 `is_310p`、worker/runner 类路径随版本变动；需锁定 CANN 8.3.RC1 + torch_npu 2.9/2.10 + 对应 vLLM-Ascend。
- **FP16 精度**：TTS 的 WER/SIM、扩散的 CLIP/FID 都要单独建基线；不能直接复用 910B BF16 结果。
- **ACLGraph 捕获失败**：采样、动态 shape、CPU 标量都可能让图回退 eager；需要逐模型统计 capture 成功率。
- **PCIe 多 chip**：TP 通信可能成为瓶颈；优先 stage 拆分。
- **43 GB 单 chip 上限**：7B 以上要算上 KV/激活；20B 单 chip 紧张。
- **CPU 回退**：mel/Mimi/F0 等 CPU 回退在低并发下不明显，高并发会放大为首包/吞吐瓶颈。
- **无 E2E CI**：当前 310P 改动很容易"接线正确但模型跑错"，P0 必须先补 E2E。

> 交叉引用：Part B B.8.5 补充，vllm-omni main 目标 vLLM 0.33.0，vllm-ascend 最新 release 为 v0.32.0rc1，仍存在版本差。

---

## 附录 A：关键代码索引

| 主题 | 文件 |
|---|---|
| 310P 平台检测/patch 入口 | [vllm_omni/platforms/npu/_310p/\_\_init\_\_.py](../vllm_omni/platforms/npu/_310p/__init__.py) |
| 310P patch 分发 | [vllm_omni/platforms/npu/_310p/patch/\_\_init\_\_.py](../vllm_omni/platforms/npu/_310p/patch/__init__.py) |
| 310P worker/sampler patch | [vllm_omni/platforms/npu/_310p/patch/worker.py](../vllm_omni/platforms/npu/_310p/patch/worker.py) |
| 310P Qwen3-TTS 全量 patch | [vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py](../vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py) |
| NPU 平台钩子 | [vllm_omni/platforms/npu/platform.py](../vllm_omni/platforms/npu/platform.py) |
| NPU worker 基类 | [vllm_omni/platforms/npu/worker/base.py](../vllm_omni/platforms/npu/worker/base.py) |
| NPU model runner | [vllm_omni/platforms/npu/worker/npu_model_runner.py](../vllm_omni/platforms/npu/worker/npu_model_runner.py) |
| NPU AR/Generation runner | [npu_ar_model_runner.py](../vllm_omni/platforms/npu/worker/npu_ar_model_runner.py)、[npu_generation_model_runner.py](../vllm_omni/platforms/npu/worker/npu_generation_model_runner.py) |
| NPU 通用图设施 | [graph_tools.py](../vllm_omni/platforms/npu/graph_tools.py)、[models/code2wav_graph.py](../vllm_omni/platforms/npu/models/code2wav_graph.py) |
| NPU Qwen3-TTS Code2Wav/Tokenizer patch | [models/qwen3_tts.py](../vllm_omni/platforms/npu/models/qwen3_tts.py)、[models/qwen3_tts_tokenizer_v2.py](../vllm_omni/platforms/npu/models/qwen3_tts_tokenizer_v2.py) |
| Qwen3-TTS 模型实现 | [vllm_omni/model_executor/models/qwen3_tts/](../vllm_omni/model_executor/models/qwen3_tts/) |
| Qwen3-TTS 部署配置 | [vllm_omni/deploy/qwen3_tts.yaml](../vllm_omni/deploy/qwen3_tts.yaml)、[qwen3_tts_high_concurrency.yaml](../vllm_omni/deploy/qwen3_tts_high_concurrency.yaml) |
| 310P 真机测试 | [tests/platforms/npu/test_310p_real_device.py](../tests/platforms/npu/test_310p_real_device.py) |
| 310P patch 单测 | [tests/platforms/npu/test_310p_patches.py](../tests/platforms/npu/test_310p_patches.py) |
| 310P CI job | [.buildkite/npu/test-npu-ready.yml](../.buildkite/npu/test-npu-ready.yml) |
| 支持模型矩阵 | [docs/models/supported_models.md](../docs/models/supported_models.md) |
| 安装与镜像 | [docs/getting_started/installation/npu/npu.inc.md](../docs/getting_started/installation/npu/npu.inc.md) |

---

## 附录 B：实测方法与原始数据

### B.1 硬件枚举

```bash
npu-smi info
npu-smi info -t board -i 96
npu-smi info -t memory -i 96 -c 0
npu-smi info -t topo
```

关键输出：

- `310P3`，每卡 `Chip Count: 2`，共 3 张卡（NPU 96 / 32768 / 32896）。
- 单 chip：`Total DDR Capacity: 49152 MB`，`DDR Capacity: 44280 MB`，`DDR Clock Speed: 2131 MHz`。
- topology：`SYS` / `PHB`，无 `HCCS`。

### B.2 设备属性

```bash
python - <<'PY'
import torch, torch_npu
print(torch_npu.npu.get_device_name(0))
print(torch_npu.npu.get_device_properties(0))
PY
```

输出：

```text
Ascend310P3
_NPUDeviceProperties(name='Ascend310P3', total_memory=44280.3MB,
                     cube_core_num=8, vector_core_num=7,
                     L2_cache_size=16MB)
```

### B.3 微基准

在空闲 device 2 上执行（避免干扰其他人的进程）：

```bash
ASCEND_RT_VISIBLE_DEVICES=2 python - <<'PY'
import time, torch, torch_npu
torch.npu.set_device(0)

n = 1024 * 1024 * 256
a = torch.empty(n, dtype=torch.float16, device="npu")
b = torch.empty(n, dtype=torch.float16, device="npu")
for _ in range(5):
    b.copy_(a)
torch.npu.synchronize()
t = time.perf_counter(); it = 20
for _ in range(it):
    b.copy_(a)
torch.npu.synchronize(); dt = time.perf_counter() - t
print(f"copy: {dt/it*1e3:.3f} ms/iter, {n*2*2*it/dt/1e9:.1f} GB/s")

m = 4096
x = torch.randn(m, m, dtype=torch.float16, device="npu")
y = torch.randn(m, m, dtype=torch.float16, device="npu")
for _ in range(5):
    z = x @ y
torch.npu.synchronize()
t = time.perf_counter(); it = 30
for _ in range(it):
    z = x @ y
torch.npu.synchronize(); dt = time.perf_counter() - t
print(f"matmul fp16: {dt/it*1e3:.3f} ms/iter, {2*m**3*it/dt/1e12:.1f} TFLOPS")
PY
```

输出：

```text
dev Ascend310P3
copy: 5.809 ms/iter, 184.8 GB/s
matmul fp16: 5.732 ms/iter, 24.0 TFLOPS
```

> 微基准是单算子峰值探索，不代表模型级性能；模型级还要叠加 KV cache、图捕获、算子融合、批处理等因素。

---

## 结语

**300I DUO 的正确定位是"小模型高并发推理卡"，不是"缩小版 910B"。** 当前仓库只把 Qwen3-TTS 做成了可用的 310P 路径；下一步应围绕 **Qwen3-TTS 工程化 → 0.5B 级 TTS 矩阵 → Qwen2.5-Omni-3B → 4–6B 图像模型** 推进，重点补 **E2E CI、图安全采样、W8A8、双 chip stage 拆分、CPU 回退消除** 这五件事。20B+ 图像、30B+ MoE、大视频在 310P 上不具备投入价值。

---

# Part B：vLLM-Omni 社区贡献规范与 Qwen3-MoE / Qwen3-ASR 310P 贡献方案

> 调研日期：2026-11-10
> 调研基准：本仓库 `main`（`5ed7e8887`）。上游最新 head 已到 `40f16e388`，正式提交前请以最新 `main` 文档为准。
> 本文档是本地调研记录，**不属于上游 PR 内容**，不要随代码一起提交。

---

## B.0 结论摘要

已完成的 Qwen3-MoE 310P 适配**不能直接提交 PR**，主要阻塞项：

| 类别 | 问题 | 处理方式 |
| --- | --- | --- |
| 分支基线 | 基于 v0.30.0 快照导入，与上游 `main` 无 merge base，落后 4162 commits；main 已对齐 vLLM 0.33.0 | 从 `upstream/main` 重建干净分支，只 cherry-pick 必要改动 |
| 提交内容 | HEAD 包含 `reports/`（4.2 MB）和两篇中文分析文档 | 从 PR 中移除，保留在本地 |
| 示例规范 | 新增 `examples/offline_inference/qwen3_moe/qwen3_moe.py` 模型专用 Python 示例 | 按 Examples Policy 属于 blocking，必须删除；改用共享 `x_to_text.py` + `model_extras` |
| 测试 | 没有任何 `tests/` 改动 | 补 CPU patch 单测 + 310P 真机 E2E |
| DCO | 3 个 commit 均无 `Signed-off-by:` | `git rebase --signoff upstream/main` |
| 许可证头 | 新文件使用 `Copyright contributors to the vLLM project` | 改为 `Copyright contributors to the vLLM-Omni project` |
| 重复修复 | `is_310p` 检测修复上游已合入 PR #9246 | 删除该部分改动 |
| 技术定位 | 纯文本 LLM 是否属于 vllm-omni 范围未确认 | 先开 New Model issue / RFC 与维护者确认 |

> 交叉引用：表中 `is_310p` 修复项对应 Part A A.2 与 A.6.3 第 15 条（vllm-ascend commit `86c44bf30` 移动 `is_310p`）。

**推荐路线：先 issue/RFC 确认 scope → 拆分 PR → 再正式提交。**

---

## B.1 社区贡献渠道

| 渠道 | 用途 |
| --- | --- |
| GitHub Issues | bug、feature、new model、performance、RFC |
| GitHub Pull Requests | 代码/文档贡献的唯一合入方式 |
| Slack `#sig-omni`（https://slack.vllm.ai） | 日常讨论、找 reviewer、确认 scope |
| Forum（https://discuss.vllm.ai） | 技术问答、设计讨论 |
| 社区会议 | 中英文会议，日程见 `docs/community/meetings.md` |
| Governance | committer 每月提名，最多 2 人，见 `docs/community/governance.md` |

安全漏洞**不能**走公开 issue/PR/Slack，按 `docs/community/contact_us.md#security-disclosures` 私密上报。

---

## B.2 Issue 规范

### B.2.1 基本要求

- 先搜索已有 issue，再开新 issue。
- 每个 issue 模板都要求勾选“已搜索过已有 issue，并问过文档页 chatbot”。

### B.2.2 模板与标题前缀

| 模板文件 | 用途 | 标题前缀 |
| --- | --- | --- |
| `100-documentation.yml` | 文档问题 | `[Doc]: ` |
| `200-installation.yml` | 安装问题 | `[Installation]: ` |
| `400-bug-report.yml` | Bug | `[Bug]: ` |
| `500-feature-request.yml` | 功能建议 | `[Feature]: ` |
| `600-new-model.yml` | 新模型支持 | `[New Model]: ` |
| `700-performance-discussion.yml` | 性能讨论 | `[Performance]: ` |
| `750-RFC.yml` | 重大架构/设计变更 | `[RFC]: ` |

### B.2.3 本项目的 issue 规划

建议开 **1 个 New Model issue + 1 个 RFC**：

- **New Model issue**：说明 Qwen3-MoE 纯文本模型 + 310P 支持诉求。
- **RFC issue**：改动超过 500 LOC，且涉及以下设计问题：
  1. vllm-omni 是否支持单 stage 纯文本 LLM；
  2. 310P fallback 放 vllm-omni 还是 vllm-ascend；
  3. main 的 vLLM 0.33 没有 310P vllm-ascend wheel，如何验证。

RFC 模板要求使用官方设计文档模板，并给出至少一周的反馈期。

### B.2.4 New Model issue 草稿

```markdown
Title: [New Model]: Support Qwen3-MoE text checkpoints as a single-stage LLM_AR pipeline (Ascend 310P)

### The model to consider
https://huggingface.co/Qwen/Qwen3-30B-A3B
(A plain Qwen3MoeForCausalLM checkpoint; no audio/vision stages.)

### The closest model vllm-omni already supports
Qwen3-Omni's thinker stage uses the same Qwen3-MoE backbone, but Qwen3-Omni
has audio/talker/code2wav stages. This request is text-only.

### What's your difficulty of supporting the model
1. vLLM-Omni has no pipeline entry for a plain text LLM. Without one, Omni
   falls through to the generic diffusion fallback instead of a single LLM_AR stage.
2. The omni AR runner passes omni-only kwargs (e.g. model_intermediate_buffer)
   to model.forward unconditionally; plain vLLM checkpoints do not accept them.
3. On Ascend 310P (Atlas 300I Duo), vllm-ascend's 310P path calls ATB kernels
   that the installed CANN/NNAL does not provide:
   - ReshapeAndCache
   - MoeGatingTopKSoftmax
   - _npu_flash_attention / _npu_paged_attention / splitfuse
   We currently have torch fallbacks for these.
4. Version alignment: main targets vLLM 0.33.0, but the only 310P
   vllm-ascend wheel we have is 0.30.0. The bring-up was validated on 0.30.0.

### Use case and motivation
Run text-only Qwen3-MoE on Atlas 300I Duo through the Omni entrypoint, so that
the same Omni deployment/runtime can serve both omni and plain text models.

### Validation environment
- Atlas 300I Duo (310P), 4 chips, no HCCS
- CANN 9.0.1, torch/torch_npu 2.10.0, vLLM 0.30.0, vllm-ascend 0.30.0 (310P wheel)
- vLLM-Omni v0.30.0 tree

### Questions for maintainers
1. Is a text-only LLM pipeline in scope for vLLM-Omni, or should this live in
   vLLM + vllm-ascend only?
2. If in scope, should the 310P device-op/attention/router fallbacks be
   upstreamed to vllm-ascend instead of monkeypatched from vllm-omni?
3. Which target branch should we use given main is on vLLM 0.33.0?
```

> 与 Part A 的差异：本草案验证环境记 "4 chips, no HCCS"，Part A A.1.1 实测为 3 卡 × 2 chip = 6 device；两者为不同机器/不同时间的记录，均原样保留。

### B.2.5 先例核查：PR #4841 没有关联 issue

核查方式：GitHub API 的 PR body、timeline 与 comments。

结果：

- PR #4841 `[Hardware][Ascend][Model] Optimize Qwen3-TTS on 310P` **没有关联/关闭任何 issue**。
- PR body 中没有 `Fixes #` / `Closes #` / `Related to #`，也没有任何 `#<number>` 引用。
- Timeline 中没有 `connected` 事件；只有来自 PR #4852、issue #5040（NPU Q3 Roadmap）、PR #5503 的交叉引用。
- 该 PR 于 2026-07-15 合并，labels 为 `ready`、`NPU`、`tts`，改动 9 个文件、+909/−166，27 个 commit。

**结论：关联 issue 不是所有 PR 的硬性合并门禁。** 对已有模型的 310P 优化，PR #4841 证明可以直接提 PR 并合并。

但仍需注意区别：

- #4841 是**已有模型（Qwen3-TTS）的硬件优化**，未新增模型、未改变对外能力。
- 本项目的 Qwen3-MoE 310P 工作是**新增模型 + 新增 pipeline 拓扑**，且纯文本 LLM 是否属于 vllm-omni scope 尚未确认，风险高于 #4841。
- 贡献指南规定：超过 500 LOC（不含 kernel/data/config/test）的重大架构改动，预期先有 RFC；否则可能被打 `rfc-required`。

因此建议：**issue 不是格式必需，但对“新模型 + scope 不确定”的场景是降低被 close 风险的必要动作。**

---

## B.3 PR 规范

### B.3.1 标题前缀

来源：`docs/contributing/README.md`。

| 前缀 | 适用场景 |
| --- | --- |
| `[Bugfix]` | Bug 修复 |
| `[CI/Build]` | CI/构建改进 |
| `[Doc]` | 文档 |
| `[Model]` | 新模型/模型改进（标题必须含模型名） |
| `[Frontend]` | OpenAI API server、`Omni`/`AsyncOmni` 等前端 |
| `[Kernel]` | CUDA/计算 kernel |
| `[Core]` | 核心逻辑（scheduler、processor 等） |
| `[Hardware][Vendor]` | 硬件相关，如 `[Hardware][Ascend]` |
| `[Misc]` | 其他（少用） |

跨类别需要叠加前缀。Ascend 310P 的历史先例：

```text
[Hardware][Ascend][Model] Optimize Qwen3-TTS on 310P (#4841)
[Hardware][Ascend] Adapt Qwen3 TTS for 310P (#4283)
[Bugfix][NPU] Fix 310P detection after vllm-ascend moved is_310p (#9246)
```

推荐标题：

```text
[Hardware][Ascend][Model] Support Qwen3-MoE text models on Ascend 310P
```

拆出的通用修复标题：

```text
[Bugfix][Core] Filter omni-only forward kwargs by model signature
```

### B.3.2 PR 描述模板

必须包含：

```markdown
## Purpose
## Test Plan
**vLLM Version:**
**vLLM-Omni Commit:**
## Test Result
```

要求：

- 正文提到的每个文件都必须真实出现在 diff 中。
- 新模型 PR 中 registry 条目数、`__init__.py` 导出、README 命令必须一致。
- 本地 L1/L2 测试结果需要附上。

### B.3.3 DCO / Signed-off-by

所有 commit 必须有 `Signed-off-by:`：

```bash
git commit -s
# 已提交的历史：
git rebase --signoff upstream/main
```

### B.3.4 AI Usage Policy

仓库要求明确披露 AI 辅助，见 `docs/contributing/README.md#ai-usage-policy`。

- 说明使用了哪些工具、用在哪里（代码/测试/文档）。
- 确认本人已 review，能够解释设计。
- 报告**实际运行过**的命令和结果，不能把生成内容当作测试结果。
- 未运行的检查必须明确列出。

示例：

```text
AI assistance: Used Claude Code to draft the 310P fallback patches and the
PR description. I reviewed every change, ran the commands below on the
listed hardware, and can explain the kernel-fallback trade-offs.
Validation: <commands + results + hardware + checks not run>.
```

### B.3.5 PR 数量限制

无 write 权限的贡献者最多 **5 个 open PR**。超过会被 GitHub 限制；关键工作可联系 committer 申请 bypass。

### B.3.6 提交前本地检查

| 检查项 | 命令/说明 |
| --- | --- |
| pre-commit | `pre-commit install && pre-commit run --all-files` |
| SPDX | 新文件使用 `Copyright contributors to the vLLM-Omni project` |
| forbidden imports | 库代码禁用 stdlib `re`/`base64`、pickle、HF Hub 下载 API、直接 triton/tilelang |
| `torch.cuda` | 平台适配层外不得新增 `torch.cuda.*` |
| mypy | `pre-commit run --hook-stage manual mypy-3.10` |
| test marks | 每个 `tests/**/test_*.py` 必须有 CI 等级 mark + 硬件 mark |
| markdownlint | `pre-commit run markdownlint-cli2` |
| precheck-pr | 让 coding agent 读取 `.claude/skills/precheck-pr/SKILL.md` 跑 quick/full 自检 |

注意：GitHub Actions 的 pre-commit 会 skip `check-spdx-header`、`markdownlint-cli2`、`mypy-3.10` 等 hook，**本地通过才算通过**。

### B.3.7 测试要求

- 新模型 PR：至少一个测试对比参考输出，并提供 E2E generate 路径。
- 硬件 PR：使用 `tests/helpers/mark.py` 的 `@hardware_test`。
- 310P mark 已在 `pyproject.toml` 注册。

（310P 现有测试资产与局限见 Part A A.3.8。）

真实设备测试示例：

```python
import pytest
from tests.helpers.mark import hardware_test

pytestmark = [pytest.mark.core_model, pytest.mark.npu]


@hardware_test(res={"npu": "310P"}, num_cards=1)
def test_qwen3_moe_310p_forward():
    ...
```

CPU 上的 patch-wiring 单测参考 `tests/platforms/npu/test_310p_patches.py`：

```python
pytestmark = [pytest.mark.core_model, pytest.mark.cpu]
```

真机 E2E 放 `tests/e2e/offline_inference/` 或 `tests/e2e/online_serving/`：

```bash
pytest -s -v tests/e2e/offline_inference/test_qwen3_moe.py \
  -m 'core_model and npu and 310P' --run-level core_model
```

如需进 CI，在 `.buildkite/npu/test-npu-ready.yml` 增加 `mirror_hardwares: 310p_npu_1` 的 step。

### B.3.8 新模型 PR 额外要求

- `docs/models/supported_models.md` 增加一行（架构、模型、HF 名称、Ascend NPU 列打勾）。
- `recipes/<vendor>/<model>.md`，按 `recipes/TEMPLATE.md` 和 `add-recipe` skill 编写。
- `docs/user_guide/examples/offline_inference/` 增加用户文档（如涉及命令）。
- deploy YAML + pipeline registry + 模型目录。

### B.3.9 Review 流程

- PR 提交后按 CODEOWNERS 自动路由；NPU 会打 `npu` label 并 assign `@gcanlin`。
- reviewer 每 2-3 天更新状态；7 天未 review 可以 ping。
- 需要修改会打 `action-required`。
- 本地 L1/L2 结果附上后，联系维护者加 `ready` label。
- 大改动会打 `rfc-required`。
- 冲突会有 `needs-rebase`；Mergify 仅在 `ready` + approved 时自动 rebase。

相关 owner（`.github/CODEOWNERS`）：

| 路径 | Owner |
| --- | --- |
| `vllm_omni/platforms/` | @gcanlin @tjtanaa @xuechendi |
| `vllm_omni/model_executor/models/` | @tzhouam @gcanlin @Sy0307 @amy-why-3459 @linyueqian |
| `vllm_omni/worker/` | @tzhouam @yinpeiqi @fake0fan @Sy0307 @Gaohan123 |
| `vllm_omni/config/`、`deploy/` | @lishunyang12 @alex-jw-brooks |
| `tests/` | @yenuo26 @NickCao |

---

## B.4 当前分支逐项 gap

| 改动 | 问题 | 建议 |
| --- | --- | --- |
| `vllm_omni/platforms/npu/_310p/__init__.py` 的 `is_310p` fallback | 上游 #9246 已修复 | 删除，rebase 后使用 main 实现 |
| `tools/310p_compat/sitecustomize.py` | import 期全局 monkeypatch vLLM，仅针对 0.30 import cycle；main 不需要 | 不提交到上游，仅保留为本地 0.30 环境 shim |
| `examples/offline_inference/qwen3_moe/` | 模型专用 Python 示例，违反 Examples Policy | 删除 Python 示例；使用共享 `examples/offline_inference/x_to_text/x_to_text.py`，模型差异放 `vllm_omni/model_extras/`，运行命令写入 recipe/docs |
| `vllm_omni/platforms/npu/_310p/patch/attention.py` | O(seq²) torch attention，秒级/token；属于 vllm-ascend 的 310P attention backend 问题 | 优先提到 vllm-ascend；若必须在 omni 落地，需要 config gate + 明确标注 correctness-only |
| `vllm_omni/platforms/npu/_310p/patch/device_ops.py` | `ReshapeAndCache`、`npu_moe_token_unpermute` 是 vllm-ascend 310P op 缺失；逐 token Python loop + `.item()` 很慢 | 优先提到 vllm-ascend；至少向量化并补充限制说明 |
| `vllm_omni/platforms/npu/_310p/patch/qwen3_moe.py` | patch `vllm_ascend._310p` 的 router 类 | 同上，属于 vllm-ascend 的 310P MoE 路由问题 |
| `patch/worker.py` 的 `_should_trans_nz_310p` | `except Exception: pass` 位于权重加载路径，precheck 会判 ✗ | 收窄为 `ImportError/AttributeError` 并记录日志；`weight_nz_mode=0` 应由 vllm-ascend 正式支持 |
| `vllm_omni/worker/gpu_model_runner.py` kwargs 过滤 | 通用性最好，但 main 上代码已变化（`_build_model_kwargs_extra` 在 1479 行附近） | 单独拆 `[Bugfix][Core]` PR；复用 main 已有的 `_filter_mrope_kwargs_for_model` 模式，把 `import inspect` 提到文件头 |
| `pipeline.py` / `pipeline_registry.py` / `deploy/qwen3_moe.yaml` | 为纯文本 LLM 注册单 stage pipeline，scope 未确认 | 等 RFC/issue 确认后再提 |
| `examples/.../README.md`、`run_310p.sh` | 启动脚本/环境说明有价值，但位置不对 | 移到 `recipes/Qwen/` 或 `tools/` |
| `reports/`、两篇中文分析 | 4.2 MB 图片 + 非仓库规范文档 | 从 PR 移除 |
| 所有新文件 SPDX | 写成 `vLLM project` | 改为 `vLLM-Omni project` |
| 所有 commit | 无 `Signed-off-by` | `git rebase --signoff upstream/main` |
| 无测试 | 新模型/硬件 PR 必须有测试 | CPU patch 单测 + 310P 真机 E2E + Buildkite step |
| 无 docs/recipe | 用户不可发现 | `supported_models.md` + `recipes/Qwen/Qwen3-MoE.md` |

> 交叉引用：表中 `is_310p` fallback 一行与 Part A A.2/A.6.3 第 15 条描述同一回归（vllm-ascend commit `86c44bf30` 移动 `is_310p`）。表中 `attention.py`/`device_ops.py` 的算子缺口，对应 Part A A.2 表格里的 310P FlashAttention 签名（token-major FP16 + 16 token 对齐 + FRACTAL_NZ mask）与 vLLM-Ascend 后端子集限制；Part A 从能力边界角度、本节从上游归属与代码位置角度描述同一组约束。

---

## B.5 推荐提交路线

### Step 0：先沟通（1-3 天）

1. Slack `#sig-omni` 发消息，@gcanlin（NPU/hardware）、@tzhouam（model integration），说明想 upstream Qwen3-MoE 310P。
2. 开 `[New Model]` issue（见第 B.2.4 节草稿）。
3. 维护者认可 scope 后，开 `[RFC]`，重点讨论：
   - 纯文本 LLM 是否进 omni pipeline registry；
   - 310P fallback 放 omni 还是 vllm-ascend；
   - target branch（main 0.33 vs release/v0.30.0）。

### Step 1：重建干净分支

不要在原分支硬 rebase，历史中混有 reports 和无 sign-off commit：

```bash
git remote add upstream https://github.com/vllm-project/vllm-omni.git
git fetch upstream
git checkout -b qwen3-moe-310p-clean upstream/main

# 只取需要的文件，手工适配 main 代码结构
git checkout 3dde0bb73 -- vllm_omni/worker/gpu_model_runner.py
```

### Step 2：拆成 3 个 PR

#### PR A（可独立合入，先提）

```text
[Bugfix][Core] Filter omni-only forward kwargs by model signature
```

- 文件：`vllm_omni/worker/gpu_model_runner.py` + CPU 单测。
- 单测：构造 `forward(self, input_ids, positions)` 的 dummy model，验证 omni-only kwargs 被丢弃；构造 `**kwargs` 模型，验证不丢。
- 价值：与 310P、Qwen3-MoE 解耦，维护者容易接受。

#### PR B（scope 确认后）

```text
[Hardware][Ascend][Model] Support Qwen3-MoE text models on Ascend 310P
```

- `vllm_omni/model_executor/models/qwen3_moe/pipeline.py`
- `vllm_omni/config/pipeline_registry.py`
- `vllm_omni/deploy/qwen3_moe.yaml`
- `tests/platforms/npu/test_qwen3_moe_310p_patches.py`（CPU）
- `tests/e2e/offline_inference/test_qwen3_moe.py`（310P）
- `.buildkite/npu/test-npu-ready.yml`
- `docs/models/supported_models.md`
- `recipes/Qwen/Qwen3-MoE.md`
- 仅保留 omni 侧必要 patch；`sitecustomize`、`examples/python`、重复的 `is_310p` 修复全部去掉。

#### PR C（提到 vllm-ascend）

```text
[Bugfix][310P] Add torch fallbacks for ReshapeAndCache / MoE router / attention on 310P
```

- `attention.py`、`device_ops.py`、`qwen3_moe.py`、`worker.py` 的 NZ fallback。
- 这些修改的是 `vllm_ascend._310p` 内部，放 vllm-ascend 才可持续。
- 若维护者坚持放 omni，需要在 RFC 中说明为什么不能改 vllm-ascend，并把 patch 收敛到最小、加 config gate。

### Step 3：验证并提交

```bash
# 1. 本地 lint
pre-commit install
pre-commit run --all-files

# 2. CPU patch 单测
pytest -s -v tests/platforms/npu/test_qwen3_moe_310p_patches.py -m 'core_model and cpu'

# 3. 310P 真机 E2E
pytest -s -v tests/e2e/offline_inference/test_qwen3_moe.py \
  -m 'core_model and npu and 310P' --run-level core_model

# 4. DCO
git rebase --signoff upstream/main

# 5. precheck-pr（quick 先跑，正式 review 前跑 full）
```

PR 正文建议：

```markdown
## Purpose
Add a single-stage LLM_AR pipeline for plain Qwen3-MoE text checkpoints and
enable the path on Ascend 310P (Atlas 300I Duo).

## Test Plan
**vLLM Version:** 0.33.0 (or 0.30.0 for the 310P validation image)
**vLLM-Omni Commit:** <sha>
**Hardware:** Atlas 300I Duo 310P x4, CANN 9.0.1, torch_npu 2.10.0

Commands:
```bash
pytest ...
python examples/offline_inference/x_to_text/x_to_text.py --model <path> --prompt "Hello"
```

## Test Result
- CPU patch-wiring tests: N passed
- 310P E2E: output matches reference for N tokens
- Before: first forward fails with `ReshapeAndCacheNzKernel is not found`
- After: generation works; attention fallback is correctness-first, ~X s/token
- Not run: A2/A3 (no hardware), vLLM 0.33 NPU (no 310P wheel)

AI assistance: Used Claude Code to draft patches and PR text. I reviewed all
changes and ran the commands above.
```

---

## B.6 最容易踩的 5 个坑

1. **不要直接 push 原分支开 PR**：无 merge base，CI 无法正确 diff。
2. **不要保留 `reports/` 和中文分析文档**：PR 只放代码、测试、文档、recipe。
3. **不要新增模型专用 `examples/**/*.py`**：Examples Policy blocking；走 `x_to_text.py` + `model_extras` + recipe。
4. **不要把 `sitecustomize.py` 带进上游**：import 期全局副作用，且只对 vLLM 0.30 有效。
5. **不要声称性能提升**：attention fallback 是 correctness-first，PR/issue 中要明确标注 not a performance path，否则会被要求补 benchmark 或直接质疑。

---

## B.7 关键参考

- 贡献总指南：`docs/contributing/README.md`
- Issue 模板：`.github/ISSUE_TEMPLATE/`
- PR 模板：`.github/PULL_REQUEST_TEMPLATE.md`
- 测试规范：`docs/contributing/ci/test_writing_guide.md`
- 新模型指南：`docs/contributing/model/adding_omni_model.md`
- 平台设计约束：`docs/design/module/execution_platforms.md`
- 治理/committer：`docs/community/governance.md`
- 预检 skill：`.claude/skills/precheck-pr/SKILL.md`
- 310P 测试先例：`tests/platforms/npu/test_310p_patches.py`
- 310P CI step：`.buildkite/npu/test-npu-ready.yml`

---

## B.8 Qwen3-ASR-310P 专项（2026-11-12 调研）

### B.8.1 关键结论

**如果目标只是“在 310P 上跑独立 ASR（audio → text）”，第一步不是给 vllm-omni 提 issue，而是走 vLLM + vllm-ascend。**

证据：

1. vllm-omni 的 `docs/models/supported_models.md` 没有独立的 Qwen3-ASR 条目；Qwen3-ASR 只作为 AURA Omni、JoyAI-VL-Interaction 的 stage 0 出现。
2. vllm-omni RFC #5722 维护者原话：
   > If you just want a transcript, you don't need vLLM-Omni.
   > `vllm serve Qwen/Qwen3-ASR-1.7B` already serves `/v1/audio/transcriptions` today.
3. vllm-ascend **v0.23.0 文档已经明确支持 Atlas 300I DUO（310P）**：
   - 单卡 48 GB 跑 BF16 Qwen3-ASR-1.7B
   - 镜像：`vllm-ascend:nightly-releases-v0.23.0-310p`（或更新的 `-310p`）
   - 启动：`vllm serve ... --tensor-parallel-size 1 --dtype float16 --max-model-len 4096`
4. vllm-ascend 从 **v0.30.0 起将 Qwen3-ASR-1.7B 标记为 Unmaintained（🔴）**：
   - PR #19784（2026-10-26 合入）：把教程替换为 discontinued 通告，指向 v0.23.0 历史文档。
   - 支撑矩阵仍保留该行，但状态为 🔴 Unmaintained：”previously supported, now discontinued and no longer maintained. Issues will not be fixed. Do not use in new projects.”
5. 310P 适配本身是 vllm-ascend PR #10257（v0.22/v0.23 时期）做的，Related issue #9712。
6. vllm-ascend tracking issue #6689 `[Feature]: Verify / Support Qwen/Qwen3-ASR-1.7B` 仍 open，但最后实质回复在 2026-06。

**因此你的工作更可能是“在 v0.30+ 恢复/回归验证 310P 支持”，而不是“给 vllm-omni 新增模型”。**

### B.8.2 按目标选择提交对象

| 目标 | 正确仓库 | 动作 |
| --- | --- | --- |
| 独立 ASR 服务（`/v1/chat/completions` 或 `/v1/audio/transcriptions`） | vllm-ascend | 先评论 #6689 或新开 issue，要求恢复/验证 310P 支持 |
| ASR + 对齐器（word-level timestamps） | vllm-omni | 评论 RFC #5722；这是 omni 的合理场景 |
| ASR → LLM → TTS 自定义 pipeline | vllm-omni | 开 `[Model]` / `[Hardware][Ascend][Model]` issue，说明 310P 依赖 |
| 已有 AURA / JoyAI pipeline 在 310P 上跑 | vllm-omni + vllm-ascend | omni issue 描述 pipeline；runtime gap 转 vllm-ascend |

### B.8.3 推荐操作顺序

1. **先建立 baseline**：用 vllm-ascend v0.23.0 `-310p` 镜像跑通历史文档配置，确认模型在你的 310P 上确实可用。
2. **再复现 v0.30+ 失败**：记录完整 trace、镜像 tag、CANN/torch_npu/vLLM/vllm-ascend 版本。
3. **对比差异**：如果 v0.23.0 能跑、v0.30.0 不能跑，这是 regression，不是 new model。
4. **提 vllm-ascend issue**（不是 vllm-omni），标题建议：
   ```text
   [Feature][310P] Restore / verify Qwen3-ASR-1.7B support on Atlas 300I DUO after v0.30.0 deprecation
   ```
   内容包含：v0.23.0 known-good 配置、v0.30.0 失败 trace、硬件与版本、是否愿意提交 PR。
5. **维护者同意后再提 PR**：优先恢复 docs + 310P e2e 配置；如果代码确有回归，再修代码。
6. **只有需要 omni 组合能力时**，再向 vllm-omni 提 issue/PR。

### B.8.4 vllm-ascend issue 草稿

```markdown
Title: [Feature][310P] Restore / verify Qwen3-ASR-1.7B support on Atlas 300I DUO

### Background
Qwen3-ASR-1.7B was documented as supported on Atlas 300I DUO (310P) in the
v0.23.0 tutorial (one 48 GB NPU, TP=1, dtype=float16, max-model-len=4096).
It was marked Unmaintained (🔴) in v0.30.0 by #19784, and the tutorial was
replaced with a discontinuation notice.

### Current behavior on 310P
- Image: <quay.io/ascend/vllm-ascend:...-310p>
- CANN: <...>, torch_npu: <...>, vLLM: <...>, vllm-ascend: <...>
- Command: vllm serve Qwen/Qwen3-ASR-1.7B --tensor-parallel-size 1 --dtype float16 --max-model-len 4096 ...
- Result: <full traceback / error>

### Known-good baseline
The v0.23.0 documented command works / fails as follows: <details>.

### Request
1. Is the Unmaintained status for 310P final, or can support be restored?
2. If code still works and only tests/docs are missing, I can submit a PR to
   re-enable the 310P tutorial and add a 310P e2e config.
3. Which target branch should this use (release/v0.30.0 vs main)?
```

### B.8.5 版本提醒

- vllm-omni main 目标是 vLLM 0.33.0；vllm-ascend 最新 release 是 v0.32.0rc1，仍存在版本差。
- 在 vllm-ascend 恢复 310P 支持之前，vllm-omni 侧的 310P PR 无法完整验证。
- 如果业务可以先交付，直接用 v0.23.0 / v0.25.x 的 `-310p` 栈，比等待 main 恢复更现实。

> 交叉引用：Part A A.8 的"vLLM-Ascend 版本对齐"风险与本节一致；Part A A.3.9 记录的其他 Omni/TTS/ASR 模型无 310P 补丁，也解释了为什么 Qwen3-ASR 的第一步应走 vLLM + vllm-ascend。

---
