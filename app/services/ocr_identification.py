import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.schemas.book import BookMetadata
from app.services.googlebooks import (
    GoogleBooksError,
    GoogleBooksNotFoundError,
    GoogleBooksService,
)
from app.services.isbn import InvalidISBNError, normalize_isbn
from app.services.openlibrary import BookNotFoundError, OpenLibraryError, OpenLibraryService
from app.services.ocr import OCRResult, ocr_image


_ISBN_PATTERN = re.compile(r"(?<!\d)(?:[0-9Xx][0-9Xx -]{8,16}[0-9Xx])(?!\d)")
_IGNORED_LINE_WORDS = {
    "edition",
    "library",
    "publisher",
    "press",
    "international",
    "copyright",
    "volume",
    "isbn",
}
_NON_AUTHOR_WORDS = _IGNORED_LINE_WORDS | {
    "approach",
    "design",
    "edition",
    "implementation",
    "included",
    "operating",
    "systems",
}
_TITLE_STOP_WORDS = _IGNORED_LINE_WORDS | {"book", "readers", "new", "the", "a", "an"}
_EDITION_PATTERN = re.compile(r"\b(?:\d{1,2}(?:st|nd|rd|th)?\s+edition|\d{1,2}(?:st|nd|rd|th)|edition)\b", re.IGNORECASE)


@dataclass(frozen=True)
class OCRSignals:
    title: str | None
    author: str | None
    isbns: list[str]
    confidence: float | None
    authors: list[str] = field(default_factory=list)
    subtitle: str | None = None
    edition: str | None = None
    queries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RankedBookCandidate:
    metadata: BookMetadata
    match_score: float
    evidence: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class OCRIdentificationResult:
    ocr: OCRResult
    signals: OCRSignals
    candidates: list[RankedBookCandidate]
    message: str | None


def _signal_lines(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        normalized = " ".join(line.split())
        words = re.findall(r"(?:[A-Za-z][A-Za-z'.-]*|\d+[A-Za-z]{0,3})", normalized)
        if len("".join(words)) < 3 or not words:
            continue
        lowered = {word.lower() for word in words}
        if lowered & _IGNORED_LINE_WORDS and len(words) <= 4:
            continue
        lines.append(normalized)
    return lines


def _extract_isbns(text: str) -> list[str]:
    values = []
    for match in _ISBN_PATTERN.finditer(text):
        try:
            isbn = normalize_isbn(match.group(0))
        except InvalidISBNError:
            continue
        if isbn not in values:
            values.append(isbn)
    return values


def _substantive_words(line: str) -> list[str]:
    words = re.findall(r"(?:[A-Za-z][A-Za-z'.-]*|\d+[A-Za-z]{0,3})", line)
    return [word for word in words if len(re.sub(r"[^A-Za-z]", "", word)) >= 3]


def _line_confidence(line: str, result: OCRResult) -> float:
    line_tokens = _tokens(line)
    matching = [
        block.confidence
        for block in result.blocks
        if block.confidence is not None and line_tokens & _tokens(block.text)
    ]
    return sum(matching) / len(matching) / 100 if matching else 0.0


def _is_author_line(line: str) -> bool:
    words = _substantive_words(line)
    lowered = {word.lower().strip(".,") for word in words}
    if lowered & (_NON_AUTHOR_WORDS | _TITLE_STOP_WORDS) or len(words) < 2:
        return False
    return all(any(character.isupper() for character in word) for word in words)


def _build_queries(title: str | None, authors: list[str], subtitle: str | None) -> list[str]:
    values = []
    if title and authors:
        values.extend(f"{title} {author}" for author in authors[:2])
    if authors:
        values.append(" ".join(authors[:2]))
    if title and subtitle:
        values.append(f"{title} {subtitle}")
    if title:
        values.append(title)
    return list(dict.fromkeys(value for value in values if value))


def extract_ocr_signals(result: OCRResult) -> OCRSignals:
    lines = _signal_lines(result.normalized_text)
    authors = [line for line in lines if _is_author_line(line)]
    title_lines = [
        line for line in lines
        if line not in authors
        and "book" not in _tokens(line)
        and not (_tokens(line) & _TITLE_STOP_WORDS and len(_substantive_words(line)) < 2)
    ]
    title = None
    subtitle = None
    multi_word_title_lines = [line for line in title_lines if len(_substantive_words(line)) >= 2]
    if len(multi_word_title_lines) >= 2:
        title = multi_word_title_lines[0]
        subtitle = multi_word_title_lines[1]
    elif len(title_lines) > 1 and title_lines[0].isupper() and title_lines[1].isupper():
        title = f"{title_lines[0]} {title_lines[1]}"
    elif title_lines:
        scored_lines = sorted(
            title_lines,
            key=lambda line: (
                len(_substantive_words(line)) > 1,
                max((len(re.sub(r"[^A-Za-z]", "", word)) for word in _substantive_words(line)), default=0),
                _line_confidence(line, result),
            ),
            reverse=True,
        )
        title = scored_lines[0]
    if title and len(_substantive_words(title)) == 1 and len(_substantive_words(title)[0]) < 4:
        title = None
    normalized_authors = [" ".join(_substantive_words(line)) for line in authors[:2]]
    author = " ".join(normalized_authors) if normalized_authors else None
    if subtitle is None:
        subtitle = next(
            (line for line in title_lines if line != title and len(_substantive_words(line)) >= 2),
            None,
        )
    edition_match = _EDITION_PATTERN.search(result.normalized_text)
    edition = edition_match.group(0) if edition_match else None
    confidences = [block.confidence for block in result.blocks if block.confidence is not None]
    confidence = sum(confidences) / len(confidences) / 100 if confidences else None
    return OCRSignals(
        title=title,
        author=author,
        isbns=_extract_isbns(result.text),
        confidence=confidence,
        authors=normalized_authors,
        subtitle=subtitle,
        edition=edition,
        queries=_build_queries(title, normalized_authors, subtitle),
    )


def _tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def _similarity(expected: str | None, actual: str | None) -> float:
    if not expected or not actual:
        return 0.0
    expected_tokens = _tokens(expected)
    actual_tokens = _tokens(actual)
    overlap = len(expected_tokens & actual_tokens) / max(len(expected_tokens), 1)
    sequence = SequenceMatcher(None, " ".join(sorted(expected_tokens)), " ".join(sorted(actual_tokens))).ratio()
    return max(overlap, sequence)


def _score_candidate(metadata: BookMetadata, signals: OCRSignals) -> tuple[float, dict[str, float]]:
    if signals.isbns and any(isbn in {metadata.isbn10, metadata.isbn13} for isbn in signals.isbns):
        return 1.0, {"isbn_match": 1.0}
    title_score = _similarity(signals.title, metadata.title)
    author_scores = [
        max((_similarity(signal_author, author) for author in metadata.authors), default=0.0)
        for signal_author in signals.authors
    ]
    author_score = sum(author_scores) / len(author_scores) if author_scores else 0.0
    subtitle_score = _similarity(signals.subtitle, metadata.title)
    confidence = signals.confidence or 0.0
    score = (title_score * 0.28) + (author_score * 0.52) + (subtitle_score * 0.08) + (confidence * 0.12)
    evidence = {
        "title_match": round(title_score, 3),
        "author_match": round(author_score, 3),
        "author_coverage": round(sum(score >= 0.55 for score in author_scores) / len(author_scores), 3)
        if author_scores
        else 0.0,
        "subtitle_match": round(subtitle_score, 3),
        "ocr_confidence": round(confidence, 3),
    }
    return round(min(score, 1.0), 3), evidence


def _rank(metadata: BookMetadata, signals: OCRSignals) -> float:
    return _score_candidate(metadata, signals)[0]


def _candidate_key(metadata: BookMetadata) -> str:
    return metadata.isbn13 or metadata.isbn10 or f"{metadata.title}|{','.join(metadata.authors)}".lower()


async def identify_ocr_image(image_bytes: bytes) -> OCRIdentificationResult:
    ocr_result = ocr_image(image_bytes)
    signals = extract_ocr_signals(ocr_result)
    if not signals.title and not signals.author and not signals.isbns:
        return OCRIdentificationResult(ocr_result, signals, [], "No useful text detected")

    openlibrary = OpenLibraryService()
    googlebooks = GoogleBooksService()
    metadata_results: list[BookMetadata] = []
    provider_errors = []

    for isbn in signals.isbns[:5]:
        try:
            metadata_results.append(await openlibrary.get_book_by_isbn(isbn))
            continue
        except (BookNotFoundError, OpenLibraryError) as exc:
            provider_errors.append(str(exc))
        try:
            metadata_results.append(await googlebooks.get_book_by_isbn(isbn))
        except (GoogleBooksNotFoundError, GoogleBooksError) as exc:
            provider_errors.append(str(exc))

    if not signals.isbns:
        for provider, label in ((openlibrary, "Open Library"), (googlebooks, "Google Books")):
            try:
                search_results = await provider.search_books(
                    title=signals.title,
                    author=signals.author,
                    limit=10,
                )
                metadata_results.extend(search_results)
                for query in signals.queries[:4]:
                    metadata_results.extend(await provider.search_books(query=query, limit=10))
            except (OpenLibraryError, GoogleBooksError) as exc:
                provider_errors.append(f"{label}: {exc}")

    deduplicated = {}
    for metadata in metadata_results:
        key = _candidate_key(metadata)
        existing = deduplicated.get(key)
        if existing is None or _rank(metadata, signals) > _rank(existing, signals):
            deduplicated[key] = metadata
    candidates = []
    for metadata in deduplicated.values():
        score, evidence = _score_candidate(metadata, signals)
        if evidence.get("isbn_match") or evidence.get("author_match", 0.0) >= 0.35 or evidence.get("title_match", 0.0) >= 0.55:
            candidates.append(RankedBookCandidate(metadata, score, evidence))
    candidates.sort(key=lambda candidate: candidate.match_score, reverse=True)
    message = None
    if not candidates:
        message = "No matching books found"
        if provider_errors:
            message = "Metadata providers were unavailable; no matching books found"
    return OCRIdentificationResult(ocr_result, signals, candidates[:10], message)