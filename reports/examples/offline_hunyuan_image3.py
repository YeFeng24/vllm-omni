# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""HunyuanImage3 离线推理用例（DiT-only 部署 · CUDA/NPU 通用）。

对应报告：《离线用例逐行代码分析.md》（本仓 reports/ 目录）——本脚本每一行
在该文档 §1 逐行解读，调用进入框架后的逐函数链见 §2-§7。

用法（DiT-only 部署需要 4 卡：TP=4 + 专家并行，见 deploy/hunyuan_image3_dit.yaml）：
    python offline_hunyuan_image3.py \
        --model tencent/HunyuanImage-3.0-Instruct \
        --deploy-config hunyuan_image3_dit.yaml \
        --prompt "a cute orange cat wearing an astronaut helmet, cinematic lighting" \
        --output hunyuan_image3_out.png
"""

import argparse
import time

from vllm_omni.entrypoints.omni import Omni
from vllm_omni.inputs.data import OmniDiffusionSamplingParams


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HunyuanImage3 offline text-to-image (DiT-only deploy).")
    parser.add_argument("--model", default="tencent/HunyuanImage-3.0-Instruct",
                        help="HF 模型名或本地路径（权重缺失时先 omni_snapshot_download）")
    parser.add_argument("--deploy-config", default="hunyuan_image3_dit.yaml",
                        help="DiT-only 单工段部署；裸文件名会在 vllm_omni/deploy/ 下解析")
    parser.add_argument("--prompt", default="a cute orange cat wearing an astronaut helmet, cinematic lighting")
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--num-inference-steps", type=int, default=50)
    parser.add_argument("--guidance-scale", type=float, default=None,
                        help="None = 不显式传，走 request_layout 的默认解析")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="hunyuan_image3_out.png")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # ── 1) 构造离线引擎（同步封装，阻塞直到全部 stage 就绪）─────────────────
    # 这一行触发：平台单例首触（补丁链）→ deploy YAML 解析（pipeline_registry）
    #   → stage 进程孵化（本部署 1 个 diffusion 工段）→ DiffusionWorker 初始化
    #   → HunyuanImage3Pipeline 加载（text_encoder/DiT(MoE)/VAE）→ capture/profile
    omni = Omni(
        model=args.model,
        deploy_config=args.deploy_config,
        trust_remote_code=True,  # HunyuanImage3 依赖 HF remote code
    )

    # ── 2) 请求信封：modalities=["image"] 把 final 输出路由到图像后处理 ────
    prompt = {"prompt": args.prompt, "modalities": ["image"]}

    # ── 3) 每工段一份采样参数（DiT-only 部署只有 1 个工段 → 列表长度必须 = 1）──
    sampling_params_list = [
        OmniDiffusionSamplingParams(
            height=args.height,
            width=args.width,
            num_inference_steps=args.num_inference_steps,
            guidance_scale=args.guidance_scale,  # None → 引擎按 request_layout 解析
            seed=args.seed,
        ),
    ]

    # ── 4) 离线生成：阻塞直到 final 工段产出；返回 list[OmniRequestOutput] ──
    start = time.perf_counter()
    outputs = omni.generate(prompt, sampling_params_list=sampling_params_list, use_tqdm=True)
    print(f"generation time: {time.perf_counter() - start:.2f}s")

    # ── 5) 取图保存：OmniRequestOutput.images 由 output_formatter 组装 ─────
    images = None
    for out in outputs:
        images = getattr(out, "images", None) or images
    if not images:
        raise ValueError("no images in OmniRequestOutput")
    images[0].save(args.output)
    print(f"saved: {args.output}")

    # ── 6) 关闭引擎（终止 stage 进程/编排线程；弱引用 finalizer 兜底）────────
    omni.close()


if __name__ == "__main__":
    main()
