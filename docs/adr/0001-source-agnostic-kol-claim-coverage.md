---
status: accepted
---

# Separate KOL claim extraction from coverage auditing

All KOL sources and both single-item and batch runs use one source-agnostic investment-information contract. Each complete source is first converted into an evidence-bound investment-decision claim inventory without summarization, truth judgment, user filtering, or execution filtering; an independent semantic coverage audit then rereads the complete source and fails visibly on suspected omissions, incorrect merges, or role errors before any reader output or side effect. Keywords and deterministic patterns may raise additional warnings but cannot define importance or prove completeness, because optimizing them for known examples would miss unknown but decision-relevant signals.
