"""Geração do Certificado de Ensaios de Automação em PDF (ReportLab)."""

from __future__ import annotations

import base64
import io
import os
import re
from datetime import datetime
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    CondPageBreak,
    HRFlowable,
    Image,
    Indenter,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# --------------------------------------------------------------------------
# Paleta do modelo
# --------------------------------------------------------------------------
AZUL_TITULO = colors.HexColor("#1f3864")
AZUL_TABELA = colors.HexColor("#1f4e79")
AZUL_CLARO = colors.HexColor("#dce6f1")
AZUL_CAPA = colors.HexColor("#e7ecf7")
PRETO = colors.black
CINZA = colors.HexColor("#666666")

STATUS = {
    "aprovado": ("Aprovado", colors.HexColor("#2e9e3f")),
    "ressalvas": ("Aprovado com Ressalvas", colors.HexColor("#c77700")),
    "reprovado": ("Não Aprovado", colors.HexColor("#c62828")),
    "nao_realizado": ("Não Realizado", colors.HexColor("#6b7280")),
}

# Cabeçalho e título fixos do modelo (não editáveis pela interface)
DOCUMENTO = "Certificado de Ensaios de Automação"
CABECALHO_LINHAS = ("Gerência Corporativa de Automação", "Executiva Corporativa de Automação AT e RD")
_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "logos")
LOGO_ESQUERDA = os.path.join(_ASSETS, "logo_esquerda.png")
LOGO_DIREITA = os.path.join(_ASSETS, "logo_direita.png")
MAX_LINHAS_LOG = 4000
MAX_LADO_IMAGEM = 2200  # px

PAGINA_L, PAGINA_A = A4
MARGEM_X = 54
MARGEM_TOPO = 92
MARGEM_BASE = 62

# --------------------------------------------------------------------------
# Fontes: Arial/Liberation/DejaVu quando disponíveis (Unicode), senão padrão PDF
# --------------------------------------------------------------------------
_CANDIDATOS = [
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf",
     "C:/Windows/Fonts/cour.ttf", "C:/Windows/Fonts/courbd.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
     "/System/Library/Fonts/Supplemental/Courier New.ttf", "/System/Library/Fonts/Supplemental/Courier New Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf"),
    ("/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf",
     "/usr/share/fonts/liberation-sans/LiberationSans-Bold.ttf",
     "/usr/share/fonts/liberation-mono/LiberationMono-Regular.ttf",
     "/usr/share/fonts/liberation-mono/LiberationMono-Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"),
]

FONT, FONT_B, FONT_MONO, FONT_MONO_B = "Helvetica", "Helvetica-Bold", "Courier", "Courier-Bold"
UNICODE_OK = False
for _arquivos in _CANDIDATOS:
    if all(os.path.isfile(p) for p in _arquivos):
        try:
            for _nome, _arq in zip(("Doc", "Doc-Bold", "Doc-Mono", "Doc-Mono-Bold"), _arquivos):
                pdfmetrics.registerFont(TTFont(_nome, _arq))
            pdfmetrics.registerFontFamily("Doc", normal="Doc", bold="Doc-Bold")
            FONT, FONT_B, FONT_MONO, FONT_MONO_B = "Doc", "Doc-Bold", "Doc-Mono", "Doc-Mono-Bold"
            UNICODE_OK = True
            break
        except Exception:  # fonte ilegível: tenta a próxima
            continue


def _limpo(texto) -> str:
    """Normaliza texto; sem fonte Unicode, restringe ao conjunto cp1252."""
    texto = "" if texto is None else str(texto)
    texto = texto.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    texto = "".join(ch for ch in texto if ch == "\n" or ord(ch) >= 32)
    if not UNICODE_OK:
        texto = texto.replace("→", "->").encode("cp1252", "replace").decode("cp1252")
    return texto


def _xml(texto) -> str:
    return escape(_limpo(texto).strip()).replace("\n", "<br/>")


def _linhas(texto) -> list[str]:
    """Uma entrada por linha não vazia, sem marcadores/numeração digitados."""
    saida = []
    for linha in _limpo(texto).split("\n"):
        linha = re.sub(r"^\s*(?:[-•*–·]|\d+[.)])\s+", "", linha).strip()
        if linha:
            saida.append(linha)
    return saida


# --------------------------------------------------------------------------
# Estilos
# --------------------------------------------------------------------------
def _e(nome, **kw):
    base = dict(fontName=FONT, fontSize=9, leading=12.5, textColor=PRETO)
    base.update(kw)
    return ParagraphStyle(nome, **base)


S_DOC = _e("doc", fontName=FONT_B, fontSize=15, leading=19, textColor=AZUL_TITULO)
S_SECAO = _e("secao", fontName=FONT_B, fontSize=11, leading=14, textColor=AZUL_TITULO,
             spaceBefore=16, spaceAfter=9, leftIndent=17, firstLineIndent=-17)
S_SUBSECAO = _e("subsecao", fontName=FONT_B, fontSize=9, spaceBefore=10, spaceAfter=3, leftIndent=6)
S_TEXTO = _e("texto", alignment=TA_JUSTIFY)
S_TEXTO_REC = _e("texto_rec", leftIndent=16)
S_ROTULO = _e("rotulo", fontName=FONT_B)
S_CEL = _e("cel", fontSize=8.5, leading=12)
S_CEL_B = _e("cel_b", fontSize=8.5, leading=12, fontName=FONT_B)
S_CEL_C = _e("cel_c", fontSize=8.5, leading=12, alignment=TA_CENTER)
S_TH = _e("th", fontSize=8.5, leading=12, fontName=FONT_B, textColor=colors.white)
S_TH_C = _e("th_c", fontSize=8.5, leading=12, fontName=FONT_B, textColor=colors.white, alignment=TA_CENTER)
S_REQ = _e("req", fontSize=8.5, leading=15)
S_TESTE = _e("teste", fontName=FONT_B, fontSize=10, leading=13, textColor=colors.white)
S_BLOCO = _e("bloco", fontName=FONT_B, spaceBefore=14, spaceAfter=7)
S_ITEM = _e("item", leftIndent=34, bulletIndent=18, spaceAfter=2.5)
S_ITEM_REC = _e("item_rec", leftIndent=44, bulletIndent=28, spaceAfter=2.5)
S_VAZIO = _e("vazio", textColor=CINZA)


def P(texto, estilo=S_CEL):
    conteudo = _xml(texto)
    return Paragraph(conteudo or "&nbsp;", estilo)


# --------------------------------------------------------------------------
# Imagens
# --------------------------------------------------------------------------
def _decodificar_imagem(data_url):
    """data URL/base64 -> (BytesIO PNG, largura_px, altura_px) ou None."""
    if not data_url or not isinstance(data_url, str):
        return None
    bruto = data_url.split(",", 1)[1] if data_url.startswith("data:") else data_url
    try:
        img = PILImage.open(io.BytesIO(base64.b64decode(bruto)))
        img.load()
    except Exception as exc:
        raise ValueError("Uma das imagens enviadas é inválida ou está corrompida.") from exc
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() or "transparency" in img.info else "RGB")
    if img.mode == "RGBA":  # achata sobre branco
        fundo = PILImage.new("RGB", img.size, (255, 255, 255))
        fundo.paste(img, mask=img.getchannel("A"))
        img = fundo
    if max(img.size) > MAX_LADO_IMAGEM:
        img.thumbnail((MAX_LADO_IMAGEM, MAX_LADO_IMAGEM), PILImage.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf, img.size[0], img.size[1]


def _figura(dados, larg_max, alt_max):
    buf, w, h = dados
    escala = min(larg_max / w, alt_max / h)
    img = Image(buf, width=w * escala, height=h * escala)
    img.hAlign = "CENTER"
    return img


# --------------------------------------------------------------------------
# Tabelas
# --------------------------------------------------------------------------
def _tabela(dados, larguras, grade=True, extra=()):
    """Tabela com cabeçalho azul e linhas alternadas, como no modelo."""
    t = Table(dados, colWidths=larguras, repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), AZUL_TABELA),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, AZUL_CLARO]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    if grade:
        estilo += [("BOX", (0, 0), (-1, -1), 0.6, PRETO), ("INNERGRID", (0, 0), (-1, -1), 0.5, PRETO)]
    estilo.extend(extra)
    t.setStyle(TableStyle(estilo))
    return t


def _bloco_log(nome_rele, conteudo, largura):
    tam = 7.6
    larg_char = pdfmetrics.stringWidth("M", FONT_MONO, tam)
    max_cols = max(20, int(largura / larg_char))

    saida = []
    for linha in _limpo(conteudo).strip("\n").split("\n"):
        linha = linha.rstrip()
        while len(linha) > max_cols:
            saida.append(linha[:max_cols])
            linha = "  " + linha[max_cols:]
        saida.append(linha)
    if len(saida) > MAX_LINHAS_LOG:
        saida = saida[:MAX_LINHAS_LOG] + [f"... (log truncado em {MAX_LINHAS_LOG} linhas)"]

    dados = [[_limpo(nome_rele).strip() or "Relé"]] + [[s] for s in saida]
    t = Table(dados, colWidths=[largura], repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), FONT_MONO_B),
                ("FONTSIZE", (0, 0), (-1, 0), 8.5),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
                ("TOPPADDING", (0, 0), (-1, 0), 0),
                ("FONTNAME", (0, 1), (-1, -1), FONT_MONO),
                ("FONTSIZE", (0, 1), (-1, -1), tam),
                ("LEADING", (0, 1), (-1, -1), tam + 2),
                ("TOPPADDING", (0, 1), (-1, -1), 0.2),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 0.2),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return t


_RE_TS = re.compile(r"^(\d{2,4}[-/]\d{2}[-/]\d{2,4}[ T]\d{1,2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?)\s+(.*)$")


def _interpretar_scada(texto) -> list[list[str]]:
    """Cada linha -> [timestamp, tag, mensagem]. Aceita ';', TAB ou colunas alinhadas."""
    eventos = []
    bruto = "" if texto is None else str(texto).replace("\r\n", "\n").replace("\r", "\n")
    for linha in bruto.split("\n"):
        linha = linha.strip()
        if not linha:
            continue
        if ";" in linha or "\t" in linha:
            partes = [p.strip() for p in re.split(r"[;\t]", linha)]
            partes = [p for p in partes if p] if len(partes) > 3 else partes
        else:
            m = _RE_TS.match(linha)
            if m:
                resto = re.split(r"\s{2,}", m.group(2).strip())
                if len(resto) >= 2:
                    partes = [m.group(1), " ".join(resto[:-1]), resto[-1]]
                else:
                    tag, _, msg = resto[0].rpartition(" ")
                    partes = [m.group(1), tag or msg, msg if tag else ""]
            else:
                partes = re.split(r"\s{2,}", linha)
        if len(partes) > 3:
            partes = [partes[0], " ".join(partes[1:-1]), partes[-1]]
        partes += [""] * (3 - len(partes))
        if partes[0].lower() == "timestamp":  # cabeçalho colado junto
            continue
        eventos.append(partes)
    return eventos


def _formatar_data(valor) -> str:
    valor = (valor or "").strip()
    try:
        return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return valor


# --------------------------------------------------------------------------
# Canvas: cabeçalho e rodapé em todas as páginas
# --------------------------------------------------------------------------
def _logo_fixa(caminho):
    """Logo do cabeçalho -> (ImageReader, largura_px, altura_px) ou None se o arquivo faltar."""
    try:
        with PILImage.open(caminho) as img:
            largura, altura = img.size
        return ImageReader(caminho), largura, altura
    except OSError:
        return None


def _canvas_modelo(rodape):
    leitores = {k: v for k, v in (("esq", _logo_fixa(LOGO_ESQUERDA)), ("dir", _logo_fixa(LOGO_DIREITA))) if v}
    linhas = CABECALHO_LINHAS

    class CanvasModelo(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._paginas = []

        def showPage(self):
            self._paginas.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            for estado in self._paginas:
                self.__dict__.update(estado)
                self._moldura()
                super().showPage()
            super().save()

        def _logo(self, chave, x, larg_max, alt_max, direita=False):
            if chave not in leitores:
                return 0
            leitor, w, h = leitores[chave]
            escala = min(larg_max / w, alt_max / h)
            lw, lh = w * escala, h * escala
            centro = PAGINA_A - 56
            self.drawImage(leitor, x - lw if direita else x, centro - lh / 2, lw, lh, mask="auto")
            return lw

        def _moldura(self):
            self.saveState()
            self._logo("esq", MARGEM_X, 120, 44)
            ocupado = self._logo("dir", PAGINA_L - MARGEM_X, 46, 46, direita=True)
            x_txt = PAGINA_L - MARGEM_X - (ocupado + 10 if ocupado else 0)
            self.setFillColor(PRETO)
            self.setFont(FONT, 9.5)
            y = PAGINA_A - 56 + (len(linhas) - 1) * 6.5 - 3
            for linha in linhas:
                self.drawRightString(x_txt, y, linha)
                y -= 13
            self.setFont(FONT, 8.5)
            self.drawRightString(PAGINA_L - MARGEM_X, 50, str(self._pageNumber))
            if rodape:
                self.drawString(MARGEM_X, 38, rodape)
            self.restoreState()

    return CanvasModelo


# --------------------------------------------------------------------------
# Documento
# --------------------------------------------------------------------------
def gerar_pdf(dados: dict) -> bytes:
    """Recebe o dicionário enviado pela interface e devolve o PDF em bytes."""
    capa = dados.get("capa") or {}
    met = dados.get("metodologia") or {}
    requisitos = [r for r in (dados.get("requisitos") or []) if (r.get("id") or r.get("texto"))]
    equipamentos = [q for q in (met.get("equipamentos") or []) if (q.get("nome") or q.get("aplicacao"))]
    testes = dados.get("testes") or []
    revisoes = [r for r in (dados.get("revisoes") or []) if any(str(v).strip() for v in r.values())]

    documento = DOCUMENTO
    titulo = _limpo(capa.get("titulo")).strip()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=MARGEM_X, rightMargin=MARGEM_X,
        topMargin=MARGEM_TOPO, bottomMargin=MARGEM_BASE,
        title=f"{documento} — {titulo}" if titulo else documento,
        author=_limpo(capa.get("responsavel")).strip() or "TestDoc",
    )
    L = doc.width
    el = []

    # ---------------- Capa ----------------
    el.append(Paragraph(escape(documento), S_DOC))
    el.append(HRFlowable(width="100%", thickness=1.2, color=PRETO, spaceBefore=2, spaceAfter=8))
    info = Table(
        [
            [P("Título:", S_ROTULO), P(titulo, S_TEXTO)],
            [P("Subestação:", S_ROTULO), P(capa.get("subestacao"), S_TEXTO)],
            [P("Distribuidora:", S_ROTULO), P(capa.get("distribuidora"), S_TEXTO)],
            [P("Data:", S_ROTULO), P(_formatar_data(capa.get("data")), S_TEXTO)],
            [P("Responsável Técnico", S_ROTULO), P(capa.get("responsavel"), S_TEXTO)],
            [P("Revisão:", S_ROTULO), P(capa.get("revisao"), S_TEXTO)],
        ],
        colWidths=[122, L - 122],
    )
    info.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), AZUL_CAPA),
                ("BOX", (0, 0), (-1, -1), 0.6, PRETO),
                ("LINEBEFORE", (0, 0), (0, -1), 3.5, PRETO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    el.append(info)

    # ---------------- 1. Diagrama unifilar ----------------
    img = _decodificar_imagem(dados.get("diagrama"))
    bloco = [Paragraph("1.&nbsp;&nbsp;Diagrama Unifilar", S_SECAO)]
    bloco.append(_figura(img, L * 0.9, 300) if img else P("Diagrama não informado.", S_VAZIO))
    el.append(KeepTogether(bloco))

    # ---------------- 2. Requisitos funcionais ----------------
    el.append(CondPageBreak(110))
    el.append(Paragraph("2.&nbsp;&nbsp;Requisitos Funcionais", S_SECAO))
    if requisitos:
        linhas = [[P("N°", S_TH_C), P("Requisito", S_TH_C)]]
        linhas += [[P(r.get("id"), S_CEL_B), P(r.get("texto"), S_REQ)] for r in requisitos]
        el.append(_tabela(linhas, [46, L - 46]))
    else:
        el.append(P("Nenhum requisito cadastrado.", S_VAZIO))

    # ---------------- 3. Metodologia ----------------
    el.append(CondPageBreak(130))
    el.append(Paragraph("3.&nbsp;&nbsp;Metodologia", S_SECAO))

    el.append(Paragraph("3.1. Objetivo e Escopo", S_SUBSECAO))
    el.append(P(met.get("objetivo") or "—", S_TEXTO_REC))

    topo = _decodificar_imagem(met.get("topologia"))
    cab_32 = [Paragraph("3.2. Topologia e Equipamentos", S_SUBSECAO)]
    if topo:
        cab_32 += [Spacer(1, 4), _figura(topo, L, 250)]
    el.append(KeepTogether(cab_32))
    if equipamentos:
        linhas = [[P("Equipamento", S_TH), P("Aplicação", S_TH)]]
        linhas += [[P(q.get("nome")), P(q.get("aplicacao"))] for q in equipamentos]
        el += [Spacer(1, 8), _tabela(linhas, [L * 0.42, L * 0.58], extra=[("VALIGN", (0, 1), (-1, -1), "TOP")])]

    for numero, nome, chave in (
        ("3.3", "Comunicação e Sincronismo de Tempo", "comunicacao"),
        ("3.4", "Execução dos Ensaios", "execucao"),
    ):
        itens = _linhas(met.get(chave))
        corpo = [Paragraph(f"{numero}. {nome}", S_SUBSECAO)]
        corpo += [Paragraph(escape(i), S_ITEM, bulletText="•") for i in itens] or [P("—", S_TEXTO_REC)]
        el += [Spacer(1, 8), KeepTogether(corpo)]

    # ---------------- 4. Plano de testes ----------------
    el.append(CondPageBreak(130))
    el.append(Paragraph("4.&nbsp;&nbsp;Plano de Testes", S_SECAO))
    idents = []
    if testes:
        linhas = [[P("ID", S_TH_C), P("Cenário", S_TH_C), P("Resultado Esperado", S_TH_C), P("Status", S_TH_C)]]
        for i, t in enumerate(testes, start=1):
            ident = _limpo(t.get("id")).strip() or f"T-{i}"
            nome = _limpo(t.get("titulo")).strip()
            idents.append((ident, f"{ident}: {nome}" if nome else ident))
            rotulo, cor = STATUS.get(t.get("status"), STATUS["nao_realizado"])
            s_status = ParagraphStyle(f"st{i}", parent=S_CEL_B, textColor=cor, alignment=TA_CENTER)
            linhas.append([P(ident, S_CEL_B), P(idents[-1][1]), P(t.get("resultado_plano")), P(rotulo, s_status)])
        el.append(
            _tabela(linhas, [36, 134, L - 36 - 134 - 78, 78],
                    extra=[("TOPPADDING", (0, 1), (-1, -1), 6), ("BOTTOMPADDING", (0, 1), (-1, -1), 6)])
        )
    else:
        el.append(P("Nenhum teste cadastrado.", S_VAZIO))

    # ---------------- 5. Detalhamento dos testes ----------------
    if testes:
        el.append(PageBreak())
        el.append(Paragraph("5.&nbsp;&nbsp;Detalhamento dos Testes", S_SECAO))
    rec = 22  # recuo do corpo de cada teste
    Lr = L - rec
    for i, t in enumerate(testes):
        if i:
            el.append(PageBreak())
        faixa = Table([[Paragraph(escape(idents[i][1]), S_TESTE)]], colWidths=[L])
        faixa.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), AZUL_TABELA),
                    ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        el += [Spacer(1, 6), faixa, Spacer(1, 10), Indenter(left=rec)]

        el.append(Paragraph(f"<b>Pré-Condição:</b> {_xml(t.get('pre_condicao'))}", S_TEXTO))
        pre = _decodificar_imagem(t.get("pre_img"))
        if pre:
            el += [Spacer(1, 8), _figura(pre, Lr * 0.82, 235)]

        passos = _linhas(t.get("procedimento"))
        if passos:
            corpo = [Paragraph("Procedimento:", S_BLOCO)]
            corpo += [Paragraph(escape(p), S_ITEM_REC, bulletText=f"{n}.") for n, p in enumerate(passos, 1)]
            el.append(KeepTogether(corpo))

        esp_img = _decodificar_imagem(t.get("esperado_img"))
        esperados = _linhas(t.get("esperados"))
        if esp_img or esperados:
            corpo = [Paragraph("Resultados Esperados:", S_BLOCO)]
            if esp_img:
                corpo += [_figura(esp_img, Lr * 0.82, 235), Spacer(1, 8)]
            el.append(KeepTogether(corpo))
            el += [Paragraph(escape(x), S_ITEM, bulletText="•") for x in esperados]

        el.append(
            KeepTogether(
                [Paragraph("Comentários:", S_BLOCO),
                 P(t.get("comentarios") or "Nenhum comentário adicional.", S_TEXTO)]
            )
        )

        logs = [l for l in (t.get("logs") or []) if (l.get("rele") or (l.get("conteudo") or "").strip())]
        if logs:
            el += [CondPageBreak(90), Paragraph("Logs dos relés (SER)", S_BLOCO)]
            for j, log in enumerate(logs):
                if j:
                    el.append(Spacer(1, 12))
                el.append(_bloco_log(log.get("rele"), log.get("conteudo"), Lr))

        eventos = _interpretar_scada(t.get("scada"))
        if eventos:
            linhas = [[P("Timestamp", S_TH_C), P("Tag Name", S_TH), P("Message", S_TH)]]
            linhas += [[P(a), P(b), P(c)] for a, b, c in eventos]
            tab = _tabela(
                linhas, [128, Lr - 8 - 128 - 96, 96], grade=False,
                extra=[("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)],
            )
            el += [CondPageBreak(90), Paragraph("Logs SCADA", S_BLOCO), Indenter(left=6), tab, Indenter(left=-6)]

        el.append(Indenter(left=-rec))

    # ---------------- 6. Controle de revisões ----------------
    if testes:
        el.append(PageBreak())
    linhas = [[P("Revisão", S_TH_C), P("Descrição", S_TH_C), P("Responsável", S_TH_C)]]
    linhas += [[P(r.get("rev"), S_CEL_C), P(r.get("descricao"), S_CEL_C), P(r.get("responsavel"), S_CEL_C)]
               for r in revisoes] or [[P("—", S_CEL_C)] * 3]
    el.append(
        KeepTogether(
            [
                Paragraph("6.&nbsp;&nbsp;Controle de Revisões", S_SECAO),
                _tabela(linhas, [L * 0.14, L * 0.54, L * 0.32], grade=False,
                        extra=[("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white]),
                               ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#9aa7b8")),
                               ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9aa7b8")),
                               ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]),
            ]
        )
    )

    doc.build(el, canvasmaker=_canvas_modelo(titulo))
    return buf.getvalue()
