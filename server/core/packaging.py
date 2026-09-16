"""Bundle generation output into a single zip for download.

Layout inside the zip:
  <print filename>.pdf              - ready-to-print file (marks + tiled artwork)
  <template folder name>/
      <template folder name>.pdf    - imposition template (marks only, for manual reuse)
      <template folder name>.plt    - cut file for the plotter
      <template folder name> - contour.pdf   - optional vector cut geometry

A batch run produces one print PDF per uploaded artwork, but template folders
are de-duplicated by name — several artworks that land on the same grid share
one template/PLT/contour set instead of regenerating identical files.
"""

import os
import zipfile


def build_zip(
    zip_path: str,
    print_pdf_path: str,
    template_folder_name: str,
    template_files: list[str],
) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(print_pdf_path, arcname=os.path.basename(print_pdf_path))
        for path in template_files:
            zf.write(path, arcname=f"{template_folder_name}/{os.path.basename(path)}")


def build_shape_zip(
    zip_path: str,
    print_pdf_path: str,
    plt_path: str,
    contour_pdf_path: str | None = None,
) -> None:
    """Shaped-sticker output has no template subfolder — print PDF, PLT, and the
    optional contour PDF all sit directly at the zip root.
    """
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(print_pdf_path, arcname=os.path.basename(print_pdf_path))
        zf.write(plt_path, arcname=os.path.basename(plt_path))
        if contour_pdf_path:
            zf.write(contour_pdf_path, arcname=os.path.basename(contour_pdf_path))


def build_batch_zip(
    zip_path: str,
    print_pdf_paths: list[str],
    template_folders: dict[str, list[str]],
) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in print_pdf_paths:
            zf.write(path, arcname=os.path.basename(path))
        for folder_name, paths in template_folders.items():
            for path in paths:
                zf.write(path, arcname=f"{folder_name}/{os.path.basename(path)}")
