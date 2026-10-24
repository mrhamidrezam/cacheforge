"""Tests for CacheForge CLI commands."""

import pytest
from cacheforge.cli import main
from cacheforge.disk import DiskCache


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "cacheforge" in captured.out


def test_cli_benchmark(capsys):
    code = main(["benchmark", "--iterations", "500", "--cache-size", "50"])
    assert code == 0
    captured = capsys.readouterr()
    assert "LRUCache" in captured.out
    assert "LFUCache" in captured.out
    assert "FIFOCache" in captured.out
    assert "TTLCache" in captured.out


def test_cli_inspect_and_prune(tmp_path, capsys):
    cache = DiskCache(directory=tmp_path, filename="cli_test.db")
    cache.set("a", 100)
    cache.set("b", 200)
    cache.close()

    db_file = str(tmp_path / "cli_test.db")

    # Inspect
    code = main(["inspect", db_file])
    assert code == 0
    captured = capsys.readouterr()
    assert "Total Valid Entries : 2" in captured.out

    # Prune
    code = main(["prune", db_file])
    assert code == 0
    captured = capsys.readouterr()
    assert "Pruned" in captured.out


def test_cli_help(capsys):
    code = main([])
    assert code == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out or "positional arguments:" in captured.out
