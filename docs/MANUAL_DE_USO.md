# Manual de uso

Passo a passo para colocar o bloqueio para funcionar num celular Android, do zero. Leva uns 20 minutos.

> Use só com o consentimento da pessoa dona do celular. O bloqueio é visível nas configurações do aparelho.

## 1. Criar o perfil no NextDNS

1. Crie uma conta em [nextdns.io](https://nextdns.io). O plano gratuito atende até 300 mil consultas por mês.
2. Na aba **Segurança**, ligue: detecção de ameaças por IA, domínios recém-registrados, proteção contra DGA e domínios estacionados.
3. Na aba **Controle parental**, ative a categoria **Jogos de azar** e **Bloquear métodos de contorno**.
4. Na aba **Configurações**, deixe os **registros (logs) ativados**. O bloqueador depende deles.
5. Na aba **Configuração**, anote o **ID do perfil** (algo como `abc123`).

## 2. Configurar o celular

1. Configurações → Conexão e compartilhamento (ou "Mais conexões") → **DNS privado**.
2. Escolha "Nome do host do provedor de DNS privado" e digite `abc123.dns.nextdns.io`, trocando pelo seu ID.
3. Abra [test.nextdns.io](https://test.nextdns.io) no celular: deve aparecer `"status": "ok"`.
4. Não use o "DNS 1 / DNS 2" do Wi-Fi: ele só vale naquela rede e para de funcionar nos dados móveis.

Para o bloqueio não ser desfeito, tranque o app **Configurações** com uma senha (em alguns aparelhos, como os da Xiaomi, isso fica no app Segurança → Bloqueio de apps). Desligue também, para todos os apps, a permissão de **instalar apps desconhecidos**.

## 3. Pegar a chave da API

Em [my.nextdns.io/account](https://my.nextdns.io/account), role até o fim e copie a **API Key**. Ela dá acesso total à conta: não mande para ninguém e não coloque em nenhum arquivo.

## 4. Conferir antes de ligar (opcional, no computador)

Com Python 3.10+ instalado, baixe este repositório e rode em modo de teste. Nada é bloqueado; a tela mostra o que seria:

```bash
# Windows (PowerShell)
$env:NEXTDNS_API_KEY="sua-chave"; $env:NEXTDNS_PROFILE="abc123"; $env:MODO_TESTE="1"
python bloqueador_cassino.py
```

```
[16:05:12] 412 registros analisados, 3 suspeitos.
  BLOQUEARIA: l1k4hbx.com  (nota 4: letras+números curtos, ...)
```

Se aparecer um site legítimo, acrescente o nome dele em `NUNCA_BLOQUEAR`, no começo de `bloqueador_cassino.py`.

## 5. Ligar o bloqueador na Cloudflare (sem computador ligado)

O bloqueador roda como um **Worker agendado** no plano gratuito da Cloudflare: a cada 5 minutos, nos servidores deles. O código é o arquivo [`cloudflare/worker.js`](../cloudflare/worker.js), com as mesmas regras do script Python.

**Pelo navegador, sem instalar nada:**

1. Crie uma conta gratuita em [dash.cloudflare.com](https://dash.cloudflare.com).
2. Vá em **Workers & Pages → Create → Create Worker**, dê o nome `bloqueador-cassino` e clique em **Deploy**.
3. Clique em **Edit code**, apague o código de exemplo, cole todo o conteúdo de `cloudflare/worker.js` e clique em **Deploy**.
4. Em **Settings → Variables and Secrets**, adicione dois itens do tipo **Secret**: `NEXTDNS_API_KEY` com a chave e `NEXTDNS_PROFILE` com o ID do perfil. Para conferir antes de bloquear de verdade, adicione também `MODO_TESTE` (tipo texto) com o valor `1`, e apague depois.
5. Em **Settings → Trigger Events** (ou **Triggers**), adicione um **Cron Trigger** com a expressão `*/5 * * * *`.
6. Em **Settings → Observability**, ligue os **Workers Logs** para ver o resultado de cada execução.

**Pela linha de comando** (precisa do Node.js):

```bash
cd cloudflare
npx wrangler login
npx wrangler secret put NEXTDNS_API_KEY
npx wrangler secret put NEXTDNS_PROFILE
npx wrangler deploy
```

O arquivo `cloudflare/wrangler.toml` já traz o agendamento, as variáveis e os logs ligados.

**Privacidade:** os logs do Worker ficam só na sua conta Cloudflare. Eles mostram os domínios bloqueados e os motivos, o que ajuda a achar falsos positivos.

**Alternativa sem Cloudflare:** deixe o script Python rodando num computador ou num Raspberry Pi que fique ligado, com `python bloqueador_cassino.py --loop 120`.

## 6. Manutenção

- **A cada semana:** olhe a Lista negra no NextDNS e os logs do Worker. Se domínios com o ícone do cassino estiverem passando, eles podem ter um padrão novo.
- **Falso positivo:** acrescente o domínio em `NUNCA_BLOQUEAR`, no começo de `cloudflare/worker.js` (e de `bloqueador_cassino.py`), faça o deploy de novo e remova o domínio da Lista negra no NextDNS.
- **Se a chave vazar:** gere outra em my.nextdns.io/account e atualize o *Secret* do Worker.

## Problemas comuns

| Sintoma | Causa provável |
|---|---|
| `Erro da API: 403` (Python) ou exceção `HTTP 403` no log do Worker | Chave errada, ou o ID do perfil não é dessa conta |
| `0 registros analisados` | Registros desativados no NextDNS, ou o celular não está usando o perfil |
| Log do Worker diz "Secrets ... não configurados" | Os *Secrets* `NEXTDNS_API_KEY` e `NEXTDNS_PROFILE` não foram criados no Worker |
| O Worker não roda sozinho | Falta o Cron Trigger `*/5 * * * *` |
| O app de cassino ainda abre | Ele pode estar usando IP fixo ou DNS próprio: desinstale o app e bloqueie a instalação de apps desconhecidos |
