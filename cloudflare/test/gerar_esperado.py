"""Gera esperado.json: as notas e a análise da versão Python, usadas pelos
testes da versão JavaScript (worker.test.mjs) para garantir que as duas
dão exatamente o mesmo resultado.

Rodar a partir da raiz do repositório:  python cloudflare/test/gerar_esperado.py
O teste tests/test_paridade.py falha se este arquivo ficar desatualizado.
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
import bloqueador_cassino as b  # noqa: E402

EXTRAS = [
    "API5.A-B-C-8.COM", "game-logo.6-q-r-s.com", "x.y.com.br", "abc123.com.br",
    "aaa111.com", "ab12cd.org", "ab1234567890.com", "a1b2c3.net", "k9.com",
    "zz9999.xyz", "web2py.com", "bet365.com", "mp3juices.com", "localhost", "",
]


def gerar() -> dict:
    def ler(nome):
        linhas = (RAIZ / "exemplos" / nome).read_text(encoding="utf-8").splitlines()
        return [l.strip() for l in linhas if l.strip() and not l.startswith("#")]

    dominios = ler("dominios_cassino.txt") + ler("dominios_legitimos.txt") + EXTRAS
    notas = {}
    for d in dominios:
        s, ms = b.nota(d)
        j, mj = b.nota(d, True)
        notas[d] = {"sozinho": [s, ms], "junto": [j, mj]}

    registros = json.loads((RAIZ / "exemplos" / "registros_exemplo.json").read_text(encoding="utf-8"))
    suspeitos = b.analisar(registros["logs"], set(registros["lista_negra"]))
    return {
        "notas": notas,
        "analise_exemplo": [[s.dominio, s.nota, s.motivos] for s in suspeitos],
    }


if __name__ == "__main__":
    destino = Path(__file__).with_name("esperado.json")
    destino.write_text(json.dumps(gerar(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"gravado {destino}")
