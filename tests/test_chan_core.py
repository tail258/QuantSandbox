from datetime import date, timedelta

import pytest

from backend.core.chan import Replay, recognize_daily


def bars_from_bands(bands):
    return [
        {"date": (date(2020, 1, 1) + timedelta(days=index)).isoformat(),
         "open": (low + high) / 2, "close": (low + high) / 2,
         "low": low, "high": high, "volume": 100}
        for index, (low, high) in enumerate(bands)
    ]


def waveform(vertices, steps=5):
    lengths = [steps] * (len(vertices) - 1) if isinstance(steps, int) else steps
    series = [start + (end - start) * offset / length
              for start, end, length in zip(vertices, vertices[1:], lengths)
              for offset in range(length)]
    series.append(vertices[-1])
    return bars_from_bands([(price - .02, price + .02) for price in series])


BASE = [13, 10, 16, 12, 20, 14, 17, 9, 15, 11, 18, 12, 15]
OVERLAP = BASE + [8, 14, 10, 17, 11, 14, 7, 13, 9, 16, 10, 13, 6]
GAP = [13, 10, 16, 12, 22, 18, 20, 13, 17, 14, 19, 12, 16, 13]
FIRST_BREAK = [13, 10, 16, 12, 20, 11, 17, 9, 15, 10, 16, 11, 15]


def test_containment_keeps_extreme_source_and_fractal_uses_third_group():
    # First two intervals are included, so their envelope only becomes an
    # upward merge once bars 1 and 2 show a strict direction. The opposite
    # merge at 3-4 keeps the low's earlier occurrence on equality.
    bars = bars_from_bands([(9, 13), (10, 12), (11, 14), (8, 12), (8, 11), (9, 13)])
    result = recognize_daily(bars)
    assert [(g["start_index"], g["end_index"], g["low"], g["high"], g["low_index"], g["high_index"])
            for g in result["structures"]["merged_bars"]] == [
        (0, 1, 10, 13, 1, 0), (2, 2, 11, 14, 2, 2),
        (3, 4, 8, 11, 3, 4), (5, 5, 9, 13, 5, 5),
    ]
    before_direction = recognize_daily(bars[:2])["structures"]
    assert len(before_direction["merged_bars"]) == 1
    assert before_direction["merged_bars"][0]["status"] == "candidate"
    assert before_direction["merged_bars"][0]["low"] == 9
    assert [(f["kind"], f["price"], f["index"], f["confirmed_index"])
            for f in result["structures"]["fractals"]] == [
        ("top", 14, 2, 3), ("bottom", 8, 3, 5),
    ]


def test_strict_stroke_revises_tail_while_confirmed_endpoints_keep_original_dates():
    bars = waveform([13, 10, 16, 15, 18, 12, 16], [5, 5, 1, 1, 5, 5])
    result = recognize_daily(bars)
    moves = [event for event in result["events"]
             if event["layer"] == "strokes" and event["structure"]["id"] == "stroke:5"]
    assert [(event["action"], event["structure"]["end_index"], event["index"]) for event in moves] == [
        ("created", 10, 11), ("revised", 12, 13), ("confirmed", 12, 18),
    ]
    assert [(stroke["direction"], stroke["start_index"], stroke["end_index"], stroke["status"])
            for stroke in result["structures"]["strokes"]] == [
        ("up", 5, 12, "confirmed"), ("down", 12, 17, "candidate"),
    ]
    assert moves[-1]["structure"]["first_seen_index"] == 11


def test_replacing_a_stroke_tail_must_preserve_strict_top_and_bottom_ranges():
    bars = bars_from_bands([(13, 14), (12, 13), (11, 12), (9, 10), (10, 11), (11, 12),
                           (12, 13), (15, 16), (7, 13), (8, 20), (6, 14)])
    structures = recognize_daily(bars)["structures"]
    assert structures["fractals"][-1]["price"] == 20
    assert structures["fractals"][-1]["kind"] == "top"
    assert len(structures["strokes"]) == 1
    assert structures["strokes"][0]["end_index"] == 7


def test_opening_range_waits_for_direction_then_lets_earliest_valid_segment_start():
    bars = waveform([13, 10, 20, 12, 18, 9, 15, 11, 17, 13, 16, 8, 14, 10, 16])
    assert not recognize_daily(bars[:22])["structures"]["segments"]
    first = recognize_daily(bars)["structures"]["segments"][0]
    assert first["status"] == "confirmed"
    assert (first["start_index"], first["end_index"], first["direction"]) == (10, 25, "down")


@pytest.mark.parametrize(("vertices", "expected_rule", "proof", "confirmed_at"), [
    (OVERLAP, "overlap", 5, 41),
    (GAP, "gap_reversal", 8, 56),
    (FIRST_BREAK, "first_break", 5, 41),
])
@pytest.mark.parametrize("sign", [1, -1])
def test_segment_boundary_needs_its_full_rule_evidence(vertices, expected_rule, proof, confirmed_at, sign):
    bars = waveform([25 + sign * value for value in vertices])
    early = recognize_daily(bars[:confirmed_at])["structures"]["segments"][0]
    mature = recognize_daily(bars)["structures"]["segments"][0]
    assert early["status"] == "candidate"
    assert early["confirmed_index"] is None
    assert (mature["start_index"], mature["end_index"]) == (5, 20)
    assert mature["direction"] == ("up" if sign > 0 else "down")
    assert mature["confirmation_rule"] == expected_rule
    assert mature["evidence_stroke_index"] == proof
    assert mature["confirmed_index"] == confirmed_at


def test_gap_rebound_past_pivot_cancels_the_earlier_tentative_boundary():
    bars = waveform(GAP[:9] + [23, 12, 19, 13, 21, 10, 18, 13, 20])
    result = recognize_daily(bars)
    events = [event["structure"] for event in result["events"] if event["layer"] == "segments"]
    assert any(item["end_index"] == 20 and item["status"] == "candidate" for item in events)
    assert not any(item["end_index"] == 20 and item["status"] == "confirmed" for item in events)


def test_center_preserves_the_initial_band_on_extension_and_closes_on_confirmed_departure():
    expanded = recognize_daily(waveform(OVERLAP))["structures"]["centers"][0]
    assert (expanded["lower"], expanded["upper"]) == (9.98, 18.02)
    assert expanded["phase"] == "active"
    assert expanded["status"] == "confirmed"
    assert len(expanded["segment_ids"]) == 5
    assert expanded["range_low"] < expanded["lower"]
    assert expanded["range_high"] > expanded["upper"]

    result = recognize_daily(waveform(
        BASE + [2, 6, 3, 7, 4, 6, 1, 5, 2, 6, 3, 5, .8, 4, 2, 5, 3, 4, .5, 3, 1, 4, 2, 3, .3, 2]))
    first, second = result["structures"]["centers"]
    assert (first["lower"], first["upper"]) == (9.98, 18.02)
    assert first["phase"] == "closed"
    assert len(first["segment_ids"]) == 3
    assert second["segment_ids"][0] == first["closed_by"]
    assert second["upper"] < first["lower"]
    assert second["previous_center_id"] == first["id"]
    assert second["previous_range_relation"] == "disjoint_below"
    assert not second["expansion_candidate"]


def test_neighbors_can_have_disjoint_core_bands_but_overlap_in_their_surrounding_ranges():
    replay = Replay([bar["date"] for bar in bars_from_bands([(1, 2)] * 9)])
    prices = [8, 20, 5, 18, 7, 7.5, 6, 7.25, 6]
    segments = [replay.structure(f"segment:{index}", index, index + 1, min(first, last), max(first, last),
                                 True, direction="up" if first < last else "down")
                for index, (first, last) in enumerate(zip(prices, prices[1:]))]
    first, second = replay.centers(segments)
    assert second["upper"] < first["lower"]
    assert second["previous_range_relation"] == "overlapping"
    assert second["expansion_candidate"]


def test_replay_events_equal_independent_prefixes_and_reconstruct_all_layers():
    bars = waveform(OVERLAP)
    replay = recognize_daily(bars)
    state = {layer: {} for layer in replay["structures"]}
    end = 0
    for frame in replay["frames"]:
        index, start, end = frame["index"], frame["event_start"], frame["event_end"]
        assert frame["date"] == bars[index]["date"]
        prefix = recognize_daily(bars[:index + 1])
        assert replay["events"][:end] == prefix["events"]
        for event in replay["events"][start:end]:
            assert event["index"] == index
            item = event["structure"]
            assert item["end_index"] <= index
            assert item["first_seen_index"] <= index
            assert item["confirmed_index"] is None or item["confirmed_index"] <= index
            objects = state[event["layer"]]
            if event["action"] == "removed":
                assert objects.pop(item["id"])["status"] == "candidate"
            else:
                previous = objects.get(item["id"])
                if previous and previous["status"] == "confirmed":
                    assert event["layer"] == "centers"
                    assert item["lower"] == previous["lower"] and item["upper"] == previous["upper"]
                    assert item["confirmed_index"] == previous["confirmed_index"]
                objects[item["id"]] = item
        assert {layer: list(objects.values()) for layer, objects in state.items()} == prefix["structures"]
    assert end == len(replay["events"])
