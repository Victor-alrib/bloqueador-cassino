// Testes da versão Cloudflare. Rodar com:  node --test cloudflare/test/
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import worker, { nota, analisar, executar, ClienteNextDNS, dominioPrincipal } from "../worker.js";

const esperado = JSON.parse(readFileSync(new URL("./esperado.json", import.meta.url), "utf-8"));
const exemplo = JSON.parse(readFileSync(new URL("../../exemplos/registros_exemplo.json", import.meta.url), "utf-8"));

test("notas idênticas às da versão Python (sozinho e junto de cassino)", () => {
  const dominios = Object.keys(esperado.notas);
  assert.ok(dominios.length >= 190);
  for (const d of dominios) {
    assert.deepEqual(nota(d), esperado.notas[d].sozinho, `sozinho: ${d}`);
    assert.deepEqual(nota(d, true), esperado.notas[d].junto, `junto: ${d}`);
  }
});

test("análise do registro de exemplo igual à da versão Python: 12 suspeitos", () => {
  const r = analisar(exemplo.logs, new Set(exemplo.lista_negra));
  assert.deepEqual(r.map((s) => [s.dominio, s.nota, s.motivos]), esperado.analise_exemplo);
  assert.equal(r.length, 12);
});

test("domínio principal", () => {
  assert.equal(dominioPrincipal("api5.a-b-c-8.com"), "a-b-c-8.com");
  assert.equal(dominioPrincipal("x.y.com.br"), "y.com.br");
  assert.equal(dominioPrincipal("Exemplo.COM."), "exemplo.com");
});

class ClienteFalso {
  constructor({ falharEm = new Set(), erroDeRede = new Set() } = {}) {
    this.bloqueados = [];
    this.falharEm = falharEm;
    this.erroDeRede = erroDeRede;
  }
  async listaNegra() { return new Set(exemplo.lista_negra); }
  async logs() { return exemplo.logs; }
  async bloquear(d) {
    if (this.erroDeRede.has(d)) throw new TypeError("fetch failed");
    if (this.falharEm.has(d)) { const e = new Error("HTTP 429"); e.status = 429; throw e; }
    this.bloqueados.push(d);
  }
}

test("executar bloqueia os suspeitos", async () => {
  const c = new ClienteFalso();
  const { suspeitos, falhas } = await executar(c, { log: () => {} });
  assert.equal(falhas, 0);
  assert.deepEqual(c.bloqueados, suspeitos.map((s) => s.dominio));
});

test("modo teste não bloqueia nada", async () => {
  const c = new ClienteFalso();
  const linhas = [];
  await executar(c, { teste: true, log: (l) => linhas.push(l) });
  assert.equal(c.bloqueados.length, 0);
  assert.ok(linhas.some((l) => l.startsWith("BLOQUEARIA:")));
});

test("erro de API ou de rede num domínio não impede os outros", async () => {
  const c = new ClienteFalso({ falharEm: new Set(["a-b-c-8.com"]), erroDeRede: new Set(["6-q-r-s.com"]) });
  const linhas = [];
  const { suspeitos, falhas } = await executar(c, { log: (l) => linhas.push(l) });
  assert.equal(falhas, 2);
  assert.equal(c.bloqueados.length, suspeitos.length - 2);
  assert.ok(linhas.includes(linhas.find((l) => l.startsWith("ERRO 429: a-b-c-8.com"))));
  assert.ok(linhas.some((l) => l.startsWith("ERRO de rede: 6-q-r-s.com")));
});

function fetchFalso(respostas) {
  const chamadas = [];
  const fn = async (url, opcoes) => {
    chamadas.push({ url, ...opcoes });
    const r = respostas.shift();
    return { ok: r.status < 400, status: r.status, text: async () => JSON.stringify(r.corpo ?? {}) };
  };
  return { fn, chamadas };
}

test("cliente monta as requisições como a API do NextDNS espera", async () => {
  const { fn, chamadas } = fetchFalso([
    { status: 200, corpo: { data: [{ id: "X8S9M0Q.com" }] } },
    { status: 200, corpo: { data: [{ domain: "a.com" }], meta: { pagination: { cursor: "c1" } } } },
    { status: 200, corpo: { data: [{ domain: "b.com" }], meta: { pagination: { cursor: null } } } },
    { status: 200, corpo: {} },
  ]);
  const c = new ClienteNextDNS("chave", "abc123", fn);
  assert.deepEqual([...(await c.listaNegra())], ["x8s9m0q.com"]);
  assert.equal((await c.logs(30)).length, 2);
  await c.bloquear("z6u2ybx.com");

  assert.equal(chamadas[0].url, "https://api.nextdns.io/profiles/abc123/denylist");
  assert.equal(chamadas[0].headers["X-Api-Key"], "chave");
  assert.match(chamadas[1].url, /\/logs\?from=\d{4}-\d\d-\d\dT\d\d%3A\d\d%3A\d\dZ&limit=1000$/);
  assert.match(chamadas[2].url, /cursor=c1/);
  assert.equal(chamadas[3].method, "POST");
  assert.deepEqual(JSON.parse(chamadas[3].body), { id: "z6u2ybx.com", active: true });
});

test("fetch é chamado sem `this`, como o runtime do Workers exige", async () => {
  // Imita o fetch do Workers: falha se for chamado como método de um objeto.
  function fetchDoWorkers() {
    if (this !== undefined) throw new TypeError("Illegal invocation");
    return Promise.resolve(new Response(JSON.stringify({ data: [] }), { status: 200 }));
  }
  const cliente = new ClienteNextDNS("chave", "abc123", fetchDoWorkers);
  assert.deepEqual([...(await cliente.listaNegra())], []);
});

test("erro HTTP da API vira exceção com o status", async () => {
  const { fn } = fetchFalso([{ status: 403 }]);
  const c = new ClienteNextDNS("chave", "abc123", fn);
  await assert.rejects(c.listaNegra(), (e) => e.status === 403 && e.message.startsWith("HTTP 403 em GET /denylist"));
});

test("sem Secrets, o agendamento termina sem chamar a API", async () => {
  const original = globalThis.fetch;
  let chamou = false;
  globalThis.fetch = async () => { chamou = true; throw new Error("não devia chamar"); };
  try {
    await worker.scheduled({}, {}, {});
  } finally {
    globalThis.fetch = original;
  }
  assert.equal(chamou, false);
});
