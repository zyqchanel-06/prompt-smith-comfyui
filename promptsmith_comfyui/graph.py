# -*- coding: utf-8 -*-
"""把提示词 + 渲染参数组装成 ComfyUI 工作流（API 格式）。

工作流刻意做得极简（checkpoint → 可选 LoRA → 双 CLIP 编码 → KSampler → VAE → 保存），
因为适配器的职责是"把参数送进去"，不是替用户设计工作流。
要更复杂的流程，改 build_graph 或直接传自己的工作流 JSON。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

DEFAULT_RENDER = {
    "checkpoint": "your_sdxl_checkpoint.safetensors",
    "width": 832,
    "height": 1216,
    "steps": 30,
    "cfg": 7.0,
    "sampler": "euler_ancestral",
    "scheduler": "normal",
    "lora": None,
}


def normalize_render(render: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """把档案里的 render 字段补全成完整参数。"""
    conf = dict(DEFAULT_RENDER)
    for key, value in (render or {}).items():
        if value is not None:
            conf[key] = value
    lora = conf.get("lora")
    if isinstance(lora, str):
        conf["lora"] = {"name": lora, "strength": 1.0}
    return conf


def build_graph(
    positive: str,
    negative: str,
    render: Optional[Dict[str, Any]] = None,
    seed: int = 0,
    prefix: str = "promptsmith",
) -> Dict[str, Any]:
    """构造 ComfyUI API 格式的工作流字典。"""
    conf = normalize_render(render)
    lora = conf.get("lora") or {}

    graph: Dict[str, Any] = {
        "3": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": conf["checkpoint"]},
        }
    }

    # CLIP / MODEL 的来源节点：有 LoRA 就串一层 LoraLoader
    if lora.get("name"):
        graph["4"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["3", 0],
                "clip": ["3", 1],
                "lora_name": lora["name"],
                "strength_model": float(lora.get("strength", 1.0)),
                "strength_clip": float(lora.get("strength", 1.0)),
            },
        }
        model_src, clip_src = ["4", 0], ["4", 1]
    else:
        model_src, clip_src = ["3", 0], ["3", 1]

    graph["6"] = {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": clip_src}}
    graph["7"] = {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": clip_src}}
    graph["5"] = {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": int(conf["width"]), "height": int(conf["height"]), "batch_size": 1},
    }
    graph["8"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": model_src,
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
            "seed": int(seed),
            "steps": int(conf["steps"]),
            "cfg": float(conf["cfg"]),
            "sampler_name": conf["sampler"],
            "scheduler": conf["scheduler"],
            "denoise": 1.0,
        },
    }
    graph["9"] = {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 2]}}
    graph["10"] = {
        "class_type": "SaveImage",
        "inputs": {"images": ["9", 0], "filename_prefix": prefix},
    }
    return graph
