import pytest

from bloqueador_cassino import analisar, dominio_principal, nota, transicoes_letra_numero
from conftest import ler_lista

CASSINO = ler_lista("dominios_cassino.txt")
LEGITIMOS = ler_lista("dominios_legitimos.txt")


@pytest.mark.parametrize("entrada, esperado", [
    ("api5.a-b-c-8.com", "a-b-c-8.com"),
    ("kamja7.l7alpn8c.com", "l7alpn8c.com"),
    ("x8s9m0q.com", "x8s9m0q.com"),
    ("www.nubank.com.br", "nubank.com.br"),
    ("a.b.c.exemplo.org", "exemplo.org"),
    ("GOOGLE.COM.", "google.com"),
])
def test_dominio_principal(entrada, esperado):
    assert dominio_principal(entrada) == esperado


def test_transicoes():
    assert transicoes_letra_numero("x8s9m0q") == 6
    assert transicoes_letra_numero("uhrsgh91") == 1
    assert transicoes_letra_numero("google") == 0


@pytest.mark.parametrize("dominio", CASSINO)
def test_cassino_bloqueado_quando_aparece_junto_de_outro(dominio):
    assert nota(dominio, perto_de_cassino=True)[0] >= 3


def test_cassino_sozinho_14_de_15():
    sozinhos = [d for d in CASSINO if nota(d)[0] >= 3]
    assert len(CASSINO) == 15
    assert sorted(set(CASSINO) - set(sozinhos)) == ["uhrsgh91.com"]


def test_padrao_hifen_basta_sozinho():
    assert nota("a-b-c-8.com")[0] >= 3
    assert nota("6-q-r-s.com")[0] >= 3
    assert nota("mercado-pago.com")[0] == 0
    assert nota("b-cdn.net")[0] == 0


def test_falsos_positivos_na_lista_de_legitimos():
    sozinho = [d for d in LEGITIMOS if nota(d)[0] >= 3]
    junto = [d for d in LEGITIMOS if nota(d, perto_de_cassino=True)[0] >= 3]
    assert sozinho == ["web2py.com"]
    # Só contam se o site for aberto até 3 min depois de um cassino conhecido
    assert junto == ["w3schools.com", "mp3juices.com", "mp4upload.com",
                     "web2py.com", "ad4game.com"]
    assert len(LEGITIMOS) == 169


def test_dominio_comum_nunca_ganha_ponto_por_estar_perto():
    assert nota("google.com", perto_de_cassino=True)[0] == 0


def test_tld_fora_da_lista_nao_e_analisado():
    assert nota("x8s9m0q.org")[0] == 0
    assert nota("x8s9m0q.com.br")[0] == 0


def test_nunca_bloquear(monkeypatch):
    import bloqueador_cassino as b
    monkeypatch.setattr(b, "NUNCA_BLOQUEAR", {"web2py.com"})
    assert b.nota("web2py.com")[0] == 0


# Domínios reais de um app de cassino observados nos registros (nov/2026).
# Sozinhos ficam com 2 pontos; junto de um cassino conhecido chegam a 3.
@pytest.mark.parametrize("dominio, sozinho", [
    ("x5w3.scmand.com", 2),      # subdomínio letra-número-letra-número
    ("q3d2.wjyai.com", 2),
    ("u5l1.856552.com", 4),      # subdomínio + nome só com números
    ("k9d4.t9v3k7o5.com", 4),    # já tinha 2 pelo nome
])
def test_padroes_observados_bloqueiam_junto_de_cassino(dominio, sozinho):
    assert nota(dominio)[0] == sozinho
    assert nota(dominio, perto_de_cassino=True)[0] >= 3


@pytest.mark.parametrize("dominio", [
    "readaloud.googleapis.com", "connect.facebook.net", "static.ppcabt.com",
    "163.com", "1234.com", "123456789.com",      # números: só de 5 a 8 dígitos
    "ab12.exemplo.com", "a1b2c.exemplo.com",     # subdomínio fora do padrão
])
def test_padroes_novos_nao_pegam_casos_comuns(dominio):
    assert nota(dominio, perto_de_cassino=True)[0] < 3


def test_analise_usa_o_subdominio_mas_bloqueia_o_principal():
    logs = [
        {"timestamp": "2026-11-20T14:00:00Z", "domain": "ws.j5swonwsss.com",
         "root": "j5swonwsss.com", "status": "blocked"},
        {"timestamp": "2026-11-20T14:01:30Z", "domain": "x5w3.scmand.com",
         "root": "scmand.com", "status": "default"},
        {"timestamp": "2026-11-20T14:30:00Z", "domain": "q3d2.wjyai.com",
         "root": "wjyai.com", "status": "default"},   # longe de cassino: não
    ]
    dominios = [s.dominio for s in analisar(logs, set())]
    assert "scmand.com" in dominios
    assert "wjyai.com" not in dominios
