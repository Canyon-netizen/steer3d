"""LTV 的句子对表 —— 方法里**人挑**的那一部分。

⚠⚠ 预登记表 `LTV_PREREG.md` §4 已经写明：**$S_k$ 是人挑的，与已有的措辞改写表同源，
   有拟合风险。这个风险消不掉**，只能靠 G-c 的留出集与如实标注限制。

⇒ 所以这个文件的定位必须说清楚：它**不是**数据，是**假设**。
   它的作用是让「名字」变成一句**可以被人核对的两段原文**，而不是一个模型给我的标签。
   如果这两句话之间的差别恰好就是 v 的大部分，那更可能是**我按 v 挑的句子**
   （循环），而不是模型里真有这个概念 —— 这是这套方法已知的、写在预登记表里的软肋。

## 每一对的形状

`S` 与 `S'` **意思相同、说法不同**。差分 $\\bar r(S) - \\bar r(S'_k)$
因此测的是「说法」而不是「内容」。

## 为什么是这 12 对

覆盖三条轴上已有实测的方向（confidence / reasoning 早晚 / creativity），
外加三条**故意放进去的反例**（长度、第一人称、语域）——
它们与 steering 无关，是用来当**负对照**的：如果稀疏分解把反例也吸进去，
说明拟合在吸收任何能解释方差的东西，而不是在找语义。
"""

# key -> (标签, S, S')
#   标签会原样印在产物与页面上，读者可以拿它去核对那两句话。
SENTENCE_PAIRS = [
    ("confident",   "This part of the reasoning is correct, so we can build on it.",
                    "This part of the reasoning is correct."),
    ("hesitant",    "I think this part of the reasoning might be correct.",
                    "This part of the reasoning is correct."),
    ("deliberate",  "Let us check this step carefully before moving on.",
                    "Let us check this step."),
    ("brisk",       "Moving on.", "Let us carefully and thoroughly verify this "
                                    "step before moving on to anything else."),
    ("early_setup", "First we set up the variables from the problem statement.",
                    "We now begin the standard initial setup, introducing the "
                    "quantities named in the statement one at a time."),
    ("late_chain",  "Combining these gives the requested value.",
                    "Having carried the accumulated chain forward through every "
                    "stage, we arrive at the single requested value."),
    ("exploratory", "Perhaps a different approach would also work here.",
                    "The value computed here may be checked against an "
                    "alternative route through the same identity."),
    ("verify_mode", "We should double-check this result.",
                    "The reasoning that produced this value should be verified "
                    "once more before it is reported as final."),
    # ---- 以下三条是**负对照**：与 steering 无关，只是写法不同 ----
    ("len_control", "The answer is two.",
                    "Considering the preceding identity together with the "
                    "constraints that were established at the outset of the "
                    "solution, the answer is two."),
    ("person_ctrl", "We compute the sum of the two terms.",
                    "I compute the sum of the two terms."),
    ("register_ct", "Please note that the result follows from the identity.",
                    "Yo, that number just falls straight out of the identity, "
                    "no big deal."),
]

# 负对照的 key —— 判据必须能把它们单独拎出来看。
NEGATIVE_CONTROL_KEYS = ("len_control", "person_ctrl", "register_ct")

# 注入层。层不是按方差选的，是按**可动性**选的（预登记表 §1③）：
# L22 实测推不动（3 个方向 × L22 全部 0/4 翻盘），所以候选层里没有它。
TARGET_LAYERS = (14, 20)