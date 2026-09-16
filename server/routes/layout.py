from fastapi import APIRouter

from server.core.layout import resolve_grid
from server.models import LayoutInput, LayoutResult

router = APIRouter()


@router.post("/api/layout", response_model=LayoutResult)
def recompute_layout(payload: LayoutInput) -> LayoutResult:
    """Recompute grid geometry live as the user edits sheet/margin/gap/override fields."""
    grid = resolve_grid(
        payload.dim_w, payload.dim_h,
        payload.sheet_w, payload.sheet_h,
        payload.mark_offset, payload.field_margin, payload.gap,
        orientation=payload.orientation,
        cols=payload.cols,
        rows=payload.rows,
    )
    return LayoutResult(**grid.as_dict())
