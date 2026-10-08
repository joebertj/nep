"""Parse and compare plus-form route chainage in project titles."""

import re


_MARKER = r"(?:(?:STA(?:TION)?|KM|KILOMET(?:ER|RE))\.?\s*[:=]?\s*)?"
_PATTERN = re.compile(
    rf"\b{_MARKER}(\d+(?:\.\d+)?)\s*\+\s*(\d+(?:\.\d+)?)"
    rf"(?:\s*(?:[-–]|\bTO\b)\s*{_MARKER}(\d+(?:\.\d+)?)\s*\+\s*(\d+(?:\.\d+)?))?",
    re.I,
)


_DIRECTION_ALIASES = {
    "EAST": ("east_west", "east"), "EASTERN": ("east_west", "east"),
    "ORIENTAL": ("east_west", "east"),
    "WEST": ("east_west", "west"), "WESTERN": ("east_west", "west"),
    "OCCIDENTAL": ("east_west", "west"),
    "NORTH": ("north_south", "north"), "NORTHERN": ("north_south", "north"),
    "NORTE": ("north_south", "north"), "NORTLE": ("north_south", "north"),
    "SOUTH": ("north_south", "south"), "SOUTHERN": ("north_south", "south"),
    "SUR": ("north_south", "south"),
}
_TRANCHE_PATTERN = re.compile(
    r"\b(PACKAGE|PKG|PHASE|PH|STAGE|TRANCHE|LOT|SEGMENT|SECTION|PART)"
    r"\.?\s*(?:NO|NUMBER)?\.?\s*(VIII|VII|VI|V|IV|III|II|I|X|IX|[0-9]+[A-Z]?)\b",
    re.I,
)
_TRANCHE_TYPES = {"PKG": "PACKAGE", "PH": "PHASE"}
_ROMAN_VALUES = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5",
                 "VI": "6", "VII": "7", "VIII": "8", "IX": "9", "X": "10"}


def direction_signals(text: str) -> dict[str, set[str]]:
    """Return explicit directional signals, including common Spanish forms."""
    normalized = re.sub(r"[^A-Z0-9]+", " ", str(text or "").upper())
    result: dict[str, set[str]] = {}
    for token in normalized.split():
        if token in _DIRECTION_ALIASES:
            axis, direction = _DIRECTION_ALIASES[token]
            result.setdefault(axis, set()).add(direction)
    return result


def has_directional_conflict(left: str, right: str) -> bool:
    """Flag explicit, non-overlapping directions on the same geographic axis."""
    left_signals = direction_signals(left)
    right_signals = direction_signals(right)
    return any(
        axis in right_signals and not directions.intersection(right_signals[axis])
        for axis, directions in left_signals.items()
    )


def tranche_signals(text: str) -> dict[str, set[str]]:
    """Extract explicit package, phase, stage, lot, segment, and part labels."""
    result: dict[str, set[str]] = {}
    for match in _TRANCHE_PATTERN.finditer(str(text or "")):
        marker = _TRANCHE_TYPES.get(match.group(1).upper(), match.group(1).upper())
        value = match.group(2).upper()
        value = _ROMAN_VALUES.get(value, value)
        result.setdefault(marker, set()).add(value)
    return result


def compare_tranche(left: str, right: str) -> dict[str, str | bool]:
    """Compare explicit tranche markers; differences are a soft review signal."""
    left_signals, right_signals = tranche_signals(left), tranche_signals(right)
    shared_types = left_signals.keys() & right_signals.keys()
    different = [key for key in shared_types if not left_signals[key] & right_signals[key]]
    same = [key for key in shared_types if left_signals[key] & right_signals[key]]
    if different:
        status = "different tranche"
    elif same:
        status = "same tranche"
    elif left_signals and right_signals:
        status = "different marker type"
    elif left_signals or right_signals:
        status = "one side stated"
    else:
        status = "not stated"
    detail = ""
    if different:
        key = different[0]
        left_values = ", ".join(sorted(left_signals[key]))
        right_values = ", ".join(sorted(right_signals[key]))
        detail = f"{key.title()} {left_values} vs {right_values}"
    elif status == "different marker type":
        detail = f"{', '.join(sorted(left_signals))} vs {', '.join(sorted(right_signals))}"
    elif status == "one side stated":
        signals = left_signals or right_signals
        side = "Current" if left_signals else "Prior"
        parts = [f"{kind.title()} {', '.join(sorted(values))}" for kind, values in signals.items()]
        detail = f"{side} {'; '.join(parts)} only"
    return {
        "tranche_status": status,
        "tranche_detail": detail,
        "tranche_conflict": status == "different tranche",
    }


def _metres(major: str, minor: str) -> float:
    return float(major) * 1000 + float(minor)


def _format(value: float) -> str:
    km = int(value // 1000)
    metres = value - km * 1000
    return f"{km}+{metres:06.2f}"


def parse_chainage(text: str) -> tuple[list[tuple[float, float]], list[float]]:
    """Return explicit ranges and isolated station values, both in metres."""
    ranges, points = [], []
    for match in _PATTERN.finditer(str(text or "")):
        start = _metres(match.group(1), match.group(2))
        if match.group(3) is None:
            points.append(start)
            continue
        end = _metres(match.group(3), match.group(4))
        ranges.append((min(start, end), max(start, end)))
    return ranges, points


def format_chainage(ranges: list[tuple[float, float]], points: list[float]) -> str:
    values = [f"{_format(start)}–{_format(end)}" for start, end in ranges]
    values.extend(_format(point) for point in points)
    return " · ".join(values)


def compare_chainage(current: str, prior: str) -> dict[str, str | bool]:
    current_ranges, current_points = parse_chainage(current)
    prior_ranges, prior_points = parse_chainage(prior)
    current_text = format_chainage(current_ranges, current_points)
    prior_text = format_chainage(prior_ranges, prior_points)
    overlaps = [
        (max(a0, b0), min(a1, b1))
        for a0, a1 in current_ranges
        for b0, b1 in prior_ranges
        if min(a1, b1) > max(a0, b0)
    ]
    overlap_text = " · ".join(f"{_format(a)}–{_format(b)}" for a, b in overlaps)
    if current_ranges and prior_ranges:
        status = "overlap" if overlaps else "disjoint"
    elif current_ranges or prior_ranges or current_points or prior_points:
        status = "incomplete"
    else:
        status = "not stated"
    return {
        "has_current_range": bool(current_ranges),
        "has_prior_range": bool(prior_ranges),
        "overlaps": bool(overlaps),
        "current_chainage": current_text,
        "prior_chainage": prior_text,
        "chainage_overlap": overlap_text,
        "chainage_status": status,
    }
