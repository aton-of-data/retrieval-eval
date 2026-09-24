#!/usr/bin/env bash
# The whole story of this example, end to end. Nothing here writes to the committed data:
# the --fix step works on a copy in a temporary directory.
#
#   ./run.sh

cd "$(dirname "$0")"
source ../cli.sh

echo
echo "1. Is the judgment set sound before we compute anything from it?"
step validate --judgments judgments.jsonl

echo
echo "2. Score this week's run. The mean passes. One query class does not."
step score --judgments judgments.jsonl --run hits.jsonl -k 3 \
  --gate "recall@3:0.7" \
  --gate "worst-stratum:recall@3:0.6" || true

echo
echo "3. The same run against last week's report, which is what CI would do."
step score --judgments judgments.jsonl --run hits.jsonl -k 3 \
  --baseline baseline.json \
  --gate "recall@3:-0.02" || true

echo
echo "4. Someone raises the chunk size. Now ask what that did to the labels."
step drift --judgments judgments.jsonl --corpus corpus-after-rechunk.json || true

echo
echo "5. Re-anchor the recoverable labels, on a copy."
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
cp judgments.jsonl "$scratch/judgments.jsonl"
step drift --judgments "$scratch/judgments.jsonl" --corpus corpus-after-rechunk.json --fix || true

echo
echo "6. The same labels now describe the new corpus, so a metric is comparable again."
step drift --judgments "$scratch/judgments.jsonl" --corpus corpus-after-rechunk.json

echo
echo "Done. Step 2 is the failure a mean hides. Step 4 is the one nothing else reports."
