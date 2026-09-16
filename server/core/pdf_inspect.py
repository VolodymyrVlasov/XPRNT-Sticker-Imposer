"""Read artwork geometry from an uploaded PDF."""

from dataclasses import dataclass

from server.utils.constants import MM


@dataclass
class ArtworkInfo:
    width_mm: float
    height_mm: float
    page_count: int


def inspect_pdf(path: str) -> ArtworkInfo:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(path)
    except PdfReadError as exc:
        raise ValueError(f"Не вдалося прочитати PDF: {exc}") from exc

    if len(reader.pages) == 0:
        raise ValueError("PDF не містить сторінок")

    page = reader.pages[0]
    box = page.trimbox if "/TrimBox" in page else page.mediabox
    width_mm = float(box.width) / MM
    height_mm = float(box.height) / MM

    if width_mm <= 0 or height_mm <= 0:
        raise ValueError("Некоректний розмір сторінки PDF")

    return ArtworkInfo(width_mm=width_mm, height_mm=height_mm, page_count=len(reader.pages))
