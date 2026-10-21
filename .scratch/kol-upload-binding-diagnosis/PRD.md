# Diagnose exact uploader binding loss without assuming context destruction

Baselinec2b35aa714a6c41c22002e1c7de2ea38e94efb8b. Exact retained upload inspect
reports no matching destination page. A fresh separate Browser-session cloud
read returns zero exact target but does not prove the original uploader object
was destroyed. The adapter may still see a Netdisk page at another folder.

On the existing inspect-only missing-binding branch only, emit bounded Netdisk
page metadata from the already-performed page.tabs result: page id, surface enum,
same-target folder boolean, count/max10. No title/rawURL/query/hash/folder value,
other-domain pages, credentials, hidden app state, navigation or inputs. This
supports same-page diagnosis and cannot authorize retry, reattachment or success.

Actual diagnostic found0 Netdisk pages in the retained adapter context; the
separate Browser session recovered an authenticated portal with0 exact matches,
but cannot prove uploader queue preservation. Provide restore-readback-only on
the existing adapter: select the exact existing page or navigate only if missing,
authenticate and scan exact cloud target, then return before any activation,
file marking or attachment. Reject combined inspect/recovery/activate flags and
ambiguous existing targets. Refuse navigation when any other Netdisk or nonblank
page remains, preserving a possible uploader at another folder and unrelated
pages. Diagnostic path is /disk/main or other, never a share token. It cannot reconstruct or accept the old queue or
authorize resubmission. Existing monitor/claim remains, awaiting explicit human
decision for an uncertain-effect recovery. This is not upload byte resume.
