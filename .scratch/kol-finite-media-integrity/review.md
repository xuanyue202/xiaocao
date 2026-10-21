# Review and validation

Baseline e81381fc31efd7aa437f6462ceabe5ae220eebe8; scoped finite-media integrity change.

- Initial regression: 7 failures, 2 passes. The exact observed 37.443113-second deficit was accepted with and without cached validation; missing/NaN/Infinity evidence also had unsafe paths.
- Independent Standards review: found missing/unknown media type could bypass HLS proof. Fixed to retain compatibility only for explicitly identified MP4; added four-type behavior cases.
- Independent Spec review: found downloaded reconciliation returned cached completion without probing. Fixed to revalidate offline and added a regression forbidding any cleaned-sniffer query.
- Both affected reviews: zero remaining actionable findings.
- Added first-mailbox boundary revalidation and a test that rejected media cannot invoke the exchange or consume original identity/claims.
- Rejection appends evidence and does not reset any capture/task/upload/cloud claim.
- 531 related tests passed (live capture, independent acceptance, WeChat subscription, daily coordinator/concurrency). This is code validation, not repaired media or Handoff.
- Actual original artifact revalidation rejects contract_error/compressed_media_duration_mismatch/compressed_capture. Original cloud upload is video_ready; mailbox exact GET is NOT_FOUND. No message sent.
- Same-item media recovery and true process-exit checkpoint resume are outstanding; no replacement task, native retry or upload resubmission is authorized by this validation fix.
