---
name: research-question-answering
description: Answer research questions using authorized local and web evidence, targeted source excerpts, and traceable citations. Use for questions about scientific mechanisms, empirical claims, and research methods that need outside knowledge. For mixed tasks, use it on the knowledge question only.
license: MIT
compatibility: Python 3.11 or newer for the optional helpers. Source access and citation history depend on host capabilities.
---

# Research Question Answering

1. Identify the knowledge subgoal. Translation, rewriting, format conversion, calculation and plotting of supplied data use their own capabilities. The same scientific terms do not make those tasks research questions. In a mixed request, research only the subgoal that needs outside knowledge.
2. Start with authorized evidence already available for that subgoal. Reuse adequate excerpts and host-proven equivalent discovery results directly. Equivalence requires the same query, source scope, file identity, index generation, ranking and effective permissions. If the evidence is sufficient, answer and stop without another discovery call.
3. For an unresolved knowledge subgoal, use the host-selected routes. When both local and web routes are authorized, make one bounded attempt on each, concurrently when possible. Use one focused query and a small candidate limit. Keep empty, denied, unavailable, partial and failed outcomes distinct. Do not repeat the round with synonyms or another route merely to seek agreement, and do not force both routes to produce a source.
4. Generated summaries and previews are leads only. An authorized verbatim snippet tied to stable evidence may support a claim within its exact span. If the answer still lacks a material fact, name that fact and read only the best one or a few candidates. Use the original read entry for local evidence or fetch the selected web page when more text is necessary. If the first read identifies a bad locator, make at most one corrected read with the host-returned entry; otherwise record the gap rather than paging through history to reconstruct identity.
5. Answer from the permitted excerpts actually adopted by the answer. Distinguish observation, interpretation, uncertainty and coverage gaps. Do not invent URLs or claim route coverage that did not occur. An expired or revoked reference remains unresolved unless the host starts a separately authorized discovery round.
6. Return stable evidence IDs to the host. The package must not create user-facing local/web citation labels or renumber an answer; candidate order, delivered excerpts and adopted references remain separate roles, and the host alone projects display bubbles from those stable IDs.

The optional Python helpers in [scripts/research_qa.py](scripts/research_qa.py) run one bounded discovery round, request a selected excerpt, and project adopted evidence. Use these helpers or the host's direct tools for a given round, never both as duplicate discovery. See [the host contract](references/host-capabilities.md) for callbacks, reuse and evidence identities.
