import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import AsyncMock

from examples.web_only_host import RECORD as WEB_EVIDENCE
from examples.web_only_host import run as web_only_example
from scripts.research_qa import Candidate, Discovery, Evidence, ReadResult, citation_packet, discover, read_selected

QUERY = "Which observation supports this explanation?"
BASE = Candidate(
    route="local",
    title="Synthetic base record",
    source_ref="ev:base-v2",
    document_key="base-report",
    generation="base:index-v2",
    read_entry={"candidate_id": "ev:base-v2", "turn_id": "old-turn", "generation": "base:index-v2"},
    locator={"corpus_id": "base", "chunk_id": "p2", "index_generation": "base:index-v2"},
    query_ref="query:old",
)
SHARED = replace(
    BASE,
    title="Synthetic shared record",
    source_ref="ev:shared-v8",
    document_key="shared-report",
    generation="shared:index-v8",
    read_entry={"candidate_id": "ev:shared-v8", "turn_id": "old-turn", "generation": "shared:index-v8"},
    locator={"corpus_id": "shared", "chunk_id": "p3", "index_generation": "shared:index-v8"},
)
WEB = Candidate("web", WEB_EVIDENCE.title, url=WEB_EVIDENCE.url)


def local_evidence(candidate):
    return Evidence(
        candidate.source_ref, "local", "passage", "The larger surface cooled faster.",
        title=candidate.title, document_key=candidate.document_key, locator=candidate.locator,
        query_ref=candidate.query_ref, generation=candidate.generation, read_entry=candidate.read_entry,
    )


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_professional_question_runs_both_routes_in_parallel_once(self):
        local_started = asyncio.Event()
        web_started = asyncio.Event()

        async def local(query, limit, timeout):
            local_started.set()
            await web_started.wait()
            return Discovery("hits", (BASE, SHARED))

        async def web(query, limit, timeout):
            web_started.set()
            await local_started.wait()
            return Discovery("hits", (replace(WEB, preview="x" * 1000), WEB, WEB))

        local_call = AsyncMock(side_effect=local)
        web_call = AsyncMock(side_effect=web)
        result = await discover(QUERY, {"local": local_call, "web": web_call}, limit=2, timeout=1)
        self.assertEqual(result["local"].candidates, (BASE, SHARED))
        self.assertEqual(len(result["web"].candidates), 2)
        self.assertEqual(len(result["web"].candidates[0].preview), 600)
        local_call.assert_awaited_once_with(QUERY, 2, 1)
        web_call.assert_awaited_once_with(QUERY, 2, 1)

    async def test_local_zero_hits_can_use_one_selected_web_excerpt(self):
        local = AsyncMock(return_value=Discovery("empty"))
        web = AsyncMock(return_value=Discovery("hits", (WEB,)))
        fetch = AsyncMock(return_value=ReadResult("ok", WEB_EVIDENCE))
        result = await discover(QUERY, {"local": local, "web": web})
        self.assertEqual(result["local"].status, "empty")
        fetch.assert_not_awaited()
        read = await read_selected(result["web"].candidates[0], fetch)
        self.assertEqual(citation_packet([read.evidence], [WEB_EVIDENCE.source_ref]), (WEB_EVIDENCE,))
        local.assert_awaited_once()
        web.assert_awaited_once()
        fetch.assert_awaited_once_with(WEB, 0, 2000, 10.0)

    async def test_host_omits_research_for_translation_and_attachment_plot(self):
        available_search = AsyncMock()
        for subgoal in ("Translate this pathology paragraph", "Plot this supplied qPCR table"):
            with self.subTest(subgoal=subgoal):
                self.assertEqual(await discover(subgoal, {}), {})
        mixed = await discover(QUERY, {"local": None, "web": available_search})
        self.assertEqual(mixed["local"].status, "unavailable")
        available_search.assert_awaited_once_with(QUERY, 4, 10.0)

    async def test_routes_preserve_denied_partial_and_unavailable(self):
        local = AsyncMock(return_value=Discovery("partial", reason="shared_index_unavailable"))
        web = AsyncMock(return_value=Discovery("denied", reason="network_disabled"))
        result = await discover(QUERY, {"local": local, "web": web})
        self.assertEqual(result["local"], Discovery("partial", reason="shared_index_unavailable"))
        self.assertEqual(result["web"].status, "denied")
        self.assertEqual((await discover(QUERY, {"local": None}))["local"].status, "unavailable")

    async def test_timeout_and_failure_are_distinct_and_are_not_retried(self):
        async def wait_for_timeout(query, limit, timeout):
            await asyncio.Future()

        local = AsyncMock(side_effect=wait_for_timeout)
        web = AsyncMock(side_effect=RuntimeError("private provider diagnostic"))
        result = await discover(QUERY, {"local": local, "web": web}, timeout=0.02)
        self.assertEqual(result["local"], Discovery("timeout", reason="deadline"))
        self.assertEqual(result["web"], Discovery("failed", reason="capability_error"))
        local.assert_awaited_once()
        web.assert_awaited_once()

    async def test_host_cancellation_propagates(self):
        started = asyncio.Event()

        async def local(query, limit, timeout):
            started.set()
            await asyncio.Future()

        task = asyncio.create_task(discover(QUERY, {"local": local}))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_failed_or_unanchored_results_provide_no_evidence(self):
        local = AsyncMock(return_value=Discovery("hits", (Candidate("local", "No durable handle"),)))
        web = AsyncMock(return_value=Discovery("denied", (WEB,)))
        result = await discover(QUERY, {"local": local, "web": web})
        self.assertEqual(set(item.status for item in result.values()), {"failed"})
        self.assertFalse(any(item.candidates for item in result.values()))

    async def test_web_only_second_host_runs_same_core(self):
        report = await web_only_example()
        self.assertEqual(report["routes"], {"local": "unavailable", "web": "hits"})
        self.assertEqual(report["answer"], WEB_EVIDENCE.excerpt)
        self.assertEqual(report["sources"], [WEB_EVIDENCE.source_ref])


class ReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_read_preserves_identity_generation_and_offset(self):
        original = replace(local_evidence(SHARED), offset=10, next_offset=46)
        read = AsyncMock(return_value=ReadResult("ok", original))
        self.assertEqual(await read_selected(SHARED, read, offset=10, max_chars=100), ReadResult("ok", original))
        read.assert_awaited_once_with(SHARED, 10, 100, 10.0)
        for altered in (replace(original, generation="shared:index-v9"), replace(original, source_ref=BASE.source_ref),
                        replace(original, read_entry=BASE.read_entry), replace(original, offset=0)):
            read.return_value = ReadResult("ok", altered)
            with self.subTest(altered=altered):
                self.assertEqual((await read_selected(SHARED, read, offset=10)).status, "failed")

    async def test_web_read_requires_selected_url_or_verified_redirect_receipt(self):
        redirected = replace(WEB_EVIDENCE, url="https://example.invalid/canonical")
        fetch = AsyncMock(return_value=ReadResult("ok", redirected))
        self.assertEqual((await read_selected(WEB, fetch)).status, "failed")
        fetch.return_value = ReadResult("ok", redirected, requested_url=WEB.url)
        self.assertEqual((await read_selected(WEB, fetch)).evidence, redirected)

    async def test_selected_read_accepts_no_generated_summary_or_oversized_text(self):
        for invalid in (replace(WEB_EVIDENCE, evidence_level="generated_summary"),
                        replace(WEB_EVIDENCE, excerpt="x" * 101), replace(WEB_EVIDENCE, source_ref="")):
            fetch = AsyncMock(return_value=ReadResult("ok", invalid))
            result = await read_selected(WEB, fetch, max_chars=100)
            self.assertEqual(result, ReadResult("failed", reason="invalid_evidence_result"))

    async def test_expired_denied_and_missing_reads_are_explicit(self):
        for status in ("expired", "denied", "empty"):
            read = AsyncMock(return_value=ReadResult(status))
            self.assertEqual(await read_selected(BASE, read), ReadResult(status))
            read.assert_awaited_once()
        self.assertEqual((await read_selected(BASE, None)).status, "unavailable")

    async def test_read_times_out_once(self):
        async def slow_read(candidate, offset, max_chars, timeout):
            await asyncio.Future()

        read = AsyncMock(side_effect=slow_read)
        self.assertEqual((await read_selected(BASE, read, timeout=0.02)).status, "timeout")
        read.assert_awaited_once()


class CitationTests(unittest.TestCase):
    def test_existing_permitted_evidence_projects_only_selected_refs(self):
        base = local_evidence(BASE)
        shared = local_evidence(SHARED)
        records = (base, shared, WEB_EVIDENCE)
        packet = citation_packet(records, (WEB_EVIDENCE.source_ref, shared.source_ref, WEB_EVIDENCE.source_ref))
        self.assertEqual(packet, (WEB_EVIDENCE, shared))
        self.assertEqual(citation_packet(records, []), ())
        self.assertEqual(packet[1].read_entry, SHARED.read_entry)
        self.assertEqual(packet[1].locator, SHARED.locator)

    def test_candidates_missing_refs_and_conflicts_cannot_be_cited(self):
        shared = local_evidence(SHARED)
        for records, ref in (([SHARED], SHARED.source_ref), ([shared], BASE.source_ref),
                             ([shared, replace(shared, offset=4)], shared.source_ref),
                             ([replace(shared, evidence_level="summary")], shared.source_ref)):
            with self.subTest(records=records, ref=ref), self.assertRaises(ValueError):
                citation_packet(records, [ref])

    def test_stable_local_record_can_be_restored_in_a_new_process(self):
        child = '''\
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path
from scripts.research_qa import Candidate, Evidence, ReadResult, citation_packet, read_selected

candidate = Candidate(**json.loads(sys.stdin.read()))
record = Evidence(**json.loads(Path(sys.argv[1]).read_text()))

async def read(selected, offset, max_chars, timeout):
    if selected.read_entry != record.read_entry:
        return ReadResult("expired")
    return ReadResult("ok", record)

result = asyncio.run(read_selected(candidate, read))
packet = citation_packet([result.evidence], [candidate.source_ref])
print(json.dumps(asdict(packet[0])))
'''
        expected = local_evidence(SHARED)
        with tempfile.TemporaryDirectory() as directory:
            stored = Path(directory) / "host_fixture.json"
            stored.write_text(json.dumps(asdict(expected)), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-c", child, str(stored)], input=json.dumps(asdict(SHARED)),
                check=True, capture_output=True, text=True, timeout=5,
            )
        self.assertEqual(json.loads(result.stdout), asdict(expected))
