import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
EXEMPLOS = RAIZ / "exemplos"


def ler_lista(nome):
    linhas = (EXEMPLOS / nome).read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in linhas if l.strip() and not l.startswith("#")]
