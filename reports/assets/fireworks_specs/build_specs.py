# Build the architecture figures as fireworks-tech-graph Diagram IR JSONs
# (schema v1, mode=architecture, style 1 flat).
#
# Layout engine enforces the composition contract:
#   node gap >= 40 (we use 44), container gutter >= 20 (we use 24),
#   orthogonal edges with <= 2 bends, zero crossings.
#
# NPU capability-gap annotation (per report §4/§5):
#   state="ok"    normal palette
#   state="part"  amber palette + "△ 部分支持" prefix
#   state="gap"   red palette   + "✗ NPU 缺失" prefix
#
# Render/export via render_all.sh.

from pathlib import Path
import json

OUT = Path(__file__).resolve().parent
W = 1600
GAP, PAD, LBL = 44, 24, 56

PAL = {
    "green":  ("#E8F5E9", "#43A047"),
    "blue":   ("#E3F2FD", "#1E88E5"),
    "orange": ("#FFF3E0", "#FB8C00"),
    "indigo": ("#E8EAF6", "#3949AB"),
    "purple": ("#F3E5F5", "#8E24AA"),
    "amber":  ("#FFF8E1", "#FFA000"),
    "teal":   ("#E0F2F1", "#00897B"),
    "cyan":   ("#E0F7FA", "#00ACC1"),
    "gray":   ("#F4F6F8", "#90A4AE"),
    "lime":   ("#F1F8E9", "#7CB342"),
    "red":    ("#FFEBEE", "#E53935"),
}

STATE_TAG = {"ok": "", "part": "△ ", "gap": "✗ "}


def cont(cid, label, pal):
    return {"_label": label, "_pal": pal, "_id": cid}


def nd(nid, label, sub, pal="blue", h=96, frac=1.0, state="ok"):
    pal = {"part": "amber", "gap": "red"}.get(state, pal)
    sub = (STATE_TAG[state] + sub) if STATE_TAG[state] else sub
    return {"_nid": nid, "_label": label, "_sub": sub, "_pal": pal, "_h": h,
            "_frac": frac, "_state": state}


def rows_at(x, y, w, rows):
    """Place rows (list of node-lists) starting at (x, y). Returns (placed, bottom)."""
    placed, cy = [], y
    for row in rows:
        n = len(row)
        total = w - 2 * PAD - GAP * (n - 1)
        frac_sum = sum(it["_frac"] for it in row)
        cx = x + PAD
        for item in row:
            nw = total * item["_frac"] / frac_sum
            placed.append({
                "id": item["_nid"], "kind": "rect", "x": round(cx, 1), "y": round(cy, 1),
                "width": round(nw, 1), "height": item["_h"],
                "label": item["_label"], "sublabel": item["_sub"],
                "fill": PAL[item["_pal"]][0], "stroke": PAL[item["_pal"]][1], "flat": True,
            })
            cx += nw + GAP
        cy += max(it["_h"] for it in row) + GAP
    return placed, cy - GAP + PAD  # bottom edge incl. padding


def block(cid, label, pal, x, y, w, rows, min_h=0):
    """Container + stacked node rows. Returns (container_dict, node_list, bottom_y)."""
    nodes, bottom = rows_at(x, y + LBL, w, rows)
    h = max(min_h, bottom - y)
    container = {"id": cid, "x": x, "y": y, "width": w, "height": round(h, 1),
                 "label": label, "stroke": PAL[pal][1], "fill": PAL[pal][0]}
    return container, nodes, y + h


def spec(title, subtitle, blocks, arrows, footer, height, legend=None):
    containers = [b[0] for b in blocks]
    nodes = [n for b in blocks for n in b[1]]
    s = {
        "schema_version": 1, "mode": "architecture", "template_type": "architecture",
        "style": 1, "quality_profile": "showcase",
        "width": W, "height": height,
        "title": title, "subtitle": subtitle,
        "containers": containers, "nodes": nodes, "arrows": arrows,
        "legend_orientation": "horizontal",
        "footer": footer,
    }
    if legend:
        s["legend"] = [{"flow": f, "label": l} for f, l in legend]
    return s


def arr(aid, src, dst, label, sp="bottom", tp="top", flow="control"):
    return {"id": aid, "source": src, "target": dst, "source_port": sp,
            "target_port": tp, "flow": flow, "label": label}


# ---------------------------------------------------------------- 图 A
def fig_a():
    B, A = [], []
    x0, iw = 80, 1440
    c, n, bot = block("ep", "EntryPoints · API 入口层（entrypoints/ 115 文件 / 4.0 万行）", "green", x0, 150, iw, [
        [nd("apiserver", "APIServer", "entrypoints/openai/api_server.py — 流式媒体族 · 74 文件", "green", 92),
         nd("omni", "Omni / AsyncOmni", "entrypoints/omni.py · async_omni.py — 引擎总开关", "green", 92),
         nd("omnistage", "OmniStage", "engine/stage_client.py · stage_diffusion_client.py", "green", 92)],
    ])
    B.append((c, n, bot))
    arx, dfx, colw = 80, 820, 700
    c, n, bot = block("ar", "AR 文本线（vLLM 原生栈）", "blue", arx, 420, colw, [
        [nd("cacheeng", "Cache Engine", "core/prefix_cache/ ＋ vllm kv_ops", "blue", 96, frac=1.0),
         nd("llmengine", "LLMEngine", "vllm.v1.engine.* ★pip 依赖", "blue", 96, frac=0.47)],
        [nd("arsched", "Scheduler · 连续批处理", "core/sched/omni_ar_scheduler.py — 17 文件 / 8.6 千行", "blue", 96)],
        [nd("arworker", "Executor ＆ Worker / ModelRunner", "worker/gpu_ar_{worker, model_runner}.py — 19 文件", "blue", 96)],
        [nd("mrv2", "双轨 worker_v2/（Model Runner V2）", "MRv2 duplex / 流式音频 — duplex 会话 NPU 未支持 · 16 文件", "blue", 96, state="gap")],
    ])
    B.append((c, n, bot))
    c, n, bot = block("df", "Diffusion 图像/视频线", "orange", dfx, 420, colw, [
        [nd("dfengine", "DiffusionEngine — 638 文件 / 27.0 万行", "diffusion/diffusion_engine.py — asyncio · 扩散 KV 控制面", "orange", 96)],
        [nd("dfsched", "Scheduler · 双模式", "diffusion/sched/ — 批兼容键 · 准入合并 · 步级并波 [6 文件]", "orange", 96)],
        [nd("dfworker", "Worker（工段执行器）", "diffusion/worker/ — cache/offload/compile 装配点（图 F 标注差距）", "orange", 96, state="part")],
        [nd("dfpipe", "Pipeline（模型实现）", "diffusion/models/ 63 项 — 382 文件 / 19.3 万行", "orange", 96)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("ml", "Model / Layer / Ops · 公共执行底座（model_executor/ 574 文件 / 19.7 万行 · 被依赖第一名）", "indigo", x0, 1120, iw, [
        [nd("mlmodel", "Model（模型注册表）", "model_executor/models/（AR/omni）＋ diffusion/models/（DiT）", "indigo", 96, frac=0.49),
         nd("mlayer", "Layer / Ops（层与算子）", "vllm layers ＋ attention/ ＋ platforms/{cuda,npu}/layers/", "indigo", 96)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("plat", "平台层 ★概念图补画 — 硬件适配（310P 子平台所在 · 图 B-L6 ／ 图 F 放大）", "teal", x0, bot + 44, iw, [
        [nd("platnpu", "platforms/npu/ — NPU 唯一完整子树", "platform · worker · layers · quant · omni_connectors · models", "teal", 84, frac=0.58, state="part"),
         nd("plat310p", "_310p/ · Ascend 310P 子平台", "is_310p → NPUWorker310 ＋ Qwen3-TTS talker/code2wav patch", "teal", 84, frac=0.42, state="part")],
    ])
    B.append((c, n, bot))
    c, n, bot = block("oc", "OmniConnector（E/P/D/G）· 工段间数据总线（distributed/ 38 文件 / 1.5 万行）", "purple", x0, bot + 44, iw, [
        [nd("ocbus", "可插拔传输后端", "connectors/{shm, mooncake×2, nixl, yuanrong×2, mori} ＋ kv_transfer_manager ＋ chunk adapter", "purple", 84, state="part")],
    ])
    B.append((c, n, bot))
    c, n, bot = block("vllm", "vLLM core（pip 外部依赖 — AR 线整体复用，不复制不修改本体）", "gray", x0, bot + 44, iw, [
        [nd("vllmcore", "vllm.v1 — 引擎 / 调度器 / KV cache / CUDA Graph", "", "gray", 48)],
    ])
    B.append((c, n, bot))
    A = [arr("req1", "apiserver", "llmengine", "请求下发"),
         arr("req2", "omnistage", "dfengine", "请求下发")]
    return spec("图 A · vLLM-Omni 官方概念架构（重绘 · 代码对应版 ＋ NPU 差距标注）",
                "红 ✗ = NPU 缺失且暂无规划 · 琥珀 △ = 部分支持/进行中 · 其余 = NPU 已支持 · 青框 ★ = 概念图补画（平台层，含 310P）",
                B, A,
                "基线 commit 02bb9519a · 规模实测 · 差距明细见报告 §3/§4 与 图 G",
                legend=[("control", "请求下发")], height=int(bot + 92))


# ---------------------------------------------------------------- 图 B
def fig_b():
    B = []
    x0, iw = 80, 1440
    c, n, bot = block("l1", "L1 · EntryPoints（API 层）— 接单交付", "green", x0, 150, iw, [
        [nd("l1n", "entrypoints/ 115 文件 4.0 万行（openai/ 74 文件 3.0 万）＋ apps/（ComfyUI）", "", "green", 52)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("l2", "L2 · 编排 ★概念图折叠 — omni 区别于 vLLM 的关键", "amber", x0, bot + 44, iw, [
        [nd("l2a", "多工段总调度", "engine/ 59 文件 3.1 万行 — orchestrator（asyncio）· stage_pool（每工段一进程）", "amber", 104, frac=0.5),
         nd("l2b", "准入与弹性", "stage_admission fail-fast · phase_lock · membership · cfg_companion", "amber", 104)],
    ])
    B.append((c, n, bot))
    l3y = bot + 44
    c, n, bot = block("l3", "L3 · AR 调度 — 文本工段", "blue", x0, l3y, 880, [
        [nd("l3n", "core/ 17 文件 8.6 千行 — sched/（OmniARScheduler）＋ prefix_cache/", "", "blue", 52)],
    ])
    B.append((c, n, bot))
    l4y = bot + 44
    c, n, bot = block("l4", "L4 · Worker（三套并存）— 工段执行", "blue", x0, l4y, 880, [
        [nd("l4a", "worker/ 19 文件 7.6 千行（GPU v1）", "全平台", "blue", 84, frac=0.48),
         nd("l4b", "worker_v2/ 16 文件（MRv2）", "duplex / 流式音频 — GPU-only", "blue", 84, state="gap")],
        [nd("l4c", "platforms/npu/worker/ — NPU v1（AR ＋ Generation runner）", "is_310p → NPUWorker310（worker/base.py:10）", "blue", 84)],
    ])
    B.append((c, n, bot))
    l5y = bot + 44
    c, n, bot = block("l5", "L5a · 公共执行底座 — 两线共用", "indigo", x0, l5y, 880, [
        [nd("l5n", "model_executor/ 574 文件 19.7 万行 — 模型/层/算子注册（被依赖第一名）", "", "indigo", 52)],
    ])
    B.append((c, n, bot))
    dfb_x, dfb_w = 990, 530
    c, n, bot2 = block("dfb", "L5b · Diffusion 子系统", "orange", dfb_x, l3y, dfb_w, [
        [nd("dfb1", "diffusion/ 638 文件 27.0 万行", "engine ＋ sched 双模式 ＋ worker 装配点", "orange", 96)],
        [nd("dfb2", "能力折叠（图 E 展开）", "attention 12 后端 · cache 5 后端 · offloader", "orange", 96)],
        [nd("dfb3", "并行 ＋ 扩散 KV ＋ 模型", "cfg·hsdp·sp_plan·pp ＋ paged KV ＋ models/ 63 项", "orange", 96)],
    ], min_h=l5y + 108 - l3y)
    B.append((c, n, bot2))
    c, n, bot = block("l6", "L6 · 平台层 ★概念图折叠 — 硬件适配（图 F 放大）", "teal", x0, max(bot, bot2) + 44, iw, [
        [nd("l6a", "npu/ 32 文件（唯一完整子树）", "platform · worker · layers · quant · models", "teal", 104, frac=0.31, state="part"),
         nd("l6a310", "_310p/ · 310P 子平台", "is_310p → NPUWorker310 · Qwen3-TTS patch", "teal", 104, frac=0.31, state="part"),
         nd("l6b", "其他平台", "cuda/ rocm/ xpu/ musa/ — platform ＋ patch", "teal", 104, frac=0.38)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("l7", "L7 · 分布式传输 — 工段间快递", "purple", x0, bot + 44, iw, [
        [nd("l7n", "distributed/ 38 文件 1.5 万行 — omni_connectors/ 7 种后端（Mooncake 原生化 RFC #8928 进行中）", "", "purple", 52, state="part")],
    ])
    B.append((c, n, bot))
    c, n, bot = block("vl", "vLLM core（pip 依赖 — 整个系统 pip 安装 vllm，AR 线直接复用）", "gray", x0, bot + 44, iw, [
        [nd("vln", "vllm.v1 — 引擎 / 调度器 / KV cache / CUDA Graph", "", "gray", 48)],
    ])
    B.append((c, n, bot))
    return spec("图 B · 工程七层视图（重绘 · 规模标注 ＋ NPU 差距标注）",
                "官方概念布局 ＋ 补画编排层（L2）与平台层（L6）— 红/琥珀为 NPU 差距位 · L6 含 _310p 子平台框",
                B, [],
                "历史七层对照：L1 入口 / L2 编排 / L3-L4 AR / L5 扩散＋底座 / L6 平台 / L7 传输",
                height=int(bot + 130))


# ---------------------------------------------------------------- 图 E
def fig_e():
    B = []
    c, n, bot = block("dif", "vllm_omni/diffusion/ — 638 文件 / 27.0 万行（平台无关栈，经 current_omni_platform 钩子下沉硬件差异）", "orange", 80, 150, 1440, [
        [nd("d0", "引擎层", "diffusion_engine.py — asyncio · 取消注册表 · 扩散 KV 控制面；executor/ 三种执行器", "blue", 118, frac=0.5),
         nd("d1", "调度 sched/ · 6 文件", "批兼容键 · 扩散 KV base · 准入合并 · 步级并波 · sigma 钉死", "blue", 118)],
        [nd("d2", "执行 worker/ · 7 文件", "diffusion_worker ＋ diffusion_model_runner — cache/offload/compile 装配点", "orange", 118, frac=0.5),
         nd("d3", "注意力 attention/ · 43 文件", "registry 12 后端 · ops/ block_sparse · parallel/ ulysses·ring·allgather", "orange", 118)],
        [nd("d4", "缓存 cache/ · 33 文件", "selector → cachedit / teacache / magcache / seacache / stepcache", "green", 118, frac=0.5),
         nd("d5", "Offload offloader/ · 16 文件", "sequential / layerwise / DLO distributed_layerwise（CUDA＋NPU）", "green", 118)],
        [nd("d6", "并行 distributed/ · 40 文件", "cfg_parallel · hsdp(FSDP2) · sp_plan 声明式 · pipeline · vae_patch", "teal", 118, frac=0.5),
         nd("d7", "扩散 KV diffusion_kv/", "DiT paged KV — PAGED_SCHEDULER；NPU → Ascend FIA 128 页", "teal", 118)],
        [nd("d8", "模型 models/ · 63 项", "wan2_2 / qwen_image* / flux* / ltx2 / hunyuan_* … [382 文件 19.3 万行]", "purple", 118, frac=0.5),
         nd("d9", "量化 quantization/", "hsdp_fp8.py — HSDP×FP8 Cutlass 布局兼容（GPU 专属）", "purple", 118, state="gap")],
        [nd("d10", "支撑", "lora / hooks / interaction / postprocess / profiler / compile.py 区域编译", "amber", 118, frac=0.5, state="part"),
         nd("d11", "与平台层的接口", "worker 装配点调用 get_diffusion_* 钩子（NPU 差距标注见图 F/G）", "amber", 118)],
    ])
    B.append((c, n, bot))
    return spec("图 E · Diffusion 子系统展开（概念图中被折叠的能力拆包 ＋ NPU 差距标注）",
                "6 大能力域 ＋ 模型仓库 — 红 = GPU 专属能力，NPU 无对应实现",
                B, [],
                "引擎/调度（蓝）· 执行/注意力（橙）· 缓存/卸载（绿）· 并行/KV（青）· 模型（紫）· 支撑（琥珀）",
                height=int(bot + 110))


# ---------------------------------------------------------------- 图 F
def fig_f():
    B, A = [], []
    x0, iw = 80, 1440
    c, n, bot = block("plat", "NPUOmniPlatform（platforms/npu/platform.py:61 — OmniPlatform × vllm_ascend.NPUPlatform · hccl）", "cyan", x0, 150, iw, [
        [nd("hooks", "平台钩子", "adapt_patch · ACLGraphWrapper · inductor=False · 注意力后端解析 · paged KV 128", "cyan", 72)],
    ])
    B.append((c, n, bot))
    arx, dfx, colw = 80, 820, 700
    top = bot + 96
    c, n, bot1 = block("arc", "AR / 生成线（npu worker v1）", "blue", arx, top, colw, [
        [nd("inherit", "OmniNPUModelRunner 多重继承", "OmniGPUModelRunner（omni 逻辑）× NPUModelRunner（vllm-ascend）:39", "blue", 96)],
        [nd("aclgraph", "图模式 ＆ 采样", "ACLGraphWrapper(talker MTP) · AscendSampler · kv_quant_npu", "blue", 84)],
        [nd("kvx", "KV 分离 ＆ 多模态输出", "OmniKVTransferManager（元戎）· Mooncake RFC #8928", "blue", 84, state="part")],
        [nd("genworker", "NPUGenerationWorker / Runner", "token2wav / code2wav · async_chunk · 17 处 Omni-new", "blue", 84)],
        [nd("omninew", "同步标记：27 处 Omni-new", "升级流程 .claude/skills/vllm-omni-npu-upgrade", "blue", 72)],
    ])
    B.append((c, n, bot1))
    c, n, bot2 = block("dfc", "Diffusion 线（平台无关 worker ＋ NPU 钩子）", "orange", dfx, top, colw, [
        [nd("dworker", "DiffusionWorker / ModelRunner", "init_diffusion_worker_vllm_config: adapt_patch ＋ init_ascend_config", "orange", 84)],
        [nd("step1", "装配 ①②③", "offload DLO（CUDA＋NPU）· torch.compile 跳过 · cache selector", "orange", 96, state="part")],
        [nd("step2", "装配 ④ 注意力后端（platform.py:254）", "NPU 仅 FLASH_ATTN(fa_npu) / TORCH_SDPA / RAINFUSION — SAGE·FlashInfer·TRTLLM·VSA·FA3-HUB 缺失", "orange", 110, state="gap")],
        [nd("step3", "装配 ⑤⑥ paged KV ＋ Ulysses", "AscendBlockTables(v2) ＋ FIA 128 页 ＋ prewrite；MC2 ＋ strict-Ulysses", "orange", 96)],
        [nd("step4", "装配 ② torch.compile（regionally_compile）", "supports_torch_inductor=False → 全模型 eager — 无编译加速", "orange", 96, state="gap")],
    ])
    B.append((c, n, bot2))
    opy = max(bot1, bot2) + 96
    c, n, bot = block("ops", "平台专属算子与模型层 — NPU 深耕区", "teal", x0, opy, iw, [
        [nd("opsl", "omni NPU 层", "layers/{fused_moe, rotary_embedding} · models/ 8 wrapper · _310p（关 JIT＋NPUWorker310）", "teal", 104, frac=0.5),
         nd("opsm", "MindIE-SD 接入点（8 文件）", "diffusion/layers 融合算子 ×4 · backends/{flash_attn, rainfusion} · mxfp4_config", "teal", 104)],
    ])
    B.append((c, n, bot))
    supy = bot + 96
    c, n, b1 = block("sup1", "vllm-ascend（pip 插件）", "gray", x0, supy, 700, [
        [nd("sup1n", "NPUPlatform / AscendAttentionBackend / FIA / ACLGraph / MC2 / AscendBlockTables", "", "gray", 48)],
    ])
    B.append((c, n, b1))
    c, n, b2 = block("sup2", "MindIE-SD ＆ lite_boost（供给位）", "red", dfx, supy, 700, [
        [nd("sup2n", "注意力 / 融合算子 / 量化 kernel；lite_boost = RAINFUSION 回退", "", "red", 48)],
    ])
    B.append((c, n, b2))
    A = [arr("f1", "inherit", "aclgraph", "图捕获"), arr("f2", "aclgraph", "kvx", "采样"),
         arr("f3", "kvx", "genworker", "非 AR 段"), arr("f4", "dworker", "step1", "装配"),
         arr("f5", "step1", "step2", "注意力"), arr("f6", "step2", "step3", "KV/并行"),
         arr("f7", "step3", "step4", "编译"), arr("p1", "hooks", "inherit", "AR 线"),
         arr("p2", "hooks", "dworker", "Diffusion 线")]
    return spec("图 F · NPU 执行路径（AR 线 ＋ Diffusion 线 — 平台层放大 ＋ 差距标注）",
                "两条线共用 NPUOmniPlatform 钩子；红 ✗ = NPU 缺失能力 · 琥珀 △ = 部分/进行中",
                B, A,
                "图 A/B 的平台层（L6）放大 — 触点明细见报告 §2.6/§2.7，补充方案见 §5",
                legend=[("control", "执行流")], height=int(max(b1, b2) + 110))


# ---------------------------------------------------------------- 图 C
def fig_c():
    B, A = [], []
    bx, bw = 80, 780
    c, n, b1 = block("ep", "EntryPoints — 不参与", "gray", bx, 170, bw, [
        [nd("epn", "API / 引擎入口（MindIE-SD 不做 API 层）", "", "gray", 52)]])
    B.append((c, n, b1))
    c, n, b2 = block("ar", "AR 文本线（vLLM 原生栈）— 不参与", "gray", bx, b1 + 44, bw, [
        [nd("arn", "vLLM 原生栈 — 留给 v2 LLM 线", "", "gray", 52)]])
    B.append((c, n, b2))
    c, n, b3 = block("df", "Diffusion 图像/视频线", "orange", bx, b2 + 44, bw, [
        [nd("pipe", "Pipeline（模型实现）— hooks 落点", "block.attn 插点 · attention backend 替换 · rf_v2 mask", "orange", 84)],
        [nd("dwork", "Worker（加速 hook 共享批现场）", "编译期替换 · fusion kernel", "orange", 84)]])
    B.append((c, n, b3))
    c, n, b4 = block("ml", "Model / Layer / Ops（公共执行底座）", "indigo", bx, b3 + 44, bw, [
        [nd("mln", "model_executor ＋ diffusion/models ＋ layers/ops", "kernel 融合落点 — MindieSDBackend 5 pattern（Wan2.2 I2V +50~60%）", "indigo", 84)]])
    B.append((c, n, b4))
    c, n, b5 = block("oc", "OmniConnector（工段间传输）— 不参与", "gray", bx, b4 + 44, bw, [
        [nd("ocn", "SHM / RDMA 传输 — omni 核心自研", "", "gray", 52)]])
    B.append((c, n, b5))
    sx, sw = 1020, 500
    c, n, s5 = block("sup", "MindIE-SD（分布式 × 2025.11 · ≥ v3.1.0）", "red", sx, 170, sw, [
        [nd("s1", "① torch.compile 编译层", "MindieSDBackend 5 pattern 融合", "red", 96)],
        [nd("s2", "② attention / 稀疏算子", "attention_forward ＋ RainFusion rf_v2/v3", "red", 96)],
        [nd("s3", "③ 昇腾融合 kernel", "fast_layernorm · rotary_pos_emb · fused_qk_norm_rope", "red", 96)],
        [nd("s4", "④ 量化 kernel", "W4A4 MXFP4 QuantLinear ＋ kv_quant", "red", 96)],
        [nd("s5", "⑤ 后端选择 / CANN 时序", "platform.py:254 解析 · EZ1001 时序", "red", 96)],
    ])
    B.append((c, n, s5))
    A = [arr("t2", "s2", "pipe", "触点② 最强", sp="left", tp="right"),
         arr("t1", "s3", "mln", "触点①③④⑤ 最强", sp="left", tp="right")]
    c, n, b6 = block("limit", "已知限制", "gray", bx, b5 + 44, 1440, [
        [nd("limitn", "300I Duo 仅 5 个 SD 系模型 · parallelism 无实现层（宿主 CLI 驱动）· cache×并行 collective 失配未解", "", "gray", 52)]])
    B.append((c, n, b6))
    return spec("图 C · 现状：MindIE-SD × vLLM-Omni 合作架构（触点 → 代码锚点）",
                "灰色 = 不参与；触点全部落在 Diffusion ＋ Model/Layer/Ops 两块（与图 D 同基座对照）",
                B, A,
                "供给框内容引自 lite_boost 参考文档；触点锚点按 02bb9519a 实测修正（5 类 / 8 文件）",
                height=int(b6 + 110))


# ---------------------------------------------------------------- 图 D
def fig_d():
    B, A = [], []
    bx, bw = 80, 780
    c, n, b1 = block("ep", "EntryPoints — 职责互斥，不接", "gray", bx, 170, bw, [
        [nd("epn", "API / 引擎入口 — 生态内由 MSLiteServerDemo 承担", "", "gray", 52)]])
    B.append((c, n, b1))
    c, n, b2 = block("ar", "AR 文本线 — v2 预留（LLM 线 KV 量化）", "gray", bx, b1 + 44, bw, [
        [nd("arn", "vLLM 原生栈 · GDN 双算子已在 ops/", "", "gray", 52)]])
    B.append((c, n, b2))
    c, n, b3 = block("df", "Diffusion 图像/视频线", "orange", bx, b2 + 44, bw, [
        [nd("eng", "Engine ＋ Scheduler", "取消联动 · 批键（quality 互斥契约）· 步事件 prepare_state", "orange", 84)],
        [nd("dwork", "Worker（hooks 运行时现场）", "可逆挂载 / 按请求装卸 — 编译替换做不到请求粒度", "orange", 84)],
        [nd("pipe", "Pipeline（hooks 落点 — 最强）", "block.attn 插点 · cache 观测点 · 短路 wrapper", "orange", 84)]])
    B.append((c, n, b3))
    c, n, b4 = block("ml", "Model / Layer / Ops（公共执行底座）", "indigo", bx, b3 + 44, bw, [
        [nd("mln", "sparse/quant kernel → layers 层 · compile pattern → layer 层", "", "indigo", 60)]])
    B.append((c, n, b4))
    c, n, b5 = block("pl", "平台层 platforms/npu/ — 310P 使能包", "teal", bx, b4 + 44, bw, [
        [nd("pln", "graph_tools.py（NPUGraph 捕获/重放）· _310p eager 边界", "", "teal", 52)]])
    B.append((c, n, b5))
    c, n, b6 = block("oc", "OmniConnector — 与触点④正交互补", "gray", bx, b5 + 44, bw, [
        [nd("ocn", "工段间传输（omni 核心自研，不插手）", "", "gray", 52)]])
    B.append((c, n, b6))
    sx, sw = 1020, 500
    c, n, s5 = block("sup", "LiteBoost（MindSpore Lite · 声明式供给）", "lime", sx, 170, sw, [
        [nd("b1", "① 算子 / attention", "含 310P 手写 AscendC：innerPFA 1.62× · RoPE −88%", "lime", 96)],
        [nd("b2", "② 缓存后端", "跨 rank 一致性（all_reduce 解法）→ cache/selector", "lime", 96)],
        [nd("b3", "③ 量化 kernel ＋ 产物 schema", "QuantLinear(torch_npu) · 310P W8A8 · converter 对齐", "lime", 96)],
        [nd("b4", "④ 并行通信原语（HCCL）", "→ sp_plan ＋ group_coordinator · CFG 2 卡 1.7×", "lime", 96)],
        [nd("b5", "⑤ 编译后端", "→ platforms/npu/graph_tools.py（NPUGraph）", "lime", 96)],
    ])
    B.append((c, n, s5))
    A = [arr("t1", "b1", "pipe", "① 最强", sp="left", tp="right"),
         arr("t3", "b3", "mln", "③ 最强", sp="left", tp="right")]
    c, n, b7 = block("note", "承接形态", "gray", bx, b6 + 44, 1440, [
        [nd("noten", "嵌入式 API 契约（CacheBackend / hooks）＋ 声明数据（profile / tp_plan / 系数 JSON）",
            "与 MindIE-SD 同层不同宽：触点 3 → 5，深度覆盖 Diffusion 四模块 ＋ Model/Layer/Ops ＋ 平台层", "gray", 84)]])
    B.append((c, n, b7))
    return spec("图 D · 目标态：LiteBoost 供给下的合作架构（五触点 · 同基座逐模块对照）",
                "供给五类件：算子/attention ＋ 缓存后端 ＋ 量化 ＋ 并行原语 ＋ 编译后端",
                B, A,
                "供给框内容引自 lite_boost 参考文档（目标态）；基座与图 C 同构",
                height=int(b7 + 110))


# ---------------------------------------------------------------- 图 G（新增：差距→模块映射＋补充方案）
def fig_g():
    B, A = [], []
    x0, iw = 80, 1440
    c, n, b1 = block("perf", "性能类差距（高影响）— GPU 已支持 · NPU 缺失且暂无规划", "red", x0, 150, iw, [
        [nd("g1", "torch.compile / 区域编译", "compile.py regionally_compile — NPU inductor=False → 全 eager", "red", 96, frac=0.32),
         nd("p1", "方案 A", "acl-graph/Fx pattern 替换 or torch_npu cpp 扩展；短期 hooks 级融合", "teal", 96, frac=0.68)],
        [nd("g2", "DiT CUDA Graph decode", "qwen_image_21/decode_graph.py torch.cuda.CUDAGraph — NPU 无对应", "red", 96, frac=0.32),
         nd("p2", "方案 B", "NPUGraph 捕获（graph_tools.py 已有 exact-signature 助手可复用）", "teal", 96, frac=0.68)],
        [nd("g3", "高性能注意力后端 ×6", "SAGE_ATTN/3 · FlashInfer · TRTLLM · CUDNN · VSA · FA3-HUB — NPU 仅 FA/SDPA/RAINFUSION", "red", 96, frac=0.32),
         nd("p3", "方案 C", "MindIE-SD sparse_attention 深化 ＋ MindIE quant-attn；开源算子对齐 VSA 语义", "teal", 96, frac=0.68)],
    ])
    B.append((c, n, b1))
    c, n, b2 = block("eco", "生态/运行时类差距（中影响）", "red", x0, b1 + 44, iw, [
        [nd("g4", "MRv2（duplex / 流式音频）", "worker_v2/ GPU-only — NPU 无 runner", "red", 96, frac=0.32),
         nd("p4", "方案 D", "按 vllm-omni-npu-upgrade 流程移植；short term 保留 v1 通道", "teal", 96, frac=0.68)],
        [nd("g5", "量化矩阵缺口", "FP8 / SVDQuant(NVFP4) / bitsandbytes / torchao — NPU 有 Int8·MXFP4/8", "red", 96, frac=0.32),
         nd("p5", "方案 E", "msModelSlim / MindIE 量化产物接入 quantization/factory（W8A8 已有路径）", "teal", 96, frac=0.68)],
        [nd("g6", "HSDP×FP8", "diffusion/quantization/hsdp_fp8.py — Cutlass 布局，GPU 专属", "red", 96, frac=0.32),
         nd("p6", "方案 F", "HCCL 等价 sharded quant（MXFP4 dual-scale 已是 NPU 路线）", "teal", 96, frac=0.68)],
    ])
    B.append((c, n, b2))
    c, n, b3 = block("run", "运行时演进类（部分支持 / 进行中）", "amber", x0, b2 + 44, iw, [
        [nd("g7", "并行策略验证", "cfg_parallel / USP / HSDP 代码在 — NPU 端到端验证与 MC2 overlap 缺", "amber", 96, frac=0.32),
         nd("p7", "方案 G", "CI 扩展（A3 nightly 已跑 Wan/Qwen-Image）＋ MC2 overlap 供给", "teal", 96, frac=0.68)],
        [nd("g8", "Cache × 并行 collective", "cache 后端与 SP 并行共批失配（omni 公开承认未解）", "amber", 96, frac=0.32),
         nd("p8", "方案 H", "跨 rank 一致 cache（all_reduce sync）— LiteBoost 触点②", "teal", 96, frac=0.68)],
        [nd("g9", "OmniConnector 原生化", "AR→DiT Mooncake KV transfer — RFC #8928 进行中", "amber", 96, frac=0.32),
         nd("p9", "方案 I", "跟进 RFC；元戎 connector 为 NPU 现行通道", "teal", 96, frac=0.68)],
    ])
    B.append((c, n, b3))
    return spec("图 G · GPU ↔ NPU 能力差距标注图（差距 → 模块映射 ＋ 补充初步方案）",
                "左列 = 差距（涉及模块）· 右列 = 补充初步方案 — 红块为 §4 高/中影响项，琥珀为演进项",
                B, [],
                "差距判定基线 commit 02bb9519a；方案详见报告 §5（DiT 缺失能力）与 §4（缺失特性）",
                legend=[("control", "模块归属")], height=int(b3 + 110))


# ---------------------------------------------------------------- 图 H（新增：DiT 推理全链路代码调用逻辑图）
def fig_h():
    B, A = [], []
    x0, iw = 80, 1440
    c, n, bot = block("ent", "① 代码入口层（三选一 · 阅读起点）", "green", x0, 150, iw, [
        [nd("ent1", "CLI · vllm-omni serve ｜ HTTP · OpenAI API ｜ SDK · AsyncOmni",
            "entrypoints/cli/serve.py :1497 ｜ entrypoints/openai/api_server.py:1346 ｜ entrypoints/async_omni.py:115", "green", 84)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("orch", "② 编排层（engine/ — 多工段总调度）", "amber", x0, bot + 44, iw, [
        [nd("orch1", "AsyncOmniEngine → Orchestrator.submit_initial :1012 → StagePool 选副本 :1043", "", "amber", 52)],
        [nd("orch2", "stage_diffusion_client.add_request_async :336 — ZMQ DEALER 下发", "", "amber", 52)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("proc", "③ 工段进程入口（每工段一进程）", "blue", x0, bot + 44, iw, [
        [nd("proc1", "stage_diffusion_proc.run_loop :364 — ZMQ PULL 消息循环", "", "blue", 52)],
        [nd("proc2", "_dispatch_request :392 → 非流式 _process_request :182 ｜ 流式 _process_streaming_request :221", "", "blue", 52)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("eng", "④ DiffusionEngine（唯一执行入口）", "blue", x0, bot + 44, iw, [
        [nd("eng1", "step_streaming :515（step :595 已弃用）", "_add_prepared_request :1401 → scheduler.add_request ＋ _out_streams 队列 → async for 挂起", "blue", 84)],
        [nd("eng2", "后台调度循环 :732", "schedule → KV 注入 → execute_fn → update_from_output → _emit_outputs", "blue", 84)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("exec", "⑤ 执行器 → Worker", "indigo", x0, bot + 44, iw, [
        [nd("exec1", "execute_batch :158 ／ execute_step :175 — uniproc_executor.py（execute_fn 绑定 :482-486）", "", "indigo", 52)],
        [nd("exec2", "DiffusionWorker.execute_model :650", "", "indigo", 52)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("run", "⑥ Runner（diffusion_model_runner.py:944 — 执行模式分叉）", "indigo", x0, bot + 44, iw, [
        [nd("run1", "execute_model :944", "", "indigo", 52)],
        [nd("run2a", "批模式 _execute_request_list :773", "KV 接收 · cache 刷新 · set_forward_context → run_stage", "indigo", 84, frac=0.5),
         nd("run2b", "流式 _execute_stepwise_core :1416", "_update_states :1124 · _prepare_batch_inputs :1176", "indigo", 84, frac=0.5)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("pipe", "⑦ Pipeline（Wan22Pipeline 实例）", "orange", x0, bot + 44, iw, [
        [nd("pipe1a", "批：run_stage :760 → encode_batch :940", "text_encoder 编码 · prompt_embed_cache", "orange", 84, frac=0.5),
         nd("pipe1b", "流式：四方法契约", "denoise_step / step_scheduler / post_decode（interface.py:106-121）", "orange", 84, frac=0.5)],
        [nd("pipe2", "DiT forward — WanTransformer3DModel 28×Block", "attn1 = Attention（构造期 selector:68 平台选后端 · 调用期 forward_npu/forward_cuda）＋ FlowEulerScheduler", "orange", 96)],
        [nd("pipe3", "VAE decode :837 → DiffusionOutput(media=…)", "_decode_latents — 循环完或流式 chunk 边界", "orange", 84)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("out", "⑧ 输出回传", "purple", x0, bot + 44, iw, [
        [nd("out1", "update_from_output → _emit_outputs → _out_streams[rid]（async for 醒来 · 异步输出等 D2H）", "", "purple", 52)],
        [nd("out2", "postprocess_output :610 → format_diffusion_outputs :124 → from_diffusion :277 → ZMQ PUSH → SSE", "", "purple", 52)],
    ])
    B.append((c, n, bot))
    A = [
        arr("h1", "ent1", "orch1", "请求"),
        arr("h2", "orch2", "proc1", "ZMQ"),
        arr("h3", "proc2", "eng1", ""),
        arr("h4", "eng2", "exec1", "execute_fn"),
        arr("h5", "exec2", "run1", ""),
        arr("h6", "run2a", "pipe1a", "批"),
        arr("h7", "run2b", "pipe1b", "流式"),
        arr("h8", "pipe3", "out1", "RunnerOutput"),
    ]
    return spec("图 H · DiT 推理全链路代码调用逻辑图（入口 → 函数级 · ①→⑧ 阅读顺序）",
                "绿=入口 · 琥珀=编排 · 蓝=进程/引擎 · 靛=执行器/Runner · 橙=Pipeline/DiT · 紫=输出回传；节点副标签 = 文件:行号",
                B, A,
                "基线 commit 02bb9519a · 行号实测 · 对应报告 §1.12（Wan2.2 T2V 主线 ＋ stepwise 流式分叉）",
                legend=[("control", "调用方向")], height=int(bot + 110))


# ---------------------------------------------------------------- 图 I（新增：Qwen3-TTS Ascend 全流程数据流）
def fig_i():
    B, A = [], []
    x0, iw = 80, 1440
    c, n, bot = block("ent", "① 请求入口（text ＋ ref_audio）", "green", x0, 150, iw, [
        [nd("ent1", "HTTP / SDK — 文本 ＋ 参考音频", "serving_chat → AsyncOmni.generate（entrypoints/async_omni.py:115）→ Orchestrator", "green", 84)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("orch", "② 编排层（LLM 分支 — engine/）", "amber", x0, bot + 44, iw, [
        [nd("orch1", "Orchestrator.submit_initial :1075 → StagePool._llm_client → stage0 客户端（ZMQ）", "owns_tokenizer=True：文本分词在 stage 0 完成", "amber", 84)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("s0", "③ Stage 0 进程 · Talker（LLM_AR — NPUARWorker / NPUARModelRunner）", "blue", x0, bot + 44, iw, [
        [nd("s0a", "OmniARScheduler 连续批处理 → SchedulerOutput", "async_scheduling · prefix cache 关 · subtalker 采样参数", "blue", 84)],
        [nd("s0b", "Qwen3TTSTalker.forward：talker → talker_mtp（ACLGraphWrapper）→ code predictor（自管 ACL 图桶）", "NPUARModelRunner.execute_model — 图捕获 npu_ar_model_runner.py:163 _capture_talker_mtp_graphs", "blue", 96)],
        [nd("s0c", "sample_tokens → codes.audio [1×Q]/步 ＋ codes.ref（一次性发布）", "talker_mtp_output_key=(codes,audio)（qwen3_tts_talker.py:226）· Q=16 codebooks", "blue", 84)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("conn", "④ 工段间传输（OmniConnector · SharedMemory）", "purple", x0, bot + 44, iw, [
        [nd("conn1", "talker2code2wav_async_chunk（stage_input_processors/qwen3_tts.py:106）", "chunk 调度：IC 1 帧 → 稳态 25 帧 ＋ left_context 72 ＋ ref_code 一次性", "purple", 84)],
        [nd("conn2", "SharedMemoryConnector put/get — codec_streaming ＋ talker_first_audio 首包旁路", "deploy connectors.extra：connector_get_sleep_s=0.01 · max_wait_first_chunk=3000ms", "purple", 84)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("s1", "⑤ Stage 1 进程 · Code2Wav（LLM_GENERATION — NPUGenerationWorker / NPUGenerationModelRunner）", "orange", x0, bot + 44, iw, [
        [nd("s1a", "execute_model :109：register_chunk_recv → _update_request_states（async_chunk 拼窗）", "npu_generation_model_runner.py — chunk 逐包到达即解码", "orange", 84)],
        [nd("s1b", "Qwen3TTSCode2Wav.forward :259 → decoder.chunked_decode", "input_ids=[context 72＋chunk]×Q；NPU patch：jit off ＋ Linear/Conv 权重 NZ 转换（qwen3_tts.py:44-66）", "orange", 96)],
        [nd("s1c", "wav chunk ＋ sr → OmniOutput", "final_output_type=audio · 每包即时产出", "orange", 84)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("out", "⑥ 输出回传（音频流）", "green", x0, bot + 44, iw, [
        [nd("out1", "OmniRequestOutput（audio chunks 流式）→ HTTP SSE", "codes.audio / codec_frames 按 CONCAT_DIM0 累积（pipeline.py:22-27）", "green", 84)],
    ])
    B.append((c, n, bot))
    A = [
        arr("i1", "ent1", "orch1", "请求"),
        arr("i2", "orch1", "s0a", "ZMQ"),
        arr("i3", "s0c", "conn1", "codes 帧"),
        arr("i4", "conn2", "s1a", "chunk"),
        arr("i5", "s1c", "out1", "wav"),
    ]
    return spec("图 I · Qwen3-TTS × Ascend 全流程数据流（编排 → Talker AR → OmniConnector → Code2Wav → 音频流）",
                "绿=入口/输出 · 琥珀=编排 · 蓝=Stage 0（AR）· 紫=工段间传输 · 橙=Stage 1（生成）；副标签含 文件:行号 与张量形态",
                B, A,
                "基线 commit 02bb9519a · deploy=qwen3_tts.yaml（async_chunk · NPU v1 · PIECEWISE）· 详见 Ascend 全流程代码分析报告",
                legend=[("control", "数据流")], height=int(bot + 110))


# ---------------------------------------------------------------- 图 J（新增：从启动第一行开始的进程孵化链）
def fig_j():
    B, A = [], []
    x0, iw = 80, 1440
    c, n, bot = block("e1", "① console script（进程起点）", "green", x0, 150, iw, [
        [nd("e1n", "vllm-omni → vllm_omni.entrypoints.cli.main:main", "pyproject.toml:154 [project.scripts]；recipe 亦可走 `vllm serve … --omni`（同一 main 的 --omni 拦截分支）", "green", 84)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("e2", "② CLI main（entrypoints/cli/main.py:12）", "green", x0, bot + 44, iw, [
        [nd("e2n", "--omni flag 判定 → VLLM_LOGGING_COLOR=1 → import serve/benchmark 模块 → cli_env_setup()", "无 --omni → 转发 vllm.entrypoints.cli.main:main（原生 vLLM 行为）", "green", 84)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("e3", "③ 平台首触（★ NPU 补丁链的真正起点）", "amber", x0, bot + 44, iw, [
        [nd("e3n", "_ensure_vllm_platform（entrypoints/cli/serve.py:100）", "vLLM 平台 Unspecified → 用 current_omni_platform 顶替 —— omni 平台单例在此首次实例化：硬件探测 → NPUOmniPlatform.__init__（全部模型补丁在此安装）", "amber", 96)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("e4", "④ 命令分发（OmniServeCommand.cmd，serve.py:140）", "blue", x0, bot + 44, iw, [
        [nd("e4n", "--headless → run_headless :1366 ｜ api_server_count>1 → run_multi_api_server_omni :1299 ｜ 否则 omni_run_server", "build_vllm_config 调用点 serve.py:1497（另 stage_runtime.py:813）", "blue", 84)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("e5", "⑤ stage 进程孵化（每工段一进程）", "indigo", x0, bot + 44, iw, [
        [nd("e5n", "stage 进程 → diffusion 线：stage_diffusion_proc.run_loop :364（ZMQ PULL 消息循环）", "AR 线对应 engine/stage_engine_proc 族；deploy YAML 决定 stage 拓扑与 devices", "indigo", 84)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("e6", "⑥ worker 初始化（进程内）", "indigo", x0, bot + 44, iw, [
        [nd("e6n", "get_diffusion_worker_cls → resolve_obj_by_qualname → WorkerWrapperBase（uniproc_executor.py:66-73）", "NPU 钩子：init_diffusion_worker_vllm_config（adapt_patch ＋ init_ascend_config，diffusion_worker.py:347）→ load_model → pipeline 构造 → init_diffusion_model_runner_runtime（MC2 等）", "indigo", 96)],
    ])
    B.append((c, n, bot))
    c, n, bot = block("e7", "⑦ 就绪，等待 ZMQ 请求", "green", x0, bot + 44, iw, [
        [nd("e7n", "profile_run → capture_model → 进入 run_loop 消息循环", "diffusion 线 capture 的是主模型 PIECEWISE ACL 图；AR 线另有 talker MTP 图（Qwen3-TTS 报告 §4.4）", "green", 84)],
    ])
    B.append((c, n, bot))
    A = [
        arr("j1", "e1n", "e2n", ""),
        arr("j2", "e2n", "e3n", ""),
        arr("j3", "e3n", "e4n", "平台就绪"),
        arr("j4", "e4n", "e5n", "孵化"),
        arr("j5", "e5n", "e6n", ""),
        arr("j6", "e6n", "e7n", "加载完成"),
    ]
    return spec("图 J · 从启动第一行开始的进程孵化链（CLI → 平台首触 → stage 进程 → worker 初始化）",
                "绿=进程/就绪 · 琥珀=平台首触（NPU 补丁链起点） · 蓝=命令分发 · 靛=孵化/worker；副标签 = 文件:行号",
                B, A,
                "基线 commit 02bb9519a · 行号实测 · Qwen3-TTS 与 Boogu-Image 两份 Ascend 全流程报告共用此启动链",
                legend=[("control", "启动顺序")], height=int(bot + 110))


FIGS = {"a": fig_a, "b": fig_b, "e": fig_e, "f": fig_f, "c": fig_c, "d": fig_d, "g": fig_g, "h": fig_h, "i": fig_i, "j": fig_j}

if __name__ == "__main__":
    import sys
    keys = sys.argv[1:] or list(FIGS)
    for k in keys:
        s = FIGS[k]()
        p = OUT / f"fig_{k}.json"
        p.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"wrote {p.name}: {len(s['containers'])} containers, {len(s['nodes'])} nodes, {len(s['arrows'])} arrows")
