"""Resource-limited subprocess entry point for untrusted PDF text extraction."""

from __future__ import annotations

import io
import json
import sys


PDF_MEMORY_LIMIT_BYTES = 768 * 1024 * 1024
PDF_CPU_LIMIT_SECONDS = 20
PDF_MAX_PAGES = 300
PDF_MAX_BLOCKS = 10_000


def extract_pdf_bytes(data: bytes, max_chars: int) -> list[dict[str, object]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data), strict=True)
    if len(reader.pages) > PDF_MAX_PAGES:
        raise ValueError("The PDF exceeds the configured page limit.")

    blocks: list[dict[str, object]] = []
    extracted_chars = 0
    for number, page in enumerate(reader.pages, 1):
        page_text = page.extract_text() or ""
        extracted_chars += len(page_text)
        if extracted_chars > max_chars:
            raise ValueError("Extracted content exceeds the configured processing limit.")
        for line in page_text.splitlines():
            if not line.strip():
                continue
            if len(blocks) >= PDF_MAX_BLOCKS:
                raise ValueError("The PDF contains too many text sections to process safely.")
            blocks.append({"text": line.strip(), "location": {"page": number}})
    if not blocks:
        raise ValueError("The PDF contains no machine-readable text. OCR for scanned PDFs is not configured.")
    return blocks


def _set_resource_limits() -> None:
    import resource

    for name, limit in (
        ("RLIMIT_CORE", 0),
        ("RLIMIT_CPU", PDF_CPU_LIMIT_SECONDS),
    ):
        resource_id = getattr(resource, name, None)
        if resource_id is None:
            continue
        _, hard = resource.getrlimit(resource_id)
        bounded_limit = limit if hard == resource.RLIM_INFINITY else min(limit, hard)
        resource.setrlimit(resource_id, (bounded_limit, bounded_limit))

    # RLIMIT_AS is reliable in the Linux production container. On macOS it can
    # count shared mappings against the ceiling and reject even ordinary Python
    # allocations, so local development keeps the CPU and wall-clock limits only.
    if sys.platform.startswith("linux") and hasattr(resource, "RLIMIT_AS"):
        resource_id = resource.RLIMIT_AS
        _, hard = resource.getrlimit(resource_id)
        bounded_limit = PDF_MEMORY_LIMIT_BYTES if hard == resource.RLIM_INFINITY else min(PDF_MEMORY_LIMIT_BYTES, hard)
        resource.setrlimit(resource_id, (bounded_limit, bounded_limit))


def main() -> int:
    try:
        _set_resource_limits()
        max_input_bytes = int(sys.argv[1])
        max_chars = int(sys.argv[2])
        data = sys.stdin.buffer.read(max_input_bytes + 1)
        if len(data) > max_input_bytes:
            raise ValueError("The PDF exceeds the configured upload limit.")
        blocks = extract_pdf_bytes(data, max_chars)
        response = {"blocks": blocks}
        status = 0
    except ValueError as exc:
        safe_errors = {
            "The PDF exceeds the configured page limit.",
            "The PDF exceeds the configured upload limit.",
            "Extracted content exceeds the configured processing limit.",
            "The PDF contains too many text sections to process safely.",
            "The PDF contains no machine-readable text. OCR for scanned PDFs is not configured.",
        }
        response = {"error": str(exc) if str(exc) in safe_errors else "PDF processing failed within safe limits."}
        status = 2
    except Exception:
        response = {"error": "PDF processing failed within safe limits."}
        status = 2
    sys.stdout.write(json.dumps(response, ensure_ascii=True, separators=(",", ":")))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
