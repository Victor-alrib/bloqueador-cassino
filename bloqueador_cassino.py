#!/usr/bin/env python3
"""
Bloqueador automático de domínios de cassino ilegal ("tigrinho") para o NextDNS.

Os apps de cassino ilegal trocam de domínio a cada poucos minutos
(x8s9m0q.com, r8x1m4k.com, ...), o que torna inútil bloquear um por um à mão.
Este script lê os registros recentes de um perfil NextDNS pela API oficial,
dá uma nota de suspeita a cada domínio e coloca na Lista negra os que passam
da nota mínima.

Configuração (variáveis de ambiente):
  NEXTDNS_API_KEY  chave da API (fim da página https://my.nextdns.io/account)
  NEXTDNS_PROFILE  ID do perfil (a parte antes de .dns.nextdns.io)
  MINUTOS          minutos de registro analisados por execução (padrão 30)
  MODO_TESTE       "1" só mostra o que bloquearia, sem bloquear (padrão 0)
  NOTA_MINIMA      nota a partir da qual o domínio é bloqueado (padrão 3)
  LOG_DETALHADO    "0" escreve só "Rodada concluída", sem contagens nem
                   domínios, para quando a saída fica em logs que outras
                   pessoas leem (padrão 1)

Uso:
  python bloqueador_cassino.py                     roda uma vez
  python bloqueador_cassino.py --loop 120          roda a cada 120 s
  python bloqueador_cassino.py --arquivo LOGS.json analisa um arquivo de
                                                   registros, sem API
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

API = "https://api.nextdns.io"
# Sem um User-Agent próprio, a API às vezes recusa clientes Python (erro 1010).
USER_AGENT = "bloqueador-cassino/1.0 (+python)"

# Domínios que nunca são bloqueados, mesmo que pareçam aleatórios.
# Acrescente aqui qualquer site legítimo pego por engano.
NUNCA_BLOQUEAR: set[str] = {
    # "exemplo123.com",
}

# Terminações em que a análise é feita. Fora delas, nota zero.
TLDS_ANALISADOS = {
    "com", "net", "top", "xyz", "vip", "cc", "bet", "club", "win",
    "online", "site", "fun", "life", "app",
}

# Sufixos de dois níveis, para achar o domínio principal de "a.b.com.br".
SUFIXOS_DUPLOS = {"com.br", "net.br", "org.br", "gov.br", "co.uk", "com.ar"}

VOGAIS = set("aeiou")
PADRAO_HIFEN = re.compile(r"^(?:[a-z0-9]-){2,}[a-z0-9]$")   # a-b-c-8, 6-q-r-s
PADRAO_CURTO = re.compile(r"^[a-z0-9]{6,10}$")              # x8s9m0q

JANELA_SEGUNDOS = 180  # "apareceu junto" = até 3 min de um cassino conhecido


# --------------------------------------------------------------- nota ---

def dominio_principal(dominio: str) -> str:
    """'api5.a-b-c-8.com' -> 'a-b-c-8.com'; 'x.y.com.br' -> 'y.com.br'."""
    partes = dominio.lower().strip(".").split(".")
    if len(partes) >= 3 and ".".join(partes[-2:]) in SUFIXOS_DUPLOS:
        return ".".join(partes[-3:])
    return ".".join(partes[-2:])


def transicoes_letra_numero(nome: str) -> int:
    """Quantas vezes o nome alterna entre letra e número: 'x8s9' -> 3."""
    return sum(a.isdigit() != b.isdigit() for a, b in zip(nome, nome[1:]))


def nota(dominio: str, perto_de_cassino: bool = False) -> tuple[int, list[str]]:
    """Nota de suspeita de um domínio principal e os motivos de cada ponto."""
    dominio = dominio_principal(dominio)
    if dominio in NUNCA_BLOQUEAR:
        return 0, ["lista NUNCA_BLOQUEAR"]
    nome, _, tld = dominio.rpartition(".")
    if tld not in TLDS_ANALISADOS or "." in nome:
        return 0, [f".{tld} não analisado"]

    pontos, motivos = 0, []

    if PADRAO_HIFEN.match(nome):
        pontos += 3
        motivos.append("padrão a-b-c-8")

    letras = [c for c in nome if c.isalpha()]
    if PADRAO_CURTO.match(nome) and any(c.isdigit() for c in nome) and len(letras) >= 2:
        pontos += 1
        motivos.append("letras+números curtos")
        if transicoes_letra_numero(nome) >= 2:
            pontos += 1
            motivos.append("letras e números misturados")
        prop_vogais = sum(c in VOGAIS for c in letras) / len(letras)
        if prop_vogais < 0.25:
            pontos += 1
            motivos.append(f"poucas vogais ({prop_vogais:.0%})")

    if perto_de_cassino and pontos > 0:
        pontos += 1
        motivos.append("apareceu junto de cassino conhecido")

    return pontos, motivos


# ------------------------------------------------------------ análise ---

@dataclass
class Suspeito:
    dominio: str
    nota: int
    motivos: list[str] = field(default_factory=list)


def _horario(entrada: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(entrada["timestamp"].replace("Z", "+00:00"))
    except (KeyError, ValueError, AttributeError):
        return None


def _principal_da_entrada(entrada: dict) -> str:
    return dominio_principal(entrada.get("root") or entrada.get("domain") or "")


def analisar(logs: list[dict], lista_negra: set[str],
             nota_minima: int = 3) -> list[Suspeito]:
    """Domínios dos registros que devem ir para a Lista negra.

    Função pura: não chama a API. Um domínio é "cassino conhecido" se já está
    na Lista negra ou se foi bloqueado pelo NextDNS e tem nota própria >= 2.
    """
    lista_negra = {d.lower() for d in lista_negra}

    momentos_cassino = []
    for e in logs:
        principal = _principal_da_entrada(e)
        conhecido = principal in lista_negra or (
            e.get("status") == "blocked" and nota(principal)[0] >= 2)
        t = _horario(e)
        if conhecido and t:
            momentos_cassino.append(t)

    def perto(t: datetime | None) -> bool:
        return t is not None and any(
            abs((t - m).total_seconds()) <= JANELA_SEGUNDOS for m in momentos_cassino)

    melhores: dict[str, Suspeito] = {}
    for e in logs:
        principal = _principal_da_entrada(e)
        if not principal or principal in lista_negra:
            continue
        n, motivos = nota(principal, perto(_horario(e)))
        if n >= nota_minima and (principal not in melhores or n > melhores[principal].nota):
            melhores[principal] = Suspeito(principal, n, motivos)
    return sorted(melhores.values(), key=lambda s: (-s.nota, s.dominio))


# ---------------------------------------------------------------- API ---

class ClienteNextDNS:
    def __init__(self, chave: str, perfil: str):
        self.chave, self.perfil = chave, perfil

    def _chamar(self, metodo: str, caminho: str, corpo=None, params=None) -> dict:
        url = f"{API}/profiles/{self.perfil}{caminho}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        dados = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(url, data=dados, method=metodo, headers={
            "X-Api-Key": self.chave,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        })
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")

    def logs(self, minutos: int) -> list[dict]:
        desde = datetime.now(timezone.utc) - timedelta(minutes=minutos)
        params = {"from": desde.strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": 1000}
        resultado: list[dict] = []
        for _ in range(20):  # no máximo 20 páginas de 1000 registros
            r = self._chamar("GET", "/logs", params=params)
            resultado.extend(r.get("data", []))
            cursor = ((r.get("meta") or {}).get("pagination") or {}).get("cursor")
            if not cursor:
                break
            params["cursor"] = cursor
        return resultado

    def lista_negra(self) -> set[str]:
        r = self._chamar("GET", "/denylist")
        return {item["id"].lower() for item in r.get("data", [])}

    def bloquear(self, dominio: str) -> None:
        self._chamar("POST", "/denylist", corpo={"id": dominio, "active": True})


# ---------------------------------------------------------- execução ---

def log_detalhado_padrao() -> bool:
    """Saída detalhada, salvo LOG_DETALHADO=0."""
    return os.environ.get("LOG_DETALHADO", "1").strip() != "0"


def executar(cliente, minutos: int, teste: bool, nota_minima: int,
             saida=print, detalhado: bool = True) -> list[Suspeito]:
    """Uma rodada. Com detalhado=False, a saída não revela nada do perfil:
    nem contagens, nem domínios, nem horários (os logs podem ser públicos)."""
    lista_negra = cliente.lista_negra()
    logs = cliente.logs(minutos)
    suspeitos = analisar(logs, lista_negra, nota_minima)

    if detalhado:
        agora = datetime.now().strftime("%H:%M:%S")
        saida(f"[{agora}] {len(logs)} registros analisados, {len(suspeitos)} suspeitos.")
    falhas = 0
    for s in suspeitos:
        acao = "BLOQUEARIA" if teste else "BLOQUEADO"
        if not teste:
            try:
                cliente.bloquear(s.dominio)
            except urllib.error.HTTPError as err:
                acao = f"ERRO {err.code}"
                falhas += 1
            except (urllib.error.URLError, OSError):  # sem rede, timeout
                acao = "ERRO de rede"
                falhas += 1
        if detalhado:
            saida(f"  {acao}: {s.dominio}  (nota {s.nota}: {', '.join(s.motivos)})")
    if not detalhado:
        saida("Rodada concluída." + (" Houve erro ao bloquear algum domínio."
                                      if falhas else ""))
    return suspeitos


def analisar_arquivo(caminho: str, nota_minima: int, saida=print) -> list[Suspeito]:
    """Modo offline: lê {"logs": [...], "lista_negra": [...]} e só mostra."""
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    suspeitos = analisar(dados.get("logs", []), set(dados.get("lista_negra", [])),
                         nota_minima)
    saida(f"{len(dados.get('logs', []))} registros analisados, "
          f"{len(suspeitos)} suspeitos.")
    for s in suspeitos:
        saida(f"  BLOQUEARIA: {s.dominio}  (nota {s.nota}: {', '.join(s.motivos)})")
    return suspeitos


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--loop", type=int, metavar="SEGUNDOS",
                   help="roda sem parar, com esse intervalo")
    p.add_argument("--arquivo", help="analisa um JSON de registros, sem usar a API")
    args = p.parse_args(argv)

    nota_minima = int(os.environ.get("NOTA_MINIMA", "3"))
    if args.arquivo:
        analisar_arquivo(args.arquivo, nota_minima)
        return 0

    chave = os.environ.get("NEXTDNS_API_KEY", "").strip()
    perfil = os.environ.get("NEXTDNS_PROFILE", "").strip()
    if not chave or not perfil:
        print("Defina NEXTDNS_API_KEY e NEXTDNS_PROFILE (veja o topo do arquivo).")
        return 2
    minutos = int(os.environ.get("MINUTOS", "30"))
    teste = os.environ.get("MODO_TESTE", "0") == "1"
    detalhado = log_detalhado_padrao()
    cliente = ClienteNextDNS(chave, perfil)

    while True:
        try:
            executar(cliente, minutos, teste, nota_minima, detalhado=detalhado)
        except urllib.error.HTTPError as err:
            print(f"Erro da API: {err.code} {err.reason}. Confira a chave e o ID do perfil.")
            if args.loop is None:
                return 1
        except urllib.error.URLError as err:
            print(f"Sem conexão: {err.reason}")
            if args.loop is None:
                return 1
        if args.loop is None:
            return 0
        time.sleep(args.loop)


if __name__ == "__main__":
    sys.exit(main())
