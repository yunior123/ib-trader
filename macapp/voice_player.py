#!/usr/bin/env python3
"""Reproductor offline del banco canónico Matilda.

La ruta es deliberadamente relativa a este fichero. Funciona sin cambios tanto en
el repo (macapp/) como dentro de Contents/Resources/backend/. No usa red, TTS ni
una voz alternativa: si el banco no es íntegro, falla antes de reproducir nada.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

EXPECTED_IDS = tuple(f"{n:03d}" for n in range(1, 115))
AFPLAY = Path("/usr/bin/afplay")
_MANIFEST_LINE = re.compile(r"^(\d{3})\s*\|\s*(\S.*)$")


class VoiceBankError(RuntimeError):
    """El banco canónico no puede usarse con seguridad."""


def canonical_paths(base: Path | None = None) -> tuple[Path, Path]:
    """Devuelve banco y manifiesto desde una raíz portable."""
    root = (base or Path(__file__).resolve().parent).resolve()
    return root / "voice_bank", root / "voice_bank_texts.txt"


def load_manifest(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise VoiceBankError(f"falta el manifiesto canónico: {path}")
    entries: dict[str, str] = {}
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = _MANIFEST_LINE.fullmatch(raw.strip())
        if not match:
            raise VoiceBankError(f"manifiesto inválido en línea {line_no}")
        clip_id, text = match.groups()
        if clip_id in entries:
            raise VoiceBankError(f"ID duplicado en manifiesto: {clip_id}")
        entries[clip_id] = text
    if tuple(entries) != EXPECTED_IDS:
        raise VoiceBankError("el manifiesto debe contener exactamente 001..114 en orden")
    return entries


def _looks_like_mp3(path: Path) -> bool:
    try:
        head = path.read_bytes()[:3]
    except OSError:
        return False
    return head == b"ID3" or (len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)


def validate_bank(base: Path | None = None) -> dict[str, str]:
    """Valida de forma silenciosa el banco completo y devuelve el manifiesto."""
    bank, manifest_path = canonical_paths(base)
    manifest = load_manifest(manifest_path)
    if not bank.is_dir():
        raise VoiceBankError(f"falta el banco canónico: {bank}")
    actual = tuple(sorted(p.stem for p in bank.glob("*.mp3")))
    if actual != EXPECTED_IDS:
        missing = sorted(set(EXPECTED_IDS) - set(actual))
        extra = sorted(set(actual) - set(EXPECTED_IDS))
        detail = []
        if missing:
            detail.append("faltan " + ",".join(missing))
        if extra:
            detail.append("sobran " + ",".join(extra))
        raise VoiceBankError("banco incompleto: " + "; ".join(detail))
    invalid = [clip_id for clip_id in EXPECTED_IDS if not _looks_like_mp3(bank / f"{clip_id}.mp3")]
    if invalid:
        raise VoiceBankError("clips MP3 inválidos: " + ",".join(invalid))
    return manifest


def play_segments(
    segment_ids: Sequence[str | int],
    *,
    base: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    """Reproduce IDs canónicos en orden; valida todo antes del primer sonido."""
    manifest = validate_bank(base)
    bank, _ = canonical_paths(base)
    ids = [f"{item:03d}" if isinstance(item, int) else str(item).zfill(3) for item in segment_ids]
    if not ids:
        raise VoiceBankError("no se solicitaron segmentos")
    unknown = [clip_id for clip_id in ids if clip_id not in manifest]
    if unknown:
        raise VoiceBankError("IDs desconocidos: " + ",".join(unknown))
    if not AFPLAY.is_file():
        raise VoiceBankError("afplay no está disponible; voz desactivada")
    for clip_id in ids:
        try:
            runner([str(AFPLAY), str(bank / f"{clip_id}.mp3")], check=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            raise VoiceBankError(f"falló el clip {clip_id}; voz desactivada") from exc


def compose_and_play(*segment_ids: str | int) -> None:
    """Alias compatible: los segmentos ahora son exclusivamente IDs 001..114."""
    play_segments(segment_ids)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Voz canónica Matilda, offline y fail-closed")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="validar sin reproducir audio")
    mode.add_argument("--play", nargs="+", metavar="ID", help="reproducir IDs 001..114")
    parser.add_argument("--base", type=Path, help="raíz portable para QA")
    args = parser.parse_args(argv)
    try:
        manifest = validate_bank(args.base)
        if args.check:
            print(f"Matilda canonical voice ready: {len(manifest)}/{len(EXPECTED_IDS)}")
        else:
            play_segments(args.play, base=args.base)
        return 0
    except VoiceBankError as exc:
        print(f"VOICE_DISABLED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
