import pytest

from bloqueador_cassino import dominio_principal, nota, transicoes_letra_numero
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
