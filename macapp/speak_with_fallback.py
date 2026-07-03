#!/usr/bin/env python3
"""
speak_with_fallback.py — voz inteligente para ib-trader Cockpit.app

Cadena de fallback:
1. OpenAI TTS (si OPENAI_API_KEY en config/)
2. ElevenLabs TTS (si ELEVENLABS_API_KEY en config/)
3. Piper TTS embebido (si está compilado arm64)
4. say de macOS (sistema)

Uso desde Python:
  from macapp.speak_with_fallback import speak
  speak("Alerta ballena!")
  
Uso desde línea de comandos:
  python3 macapp/speak_with_fallback.py "Alerta ballena!"
"""

import os
import sys
import subprocess
import hashlib
from pathlib import Path
from datetime import datetime

# Directorios
REPO_ROOT = Path(__file__).parent.parent
CONFIG_DIR = REPO_ROOT / "config"
SUPPORT_DIR = Path("~/Library/Application Support/ib-trader").expanduser()
VOICE_CACHE_DIR = SUPPORT_DIR / "voice_cache"
VOICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Configuración (Yunior elige después de escuchar muestras)
VOICE_LANG = "es_ES"
VOICE_VOICE = "monica"
OPENAI_MODEL = "tts-1-hd"
OPENAI_VOICE_NAME = "nova"
ELEVENLABS_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"  # Sarah (femenino, multiidioma)
PIPER_MODEL = "es_ES-medium"

def _load_key_from_env(env_file, key_name):
    """Carga una key de un fichero .env."""
    env_path = CONFIG_DIR / env_file
    if not env_path.exists():
        return None
    
    for line in env_path.read_text().splitlines():
        if line.startswith(f"{key_name}="):
            key = line.split("=", 1)[1].strip()
            return key if key else None
    return None

def _get_voice_hash(text):
    """Calcula hash MD5 de la frase para cache."""
    return hashlib.md5(text.encode()).hexdigest()

def _speak_openai(text):
    """Genera wav con OpenAI TTS y cachea."""
    key = _load_key_from_env("llm.env", "OPENAI_API_KEY")
    if not key:
        return None
    
    try:
        import openai
    except ImportError:
        return None
    
    voice_hash = _get_voice_hash(text)
    cached_wav = VOICE_CACHE_DIR / f"openai_{voice_hash}.wav"
    if cached_wav.exists():
        return cached_wav
    
    try:
        client = openai.OpenAI(api_key=key)
        response = client.audio.speech.create(
            model=OPENAI_MODEL,
            voice=OPENAI_VOICE_NAME,
            input=text,
        )
        response.stream_to_file(str(cached_wav))
        return cached_wav
    except Exception as e:
        print(f"[speak] OpenAI falló: {e}", file=sys.stderr)
        return None

def _speak_elevenlabs(text):
    """Genera wav con ElevenLabs TTS y cachea."""
    key = _load_key_from_env("feeds.env", "ELEVENLABS_API_KEY")
    if not key:
        return None
    
    try:
        from elevenlabs.client import ElevenLabs
    except ImportError:
        # pip install elevenlabs
        return None
    
    voice_hash = _get_voice_hash(text)
    cached_wav = VOICE_CACHE_DIR / f"elevenlabs_{voice_hash}.wav"
    if cached_wav.exists():
        return cached_wav
    
    try:
        client = ElevenLabs(api_key=key)
        audio = client.generate(
            text=text,
            voice=ELEVENLABS_VOICE_ID,
            model="eleven_multilingual_v2"
        )
        
        # Guardar wav
        cached_wav.write_bytes(b"".join(audio))
        return cached_wav
    except Exception as e:
        error_str = str(e).lower()
        if "quota" in error_str or "401" in error_str:
            print(f"[speak] ElevenLabs: sin créditos o quota agotada", file=sys.stderr)
        else:
            print(f"[speak] ElevenLabs falló: {e}", file=sys.stderr)
        return None

def _speak_piper(text):
    """Genera wav con Piper embebido."""
    piper_bin = Path(__file__).parent / "engine" / "piper"
    piper_model = Path(__file__).parent / "engine" / f"{PIPER_MODEL}.onnx"
    
    if not piper_bin.exists() or not piper_model.exists():
        return None
    
    voice_hash = _get_voice_hash(text)
    cached_wav = VOICE_CACHE_DIR / f"piper_{voice_hash}.wav"
    if cached_wav.exists():
        return cached_wav
    
    try:
        result = subprocess.run(
            [str(piper_bin), "--output-file", str(cached_wav)],
            input=text.encode(),
            capture_output=True,
            timeout=10
        )
        if result.returncode == 0 and cached_wav.exists():
            return cached_wav
    except Exception as e:
        print(f"[speak] Piper falló: {e}", file=sys.stderr)
    
    return None

def _speak_system(text, voice_name=None):
    """Genera wav con say de macOS."""
    voice_hash = _get_voice_hash(text)
    cached_wav = VOICE_CACHE_DIR / f"system_{voice_hash}.wav"
    
    if cached_wav.exists():
        return cached_wav
    
    try:
        cmd = ["say", "-o", str(cached_wav)]
        if voice_name:
            voice_map = {
                "monica": "Mónica",
                "paulina": "Paulina",
                "shelley_es": "Shelley (Espagnol (Espagne))",
                "eddy_es": "Eddy (Espagnol (Espagne))",
            }
            voice = voice_map.get(voice_name)
            if voice:
                cmd.extend(["-v", voice])
        
        cmd.append(text)
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        
        # Convertir de AIFF a WAV con ffmpeg
        aiff_file = Path(str(cached_wav).replace(".wav", ".aiff"))
        if aiff_file.exists():
            subprocess.run(
                ["ffmpeg", "-i", str(aiff_file), "-c:a", "pcm_s16le", "-y", str(cached_wav)],
                capture_output=True,
                timeout=10
            )
            aiff_file.unlink()
        
        if cached_wav.exists():
            return cached_wav
    except Exception as e:
        print(f"[speak] say falló: {e}", file=sys.stderr)
    
    return None

def speak(text, voice_name=None):
    """
    Reproduce texto con fallback inteligente.
    
    Cadena:
    1. OpenAI TTS
    2. ElevenLabs TTS
    3. Piper embebido
    4. say de macOS
    """
    if not text or not text.strip():
        return
    
    wav_file = None
    
    # Intentar en orden
    for motor, func in [
        ("OpenAI", _speak_openai),
        ("ElevenLabs", _speak_elevenlabs),
        ("Piper", _speak_piper),
        ("Sistema", lambda t: _speak_system(t, voice_name=voice_name or VOICE_VOICE))
    ]:
        wav_file = func(text)
        if wav_file:
            print(f"[speak] {motor}: {wav_file}", file=sys.stderr)
            break
    
    # Reproducir
    if wav_file and wav_file.exists():
        try:
            subprocess.run(["afplay", str(wav_file)], timeout=30)
        except Exception as e:
            print(f"[speak] afplay falló: {e}", file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        msg = " ".join(sys.argv[1:])
        speak(msg)
    else:
        print("Uso: speak_with_fallback.py <mensaje>", file=sys.stderr)
