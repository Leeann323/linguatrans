"""设置项与默认行为测试。

对应产品决策：
    - 硬字幕为默认，用户可在设置里改为软字幕
    - 语音识别自带小模型，用户可换更大档位
    - OCR 同时保留手动框选与全屏识别
    - 中英字幕样式可分别调整
"""

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from linguatrans.io import asr  # noqa: E402
from linguatrans.ui.settings import Settings, config_dir  # noqa: E402


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """把配置目录指到临时目录，避免污染真实配置。"""
    target = tmp_path / "cfg"
    target.mkdir()
    monkeypatch.setattr("linguatrans.ui.settings.config_dir", lambda: target)
    return target


# ---------------- 默认值 ----------------

def test_hard_subtitle_is_default():
    """产品决策：默认硬字幕，用户可自选软字幕。"""
    assert Settings().hard_subtitle is True


def test_soft_subtitle_selectable():
    s = Settings()
    s.hard_subtitle = False
    assert s.hard_subtitle is False


def test_default_model_is_small_and_changeable():
    """自带模型不宜太大，且必须能换成更大档位。"""
    s = Settings()
    assert s.model_name == asr.DEFAULT_MODEL
    assert asr.DEFAULT_MODEL == "small", "默认档位应与产品决策一致"

    for bigger in ("medium", "large-v3"):
        s.model_name = bigger
        assert s.model_name == bigger


def test_available_models_listed():
    names = list(asr.MODEL_SIZES)
    assert "small" in names
    assert "medium" in names
    assert "large-v3" in names
    # 档位应从快到准有序排列
    assert names.index("tiny") < names.index("small") < names.index("large-v3")


def test_model_size_labels_present():
    """界面上要能告诉用户每个档位多大，便于取舍。"""
    for name, size in asr.MODEL_SIZES.items():
        assert isinstance(size, str) and size, f"{name} 缺少体积说明"


def test_bilingual_default_and_style_split():
    s = Settings()
    assert s.bilingual is True, "默认中英双语字幕"
    style = s.subtitle_style()
    assert style.en_size > 0 and style.zh_size > 0
    assert style.en_color and style.zh_color


def test_style_reflects_edits():
    s = Settings()
    s.en_size = 40
    s.zh_size = 44
    s.margin_v = 60
    style = s.subtitle_style()
    assert style.en_size == 40
    assert style.zh_size == 44
    assert style.margin_v == 60


def test_ocr_modes_both_available():
    """产品决策：手动框选与全屏识别都保留。"""
    from linguatrans.io import screen

    assert hasattr(screen, "recognize_region"), "应保留手动框选识别"
    assert hasattr(screen, "recognize_screen"), "应保留全屏识别"


# ---------------- 存取 ----------------

def test_save_and_load_roundtrip(isolated_config):
    s = Settings()
    s.model_name = "medium"
    s.hard_subtitle = False
    s.zh_size = 42
    s.recent = ["/tmp/a", "/tmp/b"]
    s.save()

    back = Settings.load()
    assert back.model_name == "medium"
    assert back.hard_subtitle is False
    assert back.zh_size == 42
    assert back.recent == ["/tmp/a", "/tmp/b"]


def test_load_missing_file_returns_defaults(isolated_config):
    back = Settings.load()
    assert back.model_name == asr.DEFAULT_MODEL
    assert back.hard_subtitle is True


def test_load_broken_json_falls_back(isolated_config):
    (isolated_config / "settings.json").write_text("{坏掉的 json", encoding="utf-8")
    back = Settings.load()
    assert back.model_name == asr.DEFAULT_MODEL


def test_load_ignores_unknown_keys(isolated_config):
    """旧版本写的字段不该让新版本启动失败。"""
    (isolated_config / "settings.json").write_text(
        json.dumps({"model_name": "base", "已废弃字段": 1}),
        encoding="utf-8",
    )
    back = Settings.load()
    assert back.model_name == "base"


def test_saved_file_is_readable_json(isolated_config):
    Settings().save()
    data = json.loads((isolated_config / "settings.json").read_text(encoding="utf-8"))
    assert "model_name" in data
    assert "hard_subtitle" in data
