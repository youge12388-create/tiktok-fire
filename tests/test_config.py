import pytest

from core.config import load_config, save_config


def test_valid_schedule_saved():
    cfg = save_config(
        {"schedule_time": "21:00", "jitter_minutes": 30, "send_gap_min": 6,
         "send_gap_max": 12, "max_friends_per_run": 0, "friends": ["a"], "messages": ["🔥"]},
        "default",
    )
    assert cfg["schedule_time"] == "21:00"
    assert load_config("default")["schedule_time"] == "21:00"


def test_bad_schedule_raises():
    with pytest.raises(ValueError):
        save_config({"schedule_time": "99:00"}, "default")


def test_gap_max_not_less_than_min():
    cfg = save_config({"send_gap_min": 12, "send_gap_max": 6}, "default")
    assert cfg["send_gap_max"] >= cfg["send_gap_min"]


def test_friends_messages_normalized():
    cfg = save_config({"friends": [" 甲 ", "", "乙"], "messages": ["x", "", "  y  "]}, "default")
    assert cfg["friends"] == ["甲", "乙"]
    # messages 只过滤空行，不去除首尾空格（与 save_config 当前行为一致）
    assert cfg["messages"] == ["x", "  y  "]
