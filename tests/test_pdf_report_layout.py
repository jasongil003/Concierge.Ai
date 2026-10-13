"""Parse actual PDF text geometry, rather than accepting only its signature."""

from io import BytesIO

import pytest
from pypdf import PdfReader

from app.reporting import build_pdf


@pytest.mark.parametrize("record_count", [1, 160])
def test_pdf_report_text_stays_inside_each_page(record_count):
    values = [f"Recorded count {index}: {index + 3}." for index in range(record_count)]
    document = PdfReader(BytesIO(build_pdf("Synthetic Hotel A", "Verified report", [("Recorded metrics", values)])))
    extracted = []
    for page in document.pages:
        coordinates = []

        def visit(text, cm, tm, font, size):
            if text.strip():
                coordinates.append((text.strip(), tm[4], tm[5], size))

        extracted.append(page.extract_text(visitor_text=visit))
        assert coordinates
        for text, x, y, size in coordinates:
            assert 42 <= x < float(page.mediabox.right), text
            assert 42 <= y <= float(page.mediabox.top) - size, (text, y)
        assert all(first[2] > second[2] for first, second in zip(coordinates, coordinates[1:])), coordinates
    output = "\n".join(extracted)
    assert "Synthetic Hotel A" in output
    assert "Verified report" in output
    assert "Recorded metrics" in output
    for value in values:
        assert value in output
    assert (len(document.pages) > 1) is (record_count > 1)
