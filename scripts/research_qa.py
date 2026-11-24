"""Bounded operations over research capabilities already authorized by a host."""

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Literal

Route = Literal["local", "web"]
Status = Literal["hits", "partial", "empty", "failed", "unavailable", "denied", "timeout"]
_CITABLE_LEVELS = {"passage", "excerpt", "abstract", "verbatim_snippet", "fulltext"}
_FAILURES = {"failed", "unavailable", "denied", "timeout"}


@dataclass(frozen=True)
class Candidate:
    route: Route
    title: str
    preview: str = ""
    url: str = ""
    source_ref: str = ""
    document_key: str = ""
    display_label: str = ""
    locator: Mapping[str, object] = field(default_factory=dict)
    generation: str = ""
    read_entry: Mapping[str, str] = field(default_factory=dict)
    query_ref: str = ""


@dataclass(frozen=True)
class Evidence:
    source_ref: str
    origin: Literal["local", "web", "file"]
    evidence_level: str
    excerpt: str
    offset: int = 0
    next_offset: int | None = None
    title: str = ""
    document_key: str = ""
    display_label: str = ""
    locator: Mapping[str, object] = field(default_factory=dict)
    url: str = ""
    retrieved_at: str = ""
    query_ref: str = ""
    generation: str = ""
    read_entry: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Discovery:
    status: Status
    candidates: tuple[Candidate, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class ReadResult:
    status: Literal["ok", "empty", "failed", "unavailable", "denied", "expired", "timeout"]
    evidence: Evidence | None = None
    reason: str = ""
    requested_url: str = ""


Discover = Callable[[str, int, float], Awaitable[Discovery]]
Read = Callable[[Candidate, int, int, float], Awaitable[ReadResult]]


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_limit(count: int, maximum: int) -> None:
    if type(count) is not int or not 1 <= count <= maximum:
        raise ValueError(f"limit must be an integer between 1 and {maximum}")


def _check_timeout(timeout: float) -> None:
    if type(timeout) not in {int, float} or not 0 < timeout < float("inf"):
        raise ValueError("timeout must be a positive finite number of seconds")


def _valid_candidate(candidate: Candidate) -> bool:
    if not isinstance(candidate, Candidate):
        return False
    if candidate.route == "local":
        return _nonempty(candidate.source_ref) and bool(candidate.read_entry)
    return candidate.route == "web" and (_nonempty(candidate.url) or (
        _nonempty(candidate.source_ref) and bool(candidate.read_entry)))


def _bounded_discovery(route: Route, result: Discovery, limit: int) -> Discovery:
    if not isinstance(result, Discovery):
        return Discovery("failed", reason="invalid_discovery_result")
    if result.status in _FAILURES | {"empty"} and not result.candidates:
        return result
    candidates = result.candidates[:limit]
    if (result.status == "partial" or (result.status == "hits" and candidates)) and all(
        _valid_candidate(item) and item.route == route for item in candidates
    ):
        bounded = tuple(replace(item, preview=item.preview[:600]) for item in candidates)
        return replace(result, candidates=bounded)
    return Discovery("failed", reason="invalid_discovery_result")


async def _discover_route(route: Route, call: Discover | None, query: str,
                          limit: int, timeout: float) -> Discovery:
    if call is None:
        return Discovery("unavailable", reason="capability_missing")
    try:
        async with asyncio.timeout(timeout):
            result = await call(query, limit, timeout)
        return _bounded_discovery(route, result, limit)
    except TimeoutError:
        return Discovery("timeout", reason="deadline")
    except Exception:
        return Discovery("failed", reason="capability_error")


async def discover(query: str, routes: Mapping[Route, Discover | None], *,
                   reuse: Mapping[Route, Discovery] | None = None,
                   limit: int = 4, timeout: float = 10.0) -> dict[Route, Discovery]:
    """Run each selected route once, preferring host-proven equivalent results."""
    _check_limit(limit, 12)
    _check_timeout(timeout)
    entries = tuple(routes.items())
    if any(route not in {"local", "web"} for route, _ in entries):
        raise ValueError("unknown discovery route")
    if reuse is not None and not isinstance(reuse, Mapping):
        raise ValueError("reuse must map routes to discoveries")
    reused_entries = tuple((reuse or {}).items())
    if any(route not in {"local", "web"} for route, _ in reused_entries):
        raise ValueError("unknown reused route")
    requested = {route for route, _ in entries}
    if any(route not in requested for route, _ in reused_entries):
        raise ValueError("reused route was not requested")
    if entries and not _nonempty(query):
        raise ValueError("query must be nonempty for discovery")
    reused = {route: _bounded_discovery(route, result, limit)
              for route, result in reused_entries}
    pending = tuple((route, call) for route, call in entries if route not in reused)
    results = await asyncio.gather(*(
        _discover_route(route, call, query, limit, timeout) for route, call in pending
    ))
    combined = dict(reused)
    combined.update({route: result for (route, _), result in zip(pending, results)})
    return {route: combined[route] for route, _ in entries}


def _valid_evidence(evidence: Evidence, max_chars: int) -> bool:
    return (
        _nonempty(evidence.source_ref)
        and evidence.origin in {"local", "web", "file"}
        and evidence.evidence_level in _CITABLE_LEVELS
        and _nonempty(evidence.excerpt)
        and len(evidence.excerpt) <= max_chars
        and type(evidence.offset) is int and evidence.offset >= 0
        and (evidence.next_offset is None or (
            type(evidence.next_offset) is int and evidence.next_offset > evidence.offset
        ))
        and (evidence.origin != "local" or bool(evidence.read_entry))
        and (evidence.origin != "web" or _nonempty(evidence.url))
    )


def _matches_selection(candidate: Candidate, result: ReadResult, evidence: Evidence) -> bool:
    if evidence.origin != candidate.route:
        return False
    if candidate.source_ref and candidate.source_ref != evidence.source_ref:
        return False
    if candidate.read_entry and candidate.read_entry != evidence.read_entry:
        return False
    if candidate.generation and candidate.generation != evidence.generation:
        return False
    return not candidate.url or candidate.url in {evidence.url, result.requested_url}


async def read_selected(candidate: Candidate, call: Read | None, *, offset: int = 0,
                        max_chars: int = 2000, timeout: float = 10.0) -> ReadResult:
    """Ask the host for one bounded read or fetch of the caller's selected candidate."""
    _check_limit(max_chars, 6000)
    _check_timeout(timeout)
    if type(offset) is not int or offset < 0:
        raise ValueError("offset must be a nonnegative integer")
    if not _valid_candidate(candidate):
        raise ValueError("candidate lacks a usable selection locator")
    if call is None:
        return ReadResult("unavailable", reason="capability_missing")
    try:
        async with asyncio.timeout(timeout):
            result = await call(candidate, offset, max_chars, timeout)
        if not isinstance(result, ReadResult):
            return ReadResult("failed", reason="invalid_evidence_result")
        evidence = result.evidence
        if result.status in _FAILURES | {"empty", "expired"} and evidence is None:
            return result
        if (result.status == "ok" and isinstance(evidence, Evidence)
                and _valid_evidence(evidence, max_chars) and evidence.offset == offset
                and _matches_selection(candidate, result, evidence)):
            return result
    except TimeoutError:
        return ReadResult("timeout", reason="deadline")
    except Exception:
        return ReadResult("failed", reason="capability_error")
    return ReadResult("failed", reason="invalid_evidence_result")


def citation_packet(records: Iterable[Evidence], selected_refs: Iterable[str], *,
                    max_chars: int = 2000) -> tuple[Evidence, ...]:
    """Return adopted records in caller order without creating display labels.

    The host owns user-facing local/web numbering. Each returned ``source_ref`` is
    the stable evidence identity to persist and use for that display projection.
    """
    _check_limit(max_chars, 6000)
    if isinstance(selected_refs, str):
        raise ValueError("selected_refs must be a sequence of references")
    refs = dict.fromkeys(selected_refs)
    by_ref: dict[str, Evidence] = {}
    for record in records:
        if not isinstance(record, Evidence):
            raise ValueError("citation records must be Evidence instances")
        ref = record.source_ref
        if ref not in refs:
            continue
        if not _valid_evidence(record, max_chars):
            raise ValueError("selected reference does not identify a permitted bounded excerpt")
        if ref in by_ref and by_ref[ref] != record:
            raise ValueError("selected reference has conflicting evidence records")
        by_ref[ref] = record
    if refs.keys() - by_ref.keys():
        raise ValueError("selected reference is absent from the supplied evidence")
    return tuple(by_ref[ref] for ref in refs)
