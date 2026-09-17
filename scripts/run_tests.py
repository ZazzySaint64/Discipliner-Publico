#!/usr/bin/env python3
"""Roda todos os test_*.py da raiz do projeto e resume o resultado.

Fonte única: a CI (.github/workflows/testes.yml) chama este script, e você
roda o MESMO comando local (Windows, WSL ou Git Bash):

    python scripts/run_tests.py

Cada teste é um script solto com asserts (não pytest) — aqui só rodamos cada um
num subprocesso, com timeout, e contamos passou/falhou. Sai com código 1 se
qualquer um falhar (é o que o hook de pre-push e a CI olham).

Os 3 testes que dependem de app.run() (test_reminder, test_tutorial,
test_confirm_delete) pulam sozinhos quando a variável CI está setada — a CI já
seta; local, rodam completos.
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 180  # um app.run() que não encerra no headless não pode pendurar tudo


def main():
    tests = sorted(p.name for p in ROOT.glob("test_*.py"))
    if not tests:
        print("nenhum test_*.py encontrado em", ROOT)
        return 1

    print(f"rodando {len(tests)} testes com {sys.executable}\n")
    falhas = []
    inicio = time.monotonic()

    for t in tests:
        t0 = time.monotonic()
        try:
            r = subprocess.run(
                [sys.executable, t], cwd=ROOT,
                capture_output=True, text=True, timeout=TIMEOUT,
            )
            ok = r.returncode == 0
        except subprocess.TimeoutExpired:
            ok, r = False, None
        dt = time.monotonic() - t0

        if ok:
            print(f"  ok    {t:<26} {dt:5.1f}s")
        else:
            falhas.append(t)
            print(f"  FALHA {t:<26} {dt:5.1f}s")
            if r is None:
                print(f"        (estourou o timeout de {TIMEOUT}s)")
            else:
                cauda = (r.stdout + r.stderr).strip().splitlines()[-15:]
                for linha in cauda:
                    print(f"        {linha}")

    total = time.monotonic() - inicio
    print(f"\n{len(tests) - len(falhas)}/{len(tests)} passaram em {total:.1f}s")
    if falhas:
        print("falharam:", ", ".join(falhas))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
