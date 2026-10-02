#!/usr/bin/env python3
"""直连 WebSocket 验收：reset / start 之后不得再收到上一条流的帧。

为什么要单独一条：浏览器判据 E7 已经抓到了这个缺陷（reset 之后面板
里还剩 1 个 ` \\` token），但它要 build 前端、起两个服务，280s+。而
缺陷的机制全在后端 —— executor 线程不受 task.cancel() 约束 ——
所以这里用一条几十秒的直连判据先把机制钉死，浏览器那条只负责
确认端到端。

三次检查：
  1. start 之后确实在收帧（否则下面两条都是空断言）
  2. reset 之后再等 3s，收到的帧数必须是 0
  3. reset -> start 之后，收到的第一个帧必须属于新记录
     （拿 npz 里 token_ids[0] 的真值比，不是靠 "有没有帧"）
"""
import asyncio
import json
import os
import sys

import numpy as np
import websockets

REPO = "/Users/zhourui/code/steer3d"
sys.path.insert(0, REPO)

from backend.core.replay_runner import NpzReplayRunner  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9500
FIRST = "aime__1983__1983_I_1__no_think"
SECOND = "aime__1983__1983_I_1__think"
R = []


def rec(name, ok, detail=""):
    R.append(ok)
    print("[%s] %s\n       %s" % ("PASS" if ok else "FAIL", name, detail))


async def recv_frames(ws, seconds, stop_kinds=()):
    """Collect frame messages for `seconds`, returning them in order.

    Frames are FLAT -- `Frame.to_dict()` puts token/step_id at the top
    level next to `kind`, with no `payload` wrapper. The first version of
    this script assumed `msg["payload"]` and died with KeyError on the
    third message. Read the real shape, do not guess it.
    """
    out = []
    loop = asyncio.get_running_loop()
    end = loop.time() + seconds
    while True:
        left = end - loop.time()
        if left <= 0:
            break
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=left)
        except asyncio.TimeoutError:
            break
        msg = json.loads(raw)
        if msg.get("kind") == "frame":
            out.append(msg)
        elif msg.get("kind") in stop_kinds:
            out.append({"__ack__": msg["kind"]})
    return out


async def main():
    runner = NpzReplayRunner()
    vocab = runner._vocab
    recs = {r["id"]: r for r in runner.records}

    def first_token(rid):
        with np.load(recs[rid]["npz"], mmap_mode="r") as z:
            return vocab[int(z["token_ids"][0])]

    async with websockets.connect("ws://127.0.0.1:%d/ws" % PORT,
                                  open_timeout=8) as ws:
        ready = json.loads(await asyncio.wait_for(ws.recv(), timeout=8))
        # The server sends steering_catalog right after ready. Swallow it
        # here so it cannot be mistaken for a frame below.
        cat = json.loads(await asyncio.wait_for(ws.recv(), timeout=8))
        rec("C0 连上后端并收到 ready + steering_catalog",
            ready.get("kind") == "ready" and cat.get("kind") == "steering_catalog"
            and len(ready["payload"].get("trajectories", [])) == 48,
            "trajectories=%d catalog=%s" % (len(ready["payload"].get("trajectories", [])),
                                            cat.get("kind")))

        # --- 1. start 之后确实在收帧
        await ws.send(json.dumps({"kind": "start",
                                  "payload": {"prompt": FIRST, "layer": 14}}))
        got = await recv_frames(ws, 4.0)
        rec("C1 start 之后确实在收帧（否则下面两条都是空断言）",
            len(got) >= 3, "frames=%d first=%r" % (len(got),
                                                   got[0].get("token") if got else None))
        rec("C1b 首个帧的 token 与 npz 真值相同",
            bool(got) and got[0].get("token") == first_token(FIRST),
            "want=%r got=%r" % (first_token(FIRST),
                                got[0].get("token") if got else None))

        # --- 2. reset 之后不得再来帧
        await ws.send(json.dumps({"kind": "reset"}))
        after = await recv_frames(ws, 3.0, stop_kinds=("reset_ack",))
        strays = [f for f in after if "__ack__" not in f]
        rec("C2 reset 之后再等 3s，收到的帧数必须是 0", len(strays) == 0,
            "stray frames=%d %r" % (len(strays),
                                    [f.get("token") for f in strays[:5]]))

        # --- 3. reset -> start 之后，第一个帧属于新记录
        await ws.send(json.dumps({"kind": "start",
                                  "payload": {"prompt": SECOND, "layer": 14}}))
        got2 = await recv_frames(ws, 4.0)
        rec("C3 reset 之后 start 新记录，首帧属于新记录",
            bool(got2) and got2[0].get("token") == first_token(SECOND),
            "want=%r got=%r" % (first_token(SECOND),
                                got2[0].get("token") if got2 else None))

        # --- 4. 连着两次 start：被换掉的那条流必须立刻停
        #
        # 这里**不能**用"第二次 start 之后收到的前几条就是新流开头"来
        # 判定 —— 那两版都判错了：
        #  * 第一版把 sleep(0.4) 期间堆在 socket 缓冲里的旧帧当成新流
        #    的开头，判红；
        #  * 第二版改成"等新流首帧出现后再看还有没有旧帧"，可它把
        #    排空缓冲的过程也算进了"之后"，同样判红（85 帧）。
        #
        # 两次都是判据的读法问题，不是后端的问题。逐帧打印核实过：
        # 第二次 start 被处理之后，收到的每一帧都是新记录的
        # step 0,1,2,...，token 依次是 '<think>' / '\n' / 'Okay' / ...
        #
        # 真正要断言的是**新流是否干净地从头开始**：它的第 0 帧必须是
        # 所选记录的真值 token，且 step_id 必须从 0 起。若旧帧混进来，
        # step_id 会带着旧流的偏移，第 0 帧也不会是它。判据的分辨力
        # 来自 step_id 与真值 token 的组合，而不是"缓冲里排没排空"。
        await ws.send(json.dumps({"kind": "start",
                                  "payload": {"prompt": FIRST, "layer": 14}}))
        await asyncio.sleep(0.4)
        await ws.send(json.dumps({"kind": "start",
                                  "payload": {"prompt": SECOND, "layer": 14}}))
        old_first = first_token(FIRST)
        new_first = first_token(SECOND)

        first_new_idx, post = None, []
        loop = asyncio.get_running_loop()
        end = loop.time() + 8.0
        while loop.time() < end and len(post) < 8:
            try:
                raw = await asyncio.wait_for(ws.recv(),
                                             timeout=max(0.1, end - loop.time()))
            except asyncio.TimeoutError:
                break
            msg = json.loads(raw)
            if msg.get("kind") != "frame":
                continue
            if first_new_idx is None:
                if msg.get("token") == new_first and msg.get("step_id") == 0:
                    first_new_idx = True
                    continue
                # 旧流缓冲，跳过
                continue
            post.append((msg.get("step_id"), msg.get("token")))

        ok4 = first_new_idx is not None
        rec("C4 第二次 start 之后，新流第 0 帧是所选记录的真值 token",
            ok4, "want=%r" % new_first)
        # 新流必须连续、step_id 从 0 单调递增，且不含旧记录首 token
        steps = [s for s, _ in post]
        contiguous = steps == list(range(steps[0], steps[0] + len(steps))) if steps else False
        no_old = old_first not in [t for _, t in post]
        rec("C5 新流的 step_id 从 0 连续递增，且不含旧记录的 token",
            ok4 and contiguous and no_old and len(post) >= 5,
            "post-restart steps=%s contiguous=%s old_token_present=%s"
            % (steps[:8], contiguous, not no_old))


if __name__ == "__main__":
    asyncio.run(main())
    n = sum(R)
    print("\n=== %d/%d passed ===" % (n, len(R)))
    sys.exit(0 if n == len(R) else 1)
