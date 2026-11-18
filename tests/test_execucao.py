import json
import urllib.error

import pytest

import bloqueador_cassino as b
from conftest import EXEMPLOS

DADOS = json.loads((EXEMPLOS / "registros_exemplo.json").read_text(encoding="utf-8"))


def reg(dominio, status="default", hora="2026-01-01T12:00:00.000Z"):
    return {"timestamp": hora, "domain": dominio, "status": status}


class ClienteFalso:
    def __init__(self, logs, lista_negra=(), falhar_em=(), sem_rede_em=()):
        self._logs, self._negra = logs, set(lista_negra)
        self.bloqueados, self.falhar_em = [], set(falhar_em)
        self.sem_rede_em = set(sem_rede_em)

    def logs(self, minutos):
        return self._logs

    def lista_negra(self):
        return set(self._negra)

    def bloquear(self, dominio):
        if dominio in self.falhar_em:
            raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
        if dominio in self.sem_rede_em:
            raise TimeoutError("timed out")
        self.bloqueados.append(dominio)


def test_exemplo_real_pega_os_que_passaram():
    suspeitos = {s.dominio for s in b.analisar(DADOS["logs"], set(DADOS["lista_negra"]))}
    # Os 4 que a detecção do NextDNS deixou passar
    for d in ["uhrsgh91.com", "l1k4hbx.com", "a-b-c-8.com", "6-q-r-s.com"]:
        assert d in suspeitos
    # Nada legítimo do mesmo registro
    assert not suspeitos & {"googleapis.com", "google.com", "youtube.com", "ytimg.com",
                            "gstatic.com", "whatsapp.net", "spotify.com"}
    # Os que já estão na lista negra não são repetidos
    assert not suspeitos & set(DADOS["lista_negra"])
    assert len(suspeitos) == 12


def test_usa_dominio_principal_nao_o_subdominio():
    s = b.analisar([reg("api5.a-b-c-8.com")], set())
    assert [x.dominio for x in s] == ["a-b-c-8.com"]


def test_correlacao_respeita_a_janela_de_3_minutos():
    perto = [reg("x8s9m0q.com", "blocked", "2026-01-01T12:00:00Z"),
             reg("uhrsgh91.com", "default", "2026-01-01T12:02:59Z")]
    longe = [reg("x8s9m0q.com", "blocked", "2026-01-01T12:00:00Z"),
             reg("uhrsgh91.com", "default", "2026-01-01T12:03:01Z")]
    assert "uhrsgh91.com" in {s.dominio for s in b.analisar(perto, set())}
    assert "uhrsgh91.com" not in {s.dominio for s in b.analisar(longe, set())}


def test_lista_negra_conta_como_cassino_conhecido():
    logs = [reg("j51l4gn.com", "blocked"), reg("uhrsgh91.com")]
    s = {x.dominio for x in b.analisar(logs, {"j51l4gn.com"})}
    assert s == {"uhrsgh91.com"}


def test_registro_sem_horario_nao_quebra():
    s = b.analisar([{"domain": "x8s9m0q.com"}, {"domain": ""}, {}], set())
    assert [x.dominio for x in s] == ["x8s9m0q.com"]


def test_nota_minima_configuravel():
    logs = [reg("uhrsgh91.com")]
    assert b.analisar(logs, set(), nota_minima=3) == []
    assert [x.dominio for x in b.analisar(logs, set(), nota_minima=2)] == ["uhrsgh91.com"]


def test_modo_teste_nao_bloqueia():
    c = ClienteFalso(DADOS["logs"], DADOS["lista_negra"])
    saida = []
    s = b.executar(c, 30, teste=True, nota_minima=3, saida=saida.append)
    assert c.bloqueados == [] and len(s) == 12
    assert all("BLOQUEARIA" in l for l in saida[1:])


def test_modo_real_bloqueia_cada_suspeito_uma_vez():
    logs = DADOS["logs"] + DADOS["logs"]  # registros repetidos
    c = ClienteFalso(logs, DADOS["lista_negra"])
    b.executar(c, 30, teste=False, nota_minima=3, saida=lambda *_: None)
    assert len(c.bloqueados) == len(set(c.bloqueados)) == 12


def test_erro_da_api_num_dominio_nao_para_os_outros():
    c = ClienteFalso(DADOS["logs"], DADOS["lista_negra"], falhar_em={"a-b-c-8.com"})
    saida = []
    b.executar(c, 30, teste=False, nota_minima=3, saida=saida.append)
    assert len(c.bloqueados) == 11
    assert any("ERRO 429: a-b-c-8.com" in l for l in saida)


def test_erro_de_rede_num_dominio_nao_para_os_outros():
    c = ClienteFalso(DADOS["logs"], DADOS["lista_negra"], sem_rede_em={"6-q-r-s.com"})
    saida = []
    b.executar(c, 30, teste=False, nota_minima=3, saida=saida.append)
    assert len(c.bloqueados) == 11
    assert any("ERRO de rede: 6-q-r-s.com" in l for l in saida)


def test_modo_arquivo(capsys):
    assert b.main(["--arquivo", str(EXEMPLOS / "registros_exemplo.json")]) == 0
    out = capsys.readouterr().out
    assert "12 suspeitos" in out and "a-b-c-8.com" in out


def test_sem_credenciais_avisa_e_sai(monkeypatch, capsys):
    monkeypatch.delenv("NEXTDNS_API_KEY", raising=False)
    monkeypatch.delenv("NEXTDNS_PROFILE", raising=False)
    assert b.main([]) == 2
    assert "NEXTDNS_API_KEY" in capsys.readouterr().out


def test_cliente_monta_requisicoes_corretas(monkeypatch):
    chamadas = []

    class Resp:
        def __init__(self, corpo): self.corpo = corpo
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(self.corpo).encode()

    respostas = iter([
        {"data": [reg("x8s9m0q.com")], "meta": {"pagination": {"cursor": "abc"}}},
        {"data": [reg("l1k4hbx.com")], "meta": {"pagination": {"cursor": None}}},
        {},
    ])

    def urlopen(req, timeout):
        chamadas.append(req)
        return Resp(next(respostas))

    monkeypatch.setattr(b.urllib.request, "urlopen", urlopen)
    c = b.ClienteNextDNS("CHAVE", "abc123")
    assert len(c.logs(30)) == 2
    c.bloquear("x8s9m0q.com")

    assert chamadas[0].full_url.startswith("https://api.nextdns.io/profiles/abc123/logs?from=")
    assert "cursor=abc" in chamadas[1].full_url
    assert chamadas[0].get_header("X-api-key") == "CHAVE"
    assert chamadas[0].get_header("User-agent").startswith("bloqueador-cassino")
    assert chamadas[2].get_method() == "POST"
    assert chamadas[2].full_url.endswith("/profiles/abc123/denylist")
    assert json.loads(chamadas[2].data) == {"id": "x8s9m0q.com", "active": True}


def test_modo_silencioso_nao_revela_nada_do_perfil():
    c = ClienteFalso(DADOS["logs"], DADOS["lista_negra"])
    saida = []
    b.executar(c, 30, teste=False, nota_minima=3, saida=saida.append, detalhado=False)
    assert len(c.bloqueados) == 12          # bloqueia normalmente
    assert saida == ["Rodada concluída."]   # sem contagens, domínios ou horários


def test_modo_silencioso_avisa_erro_sem_dizer_o_dominio():
    c = ClienteFalso(DADOS["logs"], DADOS["lista_negra"], falhar_em={"a-b-c-8.com"})
    saida = []
    b.executar(c, 30, teste=False, nota_minima=3, saida=saida.append, detalhado=False)
    assert len(saida) == 1 and "erro" in saida[0] and "a-b-c-8" not in saida[0]


@pytest.mark.parametrize("variavel, esperado", [
    (None, True),     # padrão: detalhado
    ("1", True),
    ("0", False),     # logs lidos por outras pessoas: silencioso
    (" 0 ", False),
])
def test_log_detalhado_padrao(monkeypatch, variavel, esperado):
    if variavel is None:
        monkeypatch.delenv("LOG_DETALHADO", raising=False)
    else:
        monkeypatch.setenv("LOG_DETALHADO", variavel)
    assert b.log_detalhado_padrao() is esperado
