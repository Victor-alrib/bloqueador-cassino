# Resultados

> Os domínios de cassino são **reais**, observados em registros do NextDNS. No registro de exemplo, os domínios legítimos, a data e os horários são ilustrativos.

Ambiente: Python 3.13.18, pytest 9.1.1, Node 22.23.4, Linux. O resultado é determinístico: as regras não têm aleatoriedade.

## Arquivos desta pasta

| Arquivo | Conteúdo |
|---|---|
| `testes_pytest.txt` | Saída dos 61 testes em Python (pytest) |
| `testes_worker.txt` | Saída dos 11 testes do Cloudflare Worker (`node:test`), incluindo a paridade com a versão em Python |
| `execucao_exemplo.txt` | Saída de `python bloqueador_cassino.py --arquivo exemplos/registros_exemplo.json` |
| `avaliacao_dominios.txt` | Nota de cada um dos 15 domínios de cassino e dos 169 legítimos, sozinhos e "junto" de um cassino |

## Detecção dos domínios de cassino

15 domínios distintos, em dois formatos.

| Formato | Exemplos | Bloqueados sozinhos | Bloqueados junto de outro cassino |
|---|---|---|---|
| Aleatório curto | `x8s9m0q.com`, `zv3p03tf.com`, `uhrsgh91.com` | 12 de 13 | 13 de 13 |
| Caracteres com hífen (API e imagens do app) | `a-b-c-8.com`, `6-q-r-s.com` | 2 de 2 | 2 de 2 |
| **Total** | | **14 de 15** | **15 de 15** |

O único que não passa sozinho é `uhrsgh91.com` (nota 2): os números estão num bloco só no fim, como em muitos sites legítimos. Ele é pego pela correlação de horário, porque o app o consulta junto com os outros.

## Registro de exemplo

`exemplos/registros_exemplo.json` tem 23 consultas: 15 de cassino e 8 de 7 domínios legítimos. 3 domínios de cassino já estavam na Lista negra.

- **Marcados: 12**, exatamente os domínios de cassino que ainda não estavam na Lista negra.
- Entre eles, os 4 que o NextDNS tinha deixado passar: `uhrsgh91.com`, `l1k4hbx.com`, `a-b-c-8.com` (de `api5.a-b-c-8.com`) e `6-q-r-s.com` (de `game-logo.6-q-r-s.com`).
- **Nenhum legítimo marcado**: `googleapis.com`, `google.com`, `youtube.com`, `ytimg.com`, `gstatic.com`, `whatsapp.net`, `spotify.com`.

## Falsos positivos

A lista `exemplos/dominios_legitimos.txt` tem 169 domínios: os sites mais usados no Brasil, serviços comuns em celulares e nomes escolhidos para serem difíceis (com números, siglas e hífens).

| Situação | Bloqueados | Quais |
|---|---|---|
| Sozinho | 1 de 169 | `web2py.com` |
| Até 3 min depois de um cassino | 5 de 169 | `w3schools.com`, `mp3juices.com`, `mp4upload.com`, `web2py.com`, `ad4game.com` |

Nomes com número em bloco (`office365`, `bet365`, `4shared`, `365scores`) ficam com nota 1 ou 2 e não são bloqueados.

## O que estes números não mostram

- As regras foram escritas olhando estes mesmos 15 domínios. Não há um conjunto separado de domínios novos para medir o acerto sem esse viés.
- A lista de legítimos foi montada à mão; não é uma amostra do tráfego real de um celular.
- O script ainda não foi medido rodando por vários dias contra um perfil real: quantos domínios bloqueia por dia, quantos passam antes do bloqueio e quantos falsos positivos aparecem.
