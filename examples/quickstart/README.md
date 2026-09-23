# Quickstart: watch a golden set decay

A 40-line demo of the failure this tool exists to catch. No API key, no vector database, no
network.

```bash
node demo.mjs      # TypeScript / Node
python3 demo.py    # Python
```

## What it does

1. Takes a tiny 3-document corpus and chunks it at **512 tokens**.
2. Writes 4 relevance judgments against those chunks, as a human labeler would.
3. Scores a retrieval run. `recall@3` looks fine.
4. **Re-chunks the same corpus at 384 tokens**, the way you would after reading a blog post
   saying smaller chunks retrieve better.
5. Scores again. The number moves.
6. Runs `drift` and shows that most of the movement was your labels decaying, not your retriever
   changing.

## The point

Step 5 is what every team does. Step 6 is what no other tool can do.

Both scripts print the same numbers, because both implementations read the same spec.
