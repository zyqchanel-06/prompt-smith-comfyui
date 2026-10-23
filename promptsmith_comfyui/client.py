# -*- coding: utf-8 -*-
"""ComfyUI HTTP 客户端（纯标准库）。

只依赖 urllib，不需要 requests / websocket —— 出图是"提交任务 → 轮询历史"，
轮询足够了，不值得为此引入第三方依赖。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


class ComfyError(RuntimeError):
    """ComfyUI 侧的错误（未启动、任务失败、超时）。"""


class ComfyClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188", timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ---- 底层请求 ----
    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + path, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ComfyError("连不上 ComfyUI（%s）：%s" % (self.base_url, exc)) from exc

    def _get(self, path: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        try:
            with urllib.request.urlopen(self.base_url + path, timeout=timeout or self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ComfyError("连不上 ComfyUI（%s）：%s" % (self.base_url, exc)) from exc

    def _get_bytes(self, path: str, timeout: Optional[float] = None) -> bytes:
        try:
            with urllib.request.urlopen(self.base_url + path, timeout=timeout or self.timeout) as resp:
                return resp.read()
        except urllib.error.URLError as exc:
            raise ComfyError("下载图片失败：%s" % exc) from exc

    # ---- 公开能力 ----
    def alive(self) -> bool:
        """ComfyUI 是否在跑。"""
        try:
            self._get("/system_stats", timeout=5)
            return True
        except ComfyError:
            return False

    def require_alive(self) -> None:
        if not self.alive():
            raise ComfyError(
                "ComfyUI 未运行。请先启动它（默认 http://127.0.0.1:8188），"
                "或把档案里的 render.comfyui_url 指向正确地址。"
            )

    def queue(self, graph: Dict[str, Any]) -> str:
        """提交工作流，返回 prompt_id。"""
        result = self._post("/prompt", {"prompt": graph})
        pid = result.get("prompt_id")
        if not pid:
            raise ComfyError("ComfyUI 拒绝了工作流：%s" % json.dumps(result, ensure_ascii=False)[:300])
        return str(pid)

    def wait(self, prompt_id: str, timeout: float = 400.0, interval: float = 3.0) -> List[Dict[str, Any]]:
        """轮询直到完成，返回输出里的图片元信息列表。"""
        deadline = time.time() + timeout
        quoted = urllib.parse.quote(prompt_id)
        while time.time() < deadline:
            time.sleep(interval)
            try:
                history = self._get("/history/" + quoted)
            except ComfyError:
                continue
            entry = history.get(prompt_id)
            if not entry:
                continue
            status = entry.get("status") or {}
            if status.get("completed"):
                images: List[Dict[str, Any]] = []
                for _node_id, out in (entry.get("outputs") or {}).items():
                    for img in out.get("images") or []:
                        images.append(img)
                return images
            if status.get("status_str") == "error":
                raise ComfyError("ComfyUI 执行失败：%s" % json.dumps(entry, ensure_ascii=False)[:400])
        raise ComfyError("等待出图超时（%.0fs）：%s" % (timeout, prompt_id))

    def download(self, image: Dict[str, Any]) -> bytes:
        """按 /view 拿图片字节。"""
        query = urllib.parse.urlencode({
            "filename": image.get("filename", ""),
            "subfolder": image.get("subfolder", ""),
            "type": image.get("type", "output"),
        })
        return self._get_bytes("/view?" + query)
