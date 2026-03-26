"""Survey category codes and Russian display labels (KID / RCDI)."""

KID_CATEGORY_CODES = ("F", "COG", "MOT", "LAN", "SEL", "SOC")

RCDI_CATEGORY_CODES = ("SO", "SE", "GR", "FI", "EX", "LA")

KID_CATEGORY_LABELS: dict[str, str] = {
    "F": "Сводный показатель (F)",
    "COG": "Когнитивное",
    "MOT": "Моторное",
    "LAN": "Речь",
    "SEL": "Самообслуживание",
    "SOC": "Социальное",
}

RCDI_CATEGORY_LABELS: dict[str, str] = {
    "SO": "Социальная",
    "SE": "Самообслуживание",
    "GR": "Грубая моторика",
    "FI": "Тонкая моторика",
    "EX": "Экспрессия",
    "LA": "Речь",
}

STATUS_NORMAL = "норма"
STATUS_BORDERLINE = "пограничное состояние"
STATUS_RISK = "зона риска"
