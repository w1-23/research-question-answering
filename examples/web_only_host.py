"""A standalone web-only replay host with an explicitly permitted source."""

import asyncio
import json

from scripts.research_qa import Candidate, Discovery, Evidence, ReadResult, citation_packet, discover, read_selected

URL = "https://example.invalid/heat-transfer"
RECORD = Evidence(
    source_ref="fixture:web:heat-transfer-v1",
    origin="web",
    evidence_level="excerpt",
    excerpt="In the demonstration, increasing the surface area increased the cooling rate.",
    title="Synthetic Heat Transfer Demonstration",
    url=URL,
    locator={"section": "Results"},
)


async def search(query, limit, timeout):
    return Discovery("hits", (Candidate("web", RECORD.title, url=URL),))


async def read(candidate, offset, max_chars, timeout):
    if candidate.url != URL:
        return ReadResult("denied", reason="outside_replay_scope")
    if offset or len(RECORD.excerpt) > max_chars:
        return ReadResult("unavailable", reason="excerpt_range_unavailable")
    return ReadResult("ok", RECORD)


async def run():
    discovery = await discover("How did surface area affect the measured cooling rate?", {"local": None, "web": search})
    selected = await read_selected(discovery["web"].candidates[0], read)
    if selected.evidence is None:
        raise RuntimeError(f"expected an authorized fixture excerpt, got {selected.status}")
    citations = citation_packet([selected.evidence], [RECORD.source_ref])
    return {"routes": {route: result.status for route, result in discovery.items()},
            "answer": citations[0].excerpt, "sources": [record.source_ref for record in citations]}


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=2))
