import math
import os


def fmt_dim(v: float) -> str:
    """Round to the nearest whole millimetre for display in filenames and the
    on-sheet template caption — e.g. 49.38 -> "49". This only affects the
    formatted label string; every actual layout/print/cut coordinate elsewhere
    in the app keeps full float precision, untouched by this function.
    Round-half-up (not Python's banker's-rounding `round()`) so e.g. 48.5 -> 49,
    not 48 — the less surprising behavior for a human-readable label.
    """
    return str(math.floor(v + 0.5))


def extract_artwork_name(artwork_filename: str) -> str:
    """Return the artwork label: everything from the 3rd ' - ' segment onward, no extension."""
    filename = os.path.splitext(os.path.basename(artwork_filename))[0]
    parts = filename.split(" - ")
    if len(parts) >= 3:
        return " - ".join(parts[2:])
    return filename


def build_folder_name(
    cell_w: float, cell_h: float,
    cols: int, rows: int,
    orientation: str, sheet_name: str,
    gap: float = 0.0,
) -> str:
    short_side = min(cell_w, cell_h)
    long_side  = max(cell_w, cell_h)
    name = (
        f"PLT {fmt_dim(short_side)}x{fmt_dim(long_side)} - "
        f"{cols}x{rows} - {orientation} - {sheet_name}"
    )
    if gap > 0:
        name += f" - gap{fmt_dim(gap)}"
    return name


def build_print_filename(
    order: str, material: str,
    size_str: str, qty: int, sheets: int,
    artwork_filename: str | None = None,
) -> str:
    """Order number is optional — when blank the filename is built without it."""
    art_seg = f" - {extract_artwork_name(artwork_filename)}" if artwork_filename else ""
    order_seg = f"{order} - " if order else ""
    return (
        f"{order_seg}{material} - "
        f"{size_str} мм ({qty} шт){art_seg} - {sheets} арк.pdf"
    )


def get_unique_path(folder: str, base_filename: str) -> str:
    """Return a path for `base_filename` inside `folder` that does not already exist.

    If taken, inserts (2), (3), … after the first ' - ' segment.
    """
    path = os.path.join(folder, base_filename)
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(base_filename)
    counter = 2
    while True:
        idx = stem.find(" - ")
        candidate = f"{stem[:idx]} ({counter}){stem[idx:]}{ext}" if idx >= 0 else f"{stem} ({counter}){ext}"
        path = os.path.join(folder, candidate)
        if not os.path.exists(path):
            return path
        counter += 1
