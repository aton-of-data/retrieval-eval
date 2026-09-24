#!/usr/bin/env bash
# A public IR collection, into this format and back out again.
#
#   ./run.sh

cd "$(dirname "$0")"
source ../cli.sh

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

echo
echo "1. A BEIR-shaped qrels file becomes a judgment set."
step convert --qrels collection/qrels/test.tsv --to judgments > "$scratch/judgments.jsonl"
head -3 "$scratch/judgments.jsonl"

echo
echo "2. What does it say about itself?"
step validate --judgments "$scratch/judgments.jsonl" || true

echo
echo "3. Score a run against it, the same way you would score your own."
step score --judgments "$scratch/judgments.jsonl" --run hits.jsonl -k 3

echo
echo "4. And back out, for trec_eval and anything else that reads qrels."
step convert --judgments "$scratch/judgments.jsonl" --to qrels | head -3
step convert --run hits.jsonl --to trec-run | head -3

echo
echo "Nothing was lost on the way in, and nothing is locked in on the way out."
