# CacheForge Setup and Development Guide

This guide covers setting up your development environment, running unit tests, benchmarks, and building the distribution.

---

## 1. Prerequisites

- Python 3.9, 3.10, 3.11, 3.12, 3.13, or 3.14+
- `pip` and `git`
- Standard virtual environment tools (`venv`)

---

## 2. Installation for Development

Clone the repository and install in editable mode with development dependencies:

```bash
git clone https://github.com/mrhamidrezam/cacheforge.git
cd cacheforge

# Create a virtual environment (optional but recommended)
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate
# On Windows PowerShell:
.venv\Scripts\Activate.ps1

# Install package with development dependencies
pip install -e ".[dev]"
```

---

## 3. Running Unit Tests

Run the full test suite using `pytest`:

```bash
python -m pytest -v
```

To run with coverage (if `pytest-cov` is installed):

```bash
python -m pytest --cov=cacheforge tests/
```

---

## 4. Running Benchmarks

Execute the built-in CLI benchmark to compare the throughput and hit rates of LRU, LFU, FIFO, and TTL policies:

```bash
cacheforge benchmark --iterations 100000 --cache-size 1000
```

---

## 5. Building Distribution Packages

To generate source archives and wheels for publication:

```bash
pip install --upgrade build
python -m build
```

The resulting `.tar.gz` and `.whl` files will be placed into the `dist/` directory.
