"""Parse and compare explicitly labeled and plus-form route chainage."""

import re
from functools import lru_cache


_MARKER = r"(?:(?:STA(?:TION)?|CHAINAGE|KM|KILOMET(?:ER|RE)|K)\.?\s*[:=]?\s*)?"
_OFFSET = r"\(?\s*([+-]?\d+(?:\.\d+)?)\s*\)?"
_PATTERN = re.compile(
    rf"\b{_MARKER}(\d+(?:\.\d+)?)\s*\+\s*{_OFFSET}"
    rf"(?:\s*(?:[-–]|\bTO\b)\s*{_MARKER}(\d+(?:\.\d+)?)\s*\+\s*{_OFFSET})?",
    re.I,
)
_CHAINAGE_METERS = re.compile(
    r"\bCHAINAGE\s*[:=]?\s*(\d+(?:\.\d+)?)(?![\d.]|,\d|\s*\+)"
    r"(?:\s*(?:[-–]|\bTO\b)\s*(?:CHAINAGE\s*[:=]?\s*)?"
    r"(\d+(?:\.\d+)?)(?![\d.]|,\d|\s*\+))?",
    re.I,
)
_CHAINAGE_RANGE = re.compile(
    r"\bCHAINAGE\s*[:=]?\s*(\d+(?:\.\d+)?)"
    r"(?:\s*\+\s*([+-]?\d+(?:\.\d+)?))?"
    r"\s*(?:[-–]|\bTO\b)\s*(?:CHAINAGE\s*[:=]?\s*)?"
    r"(\d+(?:\.\d+)?)(?:\s*\+\s*([+-]?\d+(?:\.\d+)?))?"
    r"(?![\d.]|,\d|\s*\+)", re.I,
)


def has_ambiguous_chainage(text: str) -> bool:
    """Mixed bare/plus endpoints do not establish the bare endpoint's units."""
    return any((m[2] is None)!=(m[4] is None) for m in _CHAINAGE_RANGE.finditer(str(text or '')))


def has_bounded_nonoverlap(left: str, right: str) -> bool:
    """Exclude overlap using ordered min/max endpoints, without filling gaps.

    Mixed bare/plus ranges retain an unknown endpoint. Under the explicit
    min/max ordering assumption, a known maximum bounds the interval above;
    a known minimum bounds it below. Touching bounds have zero overlap.
    """
    def bounds(text):
        intervals=[]
        def consume(match):
            if (match[2] is None)==(match[4] is None):return match[0]
            if match[2] is None:
                intervals.append((float('-inf'),_metres(match[3],match[4])))
            else:
                intervals.append((_metres(match[1],match[2]),float('inf')))
            return ' '*len(match[0])
        remaining=_CHAINAGE_RANGE.sub(consume,str(text or ''))
        ranges,points=parse_chainage(remaining)
        if points:return None
        return intervals+ranges
    a,b=bounds(left),bounds(right)
    return bool(a and b and all(min(a1,b1)<=max(a0,b0) for a0,a1 in a for b0,b1 in b))


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
_BRIDGE_NUMBER = re.compile(
    r"\bBRIDGE\s*(?:(?:NO\.?|NUMBER|#)\s*)?"
    r"(\d+[A-Z]?|VIII|VII|VI|IV|III|II|IX|X|V|I)\b", re.I,
)


def has_structure_identity_conflict(left: str, right: str) -> bool:
    """Different explicit bridge numbers identify different structures.

    Missing labels do not resolve identity; a title listing several bridges
    can share a numbered structure with another title and is not vetoed here.
    """
    def numbers(text):
        result=set()
        for match in _BRIDGE_NUMBER.finditer(str(text or '')):
            value=match[1].upper()
            result.add(str(int(value)) if value.isdigit() else _ROMAN_VALUES.get(value,value))
        return result
    a,b=numbers(left),numbers(right)
    return bool(a and b and a.isdisjoint(b))


def direction_signals(text: str) -> dict[str, set[str]]:
    """Return explicit directional signals, including common Spanish forms."""
    normalized = re.sub(r"[^A-Z0-9]+", " ", str(text or "").upper())
    result: dict[str, set[str]] = {}
    for token in normalized.split():
        if token in _DIRECTION_ALIASES:
            axis, direction = _DIRECTION_ALIASES[token]
            result.setdefault(axis, set()).add(direction)
    return result


@lru_cache(maxsize=200000)
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
    text=str(text or "")
    # Mixed endpoint notation is incomplete: do not assume that a bare offset
    # supplies meters or silently infer its missing kilometer component.
    ranges=[];points=[]
    def consume(match):
        if (match[2] is None)!=(match[4] is None):
            if match[2] is not None:points.append(_metres(match[1],match[2]))
            if match[4] is not None:points.append(_metres(match[3],match[4]))
            return ' '*len(match[0])
        start=_metres(match[1],match[2]) if match[2] is not None else float(match[1])
        end=_metres(match[3],match[4]) if match[4] is not None else float(match[3])
        ranges.append((min(start,end),max(start,end)))
        return ' '*len(match[0])
    text=_CHAINAGE_RANGE.sub(consume,text)
    matches=list(_PATTERN.finditer(text))
    paired=set()
    # Printed/OCR titles sometimes omit the dash between two repeated labels:
    # "Station 1+215 Station 2+065". Accept exactly two consecutive, explicitly
    # labeled points separated only by whitespace. A longer station list, bare
    # point list, or intervening place/scope text does not define a range.
    def family(match):
        marker=re.match(r'^(STA(?:TION)?|CHAINAGE|KM|KILOMET(?:ER|RE)|K)\.?\s*[:=]?',match[0],re.I)
        return ('station' if marker[1].upper().startswith(('STA','CHAINAGE')) else 'kilometer') if marker else None
    def connected(a,b):
        separator=text[a.end():b.start()]
        # The offset regex can already consume trailing whitespace.
        whitespace=bool(separator) or a[0][-1:].isspace()
        return a.group(3) is None and b.group(3) is None and family(a) is not None and family(a)==family(b) and whitespace and bool(re.fullmatch(r'\s*',separator))
    for i in range(len(matches)-1):
        a,b=matches[i:i+2]
        if not connected(a,b):continue
        if (i>0 and connected(matches[i-1],a)) or (i+2<len(matches) and connected(b,matches[i+2])):continue
        start=_metres(a.group(1),a.group(2));end=_metres(b.group(1),b.group(2))
        ranges.append((min(start,end),max(start,end)));paired.update((i,i+1))
    for index,match in enumerate(matches):
        if index in paired:continue
        start = _metres(match.group(1), match.group(2))
        if match.group(3) is None:
            points.append(start)
            continue
        end = _metres(match.group(3), match.group(4))
        ranges.append((min(start, end), max(start, end)))
    # Bare values following an explicit Chainage label denote meter offsets.
    # Do not infer offsets from unlabeled road IDs, amounts or other numbers.
    for match in _CHAINAGE_METERS.finditer(text):
        if any(match.start()<m.end() and m.start()<match.end() for m in matches):
            continue
        start=float(match[1])
        if match[2] is None:
            points.append(start)
        else:
            end=float(match[2]);ranges.append((min(start,end),max(start,end)))
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
