"use strict";

const $ = (sel, raiz = document) => raiz.querySelector(sel);
const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

const MAX_IMAGEM = 12 * 1024 * 1024; // 12 MB
const MAX_LOG = 2 * 1024 * 1024; // 2 MB
const ROTULO_SELO = {
  aprovado: "Aprovado",
  ressalvas: "Com ressalvas",
  reprovado: "Não aprovado",
  nao_realizado: "Não realizado",
};

const form = $("#form");
const listaTestes = $("#testes");
let seqTeste = 0;
let urlPdf = null;

/* ------------------------------------------------------------------ toasts */
function toast(msg, tipo = "") {
  const el = document.createElement("div");
  el.className = `toast ${tipo}`;
  el.textContent = msg;
  $("#toasts").append(el);
  setTimeout(() => {
    el.classList.add("out");
    el.addEventListener("animationend", () => el.remove(), { once: true });
  }, 4200);
}

/* --------------------------------------------------------------- arquivos */
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

/* ------------------------------------------------------- área de imagem */
const ICONE_UPLOAD =
  '<svg viewBox="0 0 24 24"><path d="M4 16.5V18a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-1.5M12 15V4m0 0L8 8m4-4 4 4"/></svg>';

function iniciarDrop(drop, somentePng = false) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = somentePng ? "image/png" : "image/png,image/jpeg";
  input.hidden = true;
  drop.tabIndex = 0;
  drop.setAttribute("role", "button");
  drop.setAttribute("aria-label", drop.dataset.label);
  drop._dados = null;

  const desenhar = (nome) => {
    drop.replaceChildren(input);
    drop.classList.toggle("has", !!drop._dados);
    if (!drop._dados) {
      const vazio = document.createElement("div");
      vazio.className = "drop-empty";
      vazio.innerHTML = `${ICONE_UPLOAD}<strong></strong><small></small>`;
      $("strong", vazio).textContent = drop.dataset.label;
      $("small", vazio).textContent = drop.dataset.hint;
      drop.append(vazio);
      return;
    }
    const img = document.createElement("img");
    img.src = drop._dados;
    img.alt = drop.dataset.label;
    const barra = document.createElement("div");
    barra.className = "drop-tools";
    const trocar = Object.assign(document.createElement("button"), { type: "button", textContent: "Trocar" });
    const remover = Object.assign(document.createElement("button"), { type: "button", textContent: "Remover", className: "rm" });
    trocar.onclick = (e) => { e.stopPropagation(); input.click(); };
    remover.onclick = (e) => { e.stopPropagation(); drop._dados = null; desenhar(); atualizarProgresso(); };
    barra.append(trocar, remover);
    const rotulo = document.createElement("span");
    rotulo.className = "drop-name";
    rotulo.textContent = nome || "";
    drop.append(img, barra, rotulo);
  };

  const receber = async (arquivo) => {
    if (!arquivo) return;
    const tipos = somentePng ? ["image/png"] : ["image/png", "image/jpeg"];
    if (!tipos.includes(arquivo.type)) {
      toast(somentePng ? "Envie uma imagem no formato PNG." : "Envie uma imagem PNG ou JPG.", "err");
      return;
    }
    if (arquivo.size > MAX_IMAGEM) {
      toast("Imagem acima de 12 MB. Reduza o arquivo e tente novamente.", "err");
      return;
    }
    try {
      drop._dados = await lerDataURL(arquivo);
      desenhar(arquivo.name);
      atualizarProgresso();
    } catch {
      toast("Não foi possível ler a imagem.", "err");
    }
  };

  input.addEventListener("change", () => { receber(input.files[0]); input.value = ""; });
  drop.addEventListener("click", () => { if (!drop._dados) input.click(); });
  drop.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && e.target === drop && !drop._dados) { e.preventDefault(); input.click(); }
  });
  ["dragenter", "dragover"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => receber(e.dataTransfer.files[0]));
  drop._limpar = () => { drop._dados = null; desenhar(); };
  desenhar();
}

/* --------------------------------------------- leitura do .txt do SER */
function interpretarSer(texto, nomeArquivo) {
  const linhas = texto.replace(/\r\n?/g, "\n").split("\n");
  const ehRegua = (l) => /^\s*={10,}\s*$/.test(l || "");
  const cabecalho = [];
  const secoes = [];
  let atual = null;

  for (let i = 0; i < linhas.length; i++) {
    if (ehRegua(linhas[i]) && linhas[i + 1] !== undefined && ehRegua(linhas[i + 2])) {
      const titulo = linhas[i + 1].trim().replace(/^SER\s*[—–-]\s*/i, "");
      atual = { rele: titulo, linhas: [] };
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
    else if ((m = l.match(/^\s*Condi[çc][ãa]o simulada\s*:\s*(.+)$/i))) meta.condicao = m[1].trim();
    else if ((m = l.match(/^\s*Resultado(?: esperado)?\s*:\s*(.+)$/i))) meta.resultado = m[1].trim();
  }

  if (!secoes.length) {
    const conteudo = aparar(linhas);
    return { meta: {}, logs: conteudo ? [{ rele: nomeArquivo.replace(/\.[^.]+$/, ""), conteudo }] : [] };
  }
  return { meta, logs: secoes.map((s) => ({ rele: s.rele, conteudo: aparar(s.linhas) })) };
}

/* ----------------------------------------------------------------- testes */
function novoLog(teste, dados = {}) {
  const no = $("#tplLog").content.firstElementChild.cloneNode(true);
  $(".log-rele", no).value = dados.rele || "";
  $(".log-text", no).value = dados.conteudo || "";
  $(".log-remove", no).onclick = () => no.remove();
  $(".log-file", no).addEventListener("change", async (e) => {
    const arq = e.target.files[0];
    e.target.value = "";
    if (!arq) return;
    if (arq.size > MAX_LOG) return toast("Arquivo de log acima de 2 MB.", "err");
    const { logs } = interpretarSer(await lerTexto(arq), arq.name);
    if (!logs.length) return toast("O arquivo está vazio.", "warn");
    $(".log-text", no).value = logs.map((l) => l.conteudo).join("\n\n");
    if (!$(".log-rele", no).value.trim()) $(".log-rele", no).value = logs[0].rele;
    toast(`Log carregado de "${arq.name}".`, "ok");
  });
  $(".logs", teste).append(no);
  return no;
}

async function importarLogs(teste, arquivos) {
  let total = 0;
  for (const arq of arquivos) {
    if (arq.size > MAX_LOG) { toast(`"${arq.name}" excede 2 MB e foi ignorado.`, "err"); continue; }
    let lido;
    try { lido = interpretarSer(await lerTexto(arq), arq.name); }
    catch { toast(`Não foi possível ler "${arq.name}".`, "err"); continue; }
    const { meta, logs } = lido;
    const preencher = (sel, valor) => { const c = $(sel, teste); if (valor && !c.value.trim()) c.value = valor; };
    preencher(".test-id", meta.id);
    preencher(".t-cond", meta.condicao);
    preencher(".t-res", meta.resultado);
    logs.forEach((l) => novoLog(teste, l));
    total += logs.length;
  }
  if (total) toast(`${total} log${total > 1 ? "s" : ""} de relé importado${total > 1 ? "s" : ""}.`, "ok");
  else toast("Nenhum log encontrado nos arquivos selecionados.", "warn");
  atualizarProgresso();
}

function novoTeste() {
  const no = $("#tplTeste").content.firstElementChild.cloneNode(true);
  const grupo = `selo_${++seqTeste}`;
  $$(".chips input", no).forEach((r) => (r.name = grupo));

  const pilula = $(".seal-pill", no);
  const sincronizarSelo = () => {
    const v = $(".chips input:checked", no).value;
    pilula.className = `seal-pill ${v}`;
    pilula.textContent = ROTULO_SELO[v];
  };
  $(".chips", no).addEventListener("change", sincronizarSelo);
  sincronizarSelo();

  $(".toggle", no).onclick = () => no.classList.toggle("closed");
  $(".remove", no).onclick = () => {
    const preenchido = $$("input[type=text], textarea", no).some((c) => c.value.trim()) || $(".drop", no)._dados;
    if (preenchido && !confirm("Remover este teste e todo o seu conteúdo?")) return;
    no.classList.add("leaving");
    no.addEventListener("animationend", () => { no.remove(); renumerar(); }, { once: true });
  };
  $(".add-log", no).onclick = () => $(".log-rele", novoLog(no)).focus();
  $(".log-import", no).addEventListener("change", (e) => {
    const arquivos = [...e.target.files];
    e.target.value = "";
    if (arquivos.length) importarLogs(no, arquivos);
  });

  // arrastar .txt para dentro do teste
  no.addEventListener("dragover", (e) => { if (!e.target.closest(".drop")) e.preventDefault(); });
  no.addEventListener("drop", (e) => {
    if (e.target.closest(".drop")) return;
    e.preventDefault();
    const txts = [...e.dataTransfer.files].filter((f) => /\.(txt|log)$/i.test(f.name) || f.type === "text/plain");
    if (txts.length) importarLogs(no, txts);
  });

  iniciarDrop($(".drop", no), true);
  listaTestes.append(no);
  renumerar();
  return no;
}

function renumerar() {
  const itens = $$(".test", listaTestes);
  itens.forEach((t, i) => ($(".test-num", t).textContent = `3.${i + 1}`));
  $("#contador").textContent = `${itens.length} teste${itens.length === 1 ? "" : "s"}`;
  atualizarProgresso();
}

/* ------------------------------------------------------------- progresso */
function secaoCompleta(sec) {
  const campos = $$("[data-req]", sec);
  if (sec.id === "sec3") return $$(".test", sec).length > 0 && $$(".test", sec).every((t) => $(".t-cond", t).value.trim());
  return campos.length > 0 && campos.every((c) => c.value.trim());
}

function atualizarProgresso() {
  const campos = $$("[data-req]", form);
  let feitos = campos.filter((c) => c.value.trim()).length;
  let total = campos.length + 2; // + diagrama da SE + ao menos um teste
  if ($("#dropSE")._dados) feitos++;
  if ($$(".test", listaTestes).length) feitos++;
  const pct = Math.round((feitos / total) * 100);
  $("#ring").style.strokeDashoffset = String(97.4 * (1 - pct / 100));
  $("#ringLabel").textContent = `${pct}%`;
  $(".progress").classList.toggle("done", pct === 100);
  $$(".step").forEach((s) => s.classList.toggle("complete", secaoCompleta($(s.getAttribute("href")))));
}

/* ----------------------------------------------------------------- envio */
function coletar() {
  const v = (nome) => form.elements[nome].value.trim();
  return {
    geral: {
      nome_se: v("nome_se"),
      equipamentos: v("equipamentos"),
      norma: v("norma"),
      reles: v("reles"),
      data_emissao: v("data_emissao"),
      resultado: form.elements.resultado.value,
    },
    subestacao: {
      tensao_alta: v("tensao_alta"),
      tensao_baixa: v("tensao_baixa"),
      mala: v("mala"),
      diagrama: $("#dropSE")._dados,
    },
    testes: $$(".test", listaTestes).map((t) => ({
      id: $(".test-id", t).value.trim(),
      condicao: $(".t-cond", t).value.trim(),
      resultado: $(".t-res", t).value.trim(),
      selo: $(".chips input:checked", t).value,
      logs: $$(".log", t)
        .map((l) => ({ rele: $(".log-rele", l).value.trim(), conteudo: $(".log-text", l).value }))
        .filter((l) => l.rele || l.conteudo.trim()),
      imagem: $(".drop", t)._dados,
    })),
    validacao: {
      execucao: { nome: v("exec_nome"), matricula: v("exec_matricula"), area: v("exec_area") },
      aprovacao: { nome: v("aprov_nome"), matricula: v("aprov_matricula"), area: v("aprov_area") },
    },
  };
}

function validar() {
  $$(".invalid", form).forEach((el) => el.classList.remove("invalid"));
  const nome = form.elements.nome_se;
  if (!nome.value.trim()) {
    nome.closest(".field").classList.add("invalid");
    nome.focus();
    toast("Informe o nome da SE para gerar o certificado.", "err");
    return false;
  }
  const faltando = $$("[data-req]", form).filter((c) => !c.value.trim()).length;
  const semTeste = !$$(".test", listaTestes).length;
  if (faltando || semTeste) {
    const partes = [];
    if (faltando) partes.push(`${faltando} campo${faltando > 1 ? "s" : ""} em branco`);
    if (semTeste) partes.push("nenhum teste cadastrado");
    return confirm(`Atenção: ${partes.join(" e ")}.\nOs itens vazios aparecerão como "—" no documento.\n\nGerar mesmo assim?`);
  }
  return true;
}

async function gerar() {
  if (!validar()) return;
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
    const nome = (resp.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/)?.[1] || "Certificado_Protecao.pdf";
    if (urlPdf) URL.revokeObjectURL(urlPdf);
    urlPdf = URL.createObjectURL(blob);
    $("#btnBaixar").href = urlPdf;
    $("#btnBaixar").download = nome;
    $("#preview").src = urlPdf;
    $("#modal").hidden = false;
    $("#btnBaixar").focus();
    toast("Certificado gerado com sucesso.", "ok");
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

function limpar() {
  if (!confirm("Limpar todos os campos, imagens e testes?")) return;
  form.reset();
  $("#dropSE")._limpar();
  listaTestes.replaceChildren();
  novoTeste();
  definirHoje();
  window.scrollTo({ top: 0 });
  toast("Formulário limpo.");
}

function definirHoje() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  form.elements.data_emissao.value = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/* ------------------------------------------------------------ inicialização */
iniciarDrop($("#dropSE"));
definirHoje();
novoTeste();

$("#btnAddTeste").onclick = () => {
  const t = novoTeste();
  t.scrollIntoView({ behavior: "smooth", block: "center" });
  $(".test-id", t).focus({ preventScroll: true });
};
$("#btnGerar").onclick = gerar;
$("#btnGerar2").onclick = gerar;
$("#btnLimpar").onclick = limpar;
$("#btnFechar").onclick = fecharModal;
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") fecharModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#modal").hidden) fecharModal(); });
form.addEventListener("submit", (e) => e.preventDefault());
form.addEventListener("input", (e) => {
  e.target.closest(".invalid")?.classList.remove("invalid");
  atualizarProgresso();
});

// evita que soltar um arquivo fora das áreas de upload navegue para fora da página
["dragover", "drop"].forEach((ev) => window.addEventListener(ev, (e) => e.preventDefault()));

// aviso ao sair com dados preenchidos
window.addEventListener("beforeunload", (e) => {
  const sujo = $$("input[type=text], textarea", form).some((c) => c.value.trim());
  if (sujo && $("#modal").hidden) e.preventDefault();
});

// animação de entrada e navegação lateral
const revelar = new IntersectionObserver(
  (entradas) => entradas.forEach((en) => { if (en.isIntersecting) { en.target.classList.add("in"); revelar.unobserve(en.target); } }),
  { threshold: 0.08 },
);
$$(".reveal").forEach((el, i) => { el.style.transitionDelay = `${Math.min(i, 3) * 80}ms`; revelar.observe(el); });

const espiao = new IntersectionObserver(
  (entradas) => entradas.forEach((en) => {
    if (en.isIntersecting) $$(".step").forEach((s) => s.classList.toggle("active", s.getAttribute("href") === `#${en.target.id}`));
  }),
  { rootMargin: "-30% 0px -60% 0px" },
);
$$("section.card").forEach((s) => espiao.observe(s));

atualizarProgresso();
