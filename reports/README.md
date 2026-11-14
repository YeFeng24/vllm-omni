# vLLM-Omni 技术报告

> 更新日期：2026-11-13
> 说明：本目录包含两份技术报告和一份 310P 优化 roadmap。roadmap 按 vLLM-Omni 社区的 RFC 规范编写，可直接作为 `[RFC]` issue 草稿。

## 报告列表

### 1. [vLLM-Omni-架构与技术报告.md](vLLM-Omni-架构与技术报告.md)

约 3250 行，包含：

- **第 I 部分 · 架构与代码**：仓库定位、七层架构、目录/文件、启动流程、两条请求线、五条调用链、平台层与 Ascend 架构、NPU 特性矩阵、术语表。
- **第 II 部分 · Ascend 全流程**：共享基础设施、AR 线（Qwen3-TTS，逐函数）、Diffusion 线（HunyuanImage3，客户端逐行 + 服务端逐函数）、全链路调用树与索引。

### 2. [300I-DUO-适配与优化分析.md](300I-DUO-适配与优化分析.md)

约 1170 行，包含：

- **Part A · 300I DUO 适配与优化全景**：硬件画像、能力边界、适配清单、算法量级判断、**下一批适配模型建议（§A.5）**、特性优化、路线图、风险与验证清单。
- **Part B · 社区贡献规范与 310P 贡献方案**：vLLM-Omni Issue/PR 规范、分支 gap、PR 拆分路线、Qwen3-MoE 与 Qwen3-ASR 310P 贡献方案。

> “应该适配哪些模型”的内容在 [300I-DUO-适配与优化分析.md](300I-DUO-适配与优化分析.md) 的 **Part A §A.5**。

### 3. [310P-优化Roadmap.md](310P-优化Roadmap.md)

按社区 `[RFC]` 规范编写的 310P 优化 roadmap，包含：

- Motivation / Goals / Non-goals / 当前状态；
- 模型覆盖矩阵与 P0-P5 里程碑；
- 7 条工作流（CI、TTS 性能、TTS 矩阵、量化、小 Omni、扩散、文档）；
- PR 交付计划、验证指标、依赖与风险、Open Questions；
- Feedback Period、CC List，以及提交到社区的步骤。

### 4. [300I-DUO-30PR计划.md](300I-DUO-30PR计划.md)

把 roadmap 展开为 30 个可独立提交、独立验证的 PR，包含：

- PR-01 – PR-30 总览表：标题、仓库归属、阶段、文件范围、依赖、规模；
- 7 个阶段详情：P0 基线、P1a 运行时、P1b TTS 性能、P2 TTS 矩阵、P3 小 Omni、P4 图像、Release；
- 依赖关系图与建议合并顺序；
- 每个 PR 的社区规范检查清单（标题前缀、DCO、AI 披露、precheck-pr、规模限制）；
- **上游归属结论**：23 个 PR 走 vllm-omni（其中 9 个有条件），3 个必须走 vllm-ascend，4 个需要拆分；**不能把全部代码合入 vllm-omni**。

### 5. [TTS-代码阅读指南.md](TTS-代码阅读指南.md)

面向第一次阅读 vLLM-Omni 代码的同学，以 Qwen3-TTS 为主线：

- 先建立 6 个核心概念（TTS / token / codec / frame / AR / stage）和一张总图；
- 从 `end2end.py` 输入输出讲起，跟一条请求走完 Talker → Code2Wav 两段流水线；
- 逐段解释 `preprocess` / `forward` / `compute_logits` / `talker_mtp` / `chunked_decode`；
- 给出 4 轮阅读顺序、每个文件一句话、可先跳过的区域、8 个断点位置和 3 个最小实验；
- 单列 **310P 专线**：平台补丁、FP16、NZ/FRACTAL_Z、ACL Graph、deploy 覆盖与版本注意事项。

### 6. [Qwen3-TTS-310P-逐行代码逻辑分析报告.md](Qwen3-TTS-310P-逐行代码逻辑分析报告.md)

2026-11-13 在 Atlas 300I DUO（310P3）上实际跑通 Qwen3-TTS-12Hz-1.7B-CustomVoice 的记录与逐段代码分析，包含：

- 环境/版本矩阵与“为什么当前分支不能直接跑、升级 vLLM 能否跑 main”的结论；
- 可复现命令、310P deploy 配置差异、端到端调用链；
- 从示例入口、引擎构建、配置合并、Talker、CodePredictor、跨 stage 传输到 Code2Wav 的逐段/逐行解析；
- 本次定位的 9 个问题（BF16、NZ 权重、`sample_uniforms`、ATB/ACLNN attention 等）及本地 shim 说明；
- 运行产物、耗时/RTF 数据与后续建议；
- **§8 基于 main 的本地源码环境**：vLLM 0.33 + vllm-ascend `17f07e3` + omni main
  在 310P 上的构建步骤、4 个兼容补丁、实测结果与版本 pin 说明。

## 目录结构

```text
reports/
├── README.md                           # 本索引
├── vLLM-Omni-架构与技术报告.md          # 通用架构与代码报告
├── 300I-DUO-适配与优化分析.md            # 300I DUO / 310P 专项报告
├── 310P-优化Roadmap.md                  # 310P 优化 RFC / roadmap 草稿
├── 300I-DUO-30PR计划.md                 # 30 个 PR 的实施计划
├── TTS-代码阅读指南.md                  # 新手向 TTS 执行链路与代码阅读地图
├── Qwen3-TTS-310P-逐行代码逻辑分析报告.md  # 310P TTS 实跑与代码分析
├── assets/                             # 架构图（PNG + fireworks 图源）
└── examples/                           # 报告配套脚本
```

## 合并与拆分规则

- **内容不删减**：所有技术结论、表格、代码块、`文件:行号` 引用、命令、图表均保留。
- **重复内容合并**：同一主题内部完全重复的段落在合并时只保留信息量最大的版本。
- **按主题拆分**：通用架构与 Ascend 执行路径归入架构报告；300I DUO / 310P 适配、模型选型与贡献方案归入 300I DUO 报告。
- 7 份原始文档的内容已全部并入这两份技术报告，仓库内不再保留独立副本。

## 图表与脚本

- 架构图：`assets/fig_*.png`（均由架构报告引用）
- 图源与重绘脚本：`assets/fireworks_specs/`（`render_all.sh`）
- HunyuanImage3 离线示例：`examples/offline_hunyuan_image3.py`
