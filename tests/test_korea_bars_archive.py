#!/usr/bin/env python3
"""Test archiving of KRX bar files before truncation (2026-07-29)."""
import os
import sys
import tempfile
import shutil
import time
from datetime import datetime, timedelta

# Mock ROOT para simular el directorio del repo
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

# Stub de ib_insync SOLO si falta: pisarlo siempre envenenaba sys.modules para el
# resto de la suite ("cannot import name 'Stock'", cazado 2026-07-29)
try:
    import ib_insync  # noqa: F401
except ImportError:
    sys.modules["ib_insync"] = type(sys)("ib_insync")
    sys.modules["ib_insync"].IB = object
    sys.modules["ib_insync"].Contract = object
    sys.modules["ib_insync"].util = None

# Importar la función a testear
from korea_bar_bridge import bars_path, archive_bars_before_warmup


def test_archive_bars_with_content():
    """Fichero con barras -> archivado con fecha derivada de timestamp + truncado OK."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock ROOT
        data_dir = os.path.join(tmpdir, "data")
        hist_dir = os.path.join(data_dir, "history")
        os.makedirs(hist_dir, exist_ok=True)
        
        # Monkey-patch bars_path para usar tmpdir
        original_bars_path = bars_path
        
        def mock_bars_path(name):
            return os.path.join(data_dir, f"bars_{name}.txt")
        
        import korea_bar_bridge
        korea_bar_bridge.bars_path = mock_bars_path
        korea_bar_bridge.ROOT = tmpdir
        
        try:
            # Crear un fichero con 3 barras (epoch 1722240000 = 2024-07-29 00:00:00 UTC)
            bars_file = mock_bars_path("test_sym")
            os.makedirs(os.path.dirname(bars_file), exist_ok=True)
            
            with open(bars_file, "w") as f:
                f.write("1722240000 100.00 101.00 99.00 100.50 1000\n")
                f.write("1722240060 100.50 102.00 100.00 101.00 1100\n")
                f.write("1722240120 101.00 102.50 100.50 101.50 1200\n")
            
            # Llamar archive_bars_before_warmup
            result = korea_bar_bridge.archive_bars_before_warmup("test_sym")
            
            # Verificar resultado OK
            assert result is True, "archive_bars_before_warmup debería retornar True"
            
            # Verificar que se archivó en la carpeta correcta
            session_date = datetime.utcfromtimestamp(1722240000).strftime("%Y-%m-%d")
            archived_file = os.path.join(hist_dir, session_date, "bars", "test_sym_krx.txt")
            assert os.path.exists(archived_file), f"Archivo archivado no existe: {archived_file}"
            
            # Verificar contenido
            with open(archived_file) as f:
                lines = f.readlines()
            assert len(lines) == 3, f"Se esperaban 3 líneas, se encontraron {len(lines)}"
            assert "100.00 101.00" in lines[0], "Primera barra corrupta"
            
            # Verificar que el fichero original existe (será truncado en warmup después)
            assert os.path.exists(bars_file), "Fichero original debería existir aún"
        finally:
            korea_bar_bridge.bars_path = original_bars_path


def test_archive_bars_empty_file():
    """Fichero vacío -> retorna True sin archivar."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = os.path.join(tmpdir, "data")
        os.makedirs(data_dir, exist_ok=True)
        
        import korea_bar_bridge
        korea_bar_bridge.bars_path = lambda name: os.path.join(data_dir, f"bars_{name}.txt")
        korea_bar_bridge.ROOT = tmpdir
        
        # Crear archivo vacío
        bars_file = os.path.join(data_dir, "bars_empty.txt")
        open(bars_file, "w").close()
        
        result = korea_bar_bridge.archive_bars_before_warmup("empty")
        
        assert result is True, "Fichero vacío debería retornar True"
        # No debería haber archivo archivado
        hist_dir = os.path.join(tmpdir, "data", "history")
        assert not os.path.exists(hist_dir) or \
               not any(os.walk(hist_dir)), "No debería haber histórico archivado"


def test_archive_bars_no_file():
    """Fichero no existe -> retorna True sin error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = os.path.join(tmpdir, "data")
        os.makedirs(data_dir, exist_ok=True)
        
        import korea_bar_bridge
        korea_bar_bridge.bars_path = lambda name: os.path.join(data_dir, f"bars_{name}.txt")
        korea_bar_bridge.ROOT = tmpdir
        
        result = korea_bar_bridge.archive_bars_before_warmup("nonexistent")
        
        assert result is True, "Fichero inexistente debería retornar True"


def test_archive_bars_corrupted_epoch():
    """Fichero con línea sin epoch válido -> retorna False, NO trunca."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = os.path.join(tmpdir, "data")
        hist_dir = os.path.join(data_dir, "history")
        os.makedirs(hist_dir, exist_ok=True)
        
        import korea_bar_bridge
        korea_bar_bridge.bars_path = lambda name: os.path.join(data_dir, f"bars_{name}.txt")
        korea_bar_bridge.ROOT = tmpdir
        
        # Crear archivo con línea corrupta
        bars_file = os.path.join(data_dir, "bars_corrupt.txt")
        with open(bars_file, "w") as f:
            f.write("INVALID_EPOCH 100.00 101.00 99.00 100.50 1000\n")
        
        result = korea_bar_bridge.archive_bars_before_warmup("corrupt")
        
        assert result is False, "Datos corruptos debería retornar False"
        # El archivo original debe seguir existiendo
        assert os.path.exists(bars_file), "Fichero original debe seguir existiendo"


def test_archive_bars_idempotence():
    """Archivar dos veces el mismo día no duplica ni pisa mal."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = os.path.join(tmpdir, "data")
        hist_dir = os.path.join(data_dir, "history")
        os.makedirs(hist_dir, exist_ok=True)
        
        import korea_bar_bridge
        korea_bar_bridge.bars_path = lambda name: os.path.join(data_dir, f"bars_{name}.txt")
        korea_bar_bridge.ROOT = tmpdir
        
        # Primera archivación
        bars_file = os.path.join(data_dir, "bars_idem.txt")
        with open(bars_file, "w") as f:
            f.write("1722240000 100.00 101.00 99.00 100.50 1000\n")
        
        result1 = korea_bar_bridge.archive_bars_before_warmup("idem")
        assert result1 is True
        
        session_date = "2024-07-29"
        archived_file = os.path.join(hist_dir, session_date, "bars", "idem_krx.txt")
        with open(archived_file) as f:
            first_content = f.read()
        
        # Recrear el fichero con más datos y archivar de nuevo
        with open(bars_file, "w") as f:
            f.write("1722240000 100.00 101.00 99.00 100.50 1000\n")
            f.write("1722240060 100.50 102.00 100.00 101.00 1100\n")
        
        result2 = korea_bar_bridge.archive_bars_before_warmup("idem")
        assert result2 is True
        
        # Verificar que se sobrescribió (no se duplicó)
        with open(archived_file) as f:
            second_content = f.read()
        
        assert len(second_content.strip().split("\n")) == 2, "Debería haber 2 líneas (sobrescrito)"


def test_archive_bars_atomic_write():
    """Escritura atómica: tmp+replace, no partial file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = os.path.join(tmpdir, "data")
        hist_dir = os.path.join(data_dir, "history")
        os.makedirs(hist_dir, exist_ok=True)
        
        import korea_bar_bridge
        korea_bar_bridge.bars_path = lambda name: os.path.join(data_dir, f"bars_{name}.txt")
        korea_bar_bridge.ROOT = tmpdir
        
        # Crear fichero
        bars_file = os.path.join(data_dir, "bars_atomic.txt")
        with open(bars_file, "w") as f:
            f.write("1722240000 100.00 101.00 99.00 100.50 1000\n")
        
        result = korea_bar_bridge.archive_bars_before_warmup("atomic")
        assert result is True
        
        session_date = "2024-07-29"
        hist_bars_dir = os.path.join(hist_dir, session_date, "bars")
        
        # No debe haber archivo .tmp
        assert not any(f.endswith(".tmp") for f in os.listdir(hist_bars_dir)), \
            "No debe quedar fichero .tmp después de archive"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
