#!/usr/bin/env bash
# Graded labels, and what changes when you decide what "relevant" means.
#
#   ./run.sh

cd "$(dirname "$0")"
source ../cli.sh

echo
echo "1. Everything a human marked useful counts (--threshold 1, the default)."
step score --judgments judgments.jsonl --run hits.jsonl -k 3

echo
echo "2. Only chunks that actually answer the question count (--threshold 2)."
step score --judgments judgments.jsonl --run hits.jsonl -k 3 --threshold 2

echo
echo "3. Gate on the stricter reading, where it matters."
step score --judgments judgments.jsonl --run hits.jsonl -k 3 --threshold 2 \
  --gate "recall@3:0.9" || true

echo
echo "Same labels, same run. The grade you gate on is a product decision."
