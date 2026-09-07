#!/usr/bin/env bash
set -euo pipefail

python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m py_compile scripts/upstream.py
bash -n scripts/build-deb.sh scripts/build-rpm.sh scripts/build-all.sh scripts/test.sh

latest=$(python3 scripts/upstream.py latest \
    --input tests/fixtures/index.html \
    --index https://example.invalid/workbuddy/)
python3 -c 'import json,sys; data=json.loads(sys.argv[1]); assert data["version"] == "5.4.5"' "$latest"

echo "All tests passed."

