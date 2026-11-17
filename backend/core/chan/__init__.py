"""Causal daily Chan structures on a fixed, ordered price series.

Geometry is indexed by the observation where a price occurred. Replay events
are indexed by the observation at which the geometry was knowable.
"""

from dataclasses import dataclass

SCHEMA = "quantsandbox.chan-structure.v1"
ALGORITHM = "daily-chan-v1"
LAYERS = ("merged_bars", "fractals", "strokes", "segments", "centers")


@dataclass(frozen=True, slots=True)
class Candle:
    start: int
    end: int
    low: float
    high: float
    low_at: int
    high_at: int

    def merge(self, other: "Candle", direction: int) -> "Candle":
        # A directional merge keeps the existing source on an equal extreme.
        choose = max if direction > 0 else min
        low = choose(self.low, other.low)
        high = choose(self.high, other.high)
        return Candle(self.start, other.end, low, high,
                      self.low_at if low == self.low else other.low_at,
                      self.high_at if high == self.high else other.high_at)


def _contains(left: tuple[float, float], right: tuple[float, float]) -> bool:
    return ((left[0] <= right[0] and right[1] <= left[1])
            or (right[0] <= left[0] and left[1] <= right[1]))


def _ordered(left: tuple[float, float], right: tuple[float, float]) -> int:
    if _contains(left, right):
        return 0
    return 1 if right[1] > left[1] else -1


@dataclass(frozen=True, slots=True)
class Fractal:
    position: int
    at: int
    price: float
    direction: int
    left: Candle
    middle: Candle
    right: Candle

    @property
    def id(self) -> str:
        return f"fractal:{self.at}"


def _fractal(groups: list[Candle], right_at: int) -> Fractal | None:
    left, middle, right = groups[right_at - 2:right_at + 1]
    arriving = _ordered((left.low, left.high), (middle.low, middle.high))
    leaving = _ordered((middle.low, middle.high), (right.low, right.high))
    if not arriving or arriving == leaving or not leaving:
        return None
    at, price = (middle.high_at, middle.high) if arriving > 0 else (middle.low_at, middle.low)
    return Fractal(right_at - 1, at, price, arriving, left, middle, right)


def _valid_stroke(start: Fractal, end: Fractal) -> bool:
    top, bottom = (end, start) if end.direction > 0 else (start, end)
    return (end.position - start.position >= 4 and top.middle.low > bottom.middle.low
            and top.middle.high > bottom.middle.high)


def _accept_pivot(pivots: list[Fractal], pivot: Fractal) -> bool:
    if not pivots:
        pivots.append(pivot)
        return True
    last = pivots[-1]
    if last.direction == pivot.direction:
        more_extreme = pivot.direction * (pivot.price - last.price) > 0
        if more_extreme and (len(pivots) == 1 or _valid_stroke(pivots[-2], pivot)):
            pivots[-1] = pivot
            return True
        return False
    if not _valid_stroke(last, pivot):
        return False
    pivots.append(pivot)
    return True


@dataclass(frozen=True, slots=True)
class Stroke:
    start: Fractal
    end: Fractal

    def band(self, direction: int) -> tuple[float, float]:
        first = direction * self.start.price
        last = direction * self.end.price
        return min(first, last), max(first, last)


def _append_feature(features: list[tuple[float, float]], band: tuple[float, float]) -> bool:
    """Normalize consecutive features in one sequence, oriented toward a top."""
    if features and _contains(features[-1], band):
        prior = features[-1]
        choose = max if len(features) == 1 or prior[1] > features[-2][1] else min
        features[-1] = (choose(prior[0], band[0]), choose(prior[1], band[1]))
        return False
    features.append(band)
    return True


def _has_overlap(strokes: list[Stroke], start: int) -> bool:
    bands = [stroke.band(1) for stroke in strokes[start:start + 3]]
    return len(bands) == 3 and max(band[0] for band in bands) <= min(band[1] for band in bands)


def _opposite_turn(strokes: list[Stroke], turn: int, direction: int, pivot: float) -> int | None:
    features: list[tuple[float, float]] = []
    for index in range(turn + 1, len(strokes), 2):
        if direction * strokes[index].end.price > pivot:
            break
        appended = _append_feature(features, strokes[index].band(-direction))
        if appended and len(features) >= 3:
            left, middle, right = features[-3:]
            if _ordered(left, middle) == 1 and _ordered(middle, right) == -1:
                return index
    return None


def _turn_proof(strokes: list[Stroke], turn: int, direction: int,
                left: tuple[float, float]) -> tuple[int, str] | None:
    middle = strokes[turn].band(direction)
    pivot = middle[1]
    if middle[1] < left[1]:
        return None
    if middle[0] < left[0]:
        # Lesson 71: the reversal itself breaks the previous characteristic
        # range. It still needs an overlapping opposite sequence and follow-through.
        if not _has_overlap(strokes, turn):
            return None
        for index in range(turn + 2, len(strokes), 2):
            if direction * strokes[index - 1].end.price > pivot:
                return None
            if direction * strokes[index].end.price < middle[0]:
                return index, "first_break"
        return None
    if _ordered(left, middle) != 1:
        return None
    gap = left[1] < middle[0]
    for index in range(turn + 2, len(strokes), 2):
        right = strokes[index].band(direction)
        if right[1] > pivot:
            return None
        if _contains(middle, right):
            middle = (max(middle[0], right[0]), pivot)
            continue
        if _ordered(middle, right) != -1:
            return None
        if not gap:
            return index, "overlap"
        opposite_at = _opposite_turn(strokes, turn, direction, pivot)
        if opposite_at is not None:
            return max(index, opposite_at), "gap_reversal"
        return None
    return None


@dataclass(frozen=True, slots=True)
class Segment:
    start: int
    end: int  # Exclusive stroke index; also the next segment's starting index.
    proof: int | None = None
    rule: str | None = None


def _find_segment(strokes: list[Stroke], start: int) -> Segment | None:
    direction = strokes[start].end.direction
    features = [strokes[start + 1].band(direction)]
    peak = direction * strokes[start].end.price
    first: Segment | None = None
    for turn in range(start + 3, len(strokes), 2):
        if first is not None and first.proof is not None and turn >= first.proof:
            break
        endpoint = direction * strokes[turn - 1].end.price
        if endpoint >= peak:
            proof = _turn_proof(strokes, turn, direction, features[-1])
            if proof is not None and (first is None or first.proof is None or proof[0] < first.proof):
                first = Segment(start, turn, proof[0], proof[1])
            peak = endpoint
        _append_feature(features, strokes[turn].band(direction))
    return first


def _next_break(prices: list[float], direction: int) -> list[int]:
    """First later pivot strictly beyond each price in the given direction."""
    waiting: list[int] = []
    result = [len(prices)] * len(prices)
    for index, price in enumerate(prices):
        while waiting and direction * (price - prices[waiting[-1]]) > 0:
            result[waiting.pop()] = index
        waiting.append(index)
    return result


def _initial_segment(strokes: list[Stroke]) -> tuple[int, int] | None:
    """Choose an opening direction only once one side of the first stroke breaks."""
    if len(strokes) < 3:
        return None
    prices = [strokes[0].start.price, *(stroke.end.price for stroke in strokes)]
    breaks_above = _next_break(prices, 1)
    breaks_below = _next_break(prices, -1)
    for start in range(len(strokes) - 2):
        if not _has_overlap(strokes, start):
            continue
        forward, backward = (breaks_above, breaks_below) if strokes[start].end.direction > 0 else (
            breaks_below, breaks_above)
        if forward[start + 1] < backward[start]:
            return start, forward[start + 1] - 1
    return None


def _segment_tail(strokes: list[Stroke], start: int) -> list[Segment]:
    direction = strokes[start].end.direction
    last = max(range(start + 2, len(strokes), 2),
               key=lambda index: direction * strokes[index].end.price)
    if direction * strokes[last].end.price < direction * strokes[start].end.price:
        return []
    return [Segment(start, last + 1)]


def _segments(strokes: list[Stroke], completed: list[Segment]) -> list[Segment]:
    opening_evidence = -1
    if completed:
        start = completed[-1].end
    else:
        opening = _initial_segment(strokes)
        if opening is None:
            return []
        start, opening_evidence = opening
    # A single unfinished candidate stroke may move. Proof carried by it can
    # be shown, but can never lock a segment or its downstream center.
    while _has_overlap(strokes, start):
        result = _find_segment(strokes, start)
        if result is None:
            return _segment_tail(strokes, start)
        if opening_evidence == len(strokes) - 1 or result.proof == len(strokes) - 1:
            return [result]
        completed.append(result)
        start = result.end
    return []


class Replay:
    def __init__(self, dates: list[str]):
        self.dates = dates
        self.frames: list[dict] = []
        self.events: list[dict] = []
        self.state: dict[str, dict[str, dict]] = {layer: {} for layer in LAYERS}
        self.first_seen: dict[str, int] = {}
        self.index = 0

    def emit(self, layer: str, action: str, structure: dict) -> None:
        self.events.append({"index": self.index, "date": self.dates[self.index],
                            "layer": layer, "action": action, "structure": structure})

    def structure(self, id_: str, start: int, end: int, low: float, high: float,
                  confirmed: bool, **details) -> dict:
        return {"id": id_, "status": "confirmed" if confirmed else "candidate",
                "start_index": start, "end_index": end,
                "start_date": self.dates[start], "end_date": self.dates[end],
                "high": high, "low": low, **details}

    def update(self, layer: str, geometry: dict) -> None:
        identifier = geometry["id"]
        previous = self.state[layer].get(identifier)
        confirmed = geometry["status"] == "confirmed"
        confirmation = previous.get("confirmed_index") if previous else None
        first_at = self.first_seen.setdefault(identifier, self.index)
        confirmed_at = (self.index if confirmation is None else confirmation) if confirmed else None
        result = {**geometry, "first_seen_index": first_at, "first_seen_date": self.dates[first_at],
                  "confirmed_index": confirmed_at,
                  "confirmed_date": self.dates[confirmed_at] if confirmed_at is not None else None}
        if result == previous:
            return
        if confirmed and confirmation is None:
            action = "confirmed"
        else:
            action = "revised" if previous else "created"
        self.state[layer][identifier] = result
        self.emit(layer, action, result)

    def replace(self, layer: str, geometries: list[dict]) -> None:
        identifiers = {geometry["id"] for geometry in geometries}
        for identifier in sorted(self.state[layer].keys() - identifiers):
            self.emit(layer, "removed", self.state[layer].pop(identifier))
        for geometry in geometries:
            self.update(layer, geometry)

    def candle(self, candle: Candle, confirmed: bool) -> None:
        self.update("merged_bars", self.structure(
            f"merged:{candle.start}", candle.start, candle.end, candle.low, candle.high, confirmed,
            low_index=candle.low_at, high_index=candle.high_at,
        ))

    def fractal(self, pivot: Fractal) -> None:
        # The right candle may still absorb bars in its known direction, but
        # that cannot undo this strict high/low turn against the middle candle.
        self.update("fractals", self.structure(
            pivot.id, pivot.left.start, pivot.right.start, pivot.middle.low, pivot.middle.high, True,
            index=pivot.at, date=self.dates[pivot.at], price=pivot.price,
            kind="top" if pivot.direction > 0 else "bottom",
        ))

    def move(self, layer: str, start: Fractal, end: Fractal,
             confirmed: bool, **details) -> dict:
        return self.structure(
            f"{layer[:-1]}:{start.at}", start.at, end.at,
            min(start.price, end.price), max(start.price, end.price), confirmed,
            direction="up" if end.direction > 0 else "down", start_price=start.price,
            end_price=end.price, start_id=start.id, end_id=end.id, **details,
        )

    @staticmethod
    def center_relation(prior: dict, range_low: float, range_high: float,
                        lower: float, upper: float) -> dict:
        earlier_low = prior["range_low"]
        earlier_high = prior["range_high"]
        if range_low > earlier_high:
            relation = "disjoint_above"
        elif range_high < earlier_low:
            relation = "disjoint_below"
        elif max(range_low, earlier_low) == min(range_high, earlier_high):
            relation = "touching"
        else:
            relation = "overlapping"
        separate_bands = lower > prior["upper"] or upper < prior["lower"]
        return {"previous_center_id": prior["id"], "previous_range_relation": relation,
                "expansion_candidate": separate_bands and relation in {"touching", "overlapping"}}

    def centers(self, segments: list[dict]) -> list[dict]:
        result: list[dict] = []
        start = 0
        while start + 3 <= len(segments):
            members = segments[start:start + 3]
            lower = max(segment["low"] for segment in members)
            upper = min(segment["high"] for segment in members)
            if lower >= upper:
                start += 1
                continue
            confirmed = members[-1]["status"] == "confirmed"
            phase = "active" if confirmed else "forming"
            closed_by = None
            extend = start + 4
            # In the alternating sequence, members A and C set orientation.
            # Extend on a same-direction range that still touches the fixed band.
            while confirmed and extend < len(segments) and segments[extend]["status"] == "confirmed":
                segment = segments[extend]
                if segment["high"] < lower or segment["low"] > upper:
                    phase = "closed"
                    closed_by = segment["id"]
                    break
                members.extend(segments[extend - 1:extend + 1])
                extend += 2
            first = members[0]["start_index"]
            range_low = min(segment["low"] for segment in members)
            range_high = max(segment["high"] for segment in members)
            comparison = (self.center_relation(result[-1], range_low, range_high, lower, upper)
                          if result else {"previous_center_id": None, "previous_range_relation": None,
                                          "expansion_candidate": False})
            result.append(self.structure(
                f"center:{first}", first, members[-1]["end_index"], lower, upper, confirmed,
                lower=lower, upper=upper, phase=phase, direction=members[0]["direction"],
                segment_ids=[segment["id"] for segment in members], closed_by=closed_by,
                range_low=range_low, range_high=range_high, **comparison,
            ))
            if phase != "closed":
                break
            start = extend
        return result

    def finish(self) -> dict:
        return {"schema": SCHEMA, "algorithm": ALGORITHM, "frames": self.frames, "events": self.events,
                "structures": {layer: list(items.values()) for layer, items in self.state.items()}}


def _add_candle(groups: list[Candle], candle: Candle, direction: int) -> int:
    previous = groups[-1]
    movement = _ordered((previous.low, previous.high), (candle.low, candle.high))
    if movement:
        groups.append(candle)
        return movement
    groups[-1] = previous.merge(candle, direction)
    return direction


def recognize_daily(bars: list[dict]) -> dict:
    """Recognize every as-of frame from normalized chronological daily bars."""
    replay = Replay([bar["date"] for bar in bars])
    pending: list[Candle] = []
    groups: list[Candle] = []
    pivots: list[Fractal] = []
    completed_segments: list[Segment] = []
    direction = 0
    provisional_head: Candle | None = None
    for index, bar in enumerate(bars):
        replay.index = index
        event_start = len(replay.events)
        candle = Candle(index, index, float(bar["low"]), float(bar["high"]), index, index)
        previous_length = len(groups)
        if direction:
            direction = _add_candle(groups, candle, direction)
            if len(groups) > previous_length:
                replay.candle(groups[-2], True)
            replay.candle(groups[-1], False)
        else:
            if pending:
                direction = _ordered((pending[-1].low, pending[-1].high), (candle.low, candle.high))
            pending.append(candle)
            if direction:
                groups.append(pending[0])
                for item in pending[1:]:
                    direction = _add_candle(groups, item, direction)
                for position, group in enumerate(groups):
                    replay.candle(group, position < len(groups) - 1)
                pending.clear()
            else:
                head = provisional_head or candle
                provisional_head = Candle(head.start, index, min(head.low, candle.low),
                                          max(head.high, candle.high),
                                          candle.low_at if candle.low < head.low else head.low_at,
                                          candle.high_at if candle.high > head.high else head.high_at)
                replay.candle(provisional_head, False)

        pivots_changed = False
        for right_at in range(max(2, previous_length), len(groups)):
            pivot = _fractal(groups, right_at)
            if pivot is not None:
                replay.fractal(pivot)
                pivots_changed = _accept_pivot(pivots, pivot) or pivots_changed
        if pivots_changed and len(pivots) > 1:
            strokes = [Stroke(start, end) for start, end in zip(pivots, pivots[1:])]
            replay.replace("strokes", [replay.move("strokes", stroke.start, stroke.end,
                                                  number < len(strokes) - 1)
                                       for number, stroke in enumerate(strokes)])
            tail = _segments(strokes, completed_segments)
            segment_rows = []
            for number, segment in enumerate([*completed_segments, *tail]):
                confirmed = number < len(completed_segments)
                segment_rows.append(replay.move(
                    "segments", strokes[segment.start].start, strokes[segment.end - 1].end, confirmed,
                    confirmation_rule=segment.rule, evidence_stroke_index=segment.proof,
                    start_stroke_index=segment.start, end_stroke_index=segment.end - 1,
                ))
            replay.replace("segments", segment_rows)
            replay.replace("centers", replay.centers(segment_rows))
        replay.frames.append({"index": index, "date": replay.dates[index],
                              "event_start": event_start, "event_end": len(replay.events)})
    return replay.finish()
