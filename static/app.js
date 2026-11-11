"use strict";

const $ = (sel, raiz = document) => raiz.querySelector(sel);
const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

const MAX_IMAGEM = 12 * 1024 * 1024; // 12 MB
const MAX_TEXTO = 2 * 1024 * 1024; // 2 MB
const CHAVE_RASCUNHO = "testdoc:rascunho";
const CHAVE_TEMA = "testdoc:tema";
const LISTAS = ["requisitos", "equipamentos", "revisoes"];

const form = $("#form");
let urlPdf = null;
let restaurando = false;

/* ---------------------------------------------------------------- utilidades */
function toast(msg, tipo = "") {
  const el = document.createElement("div");
  el.className = `toast ${tipo}`;
  el.textContent = msg;
  $("#toasts").append(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 250); }, 3800);
}

const ler = (obj, caminho) => caminho.split(".").reduce((o, k) => (o == null ? o : o[k]), obj);
function gravar(obj, caminho, valor) {
  const chaves = caminho.split(".");
  const ultima = chaves.pop();
  let o = obj;
  for (const k of chaves) o = o[k] ??= {};
  o[ultima] = valor;
}

function lerDataURL(arquivo) {
  return new Promise((ok, erro) => {
    const fr = new FileReader();
    fr.onload = () => ok(fr.result);
    fr.onerror = () => erro(fr.error);
    fr.readAsDataURL(arquivo);
  });
}

async function lerTexto(arquivo) {
  const bytes = await arquivo.arrayBuffer();
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return new TextDecoder("windows-1252").decode(bytes); // exportações antigas (ANSI)
  }
}

/* ---------------------------------------------------------------------- tema */
function alternarTema() {
  const novo = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = novo;
  try { localStorage.setItem(CHAVE_TEMA, novo); } catch { /* armazenamento indisponível */ }
}
// sem escolha salva, acompanha a preferência do sistema
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
  let salvo = null;
  try { salvo = localStorage.getItem(CHAVE_TEMA); } catch { /* idem */ }
  if (!salvo) document.documentElement.dataset.theme = e.matches ? "dark" : "light";
});

/* ------------------------------------------------------------ área de imagem */
function iniciarDrop(drop) {
  const input = Object.assign(document.createElement("input"), { type: "file", accept: "image/png,image/jpeg", hidden: true });
  drop.tabIndex = 0;
  drop.setAttribute("role", "button");
  drop.setAttribute("aria-label", drop.dataset.label);
  drop._dados = null;

  const desenhar = () => {
    drop.replaceChildren(input);
    drop.classList.toggle("has", !!drop._dados);
    if (!drop._dados) {
      const vazio = document.createElement("div");
      vazio.className = "drop-empty";
      vazio.append(Object.assign(document.createElement("strong"), { textContent: drop.dataset.label }),
        Object.assign(document.createElement("small"), { textContent: drop.dataset.hint }));
      drop.append(vazio);
      return;
    }
    const img = Object.assign(document.createElement("img"), { src: drop._dados, alt: drop.dataset.label });
    const barra = document.createElement("div");
    barra.className = "drop-tools";
    const trocar = Object.assign(document.createElement("button"), { type: "button", textContent: "Trocar" });
    const remover = Object.assign(document.createElement("button"), { type: "button", textContent: "Remover" });
    trocar.onclick = (e) => { e.stopPropagation(); input.click(); };
    remover.onclick = (e) => { e.stopPropagation(); drop._definir(null); agendarRascunho(); };
    barra.append(trocar, remover);
    drop.append(img, barra);
  };

  const receber = async (arquivo) => {
    if (!arquivo) return;
    if (!["image/png", "image/jpeg"].includes(arquivo.type)) return toast("Envie uma imagem PNG ou JPG.", "err");
    if (arquivo.size > MAX_IMAGEM) return toast("Imagem acima de 12 MB. Reduza o arquivo e tente novamente.", "err");
    try {
      drop._definir(await lerDataURL(arquivo));
      agendarRascunho();
    } catch {
      toast("Não foi possível ler a imagem.", "err");
    }
  };

  drop._definir = (dados) => { drop._dados = typeof dados === "string" && dados.startsWith("data:image/") ? dados : null; desenhar(); };
  input.addEventListener("change", () => { receber(input.files[0]); input.value = ""; });
  drop.addEventListener("click", () => { if (!drop._dados) input.click(); });
  drop.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && e.target === drop && !drop._dados) { e.preventDefault(); input.click(); }
  });
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => { e.stopPropagation(); receber(e.dataTransfer.files[0]); });
  desenhar();
}

/* --------------------------------------------------- leitura do .txt do SER */
function interpretarSer(texto, nomeArquivo) {
  const linhas = texto.replace(/\r\n?/g, "\n").split("\n");
  const ehRegua = (l) => /^\s*={10,}\s*$/.test(l || "");
  const cabecalho = [];
  const secoes = [];
  let atual = null;

  for (let i = 0; i < linhas.length; i++) {
    if (ehRegua(linhas[i]) && linhas[i + 1] !== undefined && ehRegua(linhas[i + 2])) {
      atual = { rele: linhas[i + 1].trim().replace(/^SER\s*[—–-]\s*/i, ""), linhas: [] };
      secoes.push(atual);
      i += 2;
      continue;
    }
    (atual ? atual.linhas : cabecalho).push(linhas[i]);
  }

  const aparar = (ls) => ls.join("\n").replace(/^\n+/, "").replace(/\s+$/, "");
  const meta = {};
  for (const l of cabecalho) {
    let m;
    if ((m = l.match(/^\s*Teste\s+(.+?)\s*$/i)) && !meta.id) meta.id = m[1];
    else if ((m = l.match(/^\s*Condi[çc][ãa]o simulada\s*:\s*(.+)$/i))) meta.pre_condicao = m[1].trim();
    else if ((m = l.match(/^\s*Resultado(?: esperado)?\s*:\s*(.+)$/i))) meta.resultado_plano = m[1].trim();
  }
  if (!secoes.length) {
    const conteudo = aparar(linhas);
    return { meta: {}, logs: conteudo ? [{ rele: nomeArquivo.replace(/\.[^.]+$/, ""), conteudo }] : [] };
  }
  return { meta, logs: secoes.map((s) => ({ rele: s.rele, conteudo: aparar(s.linhas) })) };
}

/* ---------------------------------------------------------- linhas e testes */
function preencherCampos(no, dados) {
  $$("[data-f]", no).forEach((c) => {
    const v = dados?.[c.dataset.f];
    if (c.classList.contains("drop")) c._definir(v || null);
    else if (v != null && v !== "") c.value = v;
  });
}

function coletarCampos(no) {
  const saida = {};
  $$("[data-f]", no).forEach((c) => {
    saida[c.dataset.f] = c.classList.contains("drop") ? c._dados : c.tagName === "TEXTAREA" ? c.value : c.value.trim();
  });
  return saida;
}

function novaLinha(tipo, dados) {
  const lista = $(`#${tipo}`);
  const no = $(`#tpl-${tipo}`).content.firstElementChild.cloneNode(true);
  if (!dados && tipo === "requisitos") dados = { id: `RF-${lista.children.length + 1}` };
  preencherCampos(no, dados);
  $(".x", no).onclick = () => { no.remove(); agendarRascunho(); };
  lista.append(no);
  return no;
}

function novoLog(teste, dados = {}) {
  const no = $("#tpl-log").content.firstElementChild.cloneNode(true);
  $(".log-rele", no).value = dados.rele || "";
  $(".log-text", no).value = dados.conteudo || "";
  $(".log-remove", no).onclick = () => { no.remove(); agendarRascunho(); };
  $(".log-file", no).addEventListener("change", async (e) => {
    const arq = e.target.files[0];
    e.target.value = "";
    if (!arq) return;
    if (arq.size > MAX_TEXTO) return toast("Arquivo de log acima de 2 MB.", "err");
    const { logs } = interpretarSer(await lerTexto(arq), arq.name);
    if (!logs.length) return toast("O arquivo está vazio.", "err");
    $(".log-text", no).value = logs.map((l) => l.conteudo).join("\n\n");
    if (!$(".log-rele", no).value.trim()) $(".log-rele", no).value = logs[0].rele;
    agendarRascunho();
  });
  $(".logs", teste).append(no);
  return no;
}

async function importarLogs(teste, arquivos) {
  let total = 0;
  for (const arq of arquivos) {
    if (arq.size > MAX_TEXTO) { toast(`"${arq.name}" excede 2 MB e foi ignorado.`, "err"); continue; }
    let lido;
    try { lido = interpretarSer(await lerTexto(arq), arq.name); }
    catch { toast(`Não foi possível ler "${arq.name}".`, "err"); continue; }
    for (const [campo, valor] of Object.entries(lido.meta)) {
      const c = $(`[data-f="${campo}"]`, teste);
      if (c && valor && (!c.value.trim() || (campo === "id" && c.dataset.auto))) { c.value = valor; delete c.dataset.auto; }
    }
    lido.logs.forEach((l) => novoLog(teste, l));
    total += lido.logs.length;
  }
  toast(total ? `${total} log${total > 1 ? "s" : ""} de relé importado${total > 1 ? "s" : ""}.` : "Nenhum log encontrado nos arquivos.", total ? "" : "err");
  agendarRascunho();
}

function novoTeste(dados) {
  const lista = $("#testes");
  const no = $("#tpl-testes").content.firstElementChild.cloneNode(true);
  $$(".drop", no).forEach(iniciarDrop);
  const campoId = $('[data-f="id"]', no);
  if (dados) {
    preencherCampos(no, dados);
    (dados.logs || []).forEach((l) => novoLog(no, l));
  } else {
    campoId.value = `T-${lista.children.length + 1}`;
    campoId.dataset.auto = "1"; // pode ser substituído pelo ID vindo do .txt
  }
  campoId.addEventListener("input", () => delete campoId.dataset.auto);

  $(".toggle", no).onclick = () => no.classList.toggle("closed");
  $(".remove", no).onclick = () => {
    const d = coletarTeste(no);
    const preenchido = d.titulo || d.pre_condicao.trim() || d.procedimento.trim() || d.logs.length || d.pre_img || d.esperado_img;
    if (preenchido && !confirm("Remover este teste e todo o seu conteúdo?")) return;
    no.remove();
    agendarRascunho();
  };
  $(".add-log", no).onclick = () => $(".log-rele", novoLog(no)).focus();
  $(".log-import", no).addEventListener("change", (e) => {
    const arquivos = [...e.target.files];
    e.target.value = "";
    if (arquivos.length) importarLogs(no, arquivos);
  });
  $(".scada-import", no).addEventListener("change", async (e) => {
    const arq = e.target.files[0];
    e.target.value = "";
    if (!arq) return;
    if (arq.size > MAX_TEXTO) return toast("Arquivo acima de 2 MB.", "err");
    const campo = $('[data-f="scada"]', no);
    const texto = (await lerTexto(arq)).replace(/\r\n?/g, "\n").trim();
    campo.value = campo.value.trim() ? `${campo.value.trimEnd()}\n${texto}` : texto;
    agendarRascunho();
  });
  lista.append(no);
  return no;
}

function coletarTeste(no) {
  const t = coletarCampos(no);
  t.logs = $$(".log", no)
    .map((l) => ({ rele: $(".log-rele", l).value.trim(), conteudo: $(".log-text", l).value }))
    .filter((l) => l.rele || l.conteudo.trim());
  return t;
}

/* ------------------------------------------------------- coletar / preencher */
function coletar() {
  const d = {};
  $$("[data-k]", form).forEach((c) => {
    gravar(d, c.dataset.k, c.classList.contains("drop") ? c._dados : c.tagName === "TEXTAREA" ? c.value : c.value.trim());
  });
  d.requisitos = $$("#requisitos .row").map(coletarCampos);
  d.metodologia.equipamentos = $$("#equipamentos .row").map(coletarCampos);
  d.revisoes = $$("#revisoes .row").map(coletarCampos);
  d.testes = $$("#testes .test").map(coletarTeste);
  return d;
}

function preencher(d) {
  restaurando = true;
  try {
    $$("[data-k]", form).forEach((c) => {
      const v = ler(d, c.dataset.k);
      if (c.classList.contains("drop")) c._definir(v || null);
      else c.value = typeof v === "string" ? v : "";
    });
    LISTAS.forEach((t) => $(`#${t}`).replaceChildren());
    $("#testes").replaceChildren();
    const lista = (v) => (Array.isArray(v) ? v.filter((x) => x && typeof x === "object") : []);
    lista(d.requisitos).forEach((r) => novaLinha("requisitos", r));
    lista(d.metodologia?.equipamentos).forEach((r) => novaLinha("equipamentos", r));
    lista(d.revisoes).forEach((r) => novaLinha("revisoes", r));
    lista(d.testes).forEach((t) => novoTeste({ ...t, logs: lista(t.logs) }));
  } finally {
    restaurando = false;
  }
}

function estadoInicial(manter = {}) {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  preencher({
    cabecalho: manter.cabecalho || {},
    capa: { data: `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`, revisao: "0" },
    requisitos: [{ id: "RF-1" }],
    metodologia: { equipamentos: [{}] },
    revisoes: [{ rev: "0", descricao: "Emissão Inicial" }],
    testes: [],
  });
  novoTeste();
}

/* ------------------------------------------------------------------ rascunho */
let temporizador = null;
function agendarRascunho() {
  if (restaurando) return;
  clearTimeout(temporizador);
  temporizador = setTimeout(salvarRascunho, 600);
}

function salvarRascunho() {
  const dados = coletar();
  const aviso = $("#salvo");
  try {
    localStorage.setItem(CHAVE_RASCUNHO, JSON.stringify(dados));
    aviso.textContent = "Rascunho salvo neste navegador";
  } catch {
    // imagens grandes estouram a cota: guarda apenas os textos
    try {
      localStorage.setItem(CHAVE_RASCUNHO, JSON.stringify(dados, (_, v) => (typeof v === "string" && v.startsWith("data:image/") ? null : v)));
      aviso.textContent = "Rascunho salvo sem as imagens — use Salvar para guardar tudo";
    } catch {
      aviso.textContent = "Rascunho não salvo — use Salvar";
    }
  }
}

function salvarProjeto() {
  const dados = coletar();
  const base = (dados.capa.titulo || "projeto").normalize("NFKD").replace(/[^\w]+/g, "_").replace(/^_+|_+$/g, "") || "projeto";
  const url = URL.createObjectURL(new Blob([JSON.stringify(dados)], { type: "application/json" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: `testdoc_${base}.json` });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function abrirProjeto(arquivo) {
  try {
    const dados = JSON.parse(await arquivo.text());
    if (!dados || typeof dados !== "object" || Array.isArray(dados)) throw new Error();
    preencher(dados);
    salvarRascunho();
    toast("Projeto carregado.");
  } catch {
    toast("Arquivo de projeto inválido.", "err");
  }
}

/* --------------------------------------------------------------------- envio */
async function gerar() {
  const titulo = $('[data-k="capa.titulo"]');
  if (!titulo.value.trim()) {
    titulo.classList.add("invalid");
    titulo.focus();
    return toast("Informe o título do certificado.", "err");
  }
  const loader = $("#loader");
  loader.hidden = false;
  try {
    const resp = await fetch("/api/gerar-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(coletar()),
    });
    if (!resp.ok) {
      let msg = `Erro ${resp.status} ao gerar o PDF.`;
      try { msg = (await resp.json()).erro || msg; } catch { /* resposta sem JSON */ }
      throw new Error(msg);
    }
    const blob = await resp.blob();
    const nome = (resp.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/)?.[1] || "Certificado.pdf";
    if (urlPdf) URL.revokeObjectURL(urlPdf);
    urlPdf = URL.createObjectURL(blob);
    Object.assign($("#btnBaixar"), { href: urlPdf, download: nome });
    $("#preview").src = urlPdf;
    $("#modal").hidden = false;
    $("#btnBaixar").focus();
  } catch (e) {
    toast(e instanceof TypeError ? "Sem conexão com o servidor. Verifique se o app.py está em execução." : e.message, "err");
  } finally {
    loader.hidden = true;
  }
}

function fecharModal() {
  $("#modal").hidden = true;
  $("#preview").removeAttribute("src");
}

/* -------------------------------------------------------------- inicialização */
$$(".drop", form).forEach(iniciarDrop);

let rascunho = null;
try { rascunho = JSON.parse(localStorage.getItem(CHAVE_RASCUNHO)); } catch { /* sem rascunho válido */ }
if (rascunho && typeof rascunho === "object" && !Array.isArray(rascunho)) {
  try { preencher(rascunho); $("#salvo").textContent = "Rascunho restaurado"; } catch { estadoInicial(); }
} else {
  estadoInicial();
}

$$("[data-add]").forEach((b) => (b.onclick = () => {
  const tipo = b.dataset.add;
  const no = tipo === "testes" ? novoTeste() : novaLinha(tipo);
  (tipo === "testes" ? $(".t-title", no) : $("textarea, input", no)).focus();
  agendarRascunho();
}));
$("#btnTema").onclick = alternarTema;
$("#btnGerar").onclick = gerar;
$("#btnGerar2").onclick = gerar;
$("#btnSalvar").onclick = salvarProjeto;
$("#arqProjeto").addEventListener("change", (e) => {
  const arq = e.target.files[0];
  e.target.value = "";
  if (arq) abrirProjeto(arq);
});
$("#btnLimpar").onclick = () => {
  if (!confirm("Limpar todos os campos, imagens e testes?\nO cabeçalho (logos e linhas) será mantido.")) return;
  estadoInicial({ cabecalho: coletar().cabecalho });
  salvarRascunho();
  window.scrollTo({ top: 0 });
};
$("#btnFechar").onclick = fecharModal;
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") fecharModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#modal").hidden) fecharModal(); });
form.addEventListener("submit", (e) => e.preventDefault());
form.addEventListener("input", (e) => { e.target.classList.remove("invalid"); agendarRascunho(); });
form.addEventListener("change", agendarRascunho);

// soltar arquivo fora das áreas de upload não deve navegar para fora da página
["dragover", "drop"].forEach((ev) => window.addEventListener(ev, (e) => e.preventDefault()));

// destaque da seção atual na navegação
const espiao = new IntersectionObserver(
  (entradas) => entradas.forEach((en) => {
    if (en.isIntersecting) $$(".nav a").forEach((a) => a.classList.toggle("active", a.getAttribute("href") === `#${en.target.id}`));
  }),
  { rootMargin: "-20% 0px -70% 0px" },
);
$$("form > section").forEach((s) => espiao.observe(s));
