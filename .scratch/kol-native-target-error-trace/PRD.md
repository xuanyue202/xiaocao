# Preserve native input targeting failures

Status: Complete

The Oct20 morning capture trace retained complete tool calls but exported no
tool error for an actual invalid-element-ID response and an app-target-change
interruption. This obscures targeting failures in the WeChat protection audit.

Recognize these two observed native tool responses using stable, credential-free
codes. Preserve actual call IDs, timing bounds and hashes. Do not label them as
WeChat protection, infer a cause, alter native actions, or classify quoted
checkpoint instructions as observations. Add focused regressions and re-export
the same original capture's evidence without repeating native operations.

Validation: 16 focused trace tests pass; independent Standards and Spec reviews
against baseline `5460f0c94b056af5ebd64037b8e96e8d31667dc5` each found zero
issues. The same original Oct20 morning journal was re-exported: both targeting
responses are recorded as tool errors, with no protection/cause assertion.
