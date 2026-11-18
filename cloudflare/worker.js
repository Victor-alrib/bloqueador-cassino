/**
 * Bloqueador de cassino — versão para Cloudflare Workers (Cron Trigger).
 *
 * Mesmas regras de bloqueador_cassino.py, portadas para JavaScript para
 * caber no limite de CPU do plano gratuito (10 ms por execução; o tempo
 * esperando a API do NextDNS não conta). Os testes em cloudflare/test/
 * conferem que as notas daqui são idênticas às da versão Python.
 *
 * Configuração (painel do Worker → Settings → Variables and Secrets):
 *   NEXTDNS_API_KEY  (Secret)  chave da API do NextDNS
 *   NEXTDNS_PROFILE  (Secret)  ID do perfil
 *   MODO_TESTE       (texto)   "1" só registra o que bloquearia (padrão "0")
 *   MINUTOS          (texto)   minutos de registro analisados (padrão "10";
 *                             roda a cada 5 min, então as janelas se sobrepõem)
 *   NOTA_MINIMA      (texto)   nota mínima para bloquear (padrão "3")
 */

const API = "https://api.nextdns.io";
const USER_AGENT = "bloqueador-cassino/1.0 (+cloudflare-worker)";

// Domínios que nunca são bloqueados, mesmo que pareçam aleatórios.
export const NUNCA_BLOQUEAR = new Set([
  // "exemplo123.com",
]);

export const TLDS_ANALISADOS = new Set([
  "com", "net", "top", "xyz", "vip", "cc", "bet", "club", "win",
  "online", "site", "fun", "life", "app",
]);

const SUFIXOS_DUPLOS = new Set(["com.br", "net.br", "org.br", "gov.br", "co.uk", "com.ar"]);
const VOGAIS = new Set("aeiou");
const PADRAO_HIFEN = /^(?:[a-z0-9]-){2,}[a-z0-9]$/; // a-b-c-8, 6-q-r-s
const PADRAO_CURTO = /^[a-z0-9]{6,10}$/;            // x8s9m0q
const JANELA_MS = 180 * 1000; // "apareceu junto" = até 3 min de um cassino conhecido

const ehDigito = (c) => c >= "0" && c <= "9";
const ehLetra = (c) => c >= "a" && c <= "z";

/** 'api5.a-b-c-8.com' -> 'a-b-c-8.com'; 'x.y.com.br' -> 'y.com.br'. */
export function dominioPrincipal(dominio) {
  const partes = String(dominio || "").toLowerCase().replace(/^\.+|\.+$/g, "").split(".");
  if (partes.length >= 3 && SUFIXOS_DUPLOS.has(partes.slice(-2).join("."))) {
    return partes.slice(-3).join(".");
  }
  return partes.slice(-2).join(".");
}

function transicoesLetraNumero(nome) {
  let n = 0;
  for (let i = 1; i < nome.length; i++) {
    if (ehDigito(nome[i - 1]) !== ehDigito(nome[i])) n++;
  }
  return n;
}

// Arredondamento "para o par", igual ao f"{x:.0%}" do Python.
function percentual(x) {
  const v = x * 100;
  const piso = Math.floor(v);
  const resto = v - piso;
  let r;
  if (Math.abs(resto - 0.5) < 1e-9) r = piso % 2 === 0 ? piso : piso + 1;
  else r = Math.round(v);
  return `${r}%`;
}

/** Nota de suspeita de um domínio e os motivos de cada ponto. */
export function nota(dominio, pertoDeCassino = false) {
  dominio = dominioPrincipal(dominio);
  if (NUNCA_BLOQUEAR.has(dominio)) return [0, ["lista NUNCA_BLOQUEAR"]];
  const i = dominio.lastIndexOf(".");
  const nome = i >= 0 ? dominio.slice(0, i) : "";
  const tld = i >= 0 ? dominio.slice(i + 1) : dominio;
  if (!TLDS_ANALISADOS.has(tld) || nome.includes(".")) return [0, [`.${tld} não analisado`]];

  let pontos = 0;
  const motivos = [];

  if (PADRAO_HIFEN.test(nome)) {
    pontos += 3;
    motivos.push("padrão a-b-c-8");
  }

  const letras = [...nome].filter(ehLetra);
  if (PADRAO_CURTO.test(nome) && [...nome].some(ehDigito) && letras.length >= 2) {
    pontos += 1;
    motivos.push("letras+números curtos");
    if (transicoesLetraNumero(nome) >= 2) {
      pontos += 1;
      motivos.push("letras e números misturados");
    }
    const propVogais = letras.filter((c) => VOGAIS.has(c)).length / letras.length;
    if (propVogais < 0.25) {
      pontos += 1;
      motivos.push(`poucas vogais (${percentual(propVogais)})`);
    }
  }

  if (pertoDeCassino && pontos > 0) {
    pontos += 1;
    motivos.push("apareceu junto de cassino conhecido");
  }
  return [pontos, motivos];
}

function horario(entrada) {
  const t = Date.parse(entrada && entrada.timestamp);
  return Number.isNaN(t) ? null : t;
}

const principalDaEntrada = (e) => dominioPrincipal((e && (e.root || e.domain)) || "");

/** Domínios dos registros que devem ir para a Lista negra (função pura). */
export function analisar(logs, listaNegra, notaMinima = 3) {
  const negra = new Set([...listaNegra].map((d) => d.toLowerCase()));

  // Cada domínio se repete muito nos registros: a nota base é calculada uma
  // vez só. A nota "junto de cassino" é a base + 1 quando a base é > 0.
  const cache = new Map();
  const notaBase = (d) => {
    if (!cache.has(d)) cache.set(d, nota(d));
    return cache.get(d);
  };

  const momentosCassino = [];
  for (const e of logs) {
    const principal = principalDaEntrada(e);
    const conhecido = negra.has(principal) || (e.status === "blocked" && notaBase(principal)[0] >= 2);
    const t = horario(e);
    if (conhecido && t !== null) momentosCassino.push(t);
  }
  // Busca binária no vetor ordenado: mantém a execução dentro dos 10 ms de
  // CPU do plano gratuito mesmo com milhares de registros.
  momentosCassino.sort((a, b) => a - b);
  const perto = (t) => {
    if (t === null || momentosCassino.length === 0) return false;
    let lo = 0, hi = momentosCassino.length - 1;
    while (lo < hi) { // primeiro momento >= t - janela
      const meio = (lo + hi) >> 1;
      if (momentosCassino[meio] < t - JANELA_MS) lo = meio + 1; else hi = meio;
    }
    return Math.abs(momentosCassino[lo] - t) <= JANELA_MS;
  };

  const melhores = new Map();
  for (const e of logs) {
    const principal = principalDaEntrada(e);
    if (!principal || negra.has(principal)) continue;
    const [base, motivosBase] = notaBase(principal);
    if (base + 1 < notaMinima) continue; // nem com o ponto extra chegaria lá
    const junto = base > 0 && perto(horario(e));
    const n = junto ? base + 1 : base;
    const motivos = junto ? [...motivosBase, "apareceu junto de cassino conhecido"] : motivosBase;
    if (n >= notaMinima && (!melhores.has(principal) || n > melhores.get(principal).nota)) {
      melhores.set(principal, { dominio: principal, nota: n, motivos });
    }
  }
  return [...melhores.values()].sort((a, b) => b.nota - a.nota || (a.dominio < b.dominio ? -1 : a.dominio > b.dominio ? 1 : 0));
}

// ---------------------------------------------------------------- API ---

export class ClienteNextDNS {
  constructor(chave, perfil, fetchFn = fetch) {
    this.chave = chave;
    this.perfil = perfil;
    // No Workers, o fetch global não pode ser chamado como método de outro
    // objeto ("Illegal invocation"): guarda uma função que o chama solto.
    this.fetch = (...args) => fetchFn(...args);
  }

  async chamar(metodo, caminho, { corpo, params } = {}) {
    let url = `${API}/profiles/${this.perfil}${caminho}`;
    if (params) url += "?" + new URLSearchParams(params).toString();
    const resp = await this.fetch(url, {
      method: metodo,
      headers: {
        "X-Api-Key": this.chave,
        Accept: "application/json",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
      },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
    if (!resp.ok) {
      // O começo da resposta ajuda a diagnosticar (chave errada, perfil
      // errado, bloqueio de rede). Não contém a chave.
      let detalhe = "";
      try { detalhe = (await resp.text()).replace(/\s+/g, " ").slice(0, 200); } catch { /* sem corpo */ }
      const erro = new Error(`HTTP ${resp.status} em ${metodo} ${caminho}${detalhe ? `: ${detalhe}` : ""}`);
      erro.status = resp.status;
      throw erro;
    }
    const texto = await resp.text();
    return texto ? JSON.parse(texto) : {};
  }

  async logs(minutos) {
    const desde = new Date(Date.now() - minutos * 60 * 1000).toISOString().replace(/\.\d{3}Z$/, "Z");
    const params = { from: desde, limit: "1000" };
    const resultado = [];
    for (let i = 0; i < 20; i++) { // no máximo 20 páginas de 1000 registros
      const r = await this.chamar("GET", "/logs", { params });
      resultado.push(...(r.data || []));
      const cursor = r.meta && r.meta.pagination && r.meta.pagination.cursor;
      if (!cursor) break;
      params.cursor = cursor;
    }
    return resultado;
  }

  async listaNegra() {
    const r = await this.chamar("GET", "/denylist");
    return new Set((r.data || []).map((item) => String(item.id).toLowerCase()));
  }

  async bloquear(dominio) {
    await this.chamar("POST", "/denylist", { corpo: { id: dominio, active: true } });
  }
}

/**
 * Uma rodada. Erro ao bloquear um domínio (inclusive falha de rede) não
 * impede os outros. Os logs do Worker ficam só na conta Cloudflare do dono.
 */
export async function executar(cliente, { minutos = 10, teste = false, notaMinima = 3, log = console.log } = {}) {
  const listaNegra = await cliente.listaNegra();
  const registros = await cliente.logs(minutos);
  const suspeitos = analisar(registros, listaNegra, notaMinima);

  let falhas = 0;
  for (const s of suspeitos) {
    let acao = teste ? "BLOQUEARIA" : "BLOQUEADO";
    if (!teste) {
      try {
        await cliente.bloquear(s.dominio);
      } catch (err) {
        acao = `ERRO ${err.status || "de rede"}`;
        falhas++;
      }
    }
    log(`${acao}: ${s.dominio} (nota ${s.nota}: ${s.motivos.join(", ")})`);
  }
  log(`${registros.length} registros analisados, ${suspeitos.length} suspeitos, ${falhas} falhas.`);
  return { suspeitos, falhas };
}

export default {
  async scheduled(controller, env, ctx) {
    if (!env.NEXTDNS_API_KEY || !env.NEXTDNS_PROFILE) {
      console.log("Secrets NEXTDNS_API_KEY e NEXTDNS_PROFILE não configurados: nada a fazer.");
      return;
    }
    const cliente = new ClienteNextDNS(env.NEXTDNS_API_KEY.trim(), env.NEXTDNS_PROFILE.trim());
    await executar(cliente, {
      minutos: parseInt(env.MINUTOS || "10", 10),
      teste: (env.MODO_TESTE || "0") === "1",
      notaMinima: parseInt(env.NOTA_MINIMA || "3", 10),
    });
  },
};
