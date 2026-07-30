from __future__ import annotations

import hashlib

from docintel.processing.chunking import ChunkingConfig, chunk_page


def test_golden_chunk_boundaries_overlap_hashes_and_slices() -> None:
    text = (
        "Alpha fictional policy sentence one. Alpha sentence two.\n\n"
        "Beta fictional paragraph contains several words and a closing sentence. "
        "Gamma sentence follows with deterministic wording.\n\n"
        "Delta final paragraph closes the fictional document."
    )
    config = ChunkingConfig(
        target_chars=90,
        max_chars=120,
        overlap_chars=20,
        version="golden-v1",
    )

    chunks = chunk_page(text, config)
    boundaries = [(chunk.ordinal, chunk.char_start, chunk.char_end) for chunk in chunks]

    assert boundaries == [
        (0, 0, 58),
        (1, 38, 130),
        (2, 110, 182),
        (3, 162, 234),
    ]
    for chunk in chunks:
        assert chunk.text == text[chunk.char_start : chunk.char_end]
        assert chunk.text_sha256 == hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
        assert chunk.chunker_version == "golden-v1"
    assert chunks[0].char_end - chunks[1].char_start == 20
    assert chunks[1].char_end - chunks[2].char_start == 20
    assert chunks[2].char_end - chunks[3].char_start == 20


def test_long_uninterrupted_text_uses_hard_splits_without_crossing_limit() -> None:
    text = "x" * 4000
    config = ChunkingConfig(
        target_chars=1400,
        max_chars=1800,
        overlap_chars=200,
        version="deterministic-char-v1",
    )

    chunks = chunk_page(text, config)

    assert [(chunk.char_start, chunk.char_end) for chunk in chunks] == [
        (0, 1800),
        (1600, 3400),
        (3200, 4000),
    ]
    assert all(len(chunk.text) <= 1800 for chunk in chunks)
    assert all(chunk.text == text[chunk.char_start : chunk.char_end] for chunk in chunks)


def test_blank_page_produces_no_chunks() -> None:
    config = ChunkingConfig(1400, 1800, 200, "deterministic-char-v1")

    assert chunk_page("\n \t", config) == []
