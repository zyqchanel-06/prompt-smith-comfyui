# -*- coding: utf-8 -*-
"""prompt-smith 的 ComfyUI 渲染适配器。

    from promptsmith import SlotRequest, load_profile
    from promptsmith_comfyui import render

    profile = load_profile("profiles/example.json")
    report = render(SlotRequest(subject="1girl, solo"), profile, count=2)
    print(report["saved"])
"""
from .client import ComfyClient, ComfyError
from .graph import build_graph, normalize_render
from .render import RenderRefused, render

__version__ = "0.1.0"

__all__ = [
    "ComfyClient",
    "ComfyError",
    "RenderRefused",
    "build_graph",
    "normalize_render",
    "render",
    "__version__",
]
