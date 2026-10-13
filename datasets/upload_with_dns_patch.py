"""Wrapper that runs ``upload_to_hf.py`` with a URL rewrite patch.

Why this exists
---------------
The HF mirror at ``hf-mirror.com`` has a bug in its LFS upload flow: the
``complete_multipart`` callback URL it returns contains ``hf-mirror.org`` —
a host that resolves to **no address**, so the handshake cannot connect.
The mirror is otherwise healthy: S3 multipart uploads succeed, the API
endpoints respond, only the *completion handshake* call to
``https://hf-mirror.org/api/complete_multipart?uploadId=...`` fails with
``[Errno -5] No address associated with hostname``.

⚠ **2026-10-14 更正本段的一句措辞**。原文写的是
「a domain that does not exist in public DNS (verified against 8.8.8.8: NXDOMAIN)」。
实测今天**复现不出那个 NXDOMAIN**：

    dig +short @8.8.8.8 hf-mirror.org     → 空（**没有 A 记录**）
    host hf-mirror.org                    → 只有 MX（route1/route2.mx.cloudflare.net）
    对照：host zzz-nonexistent-9f3a2b.invalid → NXDOMAIN（⚗ 说明解析器不是「什么都答」）

⇒ ⚠⚠ **结论没错，错的是归因**：该域名在 DNS 里**存在**（有 MX），
⚗⚠⚴ **只是没有 A 记录** ⇒ 所以 HTTPS 打不到它。
⚠⚠⚴⚠⚴ **判别式：「连不上」与「不存在」是两件事** ——
⚗⚠⚴ 前者的修法是改主机名（本文件做的事），⚗⚠⚴ **后者的修法完全不同**。
⚠ 保留 MX 这一条观察，正是为了不让下一个人把它再当成「域名不存在」。
⚠ **要复核就跑上面那三行，并带上那个 `.invalid` 对照组** ——
⚠⚠⚠ 没有对照组的 DNS 查询**证明不了任何事**：一个「什么都答」的本地
⚠⚠⚠ sinkhole 会让「解析成功」和「解析失败」两个结论**长得一模一样**。

huggingface_hub's URL normaliser ``fix_hf_endpoint_in_url`` only rewrites the
default ``huggingface.co`` / ``hub-ci.huggingface.co`` hosts to the value of
``$HF_ENDPOINT``. It does not touch ``hf-mirror.org``, so the broken URL
slips through unchanged.

Workaround: monkey-patch ``fix_hf_endpoint_in_url`` so it also rewrites
``hf-mirror.org`` -> current ``HF_ENDPOINT`` (which is the value the user
already set to ``https://hf-mirror.com``). After the rewrite the completion
handshake lands back on the mirror's actual API and commits succeed.

Usage
-----
    python datasets/upload_with_dns_patch.py \\
        --repo-id Tensas/qwen3-1.7b-data \\
        --private

All other CLI / flags are passed through to ``upload_to_hf.py``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. URL rewrite patch
# ---------------------------------------------------------------------------

from huggingface_hub.utils import _http as _hfh_http
from huggingface_hub import constants as _hfh_constants

_MIRROR_ORG = "hf-mirror.org"

_orig_fix_hf_endpoint_in_url = _hfh_http.fix_hf_endpoint_in_url


def _patched_fix_hf_endpoint_in_url(url: str, endpoint: str | None) -> str:
    """Replace ``hf-mirror.org`` with the active HF_ENDPOINT before the
    default normalisation runs.

    The mirror returns ``https://hf-mirror.org/api/complete_multipart?...``
    as the completion callback. That host does not exist in DNS. We rewrite
    it to whatever $HF_ENDPOINT points at (i.e. the mirror itself,
    ``https://hf-mirror.com``), then fall through to the original logic
    which only touches ``huggingface.co`` / ``hub-ci.huggingface.co``.
    """
    if endpoint is None:
        endpoint = _hfh_constants.ENDPOINT
    if isinstance(url, str) and _MIRROR_ORG in url:
        url = url.replace(_MIRROR_ORG, endpoint.replace("https://", "").replace("http://", ""))
    return _orig_fix_hf_endpoint_in_url(url, endpoint)


_hfh_http.fix_hf_endpoint_in_url = _patched_fix_hf_endpoint_in_url  # type: ignore[assignment]

print(
    f"[url-patch] hf-mirror.org -> {os.environ.get('HF_ENDPOINT', _hfh_constants.ENDPOINT)}",
    file=sys.stderr,
)

# ---------------------------------------------------------------------------
# 2. Delegate to the real upload script
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).resolve().parent))
from upload_to_hf import main as _upload_main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(_upload_main(sys.argv[1:]))