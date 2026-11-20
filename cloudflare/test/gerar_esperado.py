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
    # subdomínio letra-número-letra-número e nome só com números
    "u5l1.856552.com", "x5w3.scmand.com", "q3d2.wjyai.com", "r9l4.c6p4d5c6.com",
    "k9d4.t9v3k7o5.com", "A5B6.Teste.COM", "a1b2.c3d4.exemplo.com", "ab12.exemplo.com",
    "a1b2c.exemplo.com", "static.ppcabt.com", "readaloud.googleapis.com",
    "connect.facebook.net", "163.com", "1234.com", "12345.com", "123456789.com",
    "x5w3.12345.com.br",
]

# Registros com subdomínio: a nota usa o endereço completo, o bloqueio é do
# domínio principal.
REGISTROS_SUBDOMINIO = [
    {"timestamp": "2026-11-20T14:00:00Z", "domain": "ws.j5swonwsss.com", "root": "j5swonwsss.com", "status": "blocked"},
    {"timestamp": "2026-11-20T14:01:00Z", "domain": "u5l1.856552.com", "root": "856552.com", "status": "default"},
    {"timestamp": "2026-11-20T14:01:30Z", "domain": "x5w3.scmand.com", "root": "scmand.com", "status": "default"},
    {"timestamp": "2026-11-20T14:20:00Z", "domain": "q3d2.wjyai.com", "root": "wjyai.com", "status": "default"},
    {"timestamp": "2026-11-20T14:20:10Z", "domain": "connect.facebook.net", "root": "facebook.net", "status": "default"},
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
        "registros_subdominio": REGISTROS_SUBDOMINIO,
        "analise_subdominio": [[s.dominio, s.nota, s.motivos]
                               for s in b.analisar(REGISTROS_SUBDOMINIO, set())],
    }


if __name__ == "__main__":
    destino = Path(__file__).with_name("esperado.json")
    destino.write_text(json.dumps(gerar(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"gravado {destino}")
