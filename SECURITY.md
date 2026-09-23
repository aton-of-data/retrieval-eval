# Security

## Scope

`retrieval-eval` reads local files, computes hashes, and writes local files. It makes **no
network requests**, executes nothing from its inputs, and has **zero runtime dependencies** in
both packages, which is most of the security story.

The realistic risks are therefore:

- a malicious `judgments.jsonl`, `corpus.json` or report causing excessive memory use;
- a path in `--out` or `drift --fix` overwriting something it should not.

`drift --fix` rewrites the judgments file you pass it, in place. It is the only command that
writes to an input.

## Reporting

Please report anything you believe is a vulnerability privately through GitHub's
[security advisory](https://github.com/aton-of-data/retrieval-eval/security/advisories/new) form rather
than a public issue. A reply should come within a week.

## Not a security tool

Passing this tool's gates says your retrieval ranks judged documents well. It says nothing about
prompt injection through retrieved content, cross-tenant leakage, or any other property of the
system you built around it. Do not present a green `retrieval-eval` run as a security result.
