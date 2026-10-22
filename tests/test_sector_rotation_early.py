"""
Tests for Sector Rotation's earliest-possible-change detection: the 1-week
RS field, the early_signal flag (this week's RS breaking from the 1M trend,
before it's big enough to move the slower 1M-vs-3M momentum_dir), and the
day-over-day snapshot diff (rs1m_delta) used for the "moved since last
check" panel.
"""
import modules.sector_strength as ss


def test_get_sector_rotation_includes_1w_and_early_signal_fields(monkeypatch):
    def fake_strength(ticker):
        # XLK: strong recent week breaking away from a flat month -> "up"
        if ticker == "XLK":
            return {"price": 100.0, "r1w": 3.0, "r1m": 1.0, "r3m": 5.0,
                     "rs1w": 6.0, "rs1m": 0.0, "above_50": True, "above_200": True,
                     "score": 7.0, "grade": "Strong", "grade_color": "#16c784"}
        # XLE: recent week falling off a flat month -> "down"
        if ticker == "XLE":
            return {"price": 80.0, "r1w": -3.0, "r1m": 0.0, "r3m": -2.0,
                     "rs1w": -6.0, "rs1m": 0.0, "above_50": False, "above_200": False,
                     "score": 3.0, "grade": "Weak", "grade_color": "#ea3a44"}
        return {}

    monkeypatch.setattr(ss, "_etf_strength", fake_strength)
    monkeypatch.setattr(ss, "_ROTATION_SECTORS",
                         [("Technology", "XLK", "Broad Sectors"),
                          ("Energy", "XLE", "Broad Sectors")])
    monkeypatch.setattr(ss, "_load_rotation_snapshot", lambda: {})
    monkeypatch.setattr(ss, "_save_rotation_snapshot", lambda rot: None)
    ss.get_sector_rotation.clear()

    rot = {r["etf"]: r for r in ss.get_sector_rotation()}
    assert rot["XLK"]["early_signal"] == "up"
    assert rot["XLE"]["early_signal"] == "down"
    assert rot["XLK"]["rs1w"] == 6.0
    assert rot["XLK"]["rs1m_delta"] is None  # no prior snapshot


def test_get_sector_rotation_computes_rs1m_delta_from_prior_snapshot(monkeypatch):
    def fake_strength(ticker):
        return {"price": 100.0, "r1w": 0.0, "r1m": 2.0, "r3m": 2.0,
                 "rs1w": 0.0, "rs1m": 5.0, "above_50": True, "above_200": True,
                 "score": 6.0, "grade": "Strong", "grade_color": "#16c784"}

    monkeypatch.setattr(ss, "_etf_strength", fake_strength)
    monkeypatch.setattr(ss, "_ROTATION_SECTORS", [("Technology", "XLK", "Broad Sectors")])
    monkeypatch.setattr(ss, "_load_rotation_snapshot", lambda: {"XLK": {"rs1m": 2.0}})
    monkeypatch.setattr(ss, "_save_rotation_snapshot", lambda rot: None)
    ss.get_sector_rotation.clear()

    rot = ss.get_sector_rotation()[0]
    assert rot["rs1m_prev_day"] == 2.0
    assert rot["rs1m_delta"] == 3.0


def test_snapshot_save_skips_same_day_overwrite(monkeypatch, tmp_path):
    snap_path = tmp_path / ".sector_rotation_snapshot.json"
    monkeypatch.setattr(ss, "_ROTATION_SNAPSHOT_PATH", snap_path)

    rot_day1 = [{"etf": "XLK", "rs1m": 1.0}]
    ss._save_rotation_snapshot(rot_day1)
    saved = ss.load_json(snap_path, default={})
    assert saved["XLK"]["rs1m"] == 1.0

    # Same day again with a different reading -> must NOT overwrite.
    rot_day1_later = [{"etf": "XLK", "rs1m": 9.0}]
    ss._save_rotation_snapshot(rot_day1_later)
    saved2 = ss.load_json(snap_path, default={})
    assert saved2["XLK"]["rs1m"] == 1.0
