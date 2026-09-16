from reportlab.lib.colors import CMYKColor

MM = 72 / 25.4          # 1 mm in PDF points
K100 = CMYKColor(0, 0, 0, 1)

# Default distance from the sheet edge to the registration marks.
DEFAULT_MARK_OFFSET = 9.0
# Default distance from the marks to the usable layout field where stickers are placed.
DEFAULT_FIELD_MARGIN = 2.0
# Default gap between adjacent stickers (0 = shared cut line, rectangular stickers only).
DEFAULT_GAP = 0.0
# HPGL cut overshoot past each line's true endpoint, so corners cut cleanly.
OVERSHOOT = 1.0

SHEET_PRESETS: dict[str, tuple[float, float]] = {
    "SRA3":  (320.0, 450.0),
    "SRA3+": (330.0, 487.0),
}

MATERIALS: list[str] = [
    "1123 Solid",
    "1123 Score",
    "Oracal WG",
    "Oracal WM",
    "Oracal + 265",
    "Oracal + 205",
    "Ri-Screen + 265",
    "Ri-Screen + 205",
    "RI-145 PVC",
    "RI-165 PVC",
    "RI-145 PVC + 265",
    "RI-145 PVC + 205",
    "Поліестрова прозора глянцева Raflatac (DP37)",
    "Поліестрова прозора матова Raflatac (DP37)",
    "RI-205 PVC",
    "RI-JET 265 PVC",
    "Вінілова біла глянцева Ritrama з сірим клеєм",
    "Ri-Screen M80 White Gloss",
    "Ri-Screen M80 White Matt",
    "Поліестрова матова Raflatac (DP77)",
    "Винна Raflatac Classic Laser (HS)",
    "Крафт коричневий Raflatac (SXA7)",
    "Самоклеючий картон глянцевий Raflatac (SPA3)",
    "Паперова некрейдована OFFSET (AR)",
    "Винна Ritrama (Martele Ivory)",
    "Винна Ritrama (Martele White)",
    "Чорна Ritrama (Classica Black)",
    "Металік Ritrama (StarLight)",
    "Скоролупа Ritrama (Eden AP1300 WG74)",
    "Інше (кастомний)",
]

CUSTOM_MATERIAL = "Інше (кастомний)"
