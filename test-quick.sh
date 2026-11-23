#!/bin/sh
set -eu
cd "$(dirname "$0")"
for test_file in \
  phoneagent/tests/test_guards.py \
  phoneagent/tests/test_web.py \
  phoneagent/tests/test_loop.py \
  phoneagent/tests/test_ollama.py \
  phoneagent/tests/test_route.py \
  phoneagent/tests/test_brain.py
do
  printf '\n== %s ==\n' "$test_file"
  python3 "$test_file"
done
