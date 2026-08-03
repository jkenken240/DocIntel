#!/usr/bin/env python3
"""Generate deterministic, fictional PDFs for the DocIntel v1.0 demonstration."""

from __future__ import annotations

import argparse
import hashlib
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Page:
    label: str
    heading: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class Document:
    filename: str
    title: str
    subtitle: str
    pages: tuple[Page, ...]


DOCUMENTS = (
    Document(
        filename="Aster Ridge Governance Brief.pdf",
        title="Aster Ridge Governance Brief",
        subtitle="Fictional compliance and operating profile",
        pages=(
            Page(
                label="COMPANY PROFILE",
                heading="Governance built for deliberate growth",
                paragraphs=(
                    "Aster Ridge Advisory is a fictional governance consultancy based at "
                    "18 Lantern Way, Meridian Vale.",
                    "The company supports the fictional Project Aurora program with policy "
                    "reviews, control testing, and board-ready reporting.",
                    "All companies, people, addresses, projects, and amounts in this document "
                    "were created solely for the DocIntel demonstration.",
                ),
            ),
            Page(
                label="AUDIT RETENTION STANDARD",
                heading="Seven-year evidence window",
                paragraphs=(
                    "Aster Ridge has a compliance audit records retention period of seven years.",
                    "Records are reviewed every April by the fictional Governance Office. "
                    "The retained package includes approval notes, test results, and remediation "
                    "sign-offs.",
                    "The policy owner is Mara Ellison, a fictional director with no connection "
                    "to a real person.",
                ),
            ),
            Page(
                label="PROJECT AURORA",
                heading="A bounded modernization program",
                paragraphs=(
                    "Project Aurora has a fictional approved budget of USD 2.4 million and a "
                    "planned review milestone in October.",
                    "Its scope covers policy indexing, evidence cataloging, and review workflows. "
                    "It does not include customer data or production credentials.",
                ),
            ),
        ),
    ),
    Document(
        filename="Blue Dune Operations Profile.pdf",
        title="Blue Dune Operations Profile",
        subtitle="Fictional controls and service overview",
        pages=(
            Page(
                label="COMPANY PROFILE",
                heading="Traceable operations by design",
                paragraphs=(
                    "Blue Dune Logistics is a fictional operations company based at 42 Harbor "
                    "Glass Road, Copper Bay.",
                    "Its fictional Project Tidal program coordinates control reviews across "
                    "regional service teams and produces evidence for management review.",
                    "All companies, people, addresses, projects, and amounts in this document "
                    "were created solely for the DocIntel demonstration.",
                ),
            ),
            Page(
                label="CONTROL PROGRAM",
                heading="Quarterly review cadence",
                paragraphs=(
                    "Blue Dune performs fictional control reviews in January, April, July, and "
                    "October. Each review records an owner, due date, result, and remediation "
                    "decision.",
                    "The service-quality lead is Jonah Vale, a fictional person. The annual "
                    "control-program budget is a fictional USD 1.8 million.",
                ),
            ),
            Page(
                label="AUDIT RETENTION STANDARD",
                heading="Nine-year evidence window",
                paragraphs=(
                    "Blue Dune has a compliance audit records retention period of nine years.",
                    "Records are reviewed every October by the fictional Risk Office. The retained "
                    "package includes review summaries, exception decisions, and closure evidence.",
                    "This longer period is a fictional internal policy and is not legal advice or "
                    "a statement about a real organization.",
                ),
            ),
        ),
    ),
)

KNOWN_FILENAMES = frozenset(document.filename for document in DOCUMENTS)


def _is_link_like(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _pdf_text(value: str) -> str:
    try:
        value.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError("Demo PDF text must remain ASCII for deterministic encoding.") from error
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _text_command(font: str, size: int, x: int, y: int, value: str, color: str) -> str:
    return f"BT /{font} {size} Tf {color} rg 1 0 0 1 {x} {y} Tm ({_pdf_text(value)}) Tj ET\n"


def _page_stream(document: Document, page: Page, page_number: int) -> bytes:
    commands = [
        "1 1 1 rg 0 0 612 792 re f\n",
        "0.055 0.075 0.12 rg 0 706 612 86 re f\n",
        "0.11 0.78 0.90 rg 0 706 10 86 re f\n",
        _text_command("F2", 10, 54, 754, "DOCINTEL V1.0 FICTIONAL DEMO", "0.45 0.88 0.96"),
        _text_command("F2", 19, 54, 724, document.title, "1 1 1"),
        _text_command("F2", 9, 54, 668, page.label, "0.18 0.48 0.62"),
        _text_command("F2", 24, 54, 628, page.heading, "0.06 0.09 0.15"),
        "0.82 0.87 0.91 RG 0.8 w 54 606 m 558 606 l S\n",
    ]

    y = 570
    for paragraph in page.paragraphs:
        for line in textwrap.wrap(paragraph, width=82, break_long_words=False):
            commands.append(_text_command("F1", 11, 54, y, line, "0.17 0.21 0.27"))
            y -= 18
        y -= 13

    commands.extend(
        [
            "0.90 0.93 0.95 RG 0.8 w 54 58 m 558 58 l S\n",
            _text_command(
                "F1",
                8,
                54,
                37,
                "FICTIONAL PORTFOLIO SAMPLE - NO REAL BUSINESS DATA",
                "0.36 0.42 0.49",
            ),
            _text_command(
                "F2", 8, 530, 37, f"{page_number} / {len(document.pages)}", "0.18 0.48 0.62"
            ),
        ]
    )
    return "".join(commands).encode("ascii")


def build_pdf(document: Document) -> bytes:
    page_count = len(document.pages)
    regular_font = 3 + page_count * 2
    bold_font = regular_font + 1
    info_object = bold_font + 1
    last_object = info_object
    page_objects = [3 + index * 2 for index in range(page_count)]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Kids [{' '.join(f'{number} 0 R' for number in page_objects)}] "
            f"/Count {page_count} >>"
        ).encode("ascii"),
        regular_font: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        bold_font: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        info_object: (
            f"<< /Title ({_pdf_text(document.title)}) /Author (DocIntel) "
            "/Creator (DocIntel deterministic demo generator) "
            "/Producer (DocIntel v1.0) /Subject (Fictional portfolio demonstration) >>"
        ).encode("ascii"),
    }

    for index, page in enumerate(document.pages):
        page_object = page_objects[index]
        content_object = page_object + 1
        stream = _page_stream(document, page, index + 1)
        objects[page_object] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {regular_font} 0 R /F2 {bold_font} 0 R >> >> "
            f"/Contents {content_object} 0 R >>"
        ).encode("ascii")
        objects[content_object] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"endstream"
        )

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (last_object + 1)
    for object_number in range(1, last_object + 1):
        offsets[object_number] = len(output)
        output.extend(f"{object_number} 0 obj\n".encode("ascii"))
        output.extend(objects[object_number])
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {last_object + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for object_number in range(1, last_object + 1):
        output.extend(f"{offsets[object_number]:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {last_object + 1} /Root 1 0 R /Info {info_object} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _validate_output_directory(raw_output: str) -> Path:
    output = Path(raw_output)
    if not output.is_absolute():
        raise ValueError("--output-dir must be an explicit absolute path.")
    if len(output.parts) < 3:
        raise ValueError("Refusing an unsafe broad output directory.")

    repository_root = Path(__file__).resolve().parent.parent
    resolved_output = output.resolve(strict=False)
    if resolved_output == repository_root or resolved_output.is_relative_to(repository_root):
        raise ValueError("Demo PDFs must be generated outside the Git repository.")
    if repository_root.is_relative_to(resolved_output):
        raise ValueError("Refusing an output directory that contains the Git repository.")

    for candidate in (output, *output.parents):
        if candidate.exists() and _is_link_like(candidate):
            raise ValueError(f"Refusing symlinked output path component: {candidate}")
        if candidate == Path(output.anchor):
            break
    if output.exists() and not output.is_dir():
        raise ValueError("The output path exists and is not a directory.")
    return resolved_output


def generate(output_directory: Path) -> list[tuple[str, str]]:
    output_directory.mkdir(parents=True, exist_ok=True)
    unexpected = sorted(
        path.name for path in output_directory.iterdir() if path.name not in KNOWN_FILENAMES
    )
    if unexpected:
        raise ValueError(f"Refusing nonempty output directory with unrelated entries: {unexpected}")

    results: list[tuple[str, str]] = []
    for document in DOCUMENTS:
        payload = build_pdf(document)
        destination = output_directory / document.filename
        if destination.exists():
            if not destination.is_file() or _is_link_like(destination):
                raise ValueError(f"Refusing unsafe existing destination: {destination}")
            if destination.read_bytes() != payload:
                raise ValueError(f"Refusing to overwrite a different existing file: {destination}")
        else:
            with destination.open("xb") as stream:
                stream.write(payload)
        results.append((document.filename, hashlib.sha256(payload).hexdigest()))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", required=True, help="Absolute directory outside the repository"
    )
    arguments = parser.parse_args()
    try:
        output_directory = _validate_output_directory(arguments.output_dir)
        results = generate(output_directory)
    except (OSError, ValueError) as error:
        print(f"DocIntel demo generation failed: {error}", file=sys.stderr)
        return 1

    print(f"Generated deterministic fictional PDFs in {output_directory}")
    for filename, digest in results:
        print(f"{digest}  {filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
