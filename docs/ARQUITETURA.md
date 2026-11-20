# Arquitetura

## Visão geral

O bloqueador existe em duas versões com as mesmas regras:

- `bloqueador_cassino.py`: Python, só biblioteca padrão. Roda no computador (uma vez ou em loop) e analisa arquivos de registro sem a API. É a **referência** das regras.
- `cloudflare/worker.js`: JavaScript, para rodar agendado no plano gratuito da Cloudflare Workers, sem servidor nem computador ligado.

Um teste garante que as duas dão exatamente as mesmas notas: `cloudflare/test/gerar_esperado.py` grava as notas da versão Python para 213 domínios e duas análises de registros (o exemplo e um caso com subdomínios) em `esperado.json`; os testes em JavaScript comparam com esse arquivo, e `tests/test_paridade.py` falha se ele ficar desatualizado.

```
bloqueador-cassino/
├── bloqueador_cassino.py          ← o bloqueador (Python, referência)
├── cloudflare/
│   ├── worker.js                  ← o bloqueador como Worker agendado
│   ├── wrangler.toml              ← agendamento a cada 5 min e variáveis
│   └── test/                      ← testes em Node e paridade com o Python
├── .github/workflows/ci.yml       ← testes Python e JavaScript a cada push
├── exemplos/
│   ├── registros_exemplo.json     ← registros de exemplo com domínios reais desses apps
│   ├── dominios_cassino.txt       ← 15 domínios de cassino vistos nos registros
│   └── dominios_legitimos.txt     ← 169 domínios legítimos para medir falsos positivos
├── tests/                         ← pytest, com a API simulada
├── resultados/
└── docs/
```

## Camadas do script

| Camada | Funções | Chama a API? |
|---|---|---|
| Nota | `dominio_principal`, `transicoes_letra_numero`, `nota` | Não |
| Análise | `analisar(logs, lista_negra, nota_minima)` | Não (função pura) |
| API | `ClienteNextDNS.logs`, `.lista_negra`, `.bloquear` | Sim |
| Execução | `executar`, `analisar_arquivo`, `main` | Por meio do cliente |

A separação permite testar toda a lógica de decisão sem rede: os testes passam um cliente falso para `executar` e chamam `analisar` diretamente.

## Fluxo de uma execução

1. **Lista negra atual.** `GET /profiles/:perfil/denylist`. Esses domínios não são analisados de novo e servem de "cassino conhecido" para a correlação.
2. **Registros.** `GET /profiles/:perfil/logs?from=<agora - MINUTOS>&limit=1000`, seguindo o `cursor` de paginação até 20 páginas. No Worker, a janela padrão é de 10 min com execuções a cada 5 min: cada registro é visto pelo menos duas vezes, o que dá margem para atrasos. No Python, o padrão é 30 min.
3. **Domínio principal.** Cada registro é reduzido ao domínio principal (`api5.a-b-c-8.com` → `a-b-c-8.com`; `x.y.com.br` → `y.com.br`), que é o que vai para a Lista negra. O campo `root` da API é usado quando existe, e o cálculo também é aplicado sobre ele. A nota, porém, usa o endereço completo (`domain`), porque o subdomínio também conta pontos.
4. **Cassinos conhecidos.** São marcados os horários de registros cujo domínio está na Lista negra, ou que foram bloqueados pelo NextDNS (`status: blocked`) e têm nota própria ≥ 2. A segunda condição evita contar como cassino qualquer domínio bloqueado por outros motivos, como rastreadores.
5. **Nota.** Para cada domínio, `nota()` soma os sinais do nome e +1 se algum registro dele estiver até 180 s de um cassino conhecido. Fica a maior nota entre os registros do domínio.
6. **Bloqueio.** Para cada suspeito com nota ≥ `NOTA_MINIMA`: `POST /profiles/:perfil/denylist` com `{"id": dominio, "active": true}`. Um erro HTTP ou de rede é registrado na saída e o próximo domínio continua.

## Por que esses sinais

Os nomes dos domínios de cassino nos registros têm três traços que nomes de sites legítimos raramente juntam:

- **curtos e alfanuméricos** (6 a 10 caracteres com número): gerados por algoritmo, não escolhidos para serem lembrados;
- **letras e números intercalados** (`x8s9m0q`): sites legítimos com número costumam ter o número num bloco (`office365`, `bet365`);
- **poucas vogais** (`zv3p03tf`, 0 %): nomes pronunciáveis têm por volta de 40 % de vogais.

Dois sinais valem 2 pontos e, sozinhos, só bloqueiam junto de um cassino conhecido. Vieram de domínios do mesmo app observados depois, que passavam com nota 0:

- **nome só com números, de 5 a 8 dígitos** (`856552.com`): sites legítimos com nome numérico costumam ser curtos (`163.com`);
- **subdomínio letra-número-letra-número** (`u5l1.`, `x5w3.`, `q3d2.`): o app usa esse formato em vários domínios, mesmo quando o nome principal parece comum (`scmand.com`, `wjyai.com`).

O padrão `a-b-c-8` (caracteres soltos com hífen) recebe 3 pontos de uma vez porque não apareceu em nenhum domínio legítimo testado, e esses domínios fixos (API e imagens do app) são os mais valiosos de bloquear.

## Execução agendada (Cloudflare Workers)

- **Cron Trigger** `*/5 * * * *` chama o handler `scheduled()` do Worker. Sem os *Secrets*, ele termina sem chamar a API.
- **Limite de CPU.** O plano gratuito permite 10 ms de CPU por execução; o tempo esperando a API do NextDNS não conta. Para caber nisso com perfis movimentados, a análise guarda em cache a nota de cada nome principal e de cada endereço completo (eles se repetem muito nos registros) e procura cassinos próximos no tempo com busca binária. Medido no Node.js (mediana de 30 execuções): 0,5 ms para 100 registros, 1,2 ms para 1.000 e 8,8 ms para 10.000; com 10.000 endereços todos diferentes, 16 ms. Em uso real, as janelas de 10 min tiveram de 34 a 93 registros.
- **Subrequests.** O plano gratuito permite 50 chamadas externas por execução: 1 para a Lista negra, 1 por página de registros e 1 por domínio bloqueado. Numa janela de 10 min, isso folga.
- **Logs.** Com `observability` ligado, cada execução registra os domínios bloqueados e os motivos nos Workers Logs, visíveis só para o dono da conta Cloudflare.

## Saída do script Python

Por padrão, cada rodada mostra os domínios bloqueados, os motivos e as contagens. Com `LOG_DETALHADO=0`, `executar` escreve só "Rodada concluída", sem contagens, domínios ou horários, para quando a saída vai para logs que outras pessoas podem ler.
