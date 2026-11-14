# TTS 代码阅读指南

> 以 Qwen3-TTS 为主线，面向第一次阅读 vLLM-Omni 代码的同学；最后一章单独讲 310P。
> 代码基线：当前 `001-reports` 分支（`c975ab71b` 前后）。
> 建议阅读方式：**先按第 1～3 章跟一条请求走通，再回头补模型细节（第 4～5 章）**。
> 不要从 `orchestrator.py`（4262 行）第一行开始读。

---

## 0. 先记住 6 个词

| 词 | 一句话解释 | 在本仓库里对应什么 |
| --- | --- | --- |
| **TTS** | Text-to-Speech，文本生成语音 | 输入文字，输出 24 kHz PCM |
| **Token** | 模型处理的最小单位 | Talker 每步输出 1 个“帧起始 token” |
| **Codec** | 把音频压成离散编号的编解码器 | 16 个码本，每帧 16 个整数 |
| **Frame** | 一帧音频 | 12.5 Hz，即 **80 ms** 一帧 |
| **AR** | 自回归，一步一步往后猜 | Talker 是一个 Qwen3 解码器 |
| **Stage** | 流水线中的一段 | Qwen3-TTS 有 2 段：Talker → Code2Wav |

再记住这张总图：

```text
文字 / 说话人 / 参考音频
        │
        ▼
┌──────────────────────────── Stage 0: Talker（AR，自回归）────────────────────────────┐
│ 1. prompt_embeds_builder 把 text + 说话人 + codec 控制符拼成 embedding               │
│ 2. Qwen3 主干（28 层，hidden=2048）逐步前向                                           │
│ 3. lm_head 采样“第 0 个码本”的 token（vocab=3072，只允许 codec id 与 EOS）           │
│ 4. CodePredictor（5 层小 Transformer）一次补齐第 1～15 个码本                        │
│ 5. 一帧 = 16 个整数；每 80 ms 产生一帧                                               │
└───────────────────────────────────────────┬─────────────────────────────────────────┘
                                            │ codes: [帧数, 16]
                                            ▼
┌──────────────────────────── Stage 1: Code2Wav（非 AR，解码器）───────────────────────┐
│ 6. 16 个码本查表 → 8 层 Transformer + 上采样卷积                                      │
│ 7. 每帧还原成 1920 个采样点（24 kHz 下正好 80 ms）                                     │
└───────────────────────────────────────────┬─────────────────────────────────────────┘
                                            ▼
                                      24 kHz PCM / wav
```

**关键认知**：vLLM-Omni 不是“一个大模型”，而是**把两个模型拆成两段流水线**，由 Orchestrator 把 Stage 0 的输出喂给 Stage 1。读代码时始终问自己：*我现在在哪一段？数据是文本、codec codes，还是波形？*

---

## 1. 先跑起来：输入和输出长什么样

先看最小的离线入口：

```bash
python examples/offline_inference/text_to_speech/qwen3_tts/end2end.py --query-type CustomVoice
```

对应文件：[examples/offline_inference/text_to_speech/qwen3_tts/end2end.py](../examples/offline_inference/text_to_speech/qwen3_tts/end2end.py)。

### 1.1 输入不是一个字符串，而是一个字典

`get_custom_voice_query()` 最终构造出：

```python
inputs = {
    "prompt_token_ids": [0] * _estimate_prompt_len(...),   # 占位，后面解释
    "additional_information": {
        "task_type": ["CustomVoice"],
        "text": ["其实我真的有发现，我是一个特别善于观察别人情绪的人。"],
        "language": ["Chinese"],
        "speaker": ["Vivian"],
        "instruct": ["用特别愤怒的语气说"],
        "max_new_tokens": [2048],
        "full_utterance_decode": [True],
    },
}
```

注意三点：

1. **每个字段都是 list**。vLLM 原生按 batch 组织请求，Omni 沿用了这个约定，`[0]` 表示取第一条。
2. **`prompt_token_ids` 全是 0**。这不是真正的文本 token。Talker 的 `preprocess()` 会用 prompt builder 重新生成 `inputs_embeds`，token id 只用于让调度器知道“这条请求有多少个 token、要占多少 KV cache”。所以**长度必须和 embedding 长度一致**，数值本身无所谓。
3. **`additional_information` 才是 TTS 的真正输入**。它在进程间以结构化形式传递，Stage 0 的 `preprocess()` 从这里取 text/speaker/instruct。

`_estimate_prompt_len()`（[end2end.py:34](../examples/offline_inference/text_to_speech/qwen3_tts/end2end.py#L34)）就是在算这个占位长度；估不准时退回 2048。

### 1.2 输出是什么

`main()` 里：

```python
for stage_outputs in omni.generate(batch):
    output = stage_outputs
    _save_wav(output_dir, output.request_id, output.outputs[0].multimodal_output)
```

`multimodal_output` 里最关键的键是：

```python
{
    "audio": [tensor_0, tensor_1, ...],  # 若干段波形
    "sr": [24000],                       # 采样率
}
```

`_save_wav()`（[end2end.py:378](../examples/offline_inference/text_to_speech/qwen3_tts/end2end.py#L378)）把所有 `audio` 段 `torch.cat` 起来写成 wav。

> 读到这里的结论：**Stage 0 产出的是 codec codes，Stage 1 产出的是 audio 波形；入口只关心最终 audio。**

### 1.3 三个 task type

| task_type | 输入 | prompt 里放什么 |
| --- | --- | --- |
| `CustomVoice` | text + speaker + 可选 instruct | 预置说话人 embedding + 文本 |
| `VoiceDesign` | text + instruct | 用自然语言描述音色 + 文本 |
| `Base` | text + ref_audio（+ ref_text） | 参考音频编码出的 codec + speaker embedding |

对应模型权重是三套不同 checkpoint，但**代码路径是同一条**，只在 `prompt_embeds_builder.build_prompt_embeds()` 里分叉。

---

## 2. 第一层：从脚本到两个 Stage 进程

### 2.1 `Omni(**kwargs)`

`Omni` 是同步入口，定义在 [vllm_omni/entrypoints/omni.py:30](../vllm_omni/entrypoints/omni.py#L30)。它的构造链：

```text
Omni(**kwargs)
  └─ OmniBase.__init__                    vllm_omni/entrypoints/omni_base.py:174
       ├─ omni_snapshot_download(model)   # 把 HF id 变成可加载的本地路径
       └─ self._create_engine(...)        # 返回 AsyncOmniEngine
            └─ AsyncOmniEngine            vllm_omni/engine/async_omni_engine.py:48
```

`Omni._create_engine()` 在 [omni.py:33](../vllm_omni/entrypoints/omni.py#L33)，直接返回 `AsyncOmniEngine`。所以“同步/异步”只是入口层的包装差异，**底层是同一套引擎**。

### 2.2 配置是怎么选出来的

关键类：`StageConfigFactory`（[vllm_omni/config/config_factory.py:130](../vllm_omni/config/config_factory.py#L130)）。

`create_from_model()`（[config_factory.py:394](../vllm_omni/config/config_factory.py#L394)）做三件事：

1. 读 HF 的 `config.json`，得到 `model_type`（Qwen3-TTS 是 `qwen3_tts`）。
2. 到 `OMNI_PIPELINES` 注册表里找对应的 `PipelineConfig`：
   - 注册表：[vllm_omni/config/pipeline_registry.py:250](../vllm_omni/config/pipeline_registry.py#L250)
   - 注册项来自：[qwen3_tts/pipeline.py:32](../vllm_omni/model_executor/models/qwen3_tts/pipeline.py#L32)
3. 如果用户没传 `--deploy-config`，自动加载 `pipeline.default_deploy_config_name` 指向的 YAML：
   - 默认值在 [pipeline.py:33](../vllm_omni/model_executor/models/qwen3_tts/pipeline.py#L33)
   - 文件是 [vllm_omni/deploy/qwen3_tts.yaml](../vllm_omni/deploy/qwen3_tts.yaml)

### 2.3 两种配置：拓扑 vs 旋钮

这是新手最容易混淆的地方：

| 配置 | 在哪 | 谁改 | 管什么 |
| --- | --- | --- | --- |
| `PipelineConfig` | 模型目录下的 `pipeline.py` | 模型开发者 | **固定拓扑**：几个 stage、各是什么类型、谁接谁、用什么模型类 |
| `DeployConfig` + `StageDeployConfig` | `vllm_omni/deploy/*.yaml` | 部署者 | **可调参数**：显存比例、batch、chunk 大小、dtype、connector |

`PipelineConfig` 是 frozen dataclass（[stage_config.py:446](../vllm_omni/config/stage_config.py#L446)），`StageDeployConfig` 在 [stage_config.py:543](../vllm_omni/config/stage_config.py#L543)。两者由 `merge_pipeline_deploy()` 合并（[stage_config.py:1552](../vllm_omni/config/stage_config.py#L1552)）：

```text
PipelineConfig（拓扑）
      +
DeployConfig（YAML，先应用 platforms.<npu> 覆盖）
      ↓  merge_pipeline_deploy
list[StageConfig]  → 每个 stage 一个 vLLM 引擎
```

### 2.4 Qwen3-TTS 的两段拓扑

打开 [pipeline.py](../vllm_omni/model_executor/models/qwen3_tts/pipeline.py)：

```python
QWEN3_TTS_PIPELINE = PipelineConfig(
    model_type="qwen3_tts",
    default_deploy_config_name="qwen3_tts.yaml",
    model_arch="Qwen3TTSTalkerForConditionalGeneration",
    stages=(
        StagePipelineConfig(
            stage_id=0,
            model_stage="qwen3_tts",
            execution_type=StageExecutionType.LLM_AR,       # 自回归
            owns_tokenizer=True,
            engine_output_type="latent",                   # 中间产物：codec
            async_chunk_process_next_stage_input_func="...talker2code2wav_async_chunk",
            custom_process_next_stage_input_func="...talker2code2wav_full_payload",
            sampling_constraints={"detokenize": False, "stop_token_ids": [2150]},
            recompute_preemption="fail",
        ),
        StagePipelineConfig(
            stage_id=1,
            model_stage="code2wav",
            execution_type=StageExecutionType.LLM_GENERATION,  # 非 AR 的“生成”阶段
            input_sources=(0,),
            final_output=True,
            final_output_type="audio",
            engine_output_type="audio",
            model_arch="Qwen3TTSCode2Wav",
            sync_process_input_func="...talker2code2wav_token_only",
            requires_full_payload_input=True,
        ),
    ),
)
```

逐字段解释：

- `execution_type=LLM_AR`：Stage 0 使用 **AR 调度器 + AR ModelRunner**，一步一步采样。
- `engine_output_type="latent"`：Stage 0 的输出是中间表示（codec），不是最终音频。
- `final_output=True` / `final_output_type="audio"`：只有 Stage 1 的输出会返回给用户。
- `stop_token_ids=[2150]`：2150 是 `codec_eos_token_id`，Talker 采样到它就停止。
- `detokenize=False`：不要用文本 tokenizer 把 codes 解成文字。
- `requires_full_payload_input=True`：Stage 1 的“真实数据”走 worker 之间的 connector，不靠 prompt 里的 token id。
- `async_chunk_process_next_stage_input_func` / `sync_process_input_func`：**同一段流水线，在两种传输模式下的输入处理器**，第 3.5 节展开。

### 2.5 Stage 进程是怎么起的

每个 stage 最终都是一个独立的 vLLM EngineCore 进程（由 `StagePool` / `stage_engine_startup.py` 管理）：

```text
主进程
 ├─ Orchestrator 线程            # 调度、转发、汇总
 ├─ Stage 0 子进程               # vLLM engine + worker + GPUARModelRunner
 └─ Stage 1 子进程               # vLLM engine + worker + GPUGenerationModelRunner
```

Stage 之间通过 **connector** 传数据；Qwen3-TTS 默认用 `SharedMemoryConnector`（见 YAML 的 `connectors.connector_of_shared_memory`）。

> **读代码建议**：第一次读到这里就够了。`stage_pool.py`、`stage_engine_startup.py` 是“进程管理”代码，和 TTS 算法无关，可以先跳过。

---

## 3. 第二层：跟一条请求走完全程（重点）

### 3.1 时序总览

```text
用户 generate(prompt)
  │
  ▼
AsyncOmniEngine.add_request()
  │  把 prompt + sampling_params 打包成 EngineQueueMessage
  ▼
Orchestrator                               engine/orchestrator.py
  ├─ 找到 stage 0，提交请求
  ├─ async_chunk=True 时，先给 stage 1 提交一个“占位请求”（prewarm）
  ▼
Stage 0: AR Engine
  ├─ Scheduler 调度
  ├─ GPUARModelRunner.execute_model()
  │    ├─ model.preprocess()          # 文本 → prompt embeddings
  │    ├─ model.forward()             # Qwen3 主干
  │    ├─ model.compute_logits()      # lm_head + codec mask
  │    ├─ sampler                      # 采样第 0 个码本
  │    └─ model.talker_mtp()          # 补齐 15 个残差码本
  └─ 输出 codes.audio: [帧数, 16]
  │
  │  async_chunk: 每攒够 N 帧发一个 chunk
  │  sync:        等 talker 结束，一次性发全量
  ▼
Stage 1: Code2Wav Engine
  ├─ GPUGenerationModelRunner.execute_model()
  │    ├─ 从 connector 收 codes
  │    ├─ model.forward()             # decoder.chunked_decode()
  │    └─ 输出 model_outputs: [samples]
  ▼
Orchestrator._route_output()
  └─ final_output=True → OutputMessage → 前端
  ▼
OmniRequestOutput.outputs[0].multimodal_output["audio"]
```

### 3.2 第一步：`preprocess()` 把文字变成 embedding

代码：[qwen3_tts_talker.py:798](../vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_talker.py#L798)。

它只有一个入口，但内部有两种模式：

#### Prefill（第一次处理这条请求）

```python
full_prompt_embeds, trailing_text_hidden, ref_code_len, ref_code = (
    self._prompt_builder.build_prompt_embeds(task_type=..., info_dict=...)
)
```

`build_prompt_embeds()`（[prompt_embeds_builder.py:1210](../vllm_omni/model_executor/models/qwen3_tts/prompt_embeds_builder.py#L1210)）负责拼出 Talker 的初始输入。可以把它理解成“手工拼一个多模态 prompt”：

```text
[instruct?] + [角色控制符] + [speaker / ref_audio codec] + [文本 embedding] + [codec BOS/EOS]
```

- `text_embedding` + `text_projection`：把文本 tokenizer 的 id 投到 Talker 的 hidden 空间。
- `codec_embedding`：把 codec 控制符（`codec_bos_id=2149`、`codec_pad_id=2148`、`codec_think_*` 等）也投到同一个空间。
- 两者**逐元素相加**后，Talker 才能同时“看到文字”和“知道现在是音频生成模式”。

Prefill 结束后，`preprocess()` 返回：

```python
(input_ids_out, prompt_embeds, info_update)
```

其中 `input_ids_out` 全部填成 `codec_pad_id`（2148），因为真正的信息在 `prompt_embeds` 里。

#### Decode（后续每一步）

每一步只处理 1 个 token。它做三件事：

1. 从 `trailing_text_hidden` 队列里取一个文本 embedding（`text_step`）；
2. 取上一步 Talker 的最后一个 hidden（`past_hidden`）；
3. 把当前输入 token 的 embedding 作为 `inputs_embeds` 返回，并把 `(past_hidden, text_step)` 放进 `mtp_inputs`，交给后面的 `talker_mtp()`。

> 这里的 `trailing_text_hidden` 就是“还没读完的文本”。`non_streaming_mode=True`（CustomVoice/VoiceDesign 默认）时，文本一次性放进 prefill，decode 只补 pad；`False`（Base 默认）时，文本在 decode 阶段一个 token 一个 token 喂。

### 3.3 第二步：`forward()` 只做 Qwen3 主干

代码：[qwen3_tts_talker.py:494](../vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_talker.py#L494)。

```python
def forward(self, input_ids, positions, intermediate_tensors=None, inputs_embeds=None, **_):
    return self.model(input_ids, positions, intermediate_tensors, inputs_embeds)
```

`self.model` 是 vLLM 的 `Qwen3Model`。Qwen3-TTS-1.7B 的 Talker 配置：

| 参数 | 值 |
| --- | --- |
| hidden_size | 2048 |
| num_hidden_layers | 28 |
| num_attention_heads | 16 |
| num_key_value_heads | 8 |
| vocab_size | 3072 |
| num_code_groups | 16 |

Talker 的 vocab 只有 3072，不是文本模型的 151936。因为它只负责“音频 token”。

### 3.4 第三步：`compute_logits()` 把输出限制在 codec 词表

代码：[qwen3_tts_talker.py:504](../vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_talker.py#L504)。

```python
logits = self.logits_processor(self.lm_head, hidden_states)
logits = logits.masked_fill(self._codec_disallowed_mask, float("-inf"))
```

`_codec_disallowed_mask` 在 `__init__` 里构造：只允许：

- `1 <= id < codebook_vocab_size`（2048）的真实 codec id；
- `codec_eos_token_id`（2150）。

这样采样器永远不会吐出普通文本 token。

### 3.5 第四步：一帧 = 16 个码本

这是 Qwen3-TTS 最核心、也最容易读晕的一步。

#### 3.5.1 第 0 个码本由主模型采样

采样器从 3072 维 logits 里选出 `layer0_code`。如果选到 2150（EOS），这一帧结束、整个请求结束；否则进入 `talker_mtp()`。

#### 3.5.2 `talker_mtp()` 补齐第 1～15 个码本

代码：[qwen3_tts_talker.py:1657](../vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_talker.py#L1657)。

```python
audio_codes = self.code_predictor(
    layer0_code=input_ids.reshape(bsz, 1),
    layer0_embed=last_id_hidden,
    last_talker_hidden=past_hidden,
    do_sample=..., temperature=..., top_k=..., top_p=...,
)  # [B, Q=16]
```

`code_predictor` 是一个 5 层小 Transformer（hidden=1024，vocab=2048），定义在 [qwen3_tts_code_predictor_vllm.py:34](../vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_code_predictor_vllm.py#L34)。它做 15 次串行预测：

```text
输入: [layer0_code, past_talker_hidden]
  → 预测 codebook 1
  → 把 codebook 1 的 embedding 拼回去
  → 预测 codebook 2
  ...
  → 预测 codebook 15
```

#### 3.5.3 为什么要“把 15 个码本加起来”

拿到 16 个 code 后，`talker_mtp()` 把它们变成下一步 Talker 的输入 embedding：

```python
gathered = embed_weight[row_idx, residual_ids_t]      # [B, 15, H]
summed = last_id_hidden + gathered.sum(dim=1)          # 当前帧音频信息
inputs_embeds_out = summed + text_step                 # 再叠加当前文本信息
```

于是下一步 Talker 的输入 = **上一帧的音频 embedding + 当前文本 embedding**。这就是“文本和音频交错自回归”的实现。

#### 3.5.4 数据形状

| 变量 | 形状 | 含义 |
| --- | --- | --- |
| `input_ids` | `[B]` | 当前步的 1 个 token |
| `audio_codes` | `[B, 16]` | 一帧的 16 个码本 |
| `inputs_embeds` | `[B, 2048]` | 下一步的输入 |
| `codes.audio`（累计） | `[帧数, 16]` | 沿 dim 0 增长 |

### 3.6 第五步：把 codes 送到 Stage 1

Stage 0 的输出由 `make_omni_output()`（[qwen3_tts_talker.py:574](../vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_talker.py#L574)）打包成 `OmniOutput`，核心是：

```python
multimodal_outputs = {
    "codes": {"audio": ...},          # [帧数, 16]
    "hidden_states": {"last": ...},   # 给下一步 MTP 用
    "meta": {"codec_frame_valid": ...},
}
```

然后 Orchestrator 根据 `async_chunk` 选一条路：

#### 路线 A：`async_chunk: true`（Qwen3-TTS 默认）

对应 YAML [qwen3_tts.yaml:21](../vllm_omni/deploy/qwen3_tts.yaml#L21)。

1. **预启动 Stage 1**：`_prewarm_async_chunk_stages()`（[orchestrator.py:3448](../vllm_omni/engine/orchestrator.py#L3448)）先给 Stage 1 提交一个占位请求，让它把模型加载、显存、CUDA Graph 都准备好，避免第一段音频来了才冷启动。
2. **每帧追加**：Stage 0 每个 decode step 产出 1 帧，`talker2code2wav_async_chunk()`（[stage_input_processors/qwen3_tts.py:158](../vllm_omni/model_executor/stage_input_processors/qwen3_tts.py#L158)）把帧追加到 `transfer_manager.code_prompt_token_ids[req_id]`。
3. **攒够一个 chunk 就发**：默认 `codec_chunk_frames=25`（[qwen3_tts.yaml:39](../vllm_omni/deploy/qwen3_tts.yaml#L39)），即 25 × 80 ms = 2 s 音频；`initial_codec_chunk_frames=1`（[qwen3_tts.yaml:42](../vllm_omni/deploy/qwen3_tts.yaml#L42)）让第一包只有 1 帧，用来压低首包延迟。
4. **带上下文**：`codec_left_context_frames=72`（[qwen3_tts.yaml:40](../vllm_omni/deploy/qwen3_tts.yaml#L40)）必须 ≥ decoder 的 `sliding_window=72`，否则 chunk 边界会有咔哒声。

> 注意 `full_utterance_decode=True` 时，`talker2code2wav_async_chunk()` 会**故意不提前发**（`if full_utterance_decode is True and not finished: return None`），等 Talker 全部结束再一次性解码。这是“质量优先”的实验开关；想测首包延迟就设 `False`。

#### 路线 B：`async_chunk: false`

1. Stage 0 结束后，走 `custom_process_next_stage_input_func` → `talker2code2wav_full_payload()`（[stage_input_processors/qwen3_tts.py:706](../vllm_omni/model_executor/stage_input_processors/qwen3_tts.py#L706)）。
2. 它把 `codes.ref`（参考音频）和 `codes.audio`（生成的音频）拼起来，转置后**按码本优先展平**：

```python
codec_codes = audio.transpose(0, 1).reshape(-1)   # [16 * 帧数]
```

3. Stage 1 的 prompt 只是一个“长度正确的占位 token 列表”（`talker2code2wav_token_only()`，[stage_input_processors/qwen3_tts.py:642](../vllm_omni/model_executor/stage_input_processors/qwen3_tts.py#L642)），真正的 codes 通过 connector 传。

#### 为什么要“转置 + 展平”

Code2Wav 的 `forward()` 约定（[qwen3_tts_code2wav.py:445](../vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_code2wav.py#L445)）是：

```text
input_ids 布局 = [context_frames, *flat_codes]
flat_codes 是 codebook-major：先 16 个 codebook 的第 0 帧，再第 1 帧……
```

而 Talker 自然产出的是 `[帧, 16]`。所以中间必须转置。这是读跨 stage 代码时最常见的“形状对不上”来源。

### 3.7 第六步：Stage 1 解码成波形

代码：[qwen3_tts_code2wav.py:445](../vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_code2wav.py#L445)。

`Qwen3TTSCode2Wav.forward()` 的关键逻辑：

1. 把 `input_ids` 按请求切分（`_split_request_ids`）；
2. 从 `runtime_additional_information` / connector 里取出真实 codes；
3. 过滤非法帧（负数、全 0、越界，见 `_filter_audio_codes_qwen3_tts()` [stage_input_processors/qwen3_tts.py:599](../vllm_omni/model_executor/stage_input_processors/qwen3_tts.py#L599)）；
4. 调 `decoder.chunked_decode()`（[modeling_qwen3_tts_tokenizer_v2.py:1325](../vllm_omni/model_executor/models/qwen3_tts/tokenizer_12hz/modeling_qwen3_tts_tokenizer_v2.py#L1325)）；
5. 返回 `OmniOutput(model_outputs=[waveform], sr=[24000])`。

Decoder 的结构（配置见模型目录 `speech_tokenizer/config.json`）：

```text
16 个码本 → 查表求和 → 8 层 Transformer → 上采样卷积 [8,5,4,3] × [2,2]
          → 每帧 1920 个采样点 → 24 kHz PCM
```

帧率换算：

```text
12.5 帧/s  →  1 帧 = 80 ms
1920 采样点 / 24000 Hz = 80 ms   ✅ 对得上
```

### 3.8 第七步：回到前端

Stage 1 是 `final_output=True`。Orchestrator 在 `_route_output()`（[orchestrator.py:2302](../vllm_omni/engine/orchestrator.py#L2302)）里把输出放进 `output_async_queue`：

```python
message = OutputMessage(
    request_id=req_id,
    stage_id=stage_id,
    engine_outputs=output,
    finished=request_finished,
)
```

入口层 `_run_generation()`（[omni.py:125](../vllm_omni/entrypoints/omni.py#L125)）把它转成 `OmniRequestOutput`，最终就是你在 `end2end.py` 里看到的 `output.outputs[0].multimodal_output`。

---

## 4. 模型内部：Talker 到底在算什么

### 4.1 三个 task type 的 prompt 分支

看 `build_prompt_embeds()` 的三个 `elif`：

| 分支 | 位置 | 额外输入 |
| --- | --- | --- |
| `Base` | [prompt_embeds_builder.py:1352](../vllm_omni/model_executor/models/qwen3_tts/prompt_embeds_builder.py#L1352) | `ref_audio` → codec codes + ECAPA speaker embedding |
| `CustomVoice` | [prompt_embeds_builder.py:1633](../vllm_omni/model_executor/models/qwen3_tts/prompt_embeds_builder.py#L1633) | `speaker` → 查 `spk_id` → 查表得到 speaker embedding |
| `VoiceDesign` | [prompt_embeds_builder.py:1705](../vllm_omni/model_executor/models/qwen3_tts/prompt_embeds_builder.py#L1705) | 无 speaker，只靠 `instruct` 文本描述音色 |

三者最后都会拼成：

```text
[instruct 文本 embedding?] + [角色符] + [speaker/ref codec] + [文本 embedding] + [codec BOS/EOS]
```

### 4.2 为什么同一个 hidden 空间能放文本和音频

```python
text_projection(text_embedding(text_ids))   # 文本 → Talker hidden (2048)
codec_embedding(codec_ids)                  # codec → Talker hidden (2048)
```

两者都是 2048 维，直接相加。这是“统一 token 空间”的做法：Talker 不区分“这是字还是音频”，它只学“下一步该出哪个 codec token”。

### 4.3 `compute_logits` 的 mask 为什么重要

如果不 mask，模型可能输出文本 token（比如 151645 `im_end`），Code2Wav 查表就会越界。`__init__` 里预先注册了**反 mask**：

```python
codec_mask = torch.zeros((vocab,), dtype=torch.bool)
codec_mask[1:min(codebook_vocab_size, vocab)] = True
codec_mask[codec_eos_token_id] = True
self.register_buffer("_codec_disallowed_mask", ~codec_mask)
```

这样每个 decode step 只做一次 `masked_fill`，不用重复构造。

### 4.4 采样参数在哪

| 参数 | 位置 | 作用 |
| --- | --- | --- |
| `temperature/top_k/top_p/max_tokens` | YAML `stages[0].default_sampling_params`（[qwen3_tts.yaml:105](../vllm_omni/deploy/qwen3_tts.yaml#L105)） | Talker 主采样 |
| `min_tokens: 2` | 同上 | 防止第一帧就 EOS，输出空音频 |
| `subtalker_sampling_params` | YAML [qwen3_tts.yaml:118](../vllm_omni/deploy/qwen3_tts.yaml#L118) | CodePredictor 的 15 个残差码本采样 |
| `silence_ban_frames` | YAML [qwen3_tts.yaml:117](../vllm_omni/deploy/qwen3_tts.yaml#L117) | 前 N 帧屏蔽静音 codec（Base 克隆用） |

### 4.5 EOS 与停止

- `stop_token_ids=[2150]` 写在 `pipeline.py` 的 `sampling_constraints`；
- `compute_logits` 允许 2150 被采到；
- 采到 2150 后，vLLM 的 stop checker 结束请求；
- `preprocess()` 会把无效的 layer0（如 EOS/PAD）映射成 0，避免 Code2Wav 越界（`talker_mtp()` 里的 `invalid0` 逻辑）。

---

## 5. Code2Wav 内部：codes → 波形

### 5.1 它不是 AR

Stage 1 的 `execution_type=LLM_GENERATION`，`compute_logits()` 直接返回 `None`（[qwen3_tts_code2wav.py:310](../vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_code2wav.py#L310)）。它借用 vLLM 的调度/批处理框架，但**模型本身是一次前向**：

```text
codes [T, 16] → decoder → waveform [T * 1920]
```

### 5.2 `chunked_decode` vs 流式解码

| 模式 | 入口 | 特点 |
| --- | --- | --- |
| 整段解码 | `Qwen3TTSTokenizerV2Decoder.chunked_decode()` | 带 `left_context`，适合异步 chunk |
| 有状态流式 | `StreamingCode2Wav.decode()`（[streaming_code2wav.py:135](../vllm_omni/model_executor/models/qwen3_tts/streaming_code2wav.py#L135)） | 维护 decoder cache，逐 chunk 增量解码；CPU/CUDA 上都可跑 |

Qwen3-TTS 默认 `decode_streaming: false`（[qwen3_tts.yaml:32](../vllm_omni/deploy/qwen3_tts.yaml#L32)），走 `chunked_decode`。想进一步降延迟可以打开，但要注意注释里的质量提醒。

### 5.3 `left_context` 为什么必须够大

Decoder 的注意力 `sliding_window=72`（约 5.76 s）。如果每次只给 25 帧、不带历史，chunk 拼接处会听见断裂。`codec_left_context_frames=72` 就是让每个 chunk 都带上足够长的历史帧，只把“新增部分”写进结果。

---

## 6. 代码阅读地图

### 6.1 推荐顺序（4 轮）

| 轮次 | 目标 | 文件 | 只看什么 |
| --- | --- | --- | --- |
| 第 1 轮 | 知道输入输出 | `examples/.../qwen3_tts/end2end.py` | `get_custom_voice_query()`、`main()`、`_save_wav()` |
| 第 2 轮 | 知道流水线怎么搭 | `qwen3_tts/pipeline.py`、`deploy/qwen3_tts.yaml`、`config_factory.py` | `QWEN3_TTS_PIPELINE`、2 个 stage 字段、默认 YAML |
| 第 3 轮 | 知道一帧怎么来 | `qwen3_tts_talker.py` | `preprocess()`、`forward()`、`compute_logits()`、`talker_mtp()` |
| 第 4 轮 | 知道一帧怎么变声音 | `stage_input_processors/qwen3_tts.py`、`qwen3_tts_code2wav.py` | `talker2code2wav_async_chunk()`、`forward()`、`chunked_decode()` |

### 6.2 每个文件一句话

| 文件 | 作用 | 建议先读的函数 |
| --- | --- | --- |
| `entrypoints/omni.py` | 同步入口 | `generate()`、`_run_generation()` |
| `entrypoints/omni_base.py` | 构造引擎、解析配置 | `__init__()` |
| `engine/async_omni_engine.py` | 请求打包、入队 | `add_request()` |
| `engine/orchestrator.py` | 跨 stage 调度 | `_route_output()`、`_forward_to_next_stage()`、`_prewarm_async_chunk_stages()` |
| `config/pipeline_registry.py` | pipeline 注册表 | `OMNI_PIPELINES` |
| `config/config_factory.py` | 选 pipeline + 默认 YAML | `create_from_model()` |
| `config/stage_config.py` | 拓扑/部署配置结构 | `StagePipelineConfig`、`StageDeployConfig`、`merge_pipeline_deploy()` |
| `models/qwen3_tts/pipeline.py` | Qwen3-TTS 拓扑 | `QWEN3_TTS_PIPELINE` |
| `models/qwen3_tts/qwen3_tts_talker.py` | Talker 模型 | `preprocess()`、`talker_mtp()` |
| `models/qwen3_tts/prompt_embeds_builder.py` | 拼 prompt | `build_prompt_embeds()` 的三个 task 分支 |
| `models/qwen3_tts/qwen3_tts_code_predictor_vllm.py` | 15 个残差码本 | `forward()` |
| `models/qwen3_tts/qwen3_tts_code2wav.py` | codes → 波形 | `forward()` |
| `models/qwen3_tts/tokenizer_12hz/modeling_qwen3_tts_tokenizer_v2.py` | 编解码器网络 | `chunked_decode()` |
| `stage_input_processors/qwen3_tts.py` | 跨 stage 数据整理 | `talker2code2wav_async_chunk()`、`talker2code2wav_full_payload()` |

### 6.3 先跳过的地方

- `orchestrator.py` 的容错、replica 管理、metrics；
- `prompt_embeds_builder.py` 的缓存/预计算分支（先只看三个 task 的主干）；
- `*_cuda_graph*`、`segmented_graph_wrapper.py`、`stream_decode.py` 等性能优化；
- `stage_pool.py` / `stage_engine_startup.py` 的进程管理细节；
- `worker_v2/`（Model Runner V2）除 `omni_ar_model_runner.py` 外的大部分。

> 性能代码是“在正确路径上加的旁路”。先读主路径，再回来看旁路，会轻松很多。

---

## 7. 310P 硬件专线

> 这一章只回答一个问题：**同样是 Qwen3-TTS，代码在 310P 上多了哪些分支？**
> 310P = Atlas 300I DUO 的 Ascend 310P3 芯片。本机 3 张卡 / 6 个 chip，无 HCCS，实测约 185 GB/s、24 TFLOPS FP16（见 `reports/300I-DUO-适配与优化分析.md`）。
> 310P 目前是 **Experimental** 支持，安装入口见 [docs/getting_started/installation/npu/npu.inc.md:31](../docs/getting_started/installation/npu/npu.inc.md#L31)（镜像 `v0.30.0-310p`）。

### 7.1 平台选择链

```text
import vllm_omni
  └─ vllm_omni/platforms/__init__.py:npu_omni_platform_plugin()
       └─ NPUOmniPlatform                     vllm_omni/platforms/npu/platform.py:61
            ├─ apply_qwen3_tts_patches()      # Code2Wav 权重/运行时（所有 NPU）
            ├─ apply_qwen3_tts_tokenizer_v2_patch()
            └─ apply_310p_patches()           # 只有 310P 生效
```

`vllm_omni/platforms/npu/_310p/__init__.py:11` 的 `is_310p()` 委托给 `vllm_ascend.device.device_config.is_310p()`；`apply_patches()`（同文件 :29）先判断芯片，再打补丁。

### 7.2 310P 与 CUDA 的关键差异

| 维度 | CUDA（H100 等） | 310P |
| --- | --- | --- |
| 计算 dtype | BF16 | **FP16**（无 BF16） |
| 权重布局 | ND / 原生 | **FRACTAL_NZ / FRACTAL_Z** |
| 图捕获 | CUDA Graph | ACL Graph（能力受限） |
| 随机采样 | 可进图 | **部分随机算子不能进 ACL Graph** |
| Triton | 可用 | **不可用**（Triton-Ascend 不支持 310P） |
| 注意力 | FlashAttention | `torch_npu._npu_flash_attention` + 16 token 对齐 |

### 7.3 310P 补丁逐文件说明

#### `platforms/npu/_310p/patch/worker.py`

```python
class _OmniNPUWorkerBase310P(OmniNPUWorkerBase):
    def _init_device(self):
        device = super()._init_device()
        disable_jit_compile()          # torch_npu.npu.set_compile_mode(jit_compile=False)
        return device

AscendSampler310.apply_penalties = staticmethod(Sampler.apply_penalties)
```

- 关闭 JIT 编译：310P 上图编译模式不稳；
- 把 `AscendSampler310` 的 penalty 实现换回 vLLM 原生版本：Triton-Ascend 不支持 310P。

#### `platforms/npu/_310p/patch/qwen3_tts.py`

| 类/函数 | 行号 | 作用 |
| --- | --- | --- |
| `_RUNTIME_DTYPE = torch.float16` | :28 | 310P 统一 FP16 |
| `_Qwen3TTSTalker310P` | :34 | Talker 子类 |
| `_Qwen3TTSPromptEmbedsBuilder310P` | :83 | mel 频谱在 CPU 上算 |
| `_Qwen3TTSCode2Wav310P` | :98 | Code2Wav 运行时 dtype 覆盖为 FP16 |
| `_Qwen3CodePredictorAttention310P` | :115 | 310P RoPE + flash attention |
| `_Qwen3CodePredictorDecoderLayer310P` | :209 | 融合 add + RMSNorm |
| `_Qwen3CodePredictorBaseModel310P` | :230 | 缓存 FRACTAL_NZ 因果 mask |

Talker 子类里有两个非常重要的行为改变：

```python
self._embedding_dtype = torch.float16
self.talker_mtp_graph_safe = False     # 310P 随机采样不能进图
```

以及：

```python
def load_weights(self, weights):
    loaded = super().load_weights(weights)
    self.encoder.to(device="cpu", dtype=torch.float32)  # Mimi 编码器只在建 prompt 时用
    return loaded
```

**为什么把参考音频编码器放 CPU？** 它只在 Base/ICL 的 prompt 构造阶段用一次，310P 对变化形状的 NPU 算子很敏感，放 CPU 更稳，也不影响 decode 性能。

CodePredictor 的 310P 路径做了三件 CUDA 上没有的事：

1. **QKV 融合 + NZ 布局**（`prepare_qkv_weights()`）：每次图重放只做一次 matmul；
2. **16 token 对齐**（`aligned_16`）：310P flash attention 要求 token 数是 16 的倍数；
3. **FRACTAL_NZ 因果 mask**（`AttentionMaskBuilder310.gen_causal_additive_mask`）：只建一次，后续图复用。

#### `platforms/npu/models/qwen3_tts.py`

所有 NPU（不只 310P）都会打的补丁：

- `_prepare_npu_code2wav_runtime()`：关闭 internal format + JIT；
- `_prepare_npu_decoder_weights()`：Linear → NZ，Conv → FRACTAL_Z；
- `_patched_load_weights()`：把 decoder 转成平台 dtype（310P 下是 FP16），并预计算 snake cache。

#### `platforms/npu/models/qwen3_tts_tokenizer_v2.py`

把 decoder 里的 RoPE 和 RMSNorm 换成 `torch_npu` 算子：

```python
modeling_qwen3_tts_tokenizer_v2.apply_rotary_pos_emb = _apply_rotary_pos_emb_npu
Qwen3TTSTokenizerV2DecoderRMSNorm.forward = _rms_norm_forward_npu
```

### 7.4 310P 上的 deploy 覆盖

YAML 末尾的 `platforms:` 段（[qwen3_tts.yaml:151](../vllm_omni/deploy/qwen3_tts.yaml#L151)）会先被 `_apply_platform_overrides()`（[stage_config.py:1198](../vllm_omni/config/stage_config.py#L1198)）合并：

```yaml
platforms:
  npu:
    model_runner: v1          # MRV2 不在 NPU 上启用
    stages:
      - stage_id: 0
        enforce_eager: false
        compilation_config:
          cudagraph_mode: PIECEWISE
      - stage_id: 1
        compilation_config:
          cudagraph_mode: PIECEWISE
```

310P 还需要在部署文件里补两件事（仓库默认 YAML 面向 GPU，不会自动帮你改）：

```yaml
model_runner: v1
dtype: float16                 # 310P 无 BF16
```

**一个容易踩的坑**：`--deploy-config` 传入的是**完整部署文件**，不是增量覆盖。仓库默认 YAML 的 Stage 1 显式写了 `dtype: bfloat16`（[qwen3_tts.yaml:126](../vllm_omni/deploy/qwen3_tts.yaml#L126)），而 `_build_engine_args()` 的合并顺序是“**顶层 dtype 先、stage 级 `engine_extras` 后**”（[stage_config.py:1376-1395](../vllm_omni/config/stage_config.py#L1376-L1395)）。所以如果你复制默认 YAML 来改，必须把 Stage 1 的 `dtype: bfloat16` 一并改成 `float16`；否则 stage 级值会把顶层 `float16` 盖掉。

一个最小完整部署文件示例（放在任意路径，用 `--deploy-config` 传入）：

```yaml
model_runner: v1
async_chunk: true
dtype: float16
connectors:
  connector_of_shared_memory:
    name: SharedMemoryConnector
    extra:
      talker_first_audio: true
      codec_streaming: true
      decode_streaming: false
      codec_chunk_frames: 25
      codec_left_context_frames: 72
      initial_codec_chunk_frames: 1
stages:
  - stage_id: 0
    max_num_seqs: 1
    gpu_memory_utilization: 0.3
    trust_remote_code: true
    max_num_batched_tokens: 512
    max_model_len: 4096
    devices: "0"
    output_connectors:
      to_stage_1: connector_of_shared_memory
    default_sampling_params:
      temperature: 0.9
      top_k: 50
      max_tokens: 4096
      min_tokens: 2
      repetition_penalty: 1.05
    subtalker_sampling_params:
      do_sample: true
      temperature: 0.9
      top_k: 50
      top_p: 1.0
  - stage_id: 1
    max_num_seqs: 1
    gpu_memory_utilization: 0.3
    enforce_eager: false
    trust_remote_code: true
    max_num_batched_tokens: 65536
    max_model_len: 65536
    devices: "0"
    input_connectors:
      from_stage_0: connector_of_shared_memory
    default_sampling_params:
      temperature: 0.0
      top_p: 1.0
      top_k: -1
      max_tokens: 65536
      repetition_penalty: 1.0
platforms:
  npu:
    model_runner: v1
    stages:
      - stage_id: 0
        enforce_eager: false
        compilation_config:
          cudagraph_mode: PIECEWISE
      - stage_id: 1
        compilation_config:
          cudagraph_mode: PIECEWISE
```

运行：

```bash
export ASCEND_RT_VISIBLE_DEVICES=0   # 只暴露一张空闲 chip
python examples/offline_inference/text_to_speech/qwen3_tts/end2end.py \
    --query-type CustomVoice \
    --deploy-config /path/to/qwen3_tts_310p.yaml \
    --output-dir /tmp/qwen3_tts_out
```

> 版本提醒：310P 的 vLLM/vllm-ascend wheel 目前是 v0.30.0 系。若 import 阶段就报
> `compute_mm_prefix_ranges` / ATB / ACLNN 之类的错误，先核对 vLLM 与 vllm-ascend
> 版本是否匹配，再怀疑模型代码。历史排查过程见
> [Qwen3-TTS-310P-逐行代码逻辑分析报告.md](Qwen3-TTS-310P-逐行代码逻辑分析报告.md) 第 1、5 节。

### 7.5 310P 上哪些代码分支会走 / 不会走

| 分支 | 310P 是否走 | 说明 |
| --- | --- | --- |
| `model_runner: v1` | ✅ | `platforms.npu` 强制 v1 |
| Model Runner V2（`worker_v2/`） | ❌ | NPU 不启用 |
| CUDA Graph | ❌ | 走 ACL Graph / PIECEWISE |
| `decode_streaming` | 默认 ❌ | 可被试，但要注意 CPU/NPU 图捕获限制 |
| Talker MTP 整图 | ❌ | `talker_mtp_graph_safe=False` |
| CodePredictor 内部图 | ✅ | 有专门的 310P 图实现 |
| FP16 | ✅ | `_RUNTIME_DTYPE` |
| FRACTAL_NZ / FRACTAL_Z | ✅ | Linear / Conv 权重转换 |
| Triton 融合 | ❌ | 用原生 PyTorch / torch_npu 算子 |

### 7.6 在 310P 上读代码的推荐主图

```text
platforms/npu/platform.py:NPUOmniPlatform
  → platforms/npu/_310p/patch/qwen3_tts.py
       → _Qwen3TTSTalker310P.load_weights()       # encoder 放 CPU
       → _Qwen3TTSTalker310P.__init__()           # FP16 + MTP 不进图
       → _Qwen3TTSCode2Wav310P                   # decoder FP16
       → _Qwen3CodePredictor*310P                # 图内 attention / mask
  → platforms/npu/models/qwen3_tts.py            # NZ/FRACTAL_Z 权重
  → deploy/qwen3_tts.yaml:platforms.npu          # v1 + PIECEWISE
```

读完这条线，你就知道“同一份 Qwen3-TTS 模型代码，在 310P 上哪几处被替换了”。

---

## 8. 调试与动手实验

### 8.1 最值得打断点/加日志的 8 个位置

| 位置 | 想确认什么 | 建议打印 |
| --- | --- | --- |
| `qwen3_tts_talker.py:798` `preprocess()` | prompt 长度、走 prefill 还是 decode | `span_len`、`is_prefill`、`task_type` |
| `qwen3_tts_talker.py:1657` `talker_mtp()` | 一帧的 16 个 code | `audio_codes.shape`、`audio_codes[0]` |
| `qwen3_tts_talker.py:574` `make_omni_output()` | Stage 0 输出包 | `codes.audio.shape` |
| `qwen3_tts.py:158` `talker2code2wav_async_chunk()` | 当前攒了多少帧、何时发 chunk | `length`、`chunk_size`、`initial_chunk_size` |
| `qwen3_tts.py:706` `talker2code2wav_full_payload()` | 全量 payload 的扁平长度 | `audio.shape`、`ref_frames` |
| `qwen3_tts_code2wav.py:445` `forward()` | 收到多少帧、输出多少采样点 | `ids.numel()`、`model_outputs.shape` |
| `modeling_qwen3_tts_tokenizer_v2.py:1325` `chunked_decode()` | left context / chunk 边界 | `codes.shape`、`left_context` |
| `orchestrator.py:2302` `_route_output()` | 哪个 stage 在往前端发 | `stage_id`、`finished` |

### 8.2 三个最小实验

**实验 A：确认当前是不是 async_chunk**

```python
# 在 end2end.py 构造 Omni 后打印
print(omni.engine.async_chunk)
print([omni.engine.get_stage_metadata(i).stage_type for i in range(omni.num_stages)])
```

**实验 B：把 chunk 调大，听延迟变化**

复制 `qwen3_tts.yaml`，把 `codec_chunk_frames` 从 25 改成 50，重新跑；首包延迟会变大，但 Stage 1 调用次数减半。

**实验 C：关掉 full_utterance_decode，观察流式输出**

把输入里的 `"full_utterance_decode": [True]` 改成 `[False]`，用 `--streaming` 跑，观察每 2 s 左右到一段音频。

### 8.3 常见“读不懂”的报错

| 现象 | 大概率原因 |
| --- | --- |
| Code2Wav 收到长度 0 的输入 | Talker 第一帧就 EOS；检查 `min_tokens: 2` |
| 输出有咔哒声 | `codec_left_context_frames` < decoder `sliding_window`（72） |
| `prompt_token_ids` 长度和 embedding 不一致 | `_estimate_prompt_len()` 估错；用真实 tokenizer 重新估 |
| 310P 上 `Unsupported op` | 该算子没有 NPU 实现；看 `platforms/npu/_310p/patch/` 是否覆盖 |
| FP16 溢出/NaN | 310P 无 BF16；确认 `dtype: float16`，并检查权重是否 NZ 转换成功 |
| 第一包很慢 | Stage 1 没 prewarm，或 `initial_codec_chunk_frames` 太大 |

---

## 9. 术语表

| 术语 | 解释 |
| --- | --- |
| **Talker** | 生成 codec 的自回归语言模型 |
| **Code2Wav** | 把 codec 还原成波形的解码器（也叫 token2wav / vocoder） |
| **CodePredictor / subtalker** | 主 Talker 旁边的小模型，一次补齐 15 个残差码本 |
| **RVQ** | Residual Vector Quantization，多层码本逐层逼近音频 |
| **codebook** | 码本；Qwen3-TTS 有 16 个，每个 2048 项 |
| **frame** | 一帧 = 16 个码本 = 80 ms 音频 |
| **prompt** | 这里指模型输入 embedding，不是“提示词” |
| **prefill** | 第一次处理整段输入 |
| **decode** | 后续逐 token 生成 |
| **MTP** | Multi-Token Prediction，这里特指一次补 15 个码本 |
| **chunk** | 一段连续音频帧；异步模式下按 chunk 发给 Stage 1 |
| **left context** | 解码当前 chunk 时额外带上的历史帧 |
| **TTFA** | Time To First Audio，首包延迟 |
| **RTF** | Real-Time Factor，生成 1 s 音频所需时间 |
| **NZ / FRACTAL_Z** | 昇腾 NPU 的权重内存布局 |
| **ACL Graph** | 昇腾的图捕获机制，对应 CUDA Graph |

---

## 10. 关键文件与函数索引

```text
入口
  examples/offline_inference/text_to_speech/qwen3_tts/end2end.py:390   main()
  vllm_omni/entrypoints/omni.py:79                                     generate()
  vllm_omni/entrypoints/omni_base.py:174                               OmniBase.__init__()

配置
  vllm_omni/config/pipeline_registry.py:250                            OMNI_PIPELINES["qwen3_tts"]
  vllm_omni/config/config_factory.py:394                               create_from_model()
  vllm_omni/config/stage_config.py:1552                                merge_pipeline_deploy()
  vllm_omni/model_executor/models/qwen3_tts/pipeline.py:32             QWEN3_TTS_PIPELINE
  vllm_omni/deploy/qwen3_tts.yaml                                     默认部署参数

调度
  vllm_omni/engine/orchestrator.py:2302                                _route_output()
  vllm_omni/engine/orchestrator.py:2919                                _forward_to_next_stage()
  vllm_omni/engine/orchestrator.py:3448                                _prewarm_async_chunk_stages()

模型
  .../qwen3_tts/qwen3_tts_talker.py:798                                preprocess()
  .../qwen3_tts/qwen3_tts_talker.py:494                                forward()
  .../qwen3_tts/qwen3_tts_talker.py:504                                compute_logits()
  .../qwen3_tts/qwen3_tts_talker.py:1657                               talker_mtp()
  .../qwen3_tts/qwen3_tts_talker.py:574                                make_omni_output()
  .../qwen3_tts/prompt_embeds_builder.py:1210                          build_prompt_embeds()
  .../qwen3_tts/qwen3_tts_code_predictor_vllm.py:34                    CodePredictor
  .../qwen3_tts/qwen3_tts_code2wav.py:445                              Code2Wav.forward()
  .../qwen3_tts/tokenizer_12hz/modeling_qwen3_tts_tokenizer_v2.py:1325 chunked_decode()

跨 stage
  .../stage_input_processors/qwen3_tts.py:158                          talker2code2wav_async_chunk()
  .../stage_input_processors/qwen3_tts.py:642                          talker2code2wav_token_only()
  .../stage_input_processors/qwen3_tts.py:706                          talker2code2wav_full_payload()

310P
  vllm_omni/platforms/npu/platform.py:61                              NPUOmniPlatform
  vllm_omni/platforms/npu/_310p/__init__.py:11                         is_310p()
  vllm_omni/platforms/npu/_310p/patch/qwen3_tts.py:34                  _Qwen3TTSTalker310P
  vllm_omni/platforms/npu/_310p/patch/worker.py:22                     _OmniNPUWorkerBase310P
  vllm_omni/platforms/npu/models/qwen3_tts.py:84                       apply_qwen3_tts_patches()
  vllm_omni/platforms/npu/models/qwen3_tts_tokenizer_v2.py:40          apply_qwen3_tts_tokenizer_v2_patch()
```

---

## 附录：一页纸速查

```text
Qwen3-TTS-12Hz-1.7B-CustomVoice
  Talker: 28 层, hidden 2048, vocab 3072, 16 code groups
  CodePredictor: 5 层, hidden 1024, vocab 2048
  Codec: 16 quantizers, codebook 2048, 12.5 Hz, 24 kHz
  1 frame = 16 codes = 80 ms = 1920 samples
  Stage 0 输出: codes [T, 16]
  Stage 1 输出: audio [T*1920]
  默认: async_chunk=true, v2 runner (CUDA), v1 runner (NPU)
  310P: FP16 + NZ/FRACTAL_Z + v1 + ACL Graph + MTP 不进图
```

如果读完之后只能记住一句话：

> **Stage 0 每 80 ms 产出一行 16 个整数；Stage 1 把每一行还原成 1920 个采样点。中间所有代码都在搬运、拼接、过滤和加速这两件事。**
