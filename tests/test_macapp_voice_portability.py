import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PLAYER_PATH = ROOT / "macapp" / "voice_player.py"


def load_player():
    spec = importlib.util.spec_from_file_location("macapp_voice_player", PLAYER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_portable_bank(tmp_path: Path) -> Path:
    bank = tmp_path / "voice_bank"
    bank.mkdir(parents=True)
    manifest = []
    for number in range(1, 115):
        clip_id = f"{number:03d}"
        manifest.append(f"{clip_id} | clip {clip_id}")
        (bank / f"{clip_id}.mp3").write_bytes(b"ID3portable")
    (tmp_path / "voice_bank_texts.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    return tmp_path


def test_repo_canonical_bank_is_complete_and_portable():
    player = load_player()
    manifest = player.validate_bank(ROOT / "macapp")
    assert tuple(manifest) == player.EXPECTED_IDS
    assert len(manifest) == 114


def test_bundle_shaped_layout_resolves_beside_player(tmp_path):
    player = load_player()
    base = make_portable_bank(tmp_path / "Contents" / "Resources" / "backend")
    assert len(player.validate_bank(base)) == 114


def test_playback_is_silent_under_injected_runner(tmp_path, monkeypatch):
    player = load_player()
    base = make_portable_bank(tmp_path / "backend")
    calls = []

    class FakeAfplay:
        def is_file(self):
            return True

        def __str__(self):
            return "/usr/bin/afplay"

    def fake_runner(args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(player, "AFPLAY", FakeAfplay())
    player.play_segments(["001", 39], base=base, runner=fake_runner)
    assert [Path(call[0][1]).name for call in calls] == ["001.mp3", "039.mp3"]
    assert all(call[0][0] == "/usr/bin/afplay" for call in calls)


def test_missing_clip_fails_before_any_playback(tmp_path, monkeypatch):
    player = load_player()
    base = make_portable_bank(tmp_path / "backend")
    (base / "voice_bank" / "114.mp3").unlink()
    calls = []
    with pytest.raises(player.VoiceBankError, match="faltan 114"):
        player.play_segments(["001"], base=base, runner=lambda *args, **kwargs: calls.append(args))
    assert calls == []


def test_runtime_contains_no_voice_fallback():
    source = PLAYER_PATH.read_text(encoding="utf-8")
    forbidden = ["fallback_say", '["say"', "ElevenLabs", "openai"]
    assert not any(token in source for token in forbidden)


def test_bundle_excludes_developer_voices_and_hard_validates_canonical_bank():
    bundle = (ROOT / "macapp" / "bundle_backend.sh").read_text(encoding="utf-8")
    paths = (ROOT / "macapp" / "bundled_paths.txt").read_text(encoding="utf-8")
    assert "python3 macapp/voice_player.py --check" in bundle
    assert "cp macapp/speak_with_fallback.py" not in bundle
    assert "cp macapp/generate_voice_samples.sh" not in bundle
    assert "mkdir -p \"$RES/backend/voice_samples\"" not in bundle
    assert "speak_with_fallback.py" not in paths
    assert "voice_samples/" not in paths
