import importlib.util
import os
import threading


def _load():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "scripts", "notify_short.py")
    spec = importlib.util.spec_from_file_location("ibt_notify_short", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_push_es_append_only_y_no_reescribe_inode(tmp_path, monkeypatch):
    n = _load()
    path = tmp_path / "push.txt"
    monkeypatch.setattr(n, "PATH", str(path))
    n.push("UNO", "primera")
    inode = path.stat().st_ino
    n.push("DOS", "segunda")
    assert path.stat().st_ino == inode
    lines = path.read_text().splitlines()
    assert len(lines) == 2 and "UNO | primera" in lines[0] and "DOS | segunda" in lines[1]


def test_push_concurrente_no_pierde_lineas(tmp_path, monkeypatch):
    n = _load()
    path = tmp_path / "push.txt"
    monkeypatch.setattr(n, "PATH", str(path))
    threads = [threading.Thread(target=n.push, args=(f"T{i}", f"M{i}")) for i in range(80)]
    for t in threads: t.start()
    for t in threads: t.join()
    lines = path.read_text().splitlines()
    assert len(lines) == 80
    assert {line.split(" | ", 2)[1] for line in lines} == {f"T{i}" for i in range(80)}


def test_push_aplana_saltos_de_linea(tmp_path, monkeypatch):
    n = _load()
    path = tmp_path / "push.txt"
    monkeypatch.setattr(n, "PATH", str(path))
    n.push("T", "uno\ndos")
    assert len(path.read_text().splitlines()) == 1
