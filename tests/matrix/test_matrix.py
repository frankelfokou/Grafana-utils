"""La matrice comandi × parametri come test della suite.

`run_matrix.run_all()` esegue ~316 combinazioni sui due file di partenza e
verifica ogni output. Qui diventa un test unico: se una combinazione regredisce,
il fallimento arriva come subTest con il nome del caso, il comando e i problemi
rilevati.
"""
from __future__ import annotations

import unittest

from . import run_matrix


class MatrixTest(unittest.TestCase):
    """Esegue la matrice completa e riporta un subTest per ogni caso fallito."""

    def test_matrice_comandi_e_parametri(self):
        outcomes, untouched = run_matrix.run_all()

        self.assertTrue(outcomes, "la matrice non ha prodotto alcun caso")
        self.assertTrue(untouched, "un file di input è stato modificato")

        failed = [outcome for outcome in outcomes if outcome.status != "PASS"]
        for outcome in failed:
            with self.subTest(case=outcome.name, source=outcome.src):
                details = "; ".join(outcome.problems) or "nessun dettaglio"
                self.fail(
                    f"{outcome.name} (sorgente {outcome.src}, exit {outcome.code}, "
                    f"comando: {' '.join(outcome.argv)}): {details}"
                )


if __name__ == "__main__":
    unittest.main()
