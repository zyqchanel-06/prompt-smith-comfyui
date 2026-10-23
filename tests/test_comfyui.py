# -*- coding: utf-8 -*-
"""适配器测试：工作流结构、参数补全、自检门禁。

不需要真的跑 ComfyUI —— 所有用例都在"提交给 ComfyUI 之前"结束。
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)
CORE_ROOT = os.path.join(PKG_ROOT, "..", "prompt-smith")
for path in (PKG_ROOT, CORE_ROOT):
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, os.path.abspath(path))

from promptsmith import SlotRequest, load_profile  # noqa: E402
from promptsmith_comfyui.graph import build_graph, normalize_render  # noqa: E402
from promptsmith_comfyui.render import RenderRefused, render  # noqa: E402

PROFILE_PATH = os.path.join(os.path.abspath(CORE_ROOT), "profiles", "example.json")


class TestNormalizeRender(unittest.TestCase):
    def test_defaults_applied(self):
        conf = normalize_render({})
        self.assertEqual(conf["width"], 832)
        self.assertEqual(conf["steps"], 30)
        self.assertIsNone(conf["lora"])

    def test_lora_string_becomes_object(self):
        conf = normalize_render({"lora": "style.safetensors"})
        self.assertEqual(conf["lora"]["name"], "style.safetensors")
        self.assertEqual(conf["lora"]["strength"], 1.0)

    def test_none_values_ignored(self):
        conf = normalize_render({"steps": None, "cfg": 6.5})
        self.assertEqual(conf["steps"], 30)
        self.assertEqual(conf["cfg"], 6.5)


class TestBuildGraph(unittest.TestCase):
    def test_without_lora(self):
        graph = build_graph("pos", "neg", {"checkpoint": "c.safetensors"}, seed=42)
        self.assertNotIn("4", graph)
        self.assertEqual(graph["3"]["inputs"]["ckpt_name"], "c.safetensors")
        self.assertEqual(graph["8"]["inputs"]["seed"], 42)
        self.assertEqual(graph["8"]["inputs"]["model"], ["3", 0])
        self.assertEqual(graph["6"]["inputs"]["text"], "pos")
        self.assertEqual(graph["7"]["inputs"]["text"], "neg")

    def test_with_lora_chain(self):
        graph = build_graph("pos", "neg",
                            {"checkpoint": "c.safetensors",
                             "lora": {"name": "l.safetensors", "strength": 0.8}}, seed=1)
        self.assertIn("4", graph)
        self.assertEqual(graph["4"]["inputs"]["lora_name"], "l.safetensors")
        self.assertEqual(graph["4"]["inputs"]["strength_model"], 0.8)
        self.assertEqual(graph["8"]["inputs"]["model"], ["4", 0])
        self.assertEqual(graph["6"]["inputs"]["clip"], ["4", 1])

    def test_save_node_uses_prefix(self):
        graph = build_graph("pos", "neg", {}, seed=1, prefix="test_01")
        self.assertEqual(graph["10"]["inputs"]["filename_prefix"], "test_01")
        self.assertEqual(graph["10"]["class_type"], "SaveImage")


class TestSelfCheckGate(unittest.TestCase):
    """自检没过就不该走到 ComfyUI —— 这里验证它在连接之前就拒绝。"""

    def setUp(self):
        self.profile = load_profile(PROFILE_PATH)

    def test_refuse_when_check_fails(self):
        # watermark 是示例档案的红线词
        request = SlotRequest(subject="1girl", extra_positive="watermark")
        with self.assertRaises(RenderRefused) as ctx:
            render(request, self.profile, count=1)
        self.assertIn("FORBIDDEN_TAG", str(ctx.exception) + json_codes(ctx.exception))

    def test_force_bypasses_gate_but_then_needs_comfy(self):
        # 加 --force 后会去连 ComfyUI；本地没跑 ComfyUI，应抛 ComfyError 而不是 RenderRefused
        from promptsmith_comfyui.client import ComfyError
        request = SlotRequest(subject="1girl", extra_positive="watermark")
        profile = dict(self.profile)
        profile["render"] = dict(profile.get("render") or {}, comfyui_url="http://127.0.0.1:1")
        with self.assertRaises(ComfyError):
            render(request, profile, count=1, force=True)


def json_codes(build_error):
    try:
        return " ".join(item.code for item in build_error.build.checks)
    except Exception:
        return ""


if __name__ == "__main__":
    unittest.main()
