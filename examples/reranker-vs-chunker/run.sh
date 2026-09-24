#!/usr/bin/env bash
# Localize a retrieval failure before changing anything.
#
#   ./run.sh

cd "$(dirname "$0")"
source ../cli.sh

echo
echo "1. The number someone reported: recall@5 is poor."
step score --judgments judgments.jsonl --run hits.jsonl -k 5

echo
echo "2. The same run, same labels, wider cutoff."
step score --judgments judgments.jsonl --run hits.jsonl -k 20

echo
echo "3. Rerank the candidates you already had. Nothing else changed."
step score --judgments judgments.jsonl --run hits-reranked.jsonl -k 5

echo
echo "Retrieval was never the problem. Ranking was."
