# Qwen3-TTS 在 Ascend 310P 上的端到端跑通与逐行代码逻辑分析

> 运行日期：2026-11-13（v0.30 首次）/ 2026-11-14（v0.30 复跑 + **main 本地源码环境**）
> 运行代码（§1-§7）：`vllm-omni` v0.30.0 release 树（orphan 根提交 `31af36cb0` + 310P Qwen3-MoE 补丁，HEAD `3dde0bb73`）
> 运行代码（§8）：`vllm-omni` main + vLLM 0.33.0 + vllm-ascend `17f07e3` + CANN 9.1.0
> 工作树：`/home/yf/WorkSpace/.worktrees/vllm-omni-v030`（含 2 个本地 310P 兼容 shim，见 §5.1）
> 运行环境：`/home/yf/WorkSpace/.venvs/vllm-omni-310p`
> 硬件：Atlas 300I DUO（Ascend 310P3），本次使用物理 chip 2
> 结论：**端到端跑通，输出 4.64 s / 24 kHz 有效语音**；两次独立运行输出完全一致

---

## 0. TL;DR

| 项目 | 结果 |
| --- | --- |
| 模型 | `Qwen3-TTS-12Hz-1.7B-CustomVoice`（1.7B，BF16 权重约 3.8 GB + codec 682 MB） |
| 任务 | CustomVoice，中文文本 + `instruct="用特别愤怒的语气说"` |
| 输出 | `output_0_bbd04f21-8f1f-4463-834f-b43c5b502427.wav` |
| 音频 | 24 000 Hz，111 360 采样点，**4.64 s**，RMS 0.0808，峰值 0.711，非静音占比 82.7% |
| 端到端耗时 | 首次 69.25 s；2026-11-14 复跑 48.79 s（Stage 0 40.46 s，Stage 1 48.79 s，同一 chip 串行流水） |
| 输出 token | Stage 0：输入 36、输出 59（codec frame），ITL ≈ 462 ms |
| RTF | ≈ 14.9（当前为“功能跑通”基线，不是性能基线） |
| 关键结论 | 当前分支（main 基线）无法配 vLLM 0.30；必须使用仓库内 v0.30.0 release 树。310P 侧仍需 3 个兼容性 shim 才能绕过 ATB/ACLNN 的 flash-attention 限制 |

---

## 1. 环境与版本矩阵

| 组件 | 版本 / 值 | 说明 |
| --- | --- | --- |
| NPU | 6 × Ascend 310P3，单 chip 44 GB | `npu-smi` 显示 3 张 300I DUO，每张 2 chip；chip 0/1 被其他任务占用，本次用 chip 2 |
| CANN | `/home/yf/CANN/cann-9.0.1`（`ASCEND_TOOLKIT_HOME`） | 另有 `/usr/local/Ascend/ascend-toolkit/8.3.RC1` |
| NNAL ATB | 8.3.RC1（`/usr/local/Ascend/nnal/atb/8.3.RC1`） | `libatb.so` 需手动加入 `LD_LIBRARY_PATH` |
| Python | 3.11.15 | venv：`/home/yf/WorkSpace/.venvs/vllm-omni-310p` |
| torch / torch_npu | 2.10.0 / 2.10.0.post7 | vllm-ascend 0.30.0 的硬依赖 |
| vLLM | 0.30.0 | 310P wheel |
| vLLM-Ascend | 0.30.0 | 310P wheel；PyPI 上的最新版本就是 0.30.0 |
| vLLM-Omni | 0.1.dev2+g3dde0bb73（editable） | 实际通过 `PYTHONPATH` 指向 v0.30.0 worktree |
| transformers | 5.14.1 | |
| 模型权重 | `/data/xp/qwen3-tts/Qwen3-TTS-12Hz-1.7B-CustomVoice` | 免下载，直接复用本地 model 目录 |

### 1.1 为什么不能直接在当前分支执行？

用户先问“不能在当前分支直接执行吗？”。实测答案：**不能**。

当前分支 `001-reports` 基于 main（`7c586b5cb`），其 `vllm_omni/patch.py` 在 import 阶段就调用：

```python
# vllm_omni/patch.py:50（main）
apply_img2img_mm_prefix_patch()

# vllm_omni/utils/mm_prefix.py:25（main）
original = utils.compute_mm_prefix_ranges
```

而 vLLM 0.30.0 的 `vllm.v1.attention.backends.utils` 只有
`compute_mm_prefix_range_tensor`，没有 `compute_mm_prefix_ranges`，于是直接：

```text
AttributeError: module 'vllm.v1.attention.backends.utils'
has no attribute 'compute_mm_prefix_ranges'
```

根因是 **main 树与 vLLM 0.30.0 不匹配**：main 文档要求 vLLM 0.33.0；本机 310P
栈是 vLLM 0.30.0 + vllm-ascend 0.30.0。仓库里另有一条独立的 **v0.30.0 release
树**（root commit `31af36cb0`，本地在其上加了 Qwen3-MoE 310P 补丁 `3dde0bb73`），
这条树才与本机 310P 环境对齐。因此本次用
`git worktree add /home/yf/WorkSpace/.worktrees/vllm-omni-v030 3dde0bb73`
单独检出，并通过 `PYTHONPATH` 让它优先于主仓库被 import，**不改动用户当前分支**。

### 1.2 升级 vLLM 能不能基于 main 推理？

用户接着问“如果更新这个版本，是可以基于 main 进行推理吗？”。结论：**目前不行**。

| 检查项 | 结果 |
| --- | --- |
| `pip index versions vllm` | 最新 0.33.0（有 wheel） |
| `pip index versions vllm-ascend` | **最新 0.30.0**，没有 0.32/0.33 |
| 310P 支持 | 只在 vllm-ascend 0.30.0 的 310P wheel 中提供（experimental） |
| main 要求 | vLLM 0.33.0 + 匹配的 vllm-ascend |

即：单独把 vLLM 升到 0.33.0 会立刻失去 NPU 插件（vllm-ascend 0.30.0 锁定
`torch==2.10.0 / torch-npu==2.10.0.post7`，且没有 0.33 对应发布）。要基于 main
在 310P 上跑，需要**从源码构建与 vLLM 0.33 匹配、且包含 310P 支持的
vllm-ascend**，这不在当前已发布/已验证范围内（roadmap 里也把“310P wheel 可用性”
列为关键依赖）。

---

## 2. 本次可复现命令

```bash
# 1) 独立的 v0.30.0 worktree（不动当前分支）
git worktree add /home/yf/WorkSpace/.worktrees/vllm-omni-v030 3dde0bb73

# 2) 本地模型别名：让示例里写死的 HF repo id 落到本地目录
mkdir -p /tmp/qwen3tts_run/Qwen
ln -sfn /data/xp/qwen3-tts/Qwen3-TTS-12Hz-1.7B-CustomVoice \
        /tmp/qwen3tts_run/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice

# 3) 运行（关键环境变量）
cd /tmp/qwen3tts_run
# 可选：仅当启用 310P 原始 ATB flash-attention 路径时需要；
# 当前 eager-attention shim 不加载 libatb.so，复跑未设置该变量也能通过。
export LD_LIBRARY_PATH=/usr/local/Ascend/nnal/atb/8.3.RC1/atb/cxx_abi_1/lib:$LD_LIBRARY_PATH
export ASCEND_RT_VISIBLE_DEVICES=2          # 只暴露空闲 chip 2 为逻辑 0
export PYTHONPATH=/home/yf/WorkSpace/.worktrees/vllm-omni-v030:$PYTHONPATH

/home/yf/WorkSpace/.venvs/vllm-omni-310p/bin/python \
  /home/yf/WorkSpace/.worktrees/vllm-omni-v030/examples/offline_inference/text_to_speech/qwen3_tts/end2end.py \
  --deploy-config /tmp/qwen3tts_run/qwen3_tts_310p.yaml \
  --output-dir /tmp/qwen3tts_run/out \
  --log-stats
```

310P 专用 deploy 配置相对默认 `qwen3_tts.yaml` 的差异：

```yaml
dtype: float16                    # 310P 无 BF16
stages:
  - stage_id: 0
    additional_config:
      weight_nz_mode: 0           # CANN 9.0.1 ascend310p 无 aclnnMatmulWeightNz
    model_loader_extra_config:
      enable_weights_track: false # 310P patch 的 _fused_qkv_weight 是运行期派生量
    enforce_eager: true
  - stage_id: 1
    dtype: float16
    additional_config: {weight_nz_mode: 0}
    model_loader_extra_config: {enable_weights_track: false}
    enforce_eager: true
platforms:
  npu:
    model_runner: v1
    stages:
      - {stage_id: 0, enforce_eager: true}
      - {stage_id: 1, enforce_eager: true}
```

---

## 3. 端到端调用链（概览）

```text
examples/offline_inference/text_to_speech/qwen3_tts/end2end.py
  └─ get_custom_voice_query()                   构造 additional_information
  └─ _estimate_prompt_len()                    估算 prompt_token_ids 占位长度
  └─ Omni(**kwargs)                            离线入口
       └─ OmniBase.__init__                    omni_base.py:170
            └─ AsyncOmniEngine.__init__        omni_engine_base.py:130
                 ├─ _resolve_stage_configs     deploy yaml + 平台覆盖 + 校验
                 ├─ StageRuntime.initialize    stage_runtime.py:287
                 │    ├─ _initialize_local_llm_replica   stage_runtime.py:1086
                 │    │    └─ launch_stage_replica        stage_engine_startup.py:1129
                 │    │         ├─ StageEngineCoreProc(stage0)  talker
                 │    │         └─ StageEngineCoreProc(stage1)  code2wav
                 │    └─ 等待 engine core ready / 注册 stage route
                 └─ Orchestrator                  连接 stage client
  └─ omni.generate([prompt])                    omni.py:78
       └─ Orchestrator: stage0 → connector → stage1
            Stage 0 (talker)：
              NPUARModelRunner.execute_model     npu_ar_model_runner.py:313
                └─ _preprocess                   gpu_model_runner.py:1638
                     ├─ talker.preprocess         qwen3_tts_talker.py:868
                     └─ _talker_mtp_forward       gpu_model_runner.py:1962
                          └─ talker.talker_mtp     qwen3_tts_talker.py:1495
                               └─ code_predictor.forward  qwen3_code_predictor.py:1090
            Stage 0 → Stage 1：
              talker2code2wav_async_chunk        stage_input_processors/qwen3_tts.py:106
              SharedMemoryConnector              shm_connector.py:20
            Stage 1 (code2wav)：
              Qwen3TTSCode2Wav.forward            qwen3_tts_code2wav.py:256
  └─ _save_wav()                                end2end.py:365
```

---

## 4. 逐行 / 逐段代码解析

下面按实际执行顺序展开。行号均指 **v0.30.0 worktree** 中的文件。

### 4.1 示例入口：`end2end.py`

#### 4.1.1 `_estimate_prompt_len`（`end2end.py:38-140`）

这是一个“占位长度估算器”，不参与真正的 token 化推理：

- `end2end.py:56-60`：缓存 `(tokenizer, talker_config, speech_tokenizer)`，避免每条 prompt
  重复加载 tokenizer。
- `end2end.py:62-66`：读取 `task_type`，决定后面走 CustomVoice / VoiceDesign / Base 分支。
- `end2end.py:68-124`：`_estimate_ref_code_len` 只在 Base（voice clone）任务用：
  - 用 `MediaConnector` / `load_audio` 读参考音频；
  - 用 `Qwen3TTSTokenizer.encode()` 得到真实 `audio_codes` 帧数；
  - 失败则用 `duration * codec_frame_rate` 估算（`end2end.py:117-119`）。
- `end2end.py:127-133`：最终调用
  `Qwen3TTSPromptEmbedsBuilder.estimate_prompt_len_from_additional_information()`。

> 注意：本地模型目录下 `speech_tokenizer/config.json` 存在，但
> `speech_vq.py` import `onnxruntime` 时在本环境打印了
> `_ARRAY_API not found`（NumPy 2.x 与 onnxruntime 编译版本不匹配）。
> 这个异常被 `try/except` 捕获，退化为“按语速估算”，不影响 CustomVoice 结果。

#### 4.1.2 `get_custom_voice_query`（`end2end.py:145-205`）

单条请求构造：

```python
text = "其实我真的有发现，我是一个特别善于观察别人情绪的人。"
language = "Chinese"
speaker = "Vivian"
instruct = "用特别愤怒的语气说"
additional_information = {
    "task_type": [task_type],   # "CustomVoice"
    "text": [text],
    "language": [language],
    "speaker": [speaker],
    "instruct": [instruct],
    "max_new_tokens": [2048],
    "full_utterance_decode": [True],
}
inputs = {
    "prompt_token_ids": [0] * _estimate_prompt_len(...),
    "additional_information": additional_information,
}
```

逐行含义：

- `text` / `language` / `speaker` / `instruct`：TTS 的语义输入；
- `max_new_tokens=2048`：codec frame 上限；
- `full_utterance_decode=True`：Code2Wav 侧整句解码（非流式分块）；
- `prompt_token_ids`：**只提供长度**。Talker 的 `preprocess()` 会用 text + speaker +
  instruct 重新构造 embedding，占位值 0 没有语义，但长度必须与
  `preprocess()` 实际产生的 embedding 长度一致（见 4.5.2）。

#### 4.1.3 `_build_inputs`（`end2end.py:339-363`）

- `end2end.py:342-346`：校验 `batch_size` 必须是 2 的幂（Code2Wav 的 CUDA graph
  档位按 2 的幂捕捉；310P eager 下仍保留该校验）。
- `end2end.py:348-354`：按 `query_type` 调对应构造函数。
- `end2end.py:358-368`：若给了 `--txt-prompts`，用模板里的
  `additional_information` 逐行替换 `text`，并重新估算占位长度。

#### 4.1.4 `main`（`end2end.py:390-406`）

```python
model_name, inputs = _build_inputs(args)      # 模型名 + Omni 输入
os.makedirs(output_dir, exist_ok=True)
omni_kwargs = vars(args).copy()
omni_kwargs["model"] = model_name             # 覆盖 CLI --model
omni = Omni(**omni_kwargs)                    # 构造引擎（最重的一步）
for batch_start in range(0, len(inputs), batch_size):
    batch = inputs[batch_start : batch_start + batch_size]
    for stage_outputs in omni.generate(batch):
        _save_wav(output_dir, output.request_id,
                  output.outputs[0].multimodal_output)
```

- 示例把 `model_name` 写死为 `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`，因此本地运行
  用 2 节里的目录软链接让它解析到本地权重。
- `Omni(**kwargs)` 会把所有 CLI 字段传给引擎；引擎只取认识的字段。

#### 4.1.5 `_save_wav`（`end2end.py:365-374`）

```python
audio_data = mm["audio"]                       # list[Tensor] 或 Tensor
sr_val = sr_raw[-1] if isinstance(sr_raw, list) and sr_raw else sr_raw
audio_tensor = torch.cat(audio_data, dim=-1) if isinstance(audio_data, list) else audio_data
sf.write(out_wav, audio_tensor.float().cpu().numpy().flatten(),
         samplerate=sr, format="WAV")
```

- `audio` 是分块流式结果，按最后一维拼接；
- `sr` 取 list 最后一个元素（stage 输出的采样率元数据）；
- 本次 `sr=24000`，`audio` 长度 111 360，正好 4.64 s。

---

### 4.2 引擎构建：从 `Omni` 到两个 StageEngineCore

#### 4.2.1 `OmniBase.__init__`（`omni_base.py:170-256`）

- `omni_base.py:180-205`：把用户 kwargs 拆成 engine kwargs 与 pipeline 配置；`model`
  可以是 HF repo id 或本地目录。
- `omni_base.py:215`：`self.engine = self._create_engine(...)`。
- `Omni._create_engine`（`omni.py:32-34`）直接返回 `AsyncOmniEngine(**engine_kwargs)`。

#### 4.2.2 `AsyncOmniEngine.__init__`（`omni_engine_base.py:130-345`）

关键步骤：

1. `omni_engine_base.py:140-180`：解析 `vllm_config` / tokenizer / dtype / model path。
2. `omni_engine_base.py:200-245`：调用
   `StageConfigFactory.get_pipeline_config(model, trust_remote_code, deploy_config_path)`，
   得到 `QWEN3_TTS_PIPELINE`（见 4.3）。
3. `omni_engine_base.py:250-300`：把 pipeline 的 2 个 stage 与 deploy YAML 的
   `stages` 合并，生成每个 stage 的 `StageConfig`。
4. `omni_engine_base.py:312-330`：启动 Orchestrator 线程，并在
   `_wait_for_orchestrator_init()` 中等待各 stage engine 完成初始化。
5. 每个 stage 的 `StageRuntime.initialize()` 负责真正拉起重进程。

#### 4.2.3 Stage 启动：`StageRuntime.initialize`（`stage_runtime.py:287-316`）

- `stage_runtime.py:295`：`_initialize_stage_replicas()`；
- `stage_runtime.py:810-887`：按 `init_group` 分组并行初始化；
- `stage_runtime.py:1086-1135`：本地 LLM replica 走
  `_initialize_local_llm_replica()`；
- `stage_runtime.py:1119`：`with self.launch_stage_engines(...)` 进入
  `stage_engine_startup.launch_stage_replica()`（`stage_engine_startup.py:1129`）。

`launch_stage_replica` 做三件事：

1. `scoped_spawn_device_env`（`stage_engine_startup.py:911`）把
   `ASCEND_RT_VISIBLE_DEVICES` 映射到本 stage 的 `devices`；
2. `_launch_omni_core_engines`（`stage_engine_startup.py:970`）spawn
   `StageEngineCoreProc`；
3. `wait_for_engine_startup`（`stage_engine_startup.py:1222`）等待 ready 握手。

本次日志确认映射正确：

```text
Stage 0 logical-to-physical device mapping: 0->2
Stage 1 logical-to-physical device mapping: 0->2
```

即两个 stage 都落在物理 chip 2 上（共享同一 chip、各自独立进程）。

---

### 4.3 配置解析与 310P 覆盖链

#### 4.3.1 Pipeline 定义：`qwen3_tts/pipeline.py:31-77`

```python
QWEN3_TTS_PIPELINE = PipelineConfig(
    model_type="qwen3_tts",
    default_deploy_config_name="qwen3_tts.yaml",
    model_arch="Qwen3TTSTalkerForConditionalGeneration",
    stages=(
        StagePipelineConfig(          # stage 0: talker
            stage_id=0, model_stage="qwen3_tts",
            execution_type=StageExecutionType.LLM_AR,
            owns_tokenizer=True, engine_output_type="latent",
            async_chunk_process_next_stage_input_func=
                "vllm_omni.model_executor.stage_input_processors.qwen3_tts.talker2code2wav_async_chunk",
            custom_process_next_stage_input_func=
                "...talker2code2wav_full_payload",
            sampling_constraints={"detokenize": False, "stop_token_ids": [2150]},
        ),
        StagePipelineConfig(          # stage 1: code2wav
            stage_id=1, model_stage="code2wav",
            execution_type=StageExecutionType.LLM_GENERATION,
            input_sources=(0,), final_output=True,
            final_output_type="audio", engine_output_type="audio",
            model_arch="Qwen3TTSCode2Wav",
            requires_full_payload_input=True,
        ),
    ),
)
```

逐行要点：

- `default_deploy_config_name="qwen3_tts.yaml"`：离线模式下若未显式给
  `--deploy-config`，会自动加载这份 2-stage 配置。
- stage 0 的 `engine_output_type="latent"`：talker 不直接吐音频，而是吐
  codec codes / hidden states。
- `stop_token_ids=[2150]`：codec EOS；`detokenize=False`：不让 tokenizer 提前
  把 codec id 变成文本。
- stage 1 `input_sources=(0,)` + `final_output_type="audio"`：code2wav 消费 stage 0
  的 codec，产出最终音频。
- `requires_full_payload_input=True`：同步模式下要等完整 payload；异步 chunk 模式
  则由 `talker2code2wav_async_chunk` 逐块喂。

#### 4.3.2 Deploy YAML 合并：`stage_config.py:763-834`

- `resolve_deploy_yaml`（`:763`）：支持 `base_config:` 继承；`stages` 按
  `stage_id` 深合并，`platforms` 按平台名合并。
- `load_deploy_config`（`:792`）：把 YAML 转成 `DeployConfig`；
  `dtype / quantization / trust_remote_code` 等是 pipeline-wide 字段（`:821-833`）。
- `_parse_stage_deploy`（`:637-672`）：stage 里未声明的键会落进
  `engine_extras`，最终 `_build_engine_args()`（`:1039`）用
  `engine_args.update(ds.engine_extras)` 传给 vLLM。因此：
  - stage 级 `dtype: float16` 会作为引擎参数；
  - `additional_config.weight_nz_mode=0` 会进入 vLLM 的 `additional_config`；
  - `model_loader_extra_config.enable_weights_track=false` 会进入 `LoadConfig`。
- `_apply_platform_overrides`（`:859-885`）：把 `platforms.npu` 段覆盖到对应
  stage；这就是默认 YAML 里 `platforms.npu.model_runner: v1` 生效的位置。

#### 4.3.3 310P 平台检测与 patch 入口

- `platforms/npu/platform.py:55-77`：`NPUOmniPlatform.__init__` 里调用
  `apply_qwen3_tts_patches()`、`apply_qwen3_tts_tokenizer_v2_patch()`、
  `apply_310p_patches()`；
- `platforms/npu/_310p/__init__.py:10-37`：`is_310p()` 优先从
  `vllm_ascend.device.device_config` 读取，兼容旧版 `vllm_ascend.utils.is_310p`；
- `_310p/__init__.py:42-47`：仅当 `is_310p()` 为真时才应用 310P 补丁；
- `_310p/patch/__init__.py:13-36`：`apply_patches()` 依次应用
  worker / device_ops / attention / qwen3_moe 补丁；
- `_310p/patch/__init__.py:39-69`：`apply_model_patches(model_config)` 按
  `architectures[0]` 分派：
  - `Qwen3TTSTalkerForConditionalGeneration` → `apply_talker_patches()`
  - `Qwen3TTSCode2Wav` → `apply_code2wav_patches()`
  - `Qwen3MoeForCausalLM` → `apply_qwen3_moe_patches()`

#### 4.3.4 310P worker 补丁：`_310p/patch/worker.py`

- `worker.py:25-32`：`_OmniNPUWorkerBase310P._init_device()` 在设备初始化后调用
  `disable_jit_compile()`（`torch_npu.npu.set_compile_mode(jit_compile=False)`）；
- `worker.py:35-61`：`_patch_weight_nz_fallback()` 允许
  `additional_config.weight_nz_mode=0` 关闭 FRACTAL_NZ 权重转换。
  这正是我们在 deploy YAML 里设置 `weight_nz_mode: 0` 的原因：CANN 9.0.1 的
  ascend310p 没有 `aclnnMatmulWeightNz`，不关掉会在第一个 dense Linear 处失败；
- `worker.py:63-68`：`apply_patch()` 同时把 `AscendSampler310.apply_penalties`
  换回 vLLM 原生实现（Triton-Ascend 不支持 310P）。

#### 4.3.5 310P TTS 模型补丁：`_310p/patch/qwen3_tts.py`（原始 v0.30 逻辑）

| 类 / 函数 | 原始行号 | 作用 |
| --- | --- | --- |
| 模块常量 `_RUNTIME_DTYPE = torch.float16` | `:28` | 310P 统一运行 dtype |
| `_Qwen3TTSTalker310P` | `:34-80` | Talker 包装：embedding 强制 FP16；`talker_mtp_graph_safe=False`；`talker_mtp_accepts_per_row_generators=True`；`load_weights` 后把 Mimi encoder 移到 CPU |
| `_Qwen3TTSPromptEmbedsBuilder310P` | `:83-95` | prompt embedding 的 310P 版本 |
| `_Qwen3TTSCode2Wav310P` | `:98-112` | code2wav 解码 dtype 固定 FP16 |
| `_Qwen3CodePredictorAttention310P` | `:115-206` | 310P flash-attention（`torch_npu._npu_flash_attention`）+ 16 token 对齐 + NZ mask |
| `_Qwen3CodePredictorDecoderLayer310P` | `:209-227` | 把 310P mask 传入 attention |
| `_Qwen3CodePredictorBaseModel310P` | `:230-269` | 构造 `[max_seq, max_seq]` 的 310P causal additive mask 并转 NZ |
| `_Qwen3TTSTalkerCodePredictor310P` | `:272-450` | 310P CodePredictor 循环：`_prepare_npu_weights`、`load_weights`、逐 step 采样（top-k/top-p + `random_sample`） |
| `apply_talker_patches()` | `:458-485` | 把上述类安装到对应模块全局名 |
| `apply_code2wav_patches()` | `:487-495` | 安装 `_Qwen3TTSCode2Wav310P` |

> 本次运行中，`:115-450` 的 CodePredictor 专用路径因 ATB/ACLNN 限制不可用，见第 5 节。
> 其余 310P 补丁（FP16、参考音频下沉 CPU、code2wav dtype、worker/weight_nz）正常生效。

---

### 4.4 Stage 0：Talker 执行路径

#### 4.4.1 `NPUARModelRunner.execute_model`（`npu_ar_model_runner.py:313-798`）

- `:313-360`：从 `SchedulerOutput` 收集 `req_ids`、token span、`additional_information`；
- `:560-640`：调用 `self._preprocess(...)`，返回 `inputs_embeds`、`positions`、
  `decode_req_ids` 等；
- `:640-760`：`self.model(...)` 走 talker 主干（Qwen3 decoder layers）；
- `:799-838`：`_sample` 对 talker 的 codec 头采样（temperature/top_k/top_p）；
- `:839-...`：`sample_tokens` 把结果写回请求状态，并把 codec codes 放进
  `multimodal_output` 供 stage 1 消费。

#### 4.4.2 `_preprocess`（`gpu_model_runner.py:1638-1960`）

这是 Omni 与原生 vLLM 的最大差异所在：

- `:1638-1700`：整理 `additional_information`（text/speaker/instruct/task_type/ref_audio…），
  处理多模态 payload；
- `:1700-1850`：调用模型的 `preprocess()` 得到 `inputs_embeds`；
- `:1850-1960`：如果模型声明了 `talker_mtp`，在 decode 阶段执行
  `_talker_mtp_forward()`，把 MTP（code predictor）产出的 codec 直接拼进下一步
  输入。

#### 4.4.3 `talker.preprocess`（`qwen3_tts_talker.py:868-1070`）

逐段：

1. `:874-884`：把 `additional_information` 展平；`payload / embed / hs / meta` 分层。
2. `:886-893`：`span_len = input_ids.shape[0]`；空 span 直接返回 embedding。
3. `:895-902`：判断 prefill / decode：
   `_omni_num_computed_tokens < _omni_prompt_len`。
4. `:904-905`：如果没有 text conditioning 就报错，避免空请求进模型。
5. `:907-923`：解析 `task_type` 与 `codec_streaming`（Base 任务默认流式）。
6. `:925-930`：把 `tts_pad_embed` 预取到目标 device/dtype。
7. `:932-970`：**prefill**：第一次调用
   `self._prompt_builder.build_prompt_embeds(task_type, info_dict)`，得到
   `full_prompt_embeds / tailing_text_hidden / ref_code_len / ref_code`；
   后续 chunk 从已保存的 buffer 切片。
8. `:970-1060`：**decode**：用上一步的 `last_talker_hidden` + `text_step` +
   codec embedding 组装 1 个 token 的输入；这就是 AR 循环的输入。
9. 返回 `(input_ids, inputs_embeds, extra)`，其中 `extra` 携带
   `codes.audio` / `codes.ref` 等给 stage 1。

> `prompt_token_ids` 的“占位长度”在这里被彻底忽略：真正的 embedding 由
> `_prompt_builder` 生成，长度由文本/参考音频决定。示例里的
> `_estimate_prompt_len` 只是为了让 vLLM 的 KV cache/scheduler 有一个正确的
> 长度上界。

#### 4.4.4 `talker.forward` / `compute_logits`（`qwen3_tts_talker.py:639-712`）

- `:639-648`：`self.model(...)` 走 Qwen3 backbone；`self.code_predictor` 在
  `__init__`（`:417` 附近）构造；
- `:649-712`：`compute_logits` 取 codec 头（vocab = codec codebook 大小，
  本次日志中为 3072），因此 `min_tokens` 里 151645 这类文本 stop id 会被丢弃
  （日志：`min_tokens: dropped stop token ids [151645] ... vocabulary (3072)`）。

#### 4.4.5 `talker.talker_mtp`（`qwen3_tts_talker.py:1495-1565`）

逐行：

```python
bsz = int(input_ids.shape[0])
q  = int(self.talker_config.num_code_groups)          # 本次 q=16
input_ids   = input_ids.reshape(bsz, 1).to(long)
last_id_hidden = input_embeds.reshape(bsz, 1, -1).to(dtype)
past_hidden    = last_talker_hidden.reshape(bsz, 1, -1)
text_step      = text_step.reshape(bsz, 1, -1)
max_steps = q - 1                                     # 预测 15 个 residual codebook
if max_steps <= 0: ...                                # 边界保护
subtalker_params = self._subtalker_sampling_params
# 默认 do_sample/temperature/top_k/top_p
audio_codes = self.code_predictor(
    layer0_code=..., layer0_embed=..., last_talker_hidden=...,
    do_sample=..., temperature=..., top_k=..., top_p=...,
    generator=..., generators=...,
    sample_uniforms=sample_uniforms,                  # ← 310P patch 曾缺这个参数
)
# 无效 layer0（EOS/PAD）映射为 0
# 用 _stacked_codec_embed 一次性 gather 所有 residual embedding
# 返回 (inputs_embeds_out, audio_codes)
```

关键点：

- **CodePredictor 不是独立模型**，而是 talker 每一步 decode 内联执行的 MTP 头；
- `audio_codes` 形状 `[B, q]`，每行是一个 codec frame 的 16 个 codebook id；
- `sample_uniforms` 是 MRV2/图安全采样使用的预生成均匀随机数；V1 eager 路径
  虽然传 `None`，但函数签名必须接收它——这就是本次第一个兼容性问题的来源。

#### 4.4.6 `_talker_mtp_forward`（`gpu_model_runner.py:1962-2118`）

- `:1962-1985`：根据 decode batch 决定是否走 cudagraph；如果 `talker_mtp` 不是
  平台 graph wrapper，则强制 `CUDAGraphMode.NONE`；
- `:1986-2035`：按请求解析 `tts_local_seed`，为每行建立独立的
  `torch.Generator`，保证多请求 batch 内随机性互不污染；
- `:2040-2075`：batch>1 且存在 per-row generator、但模型不声明
  `talker_mtp_accepts_per_row_generators` 时，退化为逐行串行；
- `:2076-2118`：组装 `talker_kwargs`（do_sample/temperature/top_k/top_p），
  在 `current_omni_platform.set_forward_context(...)` 中调用 `self.talker_mtp(...)`，
  拿回 `req_embeds, code_predictor_codes`。

#### 4.4.7 CodePredictor 内部（`common/qwen3_code_predictor.py`）

- `CodePredictorAttention`（`:157-317`）：packed QKV（`qkv_proj`）、q/k RMSNorm、
  RoPE、GQA、`F.scaled_dot_product_attention` / NPU fused attention；
- `CodePredictorDecoderLayer`（`:353-390`）：pre-norm + attention + `npu_add_rms_norm`
  + MLP；
- `CodePredictorBaseModel`（`:392-468`）：embedding + N 层 decoder + final norm；
- `CodePredictorWrapper`（`:615-...`）：
  - `:631-708`：初始化 `lm_head` 列表、`codec_embedding` 列表、`small_to_mtp_projection`；
  - `:734-779`：`_setup_compile()`：
    - NPU 且 `use_cuda_graphs=True` → 先 `_warmup_buckets()` 再
      `_capture_npu_graphs()`；
    - 否则直接 `self._compiled_model_fwd = self.model.forward`（纯 eager）；
  - `:1090-1248`：`forward()`：
    - `:1092-1105`：校验 `sample_uniforms` 形状 `(B, q-1, vocab)`；
    - `:1120-1145`：把 talker hidden / layer0 embed 写入 `proj_buf` 前两个位置；
    - `:1185-1240`：循环 `step=1..q-1`：
      - `lm_heads[step-1]` 得 logits；
      - `stored` 模式：top-k → top-p → Gumbel-max；
      - `per_call` 模式：temperature → top-k → Gumbel-max；
      - `sample_uniforms` 存在时用 `uniforms=step_uniforms` 做确定性 Gumbel；
      - 采样出的 code 写回 `all_codes[:, step]`；
      - 用 `codec_embedding[step-1]` + `small_to_mtp_projection` 生成下一步输入。

> 本次日志 `code_predictor: torch.compile disabled` 说明走的是 NPU 无 Inductor
> 的 eager 分支；因为我们又禁用了 NPU graph，所以没有 `_warmup_buckets` /
> `_capture_npu_graphs` 的图捕获开销。

---

### 4.5 Stage 0 → Stage 1：异步 chunk 与共享内存

#### 4.5.1 `talker2code2wav_async_chunk`（`stage_input_processors/qwen3_tts.py:106-423`）

- `:106-140`：读取 `multimodal_output` 中的 `codes.audio`、`codes.ref`；
- `:140-240`：按 `codec_chunk_frames=25`、`codec_left_context_frames=72` 切窗；
  `initial_codec_chunk_frames=1` 表示首包只发 1 帧以降低 TTFA；
- `:240-360`：构造 stage 1 的 `input_ids` / `additional_information`，
  包括参考 codec 上下文与当前窗口；
- `:360-423`：把 payload 交给 `SharedMemoryConnector`。

本次为 `full_utterance_decode=True`，stage 0 在整句结束后一次性下发完整 codec
序列（日志 `Code2Wav codec: frames=58 q=16 batch=1`），因此传输开销接近 0
（`transfers=[0->1=0.00ms]`）。

#### 4.5.2 `SharedMemoryConnector`（`distributed/omni_connectors/connectors/shm_connector.py:20+`）

- 小对象走元数据通道，大 tensor 走共享内存；
- `connector_get_sleep_s=0.01`、`connector_get_max_wait=300` 控制轮询节奏；
- 本次两 stage 在同一 chip 的两个进程上，shm 拷贝是主要传输方式。

---

### 4.6 Stage 1：Code2Wav 解码

#### 4.6.1 `Qwen3TTSCode2Wav.__init__`（`qwen3_tts_code2wav.py:73-121`）

- 构造 codec decoder（Conv/Transformer 混合结构）、`codec_embedding`、
  `speech_tokenizer` 的解码侧；
- 310P 补丁把 `_npu_decoder_runtime_dtype()` 固定为 `torch.float16`。

#### 4.6.2 `forward`（`qwen3_tts_code2wav.py:256-543`）

- `:256-300`：从 `input_ids` / `additional_information` 还原
  `[frames, q]` 的 codec 矩阵；
- `:300-380`：按 `codec_chunk_frames` 切块，逐块送 decoder；
- `:380-445`：decoder 输出波形；`Code2Wav codec: frames=58 q=16 batch=1`
  就是这里的统计；
- `:445-540`：把音频块累积到 `multimodal_output["audio"]`，并记录
  `sr=24000`；
- `:544-565`：`make_omni_output()` 把最终音频封装成 Omni 输出。

本次 Stage 1 的 `serving_time_to_first_output_ms=69 276.7`，说明它等到了
stage 0 的完整 payload 才开始解码（`full_utterance_decode` + 非流式）。

---

## 5. 本次定位的问题、根因与处理

| # | 现象 | 根因 | 处理 |
| --- | --- | --- | --- |
| 1 | `AttributeError: compute_mm_prefix_ranges` | 当前分支（main）要求 vLLM 0.33；本机是 vLLM 0.30.0 | 使用仓库内 v0.30.0 release 树 worktree |
| 2 | `aclnnInplaceOne failed ... DT_BFLOAT16` | 310P 不支持 BF16，默认 dtype 解析为 bfloat16 | deploy 配置 `dtype: float16` |
| 3 | 首个 dense Linear 处 NZ 权重失败 | CANN 9.0.1 ascend310p 无 `aclnnMatmulWeightNz` | `additional_config.weight_nz_mode: 0`（310P patch 已提供 fallback） |
| 4 | `Following weights were not initialized: code_predictor..._fused_qkv_weight` | 310P patch 的 `_fused_qkv_weight` 是运行期由 `qkv_proj` 派生的张量，不在 checkpoint 中 | `model_loader_extra_config.enable_weights_track: false` |
| 5 | `forward() got an unexpected keyword argument 'sample_uniforms'` | v0.30 talker 无条件把 `sample_uniforms` 传给 CodePredictor，310P patch 的 forward 签名未接收 | 在 worktree 的 310P forward 增加参数并忽略（V1 eager 用 torch RNG） |
| 6 | `OSError: libatb.so: cannot open shared object file` | 环境未 source NNAL ATB 的 set_env | `LD_LIBRARY_PATH` 增加 `.../atb/cxx_abi_1/lib` |
| 7 | `SelfAttentionOperation setup failed!` | ATB `_npu_flash_attention` 在当前 CANN 9.0.1 + ATB 8.3.RC1 组合下 setup 失败 | 绕过 310P CodePredictor 专用 attention patch |
| 8 | `aclnnFlashAttentionScore failed, error code 161001` | 通用 `npu_fusion_attention` 对 CodePredictor 的短 GQA 形状也不可用 | 使用纯 PyTorch matmul+softmax 的 eager attention fallback |
| 9 | `onnxruntime ... _ARRAY_API not found`（警告） | onnxruntime 由 NumPy 1.x 编译，环境是 NumPy 2.2.6 | 仅出现在 `_estimate_prompt_len` 的 try/except 中，不影响主流程 |

### 5.1 本次引入的本地兼容 shim（仅 worktree，不进入主仓库）

> 这些 shim 是为了在**当前软件栈**上先跑通功能，不是上游推荐实现。

1. `vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py`
   - `_Qwen3TTSTalkerCodePredictor310P.forward` 增加
     `sample_uniforms: torch.Tensor | None = None` 并 `del`（兼容调用签名）。
   - `apply_talker_patches()` 中注释掉 310P CodePredictor 的类替换，
     改为安装 `_CodePredictorAttentionEager310P`（纯 PyTorch attention）。
2. `vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_code_predictor_vllm.py`
   - `use_cuda_graphs=False`，避免对 eager attention 做 NPU 图捕获。

### 5.2 对上游/roadmap 的含义

- 310P 的 CodePredictor 专用路径目前**依赖 ATB flash attention**，而
  `torch_npu._npu_flash_attention` 在 CANN 9.0.1 + ATB 8.3.RC1 上 setup 失败；
  需要确认匹配的 ATB/NNAL 版本，或提供不依赖 ATB 的 310P attention 实现。
- 通用 `npu_fusion_attention` 对 `head_dim=128`、短序列、GQA 的 CodePredictor
  形状也不可用（161001），不能简单“回退到通用 SDPA”。
- `sample_uniforms` 的签名不一致说明 v0.30 release 树的 310P patch 与
  talker 代码存在版本漂移；建议在 310P CI 中加一条最小 TTS smoke。

---

## 6. 性能数据与瓶颈

日志（`--log-stats`）摘录：

| 指标 | Stage 0 (talker) | Stage 1 (code2wav) |
| --- | --- | --- |
| `stage_gen_time_ms` | 43 305.996 | 69 250.929 |
| `serving_time_to_first_output_ms` | 43 330.958 | 69 276.679 |
| `num_tokens_in / out` | 36 / 59 | 0 / 0 |
| `vllm_ttft_ms` | 16 505.863 | 69 249.474 |
| `vllm_itl_ms` | 462.190（n=58） | — |
| `audio_duration_s` | — | 4.640 |
| `audio_generated_frames` | — | 111 360 |

整体：

- `e2e_wall_time_ms = 69 277.911`
- `e2e_total_tokens = 95`
- `e2e_avg_tokens_per_s = 1.371`
- `RTF = 69.28 / 4.64 ≈ 14.9`

瓶颈判断：

1. **Stage 0 占主导**：43.3 s 生成 59 个 codec frame，ITL ≈ 462 ms/frame；
   310P 无 HCCS、无 BF16、eager 执行，单步 decode 很慢。
2. **Stage 1 串行等待**：`full_utterance_decode=True` 时 stage 1 要等 stage 0
   全部结束（69.25 s ≈ stage 0 结束 + 解码），没有流水重叠。
3. **本次不是性能基线**：attention fallback 和 `enforce_eager` 都会显著拖慢；
   要得到 310P 性能基线，需要先解决 ATB/ACLNN 的 flash-attention 路径，并恢复
   CodePredictor 图捕获。
4. **模型加载时间未计入 e2e**：`Omni(...)` 构造（两个 stage 加载 4.5 GB 权重 +
   codec）在计时之外，冷启动实际更长。

### 6.1 2026-11-14 复跑确认

使用与首次完全相同的 deploy 配置、模型和入口，在物理 chip 2 上复跑（日志
`/tmp/qwen3tts_run/run4.log`，输出 `output_0_a076d91e-...wav`）：

| 指标 | Stage 0 (talker) | Stage 1 (code2wav) |
| --- | --- | --- |
| `stage_gen_time_ms` | 40 463.088 | 48 787.538 |
| `serving_time_to_first_output_ms` | 40 486.300 | 48 811.359 |
| `num_tokens_in / out` | 36 / 59 | 0 / 0 |
| `vllm_ttft_ms` | 14 778.346 | 48 785.722 |
| `vllm_itl_ms` | 442.863（n=58） | — |
| `audio_duration_s` | — | 4.640 |
| `audio_generated_frames` | — | 111 360 |

复跑结果：

- `e2e_total_ms = 48 789.231`，`RTF = 48.79 / 4.64 ≈ 10.5`；
- 输出 wav 与首次运行**逐字节同长**（222 764 B）、同采样率、同时长、
  同峰值（0.711），说明流程稳定、可复现；
- 初始化：Stage 0 权重加载 12.97 s、engine init 5.02 s；
  Stage 1 权重加载 5.03 s、engine init 2.44 s；
- Stage 0 启动时空闲显存 42.32/43.24 GiB，权重 3.75 GiB，KV cache 4.08 GiB；
- 本次未设置 `LD_LIBRARY_PATH` 指向 ATB，仍成功——因为当前生效的是
  eager-attention shim，不加载 `libatb.so`。

> 耗时从 69.25 s 降到 48.79 s，主要差异来自机器负载/首次缓存状态，而非代码变更；
> 两者都仍是 eager、未优化的功能基线，不能作为性能结论。

---

## 7. 后续建议

1. **版本路线**：310P 继续锁 vLLM 0.30.0 + vllm-ascend 0.30.0；不要单独升级
   vLLM 到 0.33。若要跟 main，需要先发布/验证 0.33 对应的 310P vllm-ascend。
2. **ATB 对齐**：确认 310P 推荐的 NNAL ATB 版本，或让 310P patch 不依赖
   `_npu_flash_attention`；当前 8.3.RC1 与 torch_npu 2.10 的组合不可用。
3. **恢复性能路径**：在 flash-attention 可用后，恢复 CodePredictor 的 NPU graph
   捕获；先测 0.6B CustomVoice 的 RTF/首包，再评估 1.7B。
4. **量化**：310P 带宽/算力受限，W8A8 与 INT8 KV 是下一步的主要收益点。
5. **CI**：把本次 smoke 固化成 `pytest -m 'core_model and npu and 310P'` 的
   最小用例：启动、单请求、wav 非空、时长 > 0、退出码 0。
6. **清理 shim**：把 `sample_uniforms` 签名修复、attention fallback、
   `use_cuda_graphs` 开关整理成带平台条件判断的上游补丁，避免长期维护 fork。

---

## 8. 基于 main 的本地源码环境（2026-11-14）

> 本节回答“能否不用容器、直接基于本地环境跑 main 并做 310P 适配”。
> 结论：**可以**。已在本地从源码搭出 vLLM 0.33 + vllm-ascend + omni main，
> 并在物理 chip 2 上跑通 Qwen3-TTS，输出与 v0.30 基线**逐字节同长、同峰值**。

### 8.1 版本矩阵

| 组件 | 版本 / 提交 | 说明 |
| --- | --- | --- |
| vLLM | `0.33.0+empty`（源码构建） | `VLLM_TARGET_DEVICE=empty`，不依赖 CUDA |
| vllm-ascend | `17f07e3`（源码构建） | vLLM 0.33 Main2Main 之后、删除 `worker/v1` 之前 |
| vLLM-Omni | `main`（本地 `7c586b5cb` 基线 + 未提交适配） | editable 安装 |
| CANN | 9.1.0（`/home/yf/cann91/cann-9.1.0`） | 官方 310P 镜像是 9.2.1；9.1.0 属未验证组合 |
| torch / torch_npu | 2.10.0 / 2.10.0.post7 | vllm-ascend 0.33 的硬依赖 |
| transformers | 5.19.0 | 同时满足 vLLM 0.33 与 omni main |
| numpy | 2.2.6 | vLLM 0.33 构建后的版本 |
| Python | 3.11.15 | venv：`/home/yf/WorkSpace/.venvs/vllm-omni-033` |

### 8.2 为什么必须 pin `vllm-ascend 17f07e3`

omni main 的 NPU worker 仍 import `vllm_ascend.worker.v1.*`：

```python
# vllm_omni/platforms/npu/worker/npu_ar_model_runner.py:45
from vllm_ascend.worker.v1.model_runner import graph_capture
```

而 vllm-ascend main HEAD（`76ea9d2`）已被
`c3c48aa [Refactor][Worker] Remove Model Runner V1 (#20097)` 删除该目录。
`17f07e3` 是该删除提交的父提交，既包含 vLLM 0.33 对齐
（`760d7ec Main2Main v0.33.0`），又保留 `worker/v1` 与
`_310p/sample/sampler.py`，是当前 omni main 的兼容点。

> 官方 310P nightly 镜像（`quay.io/ascend/vllm-omni:nightly-...-310p`）
> 也是按某个固定 vllm-ascend 提交构建的；从源码复现时必须同样 pin 提交，
> 不能直接跟 vllm-ascend main 漂移。

### 8.3 本地构建步骤

```bash
# 0) 独立 venv，不动 v0.30 环境
python3.11 -m venv /home/yf/WorkSpace/.venvs/vllm-omni-033
V=/home/yf/WorkSpace/.venvs/vllm-omni-033/bin
$V/pip install -U pip
$V/pip install torch==2.10.0 torchvision==0.25.0 torchaudio==2.10.0 \
                torch_npu==2.10.0.post7 ninja

# 1) Rust（vLLM Rust 前端是 optional；1.95 已下架，用 stable 1.100）
export RUSTUP_DIST_SERVER=https://mirrors.tuna.tsinghua.edu.cn/rustup
curl -sSfL -o /tmp/rustup-init \
  https://mirrors.tuna.tsinghua.edu.cn/rustup/rustup/dist/aarch64-unknown-linux-gnu/rustup-init
chmod +x /tmp/rustup-init && /tmp/rustup-init -y --profile minimal --default-toolchain stable
source $HOME/.cargo/env

# 2) vLLM 0.33（CPU/empty 目标）
git clone --depth 1 -b releases/v0.33.0 \
  https://github.com/vllm-project/vllm.git /home/yf/WorkSpace/src/vllm-033
$V/pip install -r /home/yf/WorkSpace/src/vllm-033/requirements/build/rust.txt \
              -r /home/yf/WorkSpace/src/vllm-033/requirements/common.txt \
              av scipy soundfile soxr 'mistral_common[audio]'
cd /home/yf/WorkSpace/src/vllm-033
export PATH=$HOME/.cargo/bin:$PATH RUSTUP_TOOLCHAIN=stable
export PROTOC_INCLUDE=/home/yf/miniconda3/envs/py3.11/include
VLLM_TARGET_DEVICE=empty $V/pip install -e . --no-build-isolation
$V/pip uninstall -y triton
rm -rf $V/../lib/python3.11/site-packages/triton   # 空目录会让 torch._dynamo 报错

# 3) vllm-ascend 17f07e3（310P，跳过可选的 custom kernels）
git clone https://github.com/vllm-project/vllm-ascend.git \
  /home/yf/WorkSpace/src/vllm-ascend-main
cd /home/yf/WorkSpace/src/vllm-ascend-main
git checkout 17f07e3
source /home/yf/cann91/set_env_9.1.0.sh
export SOC_VERSION=ascend310p1 COMPILE_CUSTOM_KERNELS=0 \
       TASK_QUEUE_ENABLE=1 OMP_NUM_THREADS=1
$V/pip install -e . --no-build-isolation --no-deps

# 4) omni main + NPU 运行依赖
cd /home/yf/WorkSpace/vllm-omni
$V/pip install -r requirements/npu.txt \
  --extra-index-url https://mirrors.huaweicloud.com/ascend/repos/pypi \
  --extra-index-url https://mirrors.huaweicloud.com/ascend/repos/pypi/nightly
$V/pip install -e . --no-build-isolation --no-deps
```

构建环境注意（CANN 9.1.0 本地安装的坑）：

1. `cann-9.1.0/set_env.sh` 与 `bin/setenv.bash` 都硬编码了
   `/data/chenyh/ascend/9.1.0/cann-9.1.0`。前者已复制为
   `/home/yf/cann91/set_env_9.1.0.sh` 并修正；后者属于其他用户、不可写，
   因此在 vllm-ascend 构建克隆的 `csrc/build.sh::set_env()` 中追加：

   ```bash
   source /home/yf/cann91/set_env_9.1.0.sh
   ```

2. CANN 9.1 的 `pkg_inc` 在 `aarch64-linux/` 下，而 CMake 模块还会查根目录。
   已补软链：
   `cann-9.1.0/pkg_inc/base -> aarch64-linux/pkg_inc/base`，
   `aarch64-linux/pkg_inc/base/alog_pub.h -> ../../include/base/alog_pub.h`。

3. 运行期需要 ATB 库：
   `LD_LIBRARY_PATH=/usr/local/Ascend/nnal/atb/8.3.RC1/atb/cxx_abi_1/lib:$LD_LIBRARY_PATH`。

4. `COMPILE_CUSTOM_KERNELS=0` 会跳过 `build_aclnn`（310P 的 GDN/attention
   custom ops）。Qwen3-TTS 不需要这些算子；如果后续模型需要，改为 1 并完整编译。

### 8.4 为跑通 main 增加的 4 个本地适配

这些改动在当前工作区（未提交），全部位于
`vllm_omni/platforms/npu/_310p/patch/`：

| # | 文件 | 改动 | 触发问题 |
| --- | --- | --- | --- |
| 1 | `worker.py` | 对 `vllm_ascend._310p.sample.sampler.AscendSampler310` 做 `try/except ImportError` | vllm-ascend 新版本把 310P sampler 移到 `worker/v2`；旧路径不存在时不再 import 失败 |
| 2 | `device_ops.py`（新增） | 用纯 torch 实现 `Ascend310PDeviceAdaptor.reshape_and_cache` | CANN 9.1 + ATB 8.3 无 `ReshapeAndCache` kernel，KV cache 写入报 `ReshapeAndCacheOperation setup failed` |
| 3 | `attention.py`（新增） | 用纯 torch 实现 310P 的 prefill / paged decode / chunked prefill attention | ATB `SelfAttentionOperation setup failed` |
| 4 | `qwen3_tts.py` | ① 给 `_Qwen3TTSTalkerCodePredictor310P.forward` 增加 `sample_uniforms` 参数；② `apply_talker_patches()` 改为安装 `_CodePredictorAttentionEager310P`，不再安装 ATB flash-attention 的 CodePredictor | `TypeError: ... unexpected keyword argument 'sample_uniforms'`；以及 CodePredictor 的 ATB flash attention 失败 |
| 5 | `patch/__init__.py` | 在 `apply_patches()` 中调用 `apply_device_op_patches()` 与 `apply_attention_patches()` | 让 #2/#3 生效 |

> #2/#3 是针对 **CANN 9.1.0 + ATB 8.3.RC1** 的兼容回退；官方 310P 镜像使用
> CANN 9.2.1，可能不需要。若后续升级到 9.2.1，应先在真机上验证 ATB 算子是否可用，
> 再决定是否保留这些回退。

### 8.5 运行命令与结果

```bash
source /home/yf/cann91/set_env_9.1.0.sh
export PATH=/home/yf/WorkSpace/.venvs/vllm-omni-033/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/Ascend/nnal/atb/8.3.RC1/atb/cxx_abi_1/lib:$LD_LIBRARY_PATH

cd /tmp/qwen3tts_main          # 内含 Qwen/Qwen3-TTS-... 本地软链
ASCEND_RT_VISIBLE_DEVICES=2 \
/home/yf/WorkSpace/.venvs/vllm-omni-033/bin/python \
  /home/yf/WorkSpace/vllm-omni/examples/offline_inference/text_to_speech/qwen3_tts/end2end.py \
  --deploy-config /tmp/qwen3tts_main/qwen3_tts_310p.yaml \
  --output-dir /tmp/qwen3tts_main/out --log-stats
```

310P deploy 配置与 v0.30 相同：顶层 `dtype: float16`、stage 1 `dtype: float16`、
每个 stage `additional_config.weight_nz_mode: 0`、
`model_loader_extra_config.enable_weights_track: false`、`enforce_eager: true`。
配置已落到 `vllm_omni/deploy/qwen3_tts_310p.yaml`。

一键复现脚本：`scripts/run_qwen3_tts_310p_main.sh`（支持 `DEVICE_ID`、`QUERY_TYPE`、
`BATCH_SIZE`、`RUN_DIR`、`MODEL_DIR` 等环境变量覆盖，额外参数透传给 `end2end.py`）：

```bash
DEVICE_ID=2 scripts/run_qwen3_tts_310p_main.sh
# 流式 / 批量 / 指定文本
DEVICE_ID=2 scripts/run_qwen3_tts_310p_main.sh --streaming
DEVICE_ID=2 BATCH_SIZE=2 scripts/run_qwen3_tts_310p_main.sh --use-batch-sample
```

实测（日志 `/tmp/qwen3tts_main/run7.log`）：

| 指标 | 值 |
| --- | --- |
| 退出码 | 0 |
| 输出 | `output_0_54f1b1e6-....wav`，24 kHz，111,360 samples，4.640 s，峰值 0.711 |
| 端到端 | 56.38 s（Stage 0 31.52 s，Stage 1 56.38 s） |
| Stage 0 权重加载 / engine init | 12.51 s / 4.85 s |
| Stage 1 权重加载 / engine init | 4.72 s / 2.41 s |
| CodePredictor | 捕获 NPU graph buckets `[1,2,4,8,16,32,64]` |
| 与 v0.30 对比 | 输出 wav 同为 222,764 B、4.640 s、峰值 0.711；总耗时 56.38 s vs 48.79 s |

> 耗时略高于 v0.30，主要因为 #3 的纯 torch attention 回退（未走 ATB/融合算子）。
> 这仍是“功能跑通”基线，不是性能基线。

### 8.6 与官方容器镜像的关系

本地源码路线等价于在复现官方 310P 镜像的内容：

- `quay.io/atlas-ci/vllm-ascend:v0.33.0-310p`：vLLM 0.33 + vllm-ascend + 310P；
- `quay.io/ascend/vllm-omni:nightly-20261114-a7725c2-310p`：omni main + 310P
  （CANN 9.2.1）。

如果只是做模型适配、不想维护 CANN/源码构建，用镜像并通过 `-v` 挂载本地 main
仓库更省事；如果必须“本地无容器”，按 §8.3 的步骤即可复现。

### 8.7 后续建议

1. **固定版本三元组**：`vllm 0.33.0` + `vllm-ascend 17f07e3` + `omni main`。
   升级 vllm-ascend 前先确认 `worker/v1`、`_310p/sample` 等路径是否仍在。
2. **优先升级到 CANN 9.2.1**：可以去掉 #2/#3 两个回退，恢复 ATB 融合算子性能。
3. **把 4 个适配拆成上游 patch**：
   - `sample_uniforms` 签名属于 omni main 的版本漂移，应直接修；
   - `AscendSampler310` 的 import 应做版本兼容；
   - `ReshapeAndCache` / attention 回退应加 `is_310p` + CANN 版本门控，
     默认只在 9.1 启用。
4. **补 310P 真机 CI**：启动、单请求、wav 非空、时长 > 0、退出码 0；
   再逐步加 WER/CER 与 RTF。
5. 新模型适配按 `.claude/skills/add-tts-model` 的清单走，先复用
   `_310p/patch/` 的 device-op/attention 回退，再评估图捕获。

---

## 附录 A：本次运行产物

| 产物 | 路径 |
| --- | --- |
| 输出音频（首次） | `/tmp/qwen3tts_run/out/output_0_bbd04f21-8f1f-4463-834f-b43c5b502427.wav` |
| 输出音频（复跑） | `/tmp/qwen3tts_run/out/output_0_a076d91e-dfec-4df2-a86e-b5b5b611fdff.wav` |
| 成功运行日志（首次） | `/tmp/qwen3tts_run/run9.log` |
| 成功运行日志（复跑） | `/tmp/qwen3tts_run/run4.log` |
| 失败诊断日志 | `run2.log` ~ `run8.log` |
| 310P deploy 配置 | `/tmp/qwen3tts_run/qwen3_tts_310p.yaml` |
| v0.30.0 工作树 | `/home/yf/WorkSpace/.worktrees/vllm-omni-v030` |

## 附录 B：关键文件索引

| 主题 | 文件 |
| --- | --- |
| 示例入口 | `examples/offline_inference/text_to_speech/qwen3_tts/end2end.py` |
| Pipeline 定义 | `vllm_omni/model_executor/models/qwen3_tts/pipeline.py` |
| 引擎入口 | `vllm_omni/entrypoints/omni.py`、`omni_base.py` |
| 引擎编排 | `vllm_omni/engine/omni_engine_base.py` |
| Stage 运行时 | `vllm_omni/engine/stage_runtime.py`、`stage_engine_startup.py` |
| 配置解析 | `vllm_omni/config/config_factory.py`、`stage_config.py` |
| NPU runner | `vllm_omni/platforms/npu/worker/npu_ar_model_runner.py` |
| 通用 runner | `vllm_omni/worker/gpu_model_runner.py` |
| Talker | `vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_talker.py` |
| CodePredictor | `vllm_omni/model_executor/models/common/qwen3_code_predictor.py` |
| Code2Wav | `vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_code2wav.py` |
| Stage 间传输 | `vllm_omni/model_executor/stage_input_processors/qwen3_tts.py`、`distributed/omni_connectors/connectors/shm_connector.py` |
| 310P 平台 | `vllm_omni/platforms/npu/_310p/` |
