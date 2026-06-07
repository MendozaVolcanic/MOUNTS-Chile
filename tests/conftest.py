"""
Fixtures compartidas para la suite pytest de MOUNTS-Chile.

Los modulos de produccion (scraper.py, anomalies.py, db.py) viven en la raiz
del repo. Agregamos esa raiz a sys.path para que `import scraper` funcione
cuando pytest se ejecuta desde la raiz del worktree.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

# La raiz del repo es el padre de tests/
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# --- HTML fixtures ----------------------------------------------------------

@pytest.fixture
def sample_html():
    """HTML de timeseries fiel al formato real de mounts-project.com."""
    return (FIXTURES_DIR / "timeseries_sample.html").read_text(encoding="utf-8")


# --- Trace fixtures (para anomalies.py) -------------------------------------

@pytest.fixture
def constant_trace():
    """
    Serie casi constante: el quirk #4 del snapshot. Sin MAD floor, una
    desviacion minima dispararia z-scores absurdos. Con el floor, no.
    Valores ~0.1 con un punto final levemente mayor.
    """
    n = 20
    xs = [f"2026-01-{d:02d}" for d in range(1, n + 1)]
    ys = [0.1] * (n - 1) + [0.3]
    return xs, ys


@pytest.fixture
def outlier_trace():
    """Serie estable con un outlier claro al final (anomalia aislada)."""
    n = 20
    xs = [f"2026-01-{d:02d}" for d in range(1, n + 1)]
    ys = [10.0] * (n - 1) + [200.0]
    return xs, ys


@pytest.fixture
def persistent_trace():
    """Serie estable con 3 valores altos consecutivos al final (run>=3)."""
    n = 20
    xs = [f"2026-01-{d:02d}" for d in range(1, n + 1)]
    ys = [10.0] * (n - 3) + [200.0, 210.0, 205.0]
    return xs, ys


@pytest.fixture
def flat_trace():
    """Serie totalmente plana: nunca debe disparar una anomalia."""
    n = 20
    xs = [f"2026-01-{d:02d}" for d in range(1, n + 1)]
    ys = [10.0] * n
    return xs, ys


# --- DB fixtures (para db.py) ----------------------------------------------

@pytest.fixture
def memory_db():
    """
    SQLite in-memory con el schema real de db.py y la tabla volcanoes
    poblada. NUNCA toca mounts.db. Se cierra al terminar el test.
    """
    import db as db_mod

    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(db_mod.SCHEMA)
    conn.executemany(
        "INSERT INTO volcanoes(key, name, smithsonian_id, lat, lon) VALUES(?,?,?,?,?)",
        db_mod.VOLCANES_META,
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def insert_anomaly(memory_db):
    """
    Helper para insertar una anomalia sintetica en la DB in-memory.
    Devuelve una funcion (volcano_key, product, date, zscore=4.0, value=100.0).
    """
    def _insert(volcano_key, product, date, zscore=4.0, value=100.0):
        memory_db.execute(
            """INSERT OR IGNORE INTO anomalies
               (volcano_key, product, date, value, baseline_median,
                baseline_mad, zscore, severity, detected_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (volcano_key, product, date, value, 10.0, 1.0, zscore,
             "orange", "2026-01-01T00:00:00+00:00"),
        )
        memory_db.commit()
    return _insert
