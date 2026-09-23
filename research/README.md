# Research

The evidence behind the positioning in the [README](../README.md): why this tool exists, what
the ecosystem already covers, and what adoption would have to look like for the effort to be
worth it.

It is not product documentation. For the formats and the hash, read [`spec/`](../spec/). For how
to use the tool, read the [README](../README.md).

| Document | Question it answers |
|---|---|
| [01 - problem](01-problem.md) | Which failures in retrieval evaluation are real, measurable and currently unreported |
| [02 - market gap](02-market-gap.md) | What already exists, what is genuinely missing, and what the evidence grade is for each claim |
| [03 - impact](03-impact.md) | What adoption would look like, how it is meant to happen, and what would prove it wrong |

## Method and limits

- **One date.** Registry queries, star counts and repository status were pulled from the npm
  registry and the GitHub API on **2026-09-22**. Every number is a reading from that date.
- **Primary sources.** Comparison articles were not used for numbers. Where a figure comes from
  practitioner reporting rather than an audited study, it is labeled as such.
- **Claims carry a grade.** [02](02-market-gap.md) grades every gap claim as VERIFIED,
  CORROBORATED or FALSIFIED, including the two claims this research falsified against an earlier
  draft of its own thesis.
- **Evidence ages.** Issues cited as live evidence may since have been closed. A closed issue
  still documents that the problem was voiced; it does not prove the problem is open today.

Earlier drafts of this research covered a broader library under the working name `open-rag`, and
included architecture and connector designs that are out of scope for `retrieval-eval`. They were
removed rather than kept as noise. Their conclusions, and the reason the scope narrowed, are in
[02](02-market-gap.md) section 5.
