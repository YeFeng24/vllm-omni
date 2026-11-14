# [RFC]: vLLM-Omni Ascend 300I Duo (310P) Optimization Roadmap (2026 Q4)

| Field | Value |
| --- | --- |
| **Status** | Proposed — feedback requested |
| **Planning window** | 2026 Q4 (October–December 2026) |
| **Repository** | [`vllm-project/vllm-omni`](https://github.com/vllm-project/vllm-omni) |
| **Related** | [#8264](https://github.com/vllm-project/vllm-omni/issues/8264), [#9446](https://github.com/vllm-project/vllm-omni/issues/9446), [#5251](https://github.com/vllm-project/vllm-omni/issues/5251), [#6665](https://github.com/vllm-project/vllm-omni/issues/6665), [#6787](https://github.com/vllm-project/vllm-omni/issues/6787), [#6691](https://github.com/vllm-project/vllm-omni/issues/6691) |

---

## Motivation

This RFC starts from one hardware fact: the Atlas 300I Duo trades compute for memory. Its design point is not "the fastest inference card" but "the most memory per dollar", and every recommendation below follows from that.

### Hardware baseline

**Table 1. Atlas 300I Duo vs. Atlas 800I A2 platform specifications**

| Property | Atlas 300I Duo (full card, 2× 310P3) | Per chip (310P3) | Atlas 800I A2 (per module) | Implication for this roadmap |
| --- | --- | --- | --- | --- |
| AI compute (FP16) | 140 TFLOPS | 70 TFLOPS (measured Cube peak 69.5 TFLOPS) | 280 TFLOPS | ~1/4 per chip, ~1/2 per card |
| AI compute (INT8) | 280 TOPS | 140 TOPS | 560 TOPS | Same 1/4 and 1/2 relationship |
| Memory | LPDDR4X 96 GB or 48 GB, ECC | 48 GB or 24 GB | HBM 64 GB (32 GB option), ECC | Per-chip capacity matches the reference module, but bandwidth is ~8× lower; the 96 GB card can hold two-chip shards |
| Memory bandwidth | 408 GB/s (~185 GB/s per chip measured) | 204 GB/s | 1.6 TB/s | Decode is bandwidth-bound; batching and multi-chip placement are mandatory |
| BF16 | Not supported | Not supported | Supported | FP16 is the baseline for every model |
| Compute-to-memory ratio | 1.46 TFLOPS per GB (140/96) | 1.46 TFLOPS per GB (70/48) | 4.38 TFLOPS per GB (280/64) | ~1/3 of the reference: memory is abundant relative to compute — the defining trait of 310P |
| Compute-to-bandwidth ratio | 343 FLOP/byte (140/408) | 343 FLOP/byte (70/204) | 175 FLOP/byte (280/1600) | Saturating compute needs ~2× the arithmetic intensity of the reference, so kernels hit the bandwidth wall first |
| Interconnect and topology | Intra-card chip-to-chip link (~60 GB/s measured); card-to-card PCIe 4.0 x16 (~16 GB/s measured) | — | NPU full-mesh option, 392 GB/s per server | 310P has no HCCS-class fabric; cross-chip parallelism is expensive, so prefer stage splitting to TP |
| Power / form factor | 150 W; single-slot full-height full-length (10.5"), PCIe 4.0 x16 | — | 4U server, 8 modules, 4× 2.6 kW PSUs; per-module power not published | The card's 150 W leaves ample power and density headroom; per-watt throughput is computed as measured throughput ÷ power |

> Sources: [Atlas 300I Duo Inference Card](https://e.huawei.com/cn/products/computing/ascend/atlas-300i-duo) · [Atlas 800I A2](https://e.huawei.com/cn/products/computing/ascend/atlas-800i-a2) · [Atlas 300I A2](https://e.huawei.com/cn/products/computing/ascend/atlas-300i-a2)

### What this hardware implies

In one sentence: **memory per unit of compute is very generous, while bandwidth per unit of memory is severely constrained.** Four consequences drive the rest of this document.

- **If the weights fit, there is no need to shard or swap.** One chip's 48 GB holds any FP16 model under ~10B entirely; two chips' 96 GB covers the ~19B Boogu-Image execution graph and the 30B-A3B MoE weights. Memory capacity is the most valuable and least substitutable resource on this card, so "does it fit in one piece?" is the first selection criterion.
- **With limited compute, choose workloads with little work per step and a lot of resident weight.** MoE (30B total / 3B active), step-wise diffusion denoising, and single-token decode all do little arithmetic per step while needing large weights resident — a good match for this hardware. Prefill-dominated large models, long-video generation, and compute-heavy vision encoder stacks are the opposite and are not its strong suit.
- **The real bottleneck is 204 GB/s of bandwidth, so throughput comes from batching, not from peak FLOPs.** With 70 TFLOPS against 204 GB/s, saturating compute requires ~343 FLOP/byte, twice the reference platform's 175 FLOP/byte, so most kernels hit bandwidth first. The order of levers is therefore: concurrent batching (amortizing weight reads) > fewer data movements (NPU-resident preprocessing, fused operators, no D2H/H2D round-trips) > graph execution overhead (graph capture) > operator micro-efficiency.
- **Large memory means large KV pools and long contexts.** A faster card with less memory cannot do this; it suits retrieval, reranking, long-audio transcription and long-form dialogue — long context, light per-step compute.

### Positioning

**An inference tier built around memory, complementary to the Atlas 800I A2 rather than a replacement.** The previous section established the compute/memory mismatch: ~1/4 the compute of the reference module with 50% more memory. The 300I Duo therefore does not win on single-request speed; it wins by holding a larger model, a larger KV pool and more concurrency at the same cost. Three workload classes follow: dense models under ~10B (speech, VLA, reranking, small diffusion) that fit entirely in one chip's 48 GB; MoE with many total but few active parameters (e.g. Qwen3-Omni-30B-A3B, 30B total / 3B active), whose weights fill memory while its per-step compute stays light and which fits the 96 GB card; and decode-dominated, long-context workloads (long-audio transcription, long dialogue, retrieval), where larger KV pools and higher concurrency turn memory into an advantage. Prefill-dominated large models, long-video generation, accuracy reference runs and fallback stay on the Atlas 800I A2.

### Optimization target and order of levers

The target is served throughput and cost per unit of work, not single-request latency. The order of levers follows from the 343 FLOP/byte compute-to-bandwidth ratio: concurrent batching to amortize weight reads > fewer data movements > lower graph execution overhead > operator micro-efficiency. None of these changes model semantics; trailing on single-request latency is expected and acceptable as long as throughput and cost per unit of work lead.

### Current state and scope of this RFC

310P support in vLLM-Omni currently covers Qwen3-TTS only. The path works and is covered by CPU-mocked contract tests and a real-device wiring test, but it is not a product capability: there is no multi-chip deployment path, and speech recognition, VLA, image, video, retrieval and omni models are entirely absent. This RFC lays out a reviewable plan to close the gap: a model matrix ordered by "does it fit in one piece, and is per-step compute light?", per-model adaptation and optimization PRs, "two chips in one card + PP across cards" deployment plans for the two models that exceed one chip, and dataset-based accuracy and performance evidence.

---

## Proposed Change

### 1. Design principles

| Principle | Contract |
| --- | --- |
| **Memory-First** | Model selection and optimization are gated on memory capacity first: if a model fits entirely in memory, size the batch and KV pool up to what bandwidth and memory allow; split only when it does not fit. Memory is the least substitutable resource on this card. |
| **One card, two chips: CP/SP/TP inside the card, PP across cards** | The unit of deployment is a single 300I Duo (two 310P3 chips, 96 GB total). When parallelism is required, CP/SP/TP — which exchange activations or sequence shards frequently — stay inside the card and run over the intra-card link (~60 GB/s measured). Card-to-card traffic is PCIe 4.0 x16 only (~16 GB/s measured), so it carries PP, whose communication happens only at stage boundaries. If two chips still do not suffice, scale out to multi-card PP. The rule: the more communication-intensive the parallelism, the closer to the card it must stay. |
| **FP16 first** | 310P has no BF16, so every model needs a correct FP16 path. Quantization is neither a prerequisite nor excluded: if an FP16 target proves unreachable, W8A8 may be evaluated as a fallback. |
| **Reuse the Atlas 800I A2 NPU path** | Share pipelines, operators and graph utilities with the Atlas 800I A2 path, keeping 310P specifics behind `is_310p()` and platform hooks (see [#6691](https://github.com/vllm-project/vllm-omni/issues/6691)). Operators and attention backends belong to vLLM-Ascend; models and pipelines belong to vLLM-Omni. |
| **Throughput before latency parity** | Optimize batching, graph capture, prefix caching and stage overlap. Single-stream latency is model-specific and need not match the Atlas 800I A2. |
| **Every model ships functional and performant** | Each model must deliver both a working path (E2E runs, dataset accuracy within tolerance) and the best performance the hardware allows on 300I Duo (throughput close to the memory and bandwidth ceiling, not merely "it runs"). Both come with a recipe and dataset numbers. Modes that change the accuracy target or failure modes (duplex vs. turn-based, text-only vs. video input, understanding vs. speech output) are split into separate PRs. |

### 2. Current state

**Available**

- 310P detection, worker and model-runner routing: [#4283](https://github.com/vllm-project/vllm-omni/pull/4283), [#4841](https://github.com/vllm-project/vllm-omni/pull/4841), [#9246](https://github.com/vllm-project/vllm-omni/pull/9246).
- Qwen3-TTS talker, code predictor and Code2Wav 310P path: [#4283](https://github.com/vllm-project/vllm-omni/pull/4283), [#4841](https://github.com/vllm-project/vllm-omni/pull/4841).
- FP16 enforcement, JIT disable, 310P sampler, CPU-side reference audio and mel: `vllm_omni/platforms/npu/_310p/`.
- CPU-mocked contract tests and real-device wiring tests: `tests/platforms/npu/test_310p_patches.py`, `tests/platforms/npu/test_310p_real_device.py`.
- vLLM-Ascend 310P wheel and SIT configurations: `Dockerfile.310p`, `tests/e2e/*_310p`.

**In progress**

Model Runner V2 on Ascend NPU ([#9446](https://github.com/vllm-project/vllm-omni/issues/9446)), in-tree platform ownership ([#6691](https://github.com/vllm-project/vllm-omni/issues/6691)), Boogu-Image Ascend BF16 support ([#6665](https://github.com/vllm-project/vllm-omni/issues/6665), [#6787](https://github.com/vllm-project/vllm-omni/issues/6787)), and 310P installation and version pairing ([#5251](https://github.com/vllm-project/vllm-omni/issues/5251)).

**Gaps**

- No coverage of speech recognition, VLA, image, video, retrieval or omni models; the 310P matrix is effectively a single model.
- No validation of intra-card CP/SP/TP or cross-card PP for Boogu-Image and Qwen3-Omni-30B-A3B.

### 3. Goals

- Every model in the matrix runs on real 310P hardware with accuracy within tolerance on that model's own evaluation dataset.
- Every adapted model is optimized for throughput on the same dataset, with at least one measured improvement and no accuracy regression.
- Validated deployment paths for Boogu-Image and Qwen3-Omni-30B-A3B: CP/SP/TP inside the card, PP across cards, with the measured gain of each scaling step reported.
- Every model is graded Supported, Experimental or Stretch, backed by a recipe and dataset evidence.

### 4. Model coverage

The table below is the priority order. Ranking considers two things: deployment demand and dependencies between workloads, and the fit with this hardware — does it fit in one chip's 48 GB, and is per-step compute light? Not every model will reach the same support tier.

| Priority | Model | Category | Size | Fit on 310P in FP16 |
| ---: | --- | --- | --- | --- |
| 1 | Qwen3-ASR-1.7B | TTS / ASR | 1.7B | ~3.4 GB weights; a single encoder-decoder pass; low compute demand per chip |
| 2 | Qwen3-TTS-1.7B | TTS / ASR | 1.7B + codec | ~3.4 GB weights plus codec; an existing 310P path to build on |
| 3 | MiniCPM-o 4.5 | TTS / ASR (full-duplex omni) | ~8–9B + codec | ~16–18 GB weights plus codec and stage buffers; fits one chip (48 GB) with careful placement |
| 4 | Pi0.5 | VLA | 3.62B | ~7.3 GB weights; stateless and latency-sensitive, one chip |
| 5 | Boogu-Image Turbo | Image generation | ~19B execution graph (DiT + Qwen3-VL-8B + VAE) | 4-step DMD at batch 1; ~36–41 GB peak weights and activations; CP/SP/TP across the card's two chips (96 GB), cross-card PP only if still insufficient |
| 6 | Z-Image-Turbo | Image generation | 6B DiT + ~4B text encoder | 8-NFE schedule; ~20.5 GB total weights (6B DiT, 4B text encoder, VAE), less if the text encoder is released after prompt encoding; ample headroom on one chip |
| 7 | Qwen3-Reranker 0.6B | Embedding / Reranker | 0.6B | ~1.2 GB weights; high throughput on one chip |
| 8 | Qwen3-Reranker 8B | Embedding / Reranker | 8B | ~16 GB weights, fits one chip |
| 9 | LFM3-Omni-2B | Omni | 2B + codec | ~4 GB weights plus codec, ample headroom on one chip |
| 10 | Qwen3-Omni-30B-A3B | Omni | 30B total / 3B active | ~60 GB in FP16; CP/SP/TP across the card's two chips (96 GB); two cards with four chips (192 GB) via PP |
| 11 | Wan2.1-T2V-1.3B | Video generation | 1.3B | ~2.6 GB weights; video activations dominate memory and compute on one chip |

**Rationale**

- **Speech (ASR, TTS, MiniCPM-o).** The smallest models with the clearest production demand. ASR and TTS establish the audio front-end, codec and streaming primitives that every later speech or omni model reuses; MiniCPM-o adds full-duplex orchestration and ~8–9B of memory pressure on top, so it follows rather than leads.
- **VLA (Pi0.5).** The reference edge-robotics policy: 3.6B, stateless, latency-sensitive. Independent of the audio stack and can proceed in parallel.
- **Image (Boogu-Image Turbo, Z-Image-Turbo).** Boogu is the high-value generation family with an active Ascend track and a clear path from the two on-card chips to cross-card PP; Z-Image is the smaller, higher-throughput complement. Both are scheduled on their distilled Turbo checkpoints. If Boogu misses its multi-chip target, Z-Image becomes the first image target.
- **Retrieval (Qwen3-Reranker 0.6B and 8B).** Small, high-throughput and economically attractive on 310P. vLLM-Ascend discontinued this path, so the adaptation migrates it into vLLM-Omni.
- **Omni (LFM3-Omni-2B, Qwen3-Omni-30B-A3B).** LFM3 is the smallest true omni model and reuses the audio codec path; Qwen3-Omni is the only MoE candidate that remains plausible on 310P thanks to its 3B active parameters, and is a stretch target contingent on multi-chip throughput.
- **Video (Wan2.1-T2V-1.3B).** The smallest Wan model, used to validate temporal attention and VAE decoding. Video is the most bandwidth- and compute-intensive workload, so it comes last.

### 5. Technical approach

All tracks follow the same order: make the weights resident and the batch and KV pool sizeable first, then cut data movement.

- **Speech.** Enforce FP16 at load; keep preprocessing and detokenization on the NPU; capture the talker, code predictor and Code2Wav subgraphs with graph-safe sampling and batch buckets. Add long-form VAD chunking, forced alignment, first-packet latency work, and the CustomVoice / VoiceDesign variants. For MiniCPM-o, split thinker and talker/Code2Wav across the card's two chips, letting only codec chunks cross the boundary, while preserving streaming, cancellation and long-input semantics.
- **VLA.** Enable the OpenPI realtime path on NPU, including multi-camera preprocessing, proprioceptive state and the flow-matching action expert. Keep the policy stateless, capture the vision tower and action expert as graphs at batch 1, and validate action-chunk parity against the reference.
- **Image.** Validate DiT attention (`TORCH_SDPA` first, fused aclnn where available), VAE layouts and tiling, and the denoising loop under ACLGraph with a dynamic-shape fallback. Both models use their Turbo checkpoints: Boogu-Image Turbo with its 4-step DMD schedule at batch 1, Z-Image-Turbo with its 8-NFE schedule. Boogu-Image Turbo does not support request batching, so its image throughput comes from the shorter schedule and lower per-image latency rather than batched denoising. For Boogu, compare CP/SP/TP splits across the card's two chips first and extend to cross-card PP only if needed, judging every step by measured throughput.
- **Retrieval.** Migrate the pooling/reranker pipeline from the discontinued vLLM-Ascend implementation into vLLM-Omni, scoped to the model and pooling path. Validate long-context scoring and dynamic batching, and report nDCG/MRR and documents per second.
- **Omni.** For LFM3, enable the temporal model, depth decoder and LiquidCodec, capture the depth whole-loop, and validate the silent-video input path. For Qwen3-Omni, validate the encoders and thinker first, then treat talker and Code2Wav as a separate deliverable, and quantify any torch fallback in MoE gating.
- **Video.** Reuse the image DiT/VAE work, add temporal attention and frame batching, and target short low-resolution clips. Video stays experimental until a quality and stability gate exists.

---

## CC List

Selected from the repository's [`.github/CODEOWNERS`](https://github.com/vllm-project/vllm-omni/blob/main/.github/CODEOWNERS) (main branch): default owners, platform and NPU subtree owners, NPU CI owners, and the TTS benchmarks owner.

cc @Gaohan123 @hsliuustc0106 @ywang96 @gcanlin @tjtanaa @xuechendi @FayeSpica @yenuo26 @haic0 @linyueqian

## Additional Notes

- This document is a roadmap and prioritization document. It does not replace the design discussion for any individual PR; each PR still needs its own motivation, tests, and accuracy/performance evidence.
- If maintainers prefer to keep 310P as an experimental, best-effort target rather than a fully supported tier, this RFC can be downgraded to a tracking issue without changing the technical content or the model priority order.
- Contributors should follow the repository's DCO, AI-use disclosure, `precheck-pr`, and open-PR-limit requirements.
- Related work: [#4283](https://github.com/vllm-project/vllm-omni/pull/4283), [#4841](https://github.com/vllm-project/vllm-omni/pull/4841), [#4852](https://github.com/vllm-project/vllm-omni/pull/4852), [#9246](https://github.com/vllm-project/vllm-omni/pull/9246), [#8264](https://github.com/vllm-project/vllm-omni/issues/8264), [#9446](https://github.com/vllm-project/vllm-omni/issues/9446), [#5251](https://github.com/vllm-project/vllm-omni/issues/5251), [#6665](https://github.com/vllm-project/vllm-omni/issues/6665), [#6787](https://github.com/vllm-project/vllm-omni/issues/6787), [#6691](https://github.com/vllm-project/vllm-omni/issues/6691).
