#!/usr/bin/env python3
"""单条变异施加器（3D 真实回放）。用法: python3 apply_mut3d.py M1

每条一条 assert 锚点。单独成文件的原因和 backmap 那套一样：
把 Python 塞进 bash 多行字符串时 $ 和引号会被吃掉，改写静默失败，
而外层脚本继续往下跑并报告"变异已生效"——那正是"变异打在死代码上"。
"""
import io
import sys

RUNNER = "backend/core/replay_runner.py"
DEFRUN = "backend/core/model_runner.py"
SRV = "backend/server.py"


def read(p):
    return io.open(p, encoding="utf-8").read()


def write(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


def m1(s):
    """退回合成 runner —— 还原这次发现的原始状态。"""
    p = DEFRUN
    s = read(p)
    old = """    from .replay_runner import NpzReplayRunner

    runner = NpzReplayRunner()
    if runner.records:
        runner.reset()
        return runner
    return SyntheticRunner()"""
    new = "    return SyntheticRunner()  # MUT_BACK_TO_SYNTHETIC"
    assert old in s, "M1 anchor not found in model_runner.py"
    write(p, s.replace(old, new, 1))
    return "model_runner.py"


def m2(s):
    """d_model 写死 4096（合成 runner 的玩具维度）。"""
    p = RUNNER
    s = read(p)
    old = """                self.d_model = int(hs.shape[2])
                self.n_layers = int(hs.shape[1])"""
    new = """                self.d_model = 4096  # MUT_HARDCODE_DMODEL
                self.n_layers = int(hs.shape[1])"""
    assert old in s, "M2 anchor not found in replay_runner.py"
    write(p, s.replace(old, new, 1))
    return p


def m3(s):
    """层列表清空 —— UI 退回自己猜。"""
    p = RUNNER
    s = read(p)
    old = "                self.available_layers = list(range(self.n_layers))"
    new = "                self.available_layers = []  # MUT_NO_LAYERS"
    assert old in s, "M3 anchor not found"
    write(p, s.replace(old, new, 1))
    return p


def m4(s):
    """token 文本编造 —— 用步号拼一个词表外的字符串。"""
    p = RUNNER
    s = read(p)
    old = "                tok = decoder.text(tok_ids, i)"
    new = '                tok = "When we think"  # MUT_FAKE_TOKEN'
    assert old in s, "M4 anchor not found"
    write(p, s.replace(old, new, 1))
    return p


def m5(s):
    """熵改成合成 runner 的 sin 公式。"""
    p = RUNNER
    s = read(p)
    old = "                    ent = float(-(nz * np.log(nz)).sum())"
    new = "                    ent = 1.5 + 0.3 * math.sin(i * 0.5)  # MUT_SIN_ENTROPY"
    assert old in s, "M5 anchor not found"
    write(p, s.replace(old, new, 1))
    return p


def m6(s):
    """server 不再从 runner 取层列表。"""
    p = SRV
    s = read(p)
    old = """            layers=list(
                getattr(state, "available_layers", None)
                or getattr(state.runner, "available_layers", None)
                or []
            ),"""
    new = "            layers=[],  # MUT_NO_LAYER_LIST"
    assert old in s, "M6 anchor not found in server.py"
    write(p, s.replace(old, new, 1))
    return p


MUTS = {"M1": m1, "M2": m2, "M3": m3, "M4": m4, "M5": m5, "M6": m6}

if __name__ == "__main__":
    which = sys.argv[1]
    if which not in MUTS:
        print("unknown", which)
        sys.exit(2)
    print("  applied", which, "->", MUTS[which](None))
