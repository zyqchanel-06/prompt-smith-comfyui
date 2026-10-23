# -*- coding: utf-8 -*-
"""promptsmith-render：一条命令走完 构建 → 自检 → 出图 → 质检。"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from promptsmith import ProfileError, SLOT_LABELS, SLOT_ORDER, SlotRequest, load_profile

from .client import ComfyError
from .render import RenderRefused, render as do_render


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="promptsmith-render",
        description="用 prompt-smith 档案构建提示词并调用 ComfyUI 出图",
    )
    parser.add_argument("--profile", "-p", required=True, help="档案路径（.json / .yaml）")
    for slot in SLOT_ORDER:
        parser.add_argument("--" + slot, help="%s槽位" % SLOT_LABELS[slot])
    parser.add_argument("--extra", help="额外正向 tag")
    parser.add_argument("--extra-negative", help="额外负向 tag")
    parser.add_argument("--count", "-n", type=int, default=2, help="出几张（默认 2）")
    parser.add_argument("--outdir", "-o", default="out", help="输出目录（默认 out/）")
    parser.add_argument("--seed", type=int, default=None, help="基准种子；第 i 张用 seed+i")
    parser.add_argument("--prefix", default=None, help="文件名前缀（默认用档案名）")
    parser.add_argument("--force", action="store_true", help="自检有 error 也照常渲染")
    parser.add_argument("--no-gate", dest="gate", action="store_false", help="跳过出图后的亮度/对比度核对")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = load_profile(args.profile)
    except ProfileError as exc:
        print("档案错误:", exc, file=sys.stderr)
        return 2

    request = SlotRequest(
        subject=args.subject or "",
        outfit=args.outfit or "",
        scene=args.scene or "",
        pose=args.pose or "",
        expression=args.expression or "",
        framing=args.framing or "",
        extra_positive=args.extra or "",
        extra_negative=args.extra_negative or "",
    )

    try:
        report = do_render(
            request, profile,
            count=args.count, outdir=args.outdir, seed=args.seed,
            force=args.force, apply_gate=args.gate, prefix=args.prefix,
        )
    except RenderRefused as exc:
        print("拒绝渲染:", exc, file=sys.stderr)
        if args.json:
            print(json.dumps({"ok": False, "reason": str(exc),
                              "checks": [c.as_dict() for c in exc.build.checks]},
                             ensure_ascii=False, indent=2))
        return 3
    except ComfyError as exc:
        print("ComfyUI 错误:", exc, file=sys.stderr)
        return 4

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("POSITIVE:", report["positive"][:160] + ("..." if len(report["positive"]) > 160 else ""))
        print("SAVED:", len(report["saved"]))
        for path in report["saved"]:
            print("  " + path)
        for item in report["gate"]:
            verdict = "PASS" if item["pass"] else "FAIL"
            print("GATE %s  %s  亮度=%.1f 对比度=%.1f" % (
                verdict, item["image"], item["brightness"], item["contrast"]))
        if report["gate_failed"]:
            print("注意: %d 张没过质量门，建议重出" % len(report["gate_failed"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
