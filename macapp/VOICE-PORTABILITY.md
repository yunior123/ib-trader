# Voz canónica portable del Cockpit

La aplicación incluye un banco cerrado de 114 clips MP3 en español, generados
previamente con la voz Matilda elegida para ib-trader. En ejecución no hay TTS,
red, claves API, descargas ni configuración manual.

## Contrato de producción

- Fuente única: `voice_bank_texts.txt`, IDs consecutivos `001..114`.
- Audio: `voice_bank/001.mp3` … `voice_bank/114.mp3`.
- Motor: `voice_player.py`, con rutas relativas a su propio directorio.
- Reproductor del sistema: `/usr/bin/afplay`; reproduce el archivo, no genera voz.
- Bundle: `Contents/Resources/backend/{voice_player.py,voice_bank_texts.txt,voice_bank/}`.
- Política: el banco completo se valida antes del primer clip. Si falta o está
  corrupto un recurso, la voz entera queda desactivada y la app muestra un aviso.

No existe fallback a `say`, Siri, Mónica, otra voz ElevenLabs ni TTS remoto. Las
muestras y generadores que puedan existir en el repo son herramientas de desarrollo
y `bundle_backend.sh` los excluye explícitamente de la aplicación.

## QA silencioso

Validar el banco del repo sin producir audio:

```bash
python3 macapp/voice_player.py --check
```

Validar la misma disposición después de empaquetar:

```bash
python3 "macapp/ib-trader Cockpit.app/Contents/Resources/backend/voice_player.py" \
  --check
```

Solo una llamada explícita reproduce audio:

```bash
python3 macapp/voice_player.py --play 001 003 039
```

Los tests inyectan un ejecutor falso; nunca llaman a `afplay`.

## Portabilidad

`voice_player.py` resuelve el banco junto a sí mismo. Esto produce la misma
estructura en desarrollo y en un `.app` instalado en `/Applications`, Desktop o
cualquier otra ruta. No escribe dentro del bundle y no depende de `~/ib-trader`.

El build falla si no valida los 114 clips. La app vuelve a comprobarlos al arrancar
para detectar corrupción posterior y expone el estado en el menú de la barra.

## Licencia

Los clips actuales son activos pre-generados del usuario para su aplicación privada.
No se incluye la clave de ElevenLabs. Antes de redistribuir públicamente el `.app`,
hay que confirmar por separado que el plan y los términos con los que se generaron
permiten esa distribución; esta revisión técnica no sustituye una auditoría legal.
