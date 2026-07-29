#!/usr/bin/env python3
"""
voice_player.py — reproduce composiciones de voz usando clips pregrabados

Uso:
  from macapp.voice_player import compose_and_play
  compose_and_play("whale_alert", ["high_vol_puts", "in"], ["qqq"], ["bounce_likely"])

El motor:
1. Busca clips en voice_bank/ (idempotente, skippea si no existe)
2. Concatena con afplay secuencial (gap mínimo)
3. Fallback: say del sistema si falta un clip
"""

import subprocess
import json
import sys
from pathlib import Path
from time import sleep

# Rutas
REPO_ROOT = Path(__file__).parent.parent
VOICE_BANK = REPO_ROOT / "macapp" / "voice_bank"
SEGMENTS_FILE = REPO_ROOT / "macapp" / "voice_segments.json"
SUPPORT_DIR = Path("~/Library/Application Support/ib-trader").expanduser()
VOICE_CACHE = SUPPORT_DIR / "voice_cache"
VOICE_CACHE.mkdir(parents=True, exist_ok=True)

def load_segments():
    """Carga el inventario de segmentos."""
    if SEGMENTS_FILE.exists():
        return json.load(SEGMENTS_FILE.open())
    return {"segments": {}}

def find_segment_text(seg_id):
    """Busca el texto de un segmento por ID."""
    data = load_segments()
    for category, segments in data.get("segments", {}).items():
        for seg in segments:
            if seg["id"] == seg_id:
                return seg["text"]
    return None

def get_clip_path(seg_id):
    """Retorna la ruta del clip (o None si no existe)."""
    # Buscar en qué categoría está el segmento
    data = load_segments()
    for category, segments in data.get("segments", {}).items():
        for seg in segments:
            if seg["id"] == seg_id:
                slug = f"{category}_{seg_id}"
                clip = VOICE_BANK / f"{slug}.mp3"
                if clip.exists():
                    return clip
                return None
    return None

def play_clip(clip_path):
    """Reproduce un clip con afplay."""
    try:
        subprocess.run(["afplay", str(clip_path)], timeout=30)
    except Exception as e:
        print(f"[voice_player] afplay falló: {e}", file=sys.stderr)

def fallback_say(text):
    """Fallback: reproduce con say del sistema."""
    try:
        subprocess.run(
            ["say", "-v", "Mónica", text],
            capture_output=True,
            timeout=10
        )
    except Exception as e:
        print(f"[voice_player] say falló: {e}", file=sys.stderr)

def compose_and_play(*segment_ids):
    """
    Compone y reproduce una alarma concatenando segmentos.
    
    Args:
        *segment_ids: "whale_alert", "high_vol_puts", "qqq", etc.
    
    Ejemplo:
        compose_and_play("whale_alert", "high_vol_puts", "in", "qqq", "bounce_likely")
        -> "Alerta ballena alto volumen de puts en Cue Cue Cue más probable el rebote"
    """
    if not segment_ids:
        return
    
    # Recopilar clips y fallbacks
    clips = []
    text_parts = []
    
    for seg_id in segment_ids:
        clip = get_clip_path(seg_id)
        if clip:
            clips.append(clip)
        else:
            # Fallback: encontrar texto para say
            text = find_segment_text(seg_id)
            if text:
                text_parts.append(text)
    
    # Reproducir clips secuencialmente
    for clip in clips:
        play_clip(clip)
        sleep(0.1)  # gap mínimo entre clips
    
    # Fallback: say de lo que falta
    if text_parts:
        fallback_text = " ".join(text_parts)
        print(f"[voice_player] Fallback say: {fallback_text}", file=sys.stderr)
        fallback_say(fallback_text)

if __name__ == "__main__":
    # Prueba: python3 voice_player.py whale_alert bounce_likely
    if len(sys.argv) > 1:
        compose_and_play(*sys.argv[1:])
    else:
        print("Uso: voice_player.py <seg_id1> <seg_id2> ...", file=sys.stderr)
