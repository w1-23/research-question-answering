# Host capabilities

Load `SKILL.md` through the host's normal Skill discovery. The host agent chooses which subgoal needs research, whether existing evidence suffices, and which routes are authorized. The helpers below are optional Python functions. For one research round, use these helpers or the host's direct tools for discovery and selected reads, never both as duplicate calls.

| Helper | Input and result |
| --- | --- |
| `await discover(query, routes, *, reuse=None, limit=4, timeout=10)` | `routes` maps the requested `local` and/or `web` routes to async callbacks `(query, limit, timeout_seconds) -> Discovery`. Both callbacks can run concurrently. An empty mapping yields `{}`. `reuse` accepts a host-proven equivalent `Discovery` for a requested route; its callback is not invoked and its candidates are bounded by `limit`. A reused result for an unrequested route raises `ValueError`. |
| `await read_selected(candidate, callback, offset=0, max_chars=2000, timeout=10)` | Call an async `(candidate, offset, max_chars, timeout_seconds) -> ReadResult` once. The host supplies its local reader or selected-source web fetch or reader. Use `None` if that capability is absent. |
| `citation_packet(records, selected_refs, max_chars=2000)` | Select `Evidence` objects in the caller's citation order from current permitted excerpts. Duplicate refs are collapsed. Supply the single excerpt adopted for each ref. Missing refs, conflicting excerpts for a selected ref and invalid evidence raise `ValueError`. This accepts existing evidence without discovery or read calls and does not create display labels. |

`Discovery` has a status, candidate tuple and optional public reason code. Use `hits`, `partial`, `empty`, `failed`, `unavailable`, `denied` or `timeout`. Use `empty` only when the requested work completed with no matches. A local candidate must carry its durable `source_ref` and `read_entry`. A web lead has a selected URL, or a stable reference and read entry for already stored web evidence. Keep previews small. Previews and generated summaries are discovery data.

`ReadResult` uses `ok`, `empty`, `failed`, `unavailable`, `denied`, `expired` or `timeout`. Supply one `Evidence` only with `ok`. For a verified redirect, put the original requested URL in `requested_url` and the canonical source URL in `Evidence.url`. Binding the returned evidence to the selected tool call is the host's responsibility. The host may expose a verified, attributed verbatim Search snippet as `verbatim_snippet` if it persists that exact excerpt. A generated summary remains a lead.

`Evidence` preserves the host's `source_ref`, `origin`, `document_key`, `title`, `display_label`, `locator`, URL, `evidence_level`, `retrieved_at`, `query_ref`, `generation`, `read_entry`, and excerpt with offsets. The host supplies one exact authorized excerpt per response and preserves source identity on readback. The helpers allow passage, excerpt, abstract, verbatim snippet and full-text-source evidence levels with a bounded excerpt in each case. A local read must preserve the selected reference, read entry and supplied generation. The adapter verifies which ranges and provenance allow a citation. Claim relevance remains the host agent's judgment.

Bind callbacks to the current principal, request policy and experiment context. Apply effective access before each call or reuse, including urgent revocations. Preserve opaque nonsecret locator values and pass the original read entry for history restoration. The host enforces provider deadlines, cancellation, file access, network egress and artifact receipts. Use async callbacks that yield and honor cancellation. Track public status codes separately from diagnostics and credentials. Avoid fallback queries or provider changes inside the adaptation layer.

## Result roles

- A `Candidate` is a discovery lead. It is not evidence and must not become a citation by itself.
- `ReadResult.evidence` is a bounded, authorized excerpt delivered to the model. A preview or generated summary is not a citable excerpt.
- `citation_packet` returns the exact permitted records adopted by the answer, in caller order. Persist their stable `source_ref` values. The host resolves those refs through its source ledger and assigns any user-facing local/web numbering or bubble labels.
- Do not infer adopted evidence by array position, title similarity or a later provider search. A read with the wrong locator or identity may be retried at most once using the host's returned correction; otherwise keep the gap.

## Stopping and reuse

Reuse `Candidate` or `Evidence` data only when query purpose, source filters, source/file version, index generation, ranking parameters and current authorization still match. If an answer is already supported, do not call discovery again. Expand only for a new knowledge question or a named material gap, and keep the expansion to the most diagnostic one or few reads. A route that is disabled, denied, empty or failed is reported as such; do not substitute another provider silently or force route parity.

The host may satisfy an equivalent route with its existing cache. Equivalence includes query, input file identity, corpus filters, index generation, ranking parameters and current permissions within the same experiment context. Cached candidates still need the same evidence checks. For an old reference, resolve its exact original record or return `expired` or `denied`. Use separate new references for a new research round. The host owns file reads, Code execution and artifact publication when the user requests those capabilities.
