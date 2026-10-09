#!/bin/sh
set -eu
python3 /lab/portal.py &
exec bun src/index.ts
