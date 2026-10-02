#!/usr/bin/env python3
"""单条变异施加器（轨迹选择器）。用法: python3 apply_mut_picker.py M1"""
import io
import sys

PANEL = "frontend/components/ControlPanel.tsx"
SRV = "backend/server.py"
RUNNER = "backend/core/replay_runner.py"


def read(p):
    return io.open(p, encoding="utf-8").read()


def write(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


def m1(s):
    """后端不上报轨迹清单 —— UI 退回自由文本框，缺陷重现。"""
    p = SRV
    s = read(p)
    old = """            trajectories=list(
                (getattr(state.runner, "describe", None) or (lambda: []))()
            ),"""
    new = "            trajectories=[],  # MUT_NO_TRAJECTORIES"
    assert old in s, "M1 anchor not found"
    write(p, s.replace(old, new, 1))
    return p


def m2(s):
    """UI 无条件用文本框，即使后端给了清单。"""
    p = PANEL
    s = read(p)
    old = "  const pickList = trajectories.length > 0;"
    new = "  const pickList = false && trajectories.length > 0;  // MUT_FORCE_TEXTAREA"
    assert old in s, "M2 anchor not found"
    write(p, s.replace(old, new, 1))
    return p


def m3(s):
    """Start 时仍用 localPrompt（可能是不存在的 id），绕开选择器。"""
    p = PANEL
    s = read(p)
    old = "      payload: { prompt: effectivePrompt, layer },"
    new = "      payload: { prompt: localPrompt, layer },  // MUT_RAW_PROMPT"
    assert old in s, "M3 anchor not found"
    write(p, s.replace(old, new, 1))
    return p


def m4(s):
    """只报一半的轨迹 —— 有一半真实记录选不到。"""
    p = RUNNER
    s = read(p)
    old = "        return out"
    new = "        return out[:24]  # MUT_HALF_TRAJECTORIES"
    assert old in s, "M4 anchor not found"
    write(p, s.replace(old, new, 1))
    return p


MUTS = {"M1": m1, "M2": m2, "M3": m3, "M4": m4}

if __name__ == "__main__":
    which = sys.argv[1]
    if which not in MUTS:
        print("unknown", which)
        sys.exit(2)
    print("  applied", which, "->", MUTS[which](None))
