SEAT_LAYOUT = {
    "L": {"label": "يسار", "cols": 2},
    "M": {"label": "وسط", "cols": 4},
    "R": {"label": "يمين", "cols": 2},
}


def seat_code(zone: str, row: int, col: int) -> str:
    return f"{zone}{row}-{col}"


def seat_label(code: str | None) -> str:
    if not code:
        return "بدون مقعد"
    zone = code[0]
    rest = code[1:]
    row, col = rest.split("-")
    return f"{SEAT_LAYOUT.get(zone, {}).get('label', zone)} — الصف {row} مقعد {col}"


def classroom_seats(rows: int = 4) -> list[dict]:
    seats = []
    for row in range(1, rows + 1):
        for zone, meta in SEAT_LAYOUT.items():
            for col in range(1, meta["cols"] + 1):
                code = seat_code(zone, row, col)
                seats.append(
                    {
                        "code": code,
                        "zone": zone,
                        "zone_label": meta["label"],
                        "row": row,
                        "col": col,
                        "label": seat_label(code),
                    }
                )
    return seats
