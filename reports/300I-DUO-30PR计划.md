# 300I DUO（Ascend 310P）30 个 PR 实施计划

> 版本：2026-11-13
> 依据：[310P-优化Roadmap.md](310P-优化Roadmap.md)、[300I-DUO-适配与优化分析.md](300I-DUO-适配与优化分析.md) §A.3-§A.8、[vLLM-Omni-架构与技术报告.md](vLLM-Omni-架构与技术报告.md) 第 II 部分 §13
> 范围：Atlas 300I DUO / Ascend 310P3，Qwen3-TTS 为主线，逐步扩展到 TTS 矩阵、3B Omni 与图像。
> 说明：本文件是本地实施计划，不是上游文档；每个 PR 提交前仍需单独开 issue/PR 并按社区规范自检。

---

## 0. 规划原则

1. **一个 PR 做一件事**：可独立 review、独立回滚、独立测试；目标 300–800 行（不含测试/配置/文档），超过 1,000 行必须拆分。
2. **每个 PR 自带证据**：测试、精度/性能数据、复现命令；不能只写“已适配”。
3. **仓库归属明确**：310P 的 ATB/NNAL 算子、attention 后端、量化优先上游到 `vllm-ascend`；vLLM-Omni 只保留平台接线、模型级 patch、pipeline、deploy、测试和文档。
4. **依赖顺序可见**：每个 PR 标注前置 PR；未满足依赖不提前提交。
5. **社区规范**：标题前缀、DCO `Signed-off-by`、AI 使用披露、`precheck-pr`、无 write 权限最多 5 个 open PR。
6. **失败要显式**：310P 不支持的算子/模型必须 fail-fast 或明确 fallback，不允许静默走错路径。

---

## 1. 30 个 PR 总览

| ID | 标题 | 仓库 | 阶段 | 主要范围 | 依赖 | 规模 |
| --- | --- | --- | --- | --- | --- | --- |
| PR-01 | `[CI/Build] Add 310P Buildkite ready pipeline and 310p_npu_1 preset` | omni | P0 | `.buildkite/npu/`、mirror preset | #6806 | 100–200 |
| PR-02 | `[CI/Build] Add 310P Qwen3-TTS 0.6B/1.7B smoke E2E` | omni | P0 | `tests/e2e/`、Buildkite | PR-01 | 200–400 |
| PR-03 | `[CI/Build] Add 310P TTS accuracy gate (WER/CER/SIM)` | omni | P0 | `tests/dfx/accuracy/`、数据集 | PR-02 | 300–500 |
| PR-04 | `[CI/Build] Add 310P perf baseline collection (RTF/first-packet/tok/s)` | omni | P0 | `tests/dfx/perf/`、artifact | PR-02 | 200–400 |
| PR-05 | `[Doc] Add 310P version matrix, installation and support status` | omni | P0 | `docs/getting_started/installation/npu/`、`supported_models.md` | PR-01–04 | 150–300 |
| PR-06 | `[Bugfix][NPU] Add regression test for is_310p helper relocation` | omni | P0 | `tests/platforms/npu/` | 无 | 80–150 |
| PR-07 | `[Hardware][Ascend] Add 310P capability probe and fail-fast diagnostics` | omni | P1a | `platforms/npu/_310p/`、`platform.py` | 无 | 200–350 |
| PR-08 | `[Hardware][Ascend] Gate 310P ATB fallbacks behind explicit config` | omni | P1a | `_310p/patch/`、config | PR-07 | 200–350 |
| PR-09 | `[Hardware][Ascend] Vectorize ReshapeAndCache torch fallback` | ascend | P1a | `vllm_ascend/_310p/ops/` 或 omni patch | PR-08 | 200–400 |
| PR-10 | `[Hardware][Ascend] Vectorize MoE token-unpermute fallback` | ascend | P1a | `vllm_ascend/_310p/ops/` 或 omni patch | PR-08 | 150–300 |
| PR-11 | `[Hardware][Ascend] Add 310P MoE router fallback selection` | ascend | P1a | `vllm_ascend/_310p/fused_moe/` 或 omni patch | PR-08 | 150–300 |
| PR-12 | `[Bugfix][Core] Filter omni-only forward kwargs by model signature` | omni | P1a | `vllm_omni/worker/gpu_model_runner.py` | 无 | 100–200 |
| PR-13 | `[Hardware][Ascend] Add 310P attention backend selection and fallback metrics` | ascend/omni | P1a | `_310p/attention/`、`_310p/patch/attention.py` | PR-08 | 300–500 |
| PR-14 | `[Hardware][Ascend][Model] Make Talker-MTP sampling graph-safe` | omni | P1b | `qwen3_tts_talker.py`、`qwen3_code_predictor.py`、`_310p/patch/qwen3_tts.py` | PR-02、PR-13 | 400–700 |
| PR-15 | `[Hardware][Ascend][Model] Add graph-safe sampler unit tests` | omni | P1b | `tests/platforms/npu/` | PR-14 | 150–300 |
| PR-16 | `[Hardware][Ascend][Model] Bucket reference-audio encoder by duration on NPU` | omni | P1b | `_310p/patch/qwen3_tts.py`、`npu/models/qwen3_tts.py` | PR-14 | 300–500 |
| PR-17 | `[Hardware][Ascend][Model] Precompute and cache Mel spectrograms` | omni | P1b | `_310p/patch/qwen3_tts.py` | PR-16 | 150–300 |
| PR-18 | `[Hardware][Ascend] Add W8A8 quantization for Talker linear layers` | ascend+omni | P1b | `vllm_ascend/_310p/quantization/`、`deploy/qwen3_tts*.yaml` | PR-09–11、PR-14 | 400–800 |
| PR-19 | `[Hardware][Ascend] Add W8A8 accuracy calibration and gates for TTS` | omni | P1b | `tests/dfx/accuracy/`、校准配置 | PR-18 | 200–400 |
| PR-20 | `[Hardware][Ascend][Model] Split Talker/Code2Wav across two 310P chips` | omni | P1b | `deploy/qwen3_tts_310p.yaml`、stage config | PR-16–18 | 200–400 |
| PR-21 | `[Hardware][Ascend] Expand CodePredictor/Code2Wav batch buckets` | omni | P2 | `qwen3_code_predictor.py`、`code2wav_graph.py` | PR-20 | 300–500 |
| PR-22 | `[Hardware][Ascend][Model] Enable prefix caching for fixed prompts/voice descriptions` | omni | P2 | `deploy/qwen3_tts*.yaml` | PR-20 | 150–300 |
| PR-23 | `[Hardware][Ascend][Model] Port CosyVoice3 0.5B Flow/HiFT graphs to 310P` | omni | P2 | `npu/models/cosyvoice3_graph.py`、`cosyvoice2_dit_attn.py`、`_310p/patch/` | PR-21 | 500–900 |
| PR-24 | `[Hardware][Ascend][Model] Add Kokoro-82M 310P operator checks and graph capture` | omni | P2 | 模型 patch、deploy、recipe | PR-21 | 300–600 |
| PR-25 | `[Hardware][Ascend][Model] Add MOSS-TTS-Nano 310P support` | omni | P2 | 模型 patch、deploy、recipe | PR-21 | 400–800 |
| PR-26 | `[Hardware][Ascend][Model] Add Qwen2.5-Omni-3B 310P audio/vision encoder support` | omni | P3 | 模型 patch、runner、deploy | PR-20、PR-23 | 500–900 |
| PR-27 | `[Hardware][Ascend][Model] Add Qwen2.5-Omni-3B 310P talker/code2wav and streaming` | omni | P3 | pipeline、deploy、E2E | PR-26 | 400–800 |
| PR-28 | `[Hardware][Ascend] Add 310P DiT attention backend and VAE Conv FRACTAL_Z` | ascend+omni | P4 | `vllm_ascend/_310p/attention/`、`platforms/npu/platform.py` | PR-08、PR-13 | 600–1000 |
| PR-29 | `[Hardware][Ascend][Model] Add Z-Image / FLUX.2-klein 4B 310P support` | omni | P4 | 模型 patch、deploy、recipe、E2E | PR-28 | 500–900 |
| PR-30 | `[Doc] Add 310P validated model list, recipes index and release checklist` | omni | Release | `supported_models.md`、`recipes/`、release notes | 全部 | 200–400 |

---

## 2. 分阶段详情

### P0 · 基线与 CI（PR-01 – PR-06）

**目标**：让 310P 从“有 patch 测试”变成“有真机 gate、有精度/性能基线、有版本文档”。

#### PR-01 · 310P Buildkite ready pipeline

- **仓库**：vllm-omni
- **目的**：在 #6806 基础上落地 310P ready 队列与 `310p_npu_1` preset。
- **范围/文件**：`.buildkite/npu/test-npu-ready.yml`、`.buildkite/common/ci_mirror_hardwares.yml`、必要时 `tools/pre_commit/check_buildkite.py`。
- **验证**：pipeline 能上传并在 310P 队列跑通一个空/最小 step；A2/A3 job 不变。
- **风险**：310P 队列可用性；先与 SIG-CI 确认。
- **社区标题**：`[CI/Build] Add 310P Buildkite ready pipeline and 310p_npu_1 preset`

#### PR-02 · Qwen3-TTS 310P smoke E2E

- **仓库**：vllm-omni
- **目的**：在 310P 真机跑通 0.6B/1.7B 单请求，输出非空。
- **范围/文件**：`tests/e2e/offline_inference/test_qwen3_tts_310p.py`、`tests/helpers/mark.py`（已支持 `310P`）、Buildkite step。
- **验证**：`pytest -m 'core_model and npu and 310P' --run-level core_model`；启动、生成、退出码。
- **风险**：模型权重下载/缓存；CI 上使用 dummy 或小 checkpoint 需明确。

#### PR-03 · TTS 精度 gate

- **仓库**：vllm-omni
- **目的**：WER/CER（文本）、SIM（音色）与 910B 基线对比。
- **范围/文件**：`tests/dfx/accuracy/`、数据集配置、参考输出。
- **验证**：阈值内通过；失败时输出差异样本。
- **风险**：FP16 精度容差需要实测确定，不能直接复用 BF16 阈值。

#### PR-04 · 性能基线

- **仓库**：vllm-omni
- **目的**：采集 RTF、首包、tok/s、显存峰值，按 device 记录。
- **范围/文件**：`tests/dfx/perf/`、`run_benchmark.py` 配置、artifact 上传。
- **验证**：基线可重复；至少 1 warmup + 3 次测量。
- **风险**：310P 机器负载波动；记录 host load 与并发。

#### PR-05 · 版本矩阵与安装文档

- **仓库**：vllm-omni
- **目的**：明确 CANN / torch_npu / vLLM / vllm-ascend / vllm-omni 的对应关系。
- **范围/文件**：`docs/getting_started/installation/npu/`、`docs/models/supported_models.md`、`docs/...`。
- **验证**：按文档从零安装可复现；版本冲突场景有说明。
- **风险**：vLLM 0.33 暂无 310P wheel；文档需区分“可验证”和“待发布”。

#### PR-06 · is_310p 回归测试

- **仓库**：vllm-omni
- **目的**：防止 vllm-ascend 再次移动 `is_310p` 导致静默走错 worker。
- **范围/文件**：`tests/platforms/npu/test_310p_patches.py` 或新测试。
- **验证**：旧路径/新路径/缺失路径三种情况；缺失时 fail-fast。
- **备注**：代码修复已由 #9246 合入；本 PR 只补回归测试。

---

### P1a · 运行时正确性与算子（PR-07 – PR-13）

**目标**：把 310P 的隐式 monkeypatch 变成显式、可诊断、可度量的能力。

#### PR-07 · 能力探测与 fail-fast

- **目的**：启动时探测 310P 缺失的 ATB/NNAL 算子、dtype、图能力，输出清晰错误。
- **范围/文件**：`vllm_omni/platforms/npu/_310p/__init__.py`、`platforms/npu/platform.py`、错误信息。
- **验证**：CPU mock 测试（fake `vllm_ascend`）+ 真机 smoke。
- **风险**：探测本身不能引入明显启动开销。

#### PR-08 · ATB fallback 显式配置

- **目的**：`ReshapeAndCache` / MoE router / attention fallback 必须由 `additional_config` 显式开启，不允许静默替换。
- **范围/文件**：`_310p/patch/__init__.py`、`device_ops.py`、`attention.py`、config 解析。
- **验证**：默认行为、显式开启、显式关闭三种路径；patch 幂等。
- **风险**：配置键命名需要与 vllm-ascend 对齐。

#### PR-09 · ReshapeAndCache 向量化

- **仓库**：优先 vllm-ascend；若短期只能放 omni，则改 `_310p/patch/device_ops.py`。
- **目的**：去掉逐 token Python loop 和 `.item()`，改为 `index_copy_`/扁平视图。
- **验证**：与参考实现逐元素对比；decode/prefill 两种 shape；benchmark。
- **风险**：310P cache 布局 `[blocks, hidden/16, block_size, 16]` 的索引正确性。

#### PR-10 · MoE token-unpermute 向量化

- **仓库**：同 PR-09。
- **目的**：用 `index_select` + 加权和替代逐 token 循环。
- **验证**：top-k=1/2/4/8；bf16/fp16；与 ATB 参考对比。
- **风险**：310P 上 bf16 不可用，需固定 fp16。

#### PR-11 · MoE router fallback

- **仓库**：优先 vllm-ascend。
- **目的**：`MoeGatingTopKSoftmax` 缺失时走 generic softmax+topk。
- **验证**：router 输出与参考一致；renormalize 开关；不同 top-k。
- **风险**：数值差异；需记录容差。

#### PR-12 · kwargs 过滤

- **目的**：omni runner 不再把 `model_intermediate_buffer` 等 omni-only kwargs 传给普通 vLLM checkpoint。
- **范围/文件**：`vllm_omni/worker/gpu_model_runner.py`。
- **验证**：dummy model（无 `**kwargs`）与 omni model（有 `**kwargs`）两种单测。
- **风险**：不能误删 omni 模型需要的 kwargs；签名缓存要正确。

#### PR-13 · attention 后端选择与指标

- **目的**：310P 上明确选择 SDPA/torch fallback，记录后端、seq len、耗时；避免静默 O(seq²)。
- **范围/文件**：`_310p/patch/attention.py`、`platforms/npu/platform.py`、metrics。
- **验证**：prefill/decode/chunked prefill；fallback 触发日志；性能 smoke。
- **风险**：fallback 是 correctness-first，不能宣称性能路径。

---

### P1b · Qwen3-TTS 性能（PR-14 – PR-20）

**目标**：1.7B RTF ≤ 0.3、首包 ≤ 300 ms；0.6B 高并发。

#### PR-14 · Talker-MTP 图安全采样

- **目的**：预生成 uniform，图内确定性 top-k + inverse-CDF/Gumbel，把 Talker-MTP 从 eager 变 ACLGraph。
- **范围/文件**：`qwen3_tts_talker.py`、`qwen3_code_predictor.py`、`_310p/patch/qwen3_tts.py`。
- **验证**：确定性（固定 seed 同输出）、图捕获成功、RTF 对比。
- **风险**：采样语义变化；必须与 CUDA 侧 `sample_code_topk_gumbel` 对齐。

#### PR-15 · 图安全采样单测

- **目的**：覆盖 top-k、Gumbel、uniform 预生成、图内外一致性。
- **范围/文件**：`tests/platforms/npu/test_qwen3_tts_sampler_310p.py`。
- **验证**：CPU/ fake NPU 单测；固定 seed 可复现。
- **依赖**：PR-14。

#### PR-16 · 参考音频 bucket + NPU

- **目的**：按 1s/3s/5s/10s 分桶 padding，Mimi encoder 从 CPU 回 NPU。
- **范围/文件**：`_310p/patch/qwen3_tts.py`、`npu/models/qwen3_tts.py`。
- **验证**：不同音频长度 bucket 命中；encoder 输出与 CPU 参考一致；首包/RTF。
- **风险**：动态 shape 仍可能触发重编译；bucket 边界要覆盖。

#### PR-17 · Mel 预计算缓存

- **目的**：固定参考音频/音色的 mel 只算一次，避免每请求 CPU STFT。
- **范围/文件**：`_310p/patch/qwen3_tts.py`。
- **验证**：cache hit/miss；数值一致；内存上限。
- **风险**：缓存 key 要包含音频内容 hash，不能只按路径。

#### PR-18 · W8A8 Talker 量化

- **仓库**：vllm-ascend（量化算子）+ vllm-omni（配置/模型接线）。
- **目的**：Talker/Code2Wav 线性层 W8A8，吞吐约 2×、权重减半。
- **范围/文件**：`vllm_ascend/_310p/quantization/`、`deploy/qwen3_tts*.yaml`。
- **验证**：WER/SIM 在容差内；RTF/显存对比；回退路径。
- **风险**：量化校准数据、精度损失；需要 PR-19 的 gate。

#### PR-19 · W8A8 精度校准与 gate

- **目的**：为 TTS 建立量化前后对比，防止“快但不可用”。
- **范围/文件**：`tests/dfx/accuracy/`、校准配置。
- **验证**：WER/SIM、长音频、不同说话人。
- **依赖**：PR-18。

#### PR-20 · 双 chip stage 拆分

- **目的**：Talker chip0 / Code2Wav chip1，stage 间只传 codec chunk，避免 PCIe 上的 TP 通信。
- **范围/文件**：`deploy/qwen3_tts_310p.yaml`、stage config、文档。
- **验证**：双 chip E2E；首包/RTF；单 chip 回退。
- **风险**：300I DUO 无 HCCS，PCIe 传输是瓶颈；需测量 chunk 大小。

---

### P2 · TTS 模型矩阵（PR-21 – PR-25）

**目标**：从单模型扩展到可复用的 TTS 矩阵。

#### PR-21 · 扩大 batch bucket

- **目的**：CodePredictor/Code2Wav 的 `_bucket_sizes` 扩展，提升高并发吞吐。
- **范围/文件**：`qwen3_code_predictor.py`、`code2wav_graph.py`、deploy。
- **验证**：batch 1/2/4/8；图捕获；吞吐/显存。
- **风险**：bucket 过多导致编译/显存膨胀。

#### PR-22 · prefix caching

- **目的**：固定 system prompt/音色描述场景开启 prefix cache，降低 prefill。
- **范围/文件**：`deploy/qwen3_tts*.yaml`。
- **验证**：cache hit rate、首包、正确性。
- **风险**：310P 上 prefix cache 收益需实测，不能默认全开。

#### PR-23 · CosyVoice3 0.5B

- **目的**：Flow Euler + HiFT 精确图移植到 310P。
- **范围/文件**：`npu/models/cosyvoice3_graph.py`、`cosyvoice2_dit_attn.py`、`_310p/patch/cosyvoice3.py`、deploy、recipe、E2E。
- **验证**：音质/WER、RTF、首包；与 910B 对比。
- **风险**：FP16、FIA mask、HiFT 图；可能需要拆成多个 PR。

#### PR-24 · Kokoro-82M

- **目的**：极小模型高并发样板；核查 LSTM/iSTFT 等算子在 310P 的可用性。
- **范围/文件**：模型 patch、deploy、recipe、E2E。
- **验证**：算子可用性、图捕获、并发吞吐。
- **风险**：非 AR 结构，可能需要 CPU/自定义算子。

#### PR-25 · MOSS-TTS-Nano

- **目的**：复用 CodePredictor/Code2Wav 图设施，增加一个 TTS 模型。
- **范围/文件**：模型 patch、deploy、recipe、E2E。
- **验证**：E2E、WER/SIM、RTF。
- **风险**：模型结构差异；先做最小闭环。

---

### P3 · 小 Omni（PR-26 – PR-27）

**目标**：310P 上唯一的现实 Omni 入口：Qwen2.5-Omni-3B。

#### PR-26 · Qwen2.5-Omni-3B 编码器

- **目的**：音频/视觉编码器在 310P 的 FP16 算子验证。
- **范围/文件**：模型 patch、runner、deploy、E2E。
- **验证**：ASR/语音问答最小闭环；编码器输出与参考对比。
- **风险**：Whisper 类 conv/attention 算子；先用短音频。

#### PR-27 · Qwen2.5-Omni-3B talker/code2wav + 流式

- **目的**：复用 Qwen3-TTS 的 code2wav 图与 chunk 流式，完成语音输出。
- **范围/文件**：pipeline、deploy、E2E、recipe。
- **验证**：语音问答端到端、首包、短回复 tok/s。
- **风险**：stage 拆分与流式时序；依赖 PR-20 的双 chip 经验。

---

### P4 · 扩散/图像（PR-28 – PR-29）

**目标**：310P 的低成本文生图能力。

#### PR-28 · DiT attention + VAE Conv

- **仓库**：vllm-ascend（attention/VAE 算子）+ vllm-omni（平台接线）。
- **目的**：310P DiT attention 后端（SDPA 或 aclnn fused）；VAE Conv FRACTAL_Z；ACLGraph。
- **范围/文件**：`vllm_ascend/_310p/attention/`、`vllm_omni/platforms/npu/platform.py`、`diffusion/attention/`。
- **验证**：单层 attention 精度；512² 端到端；s/image。
- **风险**：MindIE-SD 可用性；可能需要拆成 attention/VAE 两个 PR。

#### PR-29 · Z-Image / FLUX.2-klein 4B

- **目的**：4–6B 图像模型在 512–768 的闭环。
- **范围/文件**：模型 patch、deploy、recipe、E2E。
- **验证**：CLIP/FID、512²×8 步 ≤ 5 s、768² ≤ 10 s。
- **风险**：FP16 数值；VAE 显存；先做一个模型，另一个跟进。

---

### Release · 发布收口（PR-30）

#### PR-30 · validated model list + recipes + release checklist

- **目的**：每个 release 发布 310P 已验证模型、recipe、版本矩阵、已知限制。
- **范围/文件**：`docs/models/supported_models.md`、`recipes/`、`docs/...`。
- **验证**：文档中的命令可复现；support matrix 与 CI 一致。
- **风险**：不要把 Experimental 写成 Supported；未验证模型明确标注。

---

## 3. 依赖关系

```text
P0
PR-01 ─┬─ PR-02 ─┬─ PR-03
       │         └─ PR-04
       └─ PR-05
PR-06（独立）

P1a
PR-07 ── PR-08 ─┬─ PR-09
                ├─ PR-10
                ├─ PR-11
                └─ PR-13
PR-12（独立）

P1b
PR-02/PR-13 ── PR-14 ─┬─ PR-15
                      ├─ PR-16 ── PR-17
                      └─ PR-18 ── PR-19
PR-16/17/18 ── PR-20

P2
PR-20 ─┬─ PR-21 ─┬─ PR-23
       │         ├─ PR-24
       │         └─ PR-25
       └─ PR-22

P3
PR-20/23 ── PR-26 ── PR-27

P4
PR-08/13 ── PR-28 ── PR-29

Release
全部 ── PR-30
```

---

## 4. 社区提交规范（每个 PR 必查）

### 4.1 标题前缀

| 前缀 | 用于 |
| --- | --- |
| `[CI/Build]` | Buildkite、镜像、测试流水线 |
| `[Doc]` | 文档、recipe、support matrix |
| `[Bugfix][NPU]` | 310P 平台 bug |
| `[Bugfix][Core]` | runner/core 逻辑 bug |
| `[Hardware][Ascend]` | 310P 平台/算子/patch |
| `[Hardware][Ascend][Model]` | 310P 模型适配/优化 |

### 4.2 每个 PR 的检查清单

- [ ] 标题前缀正确，含模型名（`[Model]` / `[Hardware][Ascend][Model]`）。
- [ ] PR 正文包含 `Purpose` / `Test Plan` / `Test Result`；注明 vLLM 版本和 Omni commit。
- [ ] 附测试命令、硬件、软件版本、实际输出；未跑的检查明确列出。
- [ ] 新增/修改行为有测试；修 bug 有回归测试。
- [ ] DCO `Signed-off-by`；AI 辅助已披露。
- [ ] 本地 `pre-commit run --all-files` 通过；跑过 `precheck-pr`。
- [ ] 新增/修改用户行为有文档；新模型有 recipe 和 support matrix 更新。
- [ ] 控制在 300–800 行；>1,000 行拆分。
- [ ] 不新增模型专用 `examples/**/*.py`；走共享入口 + recipe。
- [ ] 310P 不支持的路径必须 fail-fast 或显式 fallback，不能静默。

### 4.3 仓库差异

| 仓库 | 模板/要求 |
| --- | --- |
| `vllm-omni` | PR 模板 `Purpose/Test Plan/Test Result`；DCO；AI 披露；5 个 open PR 限制；`precheck-pr` |
| `vllm-ascend` | 模板 `What this PR does / why we need it?`、`Does this PR introduce any user-facing change?`、`How was this patch tested?`；注明 vLLM/vLLM-Ascend 版本；DCO |

### 4.4 建议的提交节奏

1. **P0 先合**：PR-01–06，建立 gate 和基线；没有这些，后续 PR 的收益无法证明。
2. **P1a 并行**：PR-07–13 可由不同人并行；PR-08 是 PR-09/10/11/13 的前置。
3. **P1b 串行**：PR-14 是 TTS 性能的核心，先合；PR-18 量化依赖 PR-09–11。
4. **P2/P3/P4**：每个模型一个 PR，先做最小闭环，再补性能/量化。
5. **PR-30 最后**：所有 validated 模型和版本矩阵收口。

---

## 5. 与 roadmap 的映射

| roadmap 工作流 | 对应 PR |
| --- | --- |
| W1 CI 与基线 | PR-01 – PR-06 |
| W2 TTS 性能 | PR-07 – PR-22 |
| W3 TTS 模型矩阵 | PR-23 – PR-25 |
| W4 量化 | PR-18 – PR-19 |
| W5 小 Omni | PR-26 – PR-27 |
| W6 扩散/图像 | PR-28 – PR-29 |
| W7 文档与发布 | PR-05、PR-30 |

---

## 6. 未纳入 30 个 PR 的后续项

以下内容有价值，但优先级低于本计划的 30 个 PR，建议作为 P5/后续 wave：

- Fish Speech S2 310P（与 PR-25 同构，可复用 codec 图设施）。
- SDXL 310P（与 PR-29 共用 DiT 后端）。
- MiniCPM-o 4.5（约 8B，等 Qwen2.5-Omni-3B 验证后再评估）。
- Wan2.2-TI2V-5B / SANA-Video 2B（480p 实验）。
- pi0 / GR00T N1.7 3B（边缘策略，场景明确后再做）。
- Qwen3-ASR 310P（vllm-ascend v0.30.0 已标记 Unmaintained；先在 vllm-ascend 恢复支持，不在本计划内）。
- MRv2 on 310P（跟随 #9446；当前 310P 停留在 V1 runner）。

---

## 7. 上游归属与可合入性结论

> **结论：不能把 30 个 PR 的代码全部合入 vllm-omni。**
> 约 23 个 PR 的目标仓库是 vllm-omni（其中 9 个有条件），3 个必须走 vllm-ascend，4 个需要拆成“vllm-ascend 实现 + vllm-omni 接线”；另有若干本地 workaround 不应提交。

### 7.1 分类

| 类别 | PR | 数量 | 目标仓库 | 说明 |
| --- | --- | --- | --- | --- |
| **A1 · omni 直接** | PR-01 – PR-06、PR-12、PR-15、PR-17、PR-19 – PR-22、PR-30 | 14 | vllm-omni | CI、测试、文档、deploy、通用 runner 修复；风险低 |
| **A2 · omni 有条件** | PR-07、PR-14、PR-16、PR-23 – PR-27、PR-29 | 9 | vllm-omni（依赖 vllm-ascend） | 模型/平台 patch；需要 model owner、310P 算子或 CI 支持 |
| **B · ascend-only** | PR-09、PR-10、PR-11 | 3 | vllm-ascend | 310P op 缺失/向量化；不要提交到 vllm-omni |
| **C · 拆分** | PR-08、PR-13、PR-18、PR-28 | 4 | vllm-ascend + vllm-omni | 算子/后端在 ascend，配置/接线/测试在 omni |
| **合计** | | **30** | | |

### 7.2 为什么不能全部进 vllm-omni

1. **仓库职责**：vllm-omni 是 vllm-ascend 的消费者；310P 的 ATB/NNAL 算子、attention 后端、量化、VAE/DiT 内核属于 vllm-ascend。把这些 patch 长期放在 `vllm_omni/platforms/npu/_310p/` 会与 vllm-ascend 内部实现耦合，升级即冲突。
2. **scope**：vllm-omni 的支持模型列表是 omni/TTS/diffusion/VLA；纯文本 Qwen3-MoE 单 stage pipeline 不在已列支持范围，维护者可能要求走 vLLM/vllm-ascend。
3. **版本**：vllm-omni main 对齐 vLLM 0.33；310P 的 vllm-ascend wheel 目前是 0.30，main 上的 310P PR 无法完整验证。
4. **CI**：310P 真机 gate 依赖 #6806；没有 CI 的硬件 PR 很难被接受。
5. **示例政策**：模型专用 `examples/**/*.py` 是 blocking；必须走共享入口 + recipe。
6. **模型状态**：Qwen3-ASR 在 vllm-ascend v0.30.0 被标记 Unmaintained，不能作为 vllm-omni 的新模型贡献。

### 7.3 不应提交到上游的本地代码

- `tools/310p_compat/sitecustomize.py`：import 期全局 patch，只适用于 vLLM 0.30 import cycle。
- 纯文本 Qwen3-MoE 的 `pipeline_registry`/`deploy` 注册：scope 未确认。
- `examples/offline_inference/qwen3_moe/*.py`：模型专用示例，违反示例政策。
- Qwen3-ASR 310P 适配：等 vllm-ascend 恢复支持后再议。
- `reports/**` 下的分析文档、roadmap、30PR 计划：本地材料，不作为上游 PR 内容。
- 针对 vLLM 0.30 / vllm-ascend 0.30 的版本 workaround：主分支不接受。

### 7.4 合入前置条件

- [ ] RFC 通过（#8264 Q4 roadmap / 本 310P roadmap）。
- [ ] 310P CI 队列与机器可用（#6806）。
- [ ] 目标 vLLM 版本有 310P 的 vllm-ascend wheel。
- [ ] NPU owner（@gcanlin 等）与 model owner 同意 scope/归属。
- [ ] 每个 PR 有 310P 真机 accuracy/perf 证据。
- [ ] 不使用模型专用示例；docs/recipe/support matrix 同步。
- [ ] DCO、AI 披露、precheck-pr、≤1000 行。

### 7.5 如果强行全部放 omni 的风险

- 与 vllm-ascend 内部实现重复/冲突，升级即坏；
- 维护者以 out-of-scope 或 patch 归属拒绝；
- 310P 无 CI，回归无法发现；
- 模型专用示例/纯文本 pipeline 被要求删除；
- 长期维护成本落在 omni，而不是硬件后端。

> 推荐策略：**按仓库拆，不按“全部进 omni”做**。omni 负责平台接线、模型 patch、pipeline/deploy、测试、文档；vllm-ascend 负责 310P 算子/后端/量化；两边各自走 RFC/PR 流程。

---

## 8. 备注

- 本计划的 30 个 PR 是**建议拆分**，实际提交时以维护者反馈为准；如果某个 PR 被要求合并/拆分，按社区意见调整。
- 算子/attention/量化类 PR 的仓库归属（vllm-omni vs vllm-ascend）需要在 RFC 反馈期内确认；本计划默认优先上游 vllm-ascend。
- 所有性能数字必须在 310P 真机、固定版本、固定并发下测量；不能用 910B 或估算值替代。
