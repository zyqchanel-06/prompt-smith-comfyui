# -*- coding: utf-8 -*-
"""渲染编排：提示词自检 → 提交 ComfyUI → 落盘 → 可选质量门。

设计原则：**自检不通过就不出图**。

这是整套流程里最容易被省掉的一步——很多人拿到一份提示词就直接开抽，
抽完发现触发词写错了、红线词混进去了，白烧十分钟显卡。
把门禁放在渲染入口，成本几乎为零。
"""
from __future__ import annotations

import os
import random
from typing import Any, Dict, List, Optional

from promptsmith import SlotRequest, compose

from .client import ComfyClient, ComfyError
from .graph import build_graph, normalize_render


class RenderRefused(RuntimeError):
    """提示词没过自检，拒绝渲染。"""

    def __init__(self, message: str, build: Any) -> None:
        super().__init__(message)
        self.build = build


def _unique_path(outdir: str, prefix: str, index: int) -> str:
    """避免覆盖已有文件：name_1.png 存在就退到 name_1_2.png。"""
    base = "%s_%d" % (prefix, index)
    path = os.path.join(outdir, base + ".png")
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(outdir, "%s_%d_%d.png" % (prefix, index, suffix))
        suffix += 1
    return path


def render(
    request: SlotRequest,
    profile: Dict[str, Any],
    count: int = 2,
    outdir: str = "out",
    seed: Optional[int] = None,
    force: bool = False,
    apply_gate: bool = True,
    prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """按档案出图，返回报告字典。

    force=True 时即使自检有 error 也照常渲染（用于"我知道我在干什么"的场景）。
    """
    build = compose(request, profile)

    if not build.ok and not force:
        messages = "; ".join(item.message for item in build.errors())
        raise RenderRefused("提示词未通过自检，已拒绝渲染：%s（确需出图请加 --force）" % messages, build)

    conf = normalize_render(profile.get("render") or {})
    base_url = conf.get("comfyui_url") or (profile.get("render") or {}).get("comfyui_url")         or "http://127.0.0.1:8188"
    client = ComfyClient(base_url)
    client.require_alive()

    os.makedirs(outdir, exist_ok=True)
    name_prefix = prefix or profile["name"].replace(" ", "_")
    base_seed = seed if seed is not None else random.randint(0, 1_000_000)

    saved: List[str] = []
    gate_results: List[Dict[str, Any]] = []
    for index in range(1, max(1, count) + 1):
        current_seed = base_seed + index - 1
        graph = build_graph(
            build.positive,
            build.negative,
            profile.get("render") or {},
            seed=current_seed,
            prefix="%s_%d" % (name_prefix, index),
        )
        images = client.wait(client.queue(graph))
        if not images:
            continue
        target = _unique_path(outdir, name_prefix, index)
        with open(target, "wb") as handle:
            handle.write(client.download(images[0]))
        saved.append(target)

    if apply_gate and saved:
        try:
            from promptsmith.quality import QualityError, gate as run_gate
        except ImportError:
            run_gate = None  # type: ignore
        if run_gate is not None:
            for path in saved:
                try:
                    gate_results.append(run_gate(path, profile))
                except QualityError:
                    gate_results = []
                    break

    return {
        "ok": True,
        "profile": profile["name"],
        "positive": build.positive,
        "negative": build.negative,
        "checks": [item.as_dict() for item in build.checks],
        "seed_base": base_seed,
        "saved": saved,
        "gate": gate_results,
        "gate_failed": [item for item in gate_results if not item["pass"]],
    }
