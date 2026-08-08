# W2 ChatGPT Review Receipt

```text
AUTHORITY = W2_CHATGPT_REVIEW_RECEIPT_LATEST
STATUS = NO_COMPLETED_AUTOMATED_REVIEW_YET
LAST_REVIEWED_IMPLEMENTATION_HEAD = NONE
LAST_REVIEWED_CODEX_RECEIPT_CONTEXT_SHA = NONE
LAST_REVIEW_RESULT = NONE
LAST_REVIEW_GATE = NONE
```

This file is maintained by the independent ChatGPT review workflow.

Its purpose is to prevent duplicate automatic reviews and duplicate notifications for the same exact implementation head / Codex completion receipt.

A completed automated review should record at minimum:

```text
REVIEWED_AT
REVIEWED_IMPLEMENTATION_HEAD
REVIEWED_PR
REVIEWED_CONTEXT_SHA
REVIEWED_CODEX_RECEIPT_IDENTITY
ACCEPTANCE_AUTHORITY
INDEPENDENT_REVIEW_RESULT = PASS | CHANGES_REQUIRED | BLOCKED
FINDINGS
CI_EVIDENCE
REPOSITORY_HYGIENE_EVIDENCE
CONTEXT_UPDATE_COMMIT_IF_ANY
NEXT_GATE
```

Codex must not edit this file as proof of its own completion.
