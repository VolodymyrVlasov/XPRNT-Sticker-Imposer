"""Low-res raster preview of an uploaded PDF's first page, for the browser layout preview."""

import base64

THUMBNAIL_DPI = 36


def render_thumbnail_data_uri(path: str, dpi: int = THUMBNAIL_DPI) -> str:
    import fitz  # PyMuPDF

    doc = fitz.open(path)
    try:
        page = doc[0]
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        png_bytes = pix.tobytes("png")
    finally:
        doc.close()

    b64 = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"
