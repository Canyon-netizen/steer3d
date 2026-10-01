#!/bin/bash
# Extract the inline <script> from index.html and run node --check on it.
# A missing `+` between two template literals is a SyntaxError that kills the
# whole classic script: every handler dies silently and the page renders as
# static markup. The browser suites report that as "element is null", which
# reads like a probe problem rather than a dead page.
set -e
cd "$(dirname "$0")/../.."
python3 - <<'PY'
import re
s = open('frontend/public/latent/index.html').read()
m = re.findall(r'<script>(.*?)</script>', s, re.S)
assert m, 'no inline script found'
open('.cache/divergence/extracted.js', 'w').write(m[-1])
print('extracted %d bytes' % len(m[-1]))
PY
node --check .cache/divergence/extracted.js && echo "JS 语法通过"
