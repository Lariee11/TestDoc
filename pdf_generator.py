"""Geração do Certificado de Ensaio de Proteção em PDF (ReportLab)."""

from __future__ import annotations

import base64
import io
import os
from datetime import datetime
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    CondPageBreak,
    Flowable,
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(BASE_DIR, "static", "logo.png")

# --------------------------------------------------------------------------
# Paleta
# --------------------------------------------------------------------------
NAVY = colors.HexColor("#14345a")
INK = colors.HexColor("#0f172a")
BLUE = colors.HexColor("#2563eb")
MUTED = colors.HexColor("#64748b")
LINE = colors.HexColor("#d8dee8")
ZEBRA = colors.HexColor("#f5f7fa")
HEAD_BG = colors.HexColor("#e6ebf2")
LOG_BG = colors.HexColor("#0b1626")
LOG_FG = colors.HexColor("#7dd3fc")
LOG_HEAD = colors.HexColor("#16263d")

STATUS = {
    "aprovado": {"label": "APROVADO", "cor": colors.HexColor("#10b981"), "icone": "check"},
    "ressalvas": {
        "label": "APROVADO COM RESSALVAS",
        "cor": colors.HexColor("#d97706"),
        "icone": "alerta",
    },
    "reprovado": {"label": "NÃO APROVADO", "cor": colors.HexColor("#dc2626"), "icone": "x"},
    "nao_realizado": {
        "label": "TESTES NÃO REALIZADOS",
        "cor": colors.HexColor("#64748b"),
        "icone": "traco",
    },
}
STATUS_TESTE_LABEL = {"nao_realizado": "NÃO REALIZADO"}

MAX_LINHAS_LOG = 4000
MAX_LADO_IMAGEM = 2200  # px

# --------------------------------------------------------------------------
# Fontes: DejaVu / Arial quando disponíveis (suporte Unicode), senão padrão PDF
# --------------------------------------------------------------------------
_CANDIDATOS = [
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ),
    (
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    ),
    (
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/consola.ttf",
    ),
    (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
    ),
]

FONT, FONT_B, FONT_MONO = "Helvetica", "Helvetica-Bold", "Courier"
UNICODE_OK = False
for _reg, _bold, _mono in _CANDIDATOS:
    if all(os.path.isfile(p) for p in (_reg, _bold, _mono)):
        try:
            pdfmetrics.registerFont(TTFont("Doc", _reg))
            pdfmetrics.registerFont(TTFont("Doc-Bold", _bold))
            pdfmetrics.registerFont(TTFont("Doc-Mono", _mono))
            pdfmetrics.registerFontFamily("Doc", normal="Doc", bold="Doc-Bold")
            FONT, FONT_B, FONT_MONO = "Doc", "Doc-Bold", "Doc-Mono"
            UNICODE_OK = True
            break
        except Exception:  # fonte corrompida/ilegível: tenta a próxima
            continue


def _limpo(texto) -> str:
    """Normaliza texto; sem fonte Unicode, restringe ao conjunto cp1252."""
    texto = "" if texto is None else str(texto)
    texto = texto.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    texto = "".join(ch for ch in texto if ch == "\n" or ord(ch) >= 32)
    if not UNICODE_OK:
        texto = texto.encode("cp1252", "replace").decode("cp1252")
    return texto


def _xml(texto) -> str:
    return escape(_limpo(texto).strip()).replace("\n", "<br/>")


# --------------------------------------------------------------------------
# Estilos
# --------------------------------------------------------------------------
S_TITULO = ParagraphStyle("titulo", fontName=FONT_B, fontSize=14, leading=17, textColor=INK)
S_SUB = ParagraphStyle("sub", fontName=FONT_B, fontSize=9, leading=12, textColor=BLUE)
S_SECAO = ParagraphStyle(
    "secao", fontName=FONT_B, fontSize=11.5, leading=14, textColor=INK, spaceBefore=14, spaceAfter=7
)
S_ROTULO = ParagraphStyle("rotulo", fontName=FONT_B, fontSize=8.3, leading=11, textColor=INK)
S_VALOR = ParagraphStyle("valor", fontName=FONT, fontSize=8.3, leading=11, textColor=INK)
S_TH = ParagraphStyle("th", fontName=FONT_B, fontSize=8.3, leading=11, textColor=colors.white)
S_TESTE = ParagraphStyle("teste", fontName=FONT_B, fontSize=9.5, leading=12, textColor=colors.white)
S_MINI = ParagraphStyle(
    "mini", fontName=FONT_B, fontSize=8, leading=10, textColor=MUTED, spaceBefore=8, spaceAfter=4
)
S_LOGHEAD = ParagraphStyle("loghead", fontName=FONT_B, fontSize=8, leading=10, textColor=colors.white)
S_VAZIO = ParagraphStyle(
    "vazio", fontName=FONT, fontSize=8.3, leading=11, textColor=MUTED, alignment=TA_CENTER
)
S_LEGENDA = ParagraphStyle(
    "legenda", fontName=FONT, fontSize=7.5, leading=10, textColor=MUTED, alignment=TA_CENTER
)


def P(texto, estilo=S_VALOR):
    conteudo = _xml(texto)
    return Paragraph(conteudo if conteudo else "—", estilo)


# --------------------------------------------------------------------------
# Selo (desenho vetorial: independe de glifos da fonte)
# --------------------------------------------------------------------------
class Selo(Flowable):
    def __init__(self, status: str, largura: float, altura: float = 20, tamanho: float = 8,
                 preenchido: bool = False, label: str | None = None):
        super().__init__()
        info = STATUS.get(status, STATUS["nao_realizado"])
        self.cor = info["cor"]
        self.icone = info["icone"]
        self.label = label or info["label"]
        self.width, self.height = largura, altura
        self.tamanho = tamanho
        self.preenchido = preenchido

    def wrap(self, *_):
        return self.width, self.height

    def _icone(self, c, cx, cy, r):
        c.setLineWidth(max(1.2, r * 0.32))
        c.setLineCap(1)
        c.setLineJoin(1)
        p = c.beginPath()
        if self.icone == "check":
            p.moveTo(cx - r, cy)
            p.lineTo(cx - r * 0.3, cy - r * 0.7)
            p.lineTo(cx + r, cy + r * 0.75)
        elif self.icone == "x":
            p.moveTo(cx - r * 0.75, cy - r * 0.75)
            p.lineTo(cx + r * 0.75, cy + r * 0.75)
            p.moveTo(cx - r * 0.75, cy + r * 0.75)
            p.lineTo(cx + r * 0.75, cy - r * 0.75)
        elif self.icone == "alerta":
            p.moveTo(cx, cy + r * 0.9)
            p.lineTo(cx, cy - r * 0.15)
            p.moveTo(cx, cy - r * 0.8)
            p.lineTo(cx, cy - r * 0.82)
        else:
            p.moveTo(cx - r * 0.8, cy)
            p.lineTo(cx + r * 0.8, cy)
        c.drawPath(p, stroke=1, fill=0)

    def draw(self):
        c = self.canv
        w, h = self.width, self.height
        fonte, tam = FONT_B, self.tamanho
        linhas = [self.label]
        r = tam * 0.42
        folga = r * 2 + 5 + 14
        # reduz e, se preciso, quebra em duas linhas para caber
        while pdfmetrics.stringWidth(self.label, fonte, tam) + folga > w and tam > 6.5:
            tam -= 0.25
        if pdfmetrics.stringWidth(self.label, fonte, tam) + folga > w and " " in self.label:
            palavras = self.label.split(" ")
            melhor = None
            for i in range(1, len(palavras)):
                a, b = " ".join(palavras[:i]), " ".join(palavras[i:])
                maior = max(pdfmetrics.stringWidth(a, fonte, tam), pdfmetrics.stringWidth(b, fonte, tam))
                if melhor is None or maior < melhor[0]:
                    melhor = (maior, [a, b])
            linhas = melhor[1]
        r = tam * 0.42
        larg_txt = max(pdfmetrics.stringWidth(l, fonte, tam) for l in linhas)
        total = r * 2 + 5 + larg_txt

        c.saveState()
        if self.preenchido:
            c.setFillColor(self.cor)
            c.roundRect(0, 0, w, h, 4, stroke=0, fill=1)
            frente = colors.white
        else:
            c.setFillColor(self.cor, alpha=0.10)
            c.setStrokeColor(self.cor)
            c.setLineWidth(0.8)
            c.roundRect(0.4, 0.4, w - 0.8, h - 0.8, 4, stroke=1, fill=1)
            frente = self.cor
        c.setFillColor(frente, alpha=1)
        c.setStrokeColor(frente)
        x0 = (w - total) / 2
        self._icone(c, x0 + r, h / 2, r)
        c.setFont(fonte, tam)
        entre = tam * 1.15
        y = h / 2 + (len(linhas) - 1) * entre / 2 - tam * 0.35
        for linha in linhas:
            c.drawString(x0 + r * 2 + 5, y, linha)
            y -= entre
        c.restoreState()


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


def _imagem_ajustada(dados, larg_max, alt_max):
    leitor, w, h = dados
    escala = min(larg_max / w, alt_max / h)
    return Image(leitor, width=w * escala, height=h * escala)


def _moldura(conteudo, largura, pad=6):
    t = Table([[conteudo]], colWidths=[largura])
    t.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.8, LINE),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), pad),
                ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
                ("LEFTPADDING", (0, 0), (-1, -1), pad),
                ("RIGHTPADDING", (0, 0), (-1, -1), pad),
                ("ROUNDEDCORNERS", [5, 5, 5, 5]),
            ]
        )
    )
    return t


# --------------------------------------------------------------------------
# Blocos
# --------------------------------------------------------------------------
def _grade_chave_valor(linhas, larguras, extra=()):
    t = Table(linhas, colWidths=larguras)
    estilo = [
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e8ecf2")),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [ZEBRA, colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]
    estilo.extend(extra)
    t.setStyle(TableStyle(estilo))
    return t


def _bloco_log(nome_rele, conteudo, largura):
    tam = 6.8
    larg_char = pdfmetrics.stringWidth("M", FONT_MONO, tam)
    max_cols = max(20, int((largura - 16) / larg_char))

    linhas = _limpo(conteudo).strip("\n").split("\n")
    saida = []
    for linha in linhas:
        linha = linha.rstrip()
        if not linha:
            saida.append("")
            continue
        while len(linha) > max_cols:
            saida.append(linha[:max_cols])
            linha = "  " + linha[max_cols:]
        saida.append(linha)
    cortado = len(saida) > MAX_LINHAS_LOG
    if cortado:
        saida = saida[:MAX_LINHAS_LOG] + [f"... (log truncado em {MAX_LINHAS_LOG} linhas)"]
    if not any(s.strip() for s in saida):
        saida = ["(log não informado)"]

    dados = [[P(nome_rele or "Relé", S_LOGHEAD)]] + [[s] for s in saida]
    t = Table(dados, colWidths=[largura], repeatRows=1)
    ult = len(dados) - 1
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LOG_HEAD),
                ("TOPPADDING", (0, 0), (-1, 0), 4),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                ("BACKGROUND", (0, 1), (-1, -1), LOG_BG),
                ("TEXTCOLOR", (0, 1), (-1, -1), LOG_FG),
                ("FONTNAME", (0, 1), (-1, -1), FONT_MONO),
                ("FONTSIZE", (0, 1), (-1, -1), tam),
                ("LEADING", (0, 1), (-1, -1), tam + 1.6),
                ("TOPPADDING", (0, 1), (-1, -1), 0.4),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 0.4),
                ("TOPPADDING", (0, 1), (-1, 1), 6),
                ("BOTTOMPADDING", (0, ult), (-1, ult), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return t


def _bloco_assinatura(titulo, rotulo_nome, pessoa, largura):
    pessoa = pessoa or {}
    cols = [largura * 0.46, largura * 0.25, largura * 0.29]
    dados = [
        [P(titulo, S_ROTULO), "", ""],
        [P(rotulo_nome, S_ROTULO), P("Matrícula", S_ROTULO), P("Área de Atuação", S_ROTULO)],
        [P(pessoa.get("nome")), P(pessoa.get("matricula")), P(pessoa.get("area"))],
    ]
    t = Table(dados, colWidths=cols)
    t.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (-1, 0)),
                ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
                ("BACKGROUND", (0, 1), (-1, 1), ZEBRA),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("INNERGRID", (0, 1), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 2), (-1, 2), 9),
                ("BOTTOMPADDING", (0, 2), (-1, 2), 9),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return t


def _formatar_data(valor) -> str:
    valor = (valor or "").strip()
    try:
        return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return valor


# --------------------------------------------------------------------------
# Canvas com rodapé "Página X de Y"
# --------------------------------------------------------------------------
def _canvas_numerado(rodape_esq):
    class CanvasNumerado(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._paginas = []

        def showPage(self):
            self._paginas.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._paginas)
            for estado in self._paginas:
                self.__dict__.update(estado)
                self._rodape(total)
                super().showPage()
            super().save()

        def _rodape(self, total):
            larg, _ = A4
            self.saveState()
            self.setStrokeColor(LINE)
            self.setLineWidth(0.6)
            self.line(14 * mm, 13 * mm, larg - 14 * mm, 13 * mm)
            self.setFont(FONT, 7.5)
            self.setFillColor(MUTED)
            self.drawString(14 * mm, 9 * mm, rodape_esq)
            self.drawRightString(larg - 14 * mm, 9 * mm, f"Página {self._pageNumber} de {total}")
            self.restoreState()

    return CanvasNumerado


# --------------------------------------------------------------------------
# Documento
# --------------------------------------------------------------------------
def gerar_pdf(dados: dict) -> bytes:
    """Recebe o dicionário enviado pela interface e devolve o PDF em bytes."""
    geral = dados.get("geral") or {}
    sub = dados.get("subestacao") or {}
    testes = dados.get("testes") or []
    val = dados.get("validacao") or {}

    nome_se = _limpo(geral.get("nome_se")).strip()
    status_geral = geral.get("resultado") if geral.get("resultado") in STATUS else "nao_realizado"

    buf = io.BytesIO()
    margem = 14 * mm
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=margem,
        rightMargin=margem,
        topMargin=14 * mm,
        bottomMargin=18 * mm,
        title=f"Certificado de Ensaio de Proteção — {nome_se}" if nome_se else "Certificado de Ensaio de Proteção",
        author="TestDoc",
        subject="Relatório Técnico de Comissionamento e Testes",
    )
    L = doc.width
    el = []

    # ---------------- Cabeçalho ----------------
    logo = Image(LOGO_PATH, width=40, height=40) if os.path.isfile(LOGO_PATH) else Spacer(40, 40)
    titulo = [
        Paragraph("CERTIFICADO DE ENSAIO DE PROTEÇÃO", S_TITULO),
        Paragraph("Relatório Técnico de Comissionamento e Testes", S_SUB),
    ]
    larg_selo = 150
    cab = Table(
        [[logo, titulo, Selo(status_geral, larg_selo, 28, 10, preenchido=True)]],
        colWidths=[50, L - 50 - larg_selo, larg_selo],
    )
    cab.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    el += [cab, HRFlowable(width="100%", thickness=1.4, color=INK, spaceBefore=2, spaceAfter=4)]

    # ---------------- 1. Informações gerais ----------------
    el.append(Paragraph("1. INFORMAÇÕES GERAIS", S_SECAO))
    c1, c3 = 112, 104
    c2 = (L - c1 - c3) * 0.56
    c4 = L - c1 - c2 - c3
    s_res = ParagraphStyle("res", parent=S_ROTULO, textColor=STATUS[status_geral]["cor"])
    el.append(
        _grade_chave_valor(
            [
                [P("Nome da SE", S_ROTULO), P(nome_se), P("Data de Emissão", S_ROTULO),
                 P(_formatar_data(geral.get("data_emissao")))],
                [P("Norma de Referência", S_ROTULO), P(geral.get("norma")),
                 P("Resultado dos Testes", S_ROTULO), P(STATUS[status_geral]["label"].title(), s_res)],
                [P("Equipamentos Simulados", S_ROTULO), P(geral.get("equipamentos")), "", ""],
                [P("Modelos de Relés Utilizados", S_ROTULO), P(geral.get("reles")), "", ""],
            ],
            [c1, c2, c3, c4],
            extra=[("SPAN", (1, 2), (3, 2)), ("SPAN", (1, 3), (3, 3))],
        )
    )

    # ---------------- 2. Informações da subestação ----------------
    el.append(Paragraph("2. INFORMAÇÕES DA SUBESTAÇÃO", S_SECAO))
    larg_img = L * 0.47
    img = _decodificar_imagem(sub.get("diagrama"))
    if img:
        quadro = _moldura(_imagem_ajustada(img, larg_img - 14, 245), larg_img)
    else:
        quadro = _moldura(P("Diagrama da subestação não informado", S_VAZIO), larg_img, pad=40)
    larg_info = L - larg_img - 10
    info = _grade_chave_valor(
        [
            [P("Subestação", S_ROTULO), P(nome_se)],
            [P("Tensão de Alta", S_ROTULO), P(sub.get("tensao_alta"))],
            [P("Tensão de Baixa", S_ROTULO), P(sub.get("tensao_baixa"))],
            [P("Mala de Testes Utilizada", S_ROTULO), P(sub.get("mala"))],
        ],
        [larg_info * 0.44, larg_info * 0.56],
    )
    lado = Table([[quadro, info]], colWidths=[larg_img + 10, larg_info])
    lado.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 10),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    el.append(lado)

    # ---------------- 3. Condições de teste e resultados ----------------
    el.append(CondPageBreak(120))
    el.append(Paragraph("3. CONDIÇÕES DE TESTE E RESULTADOS", S_SECAO))
    if not testes:
        el.append(_moldura(P("Nenhum teste cadastrado.", S_VAZIO), L, pad=14))

    larg_selo_t = 108
    for i, teste in enumerate(testes, start=1):
        status = teste.get("selo") if teste.get("selo") in STATUS else "nao_realizado"
        ident = _limpo(teste.get("id")).strip() or f"Teste {i}"

        faixa = Table([[Paragraph(f"3.{i} &nbsp;·&nbsp; {escape(ident)}", S_TESTE)]], colWidths=[L])
        faixa.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ]
            )
        )
        larg_txt = (L - larg_selo_t) / 2
        resumo = Table(
            [
                [P("Condição Simulada", S_ROTULO), P("Resultado", S_ROTULO), P("Selo de Aprovação", S_ROTULO)],
                [
                    P(teste.get("condicao")),
                    P(teste.get("resultado")),
                    Selo(status, larg_selo_t - 14, 24, 7.6, label=STATUS_TESTE_LABEL.get(status)),
                ],
            ],
            colWidths=[larg_txt, larg_txt, larg_selo_t],
        )
        resumo.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
                    ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (2, 0), (2, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 1), (-1, 1), 7),
                    ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        if i > 1:
            el.append(Spacer(1, 14))
        el.append(KeepTogether([faixa, resumo]))

        logs = [l for l in (teste.get("logs") or []) if (l.get("rele") or l.get("conteudo"))]
        el.append(CondPageBreak(70))
        el.append(Paragraph("LOG DE EVENTOS DOS RELÉS", S_MINI))
        if not logs:
            el.append(_moldura(P("Nenhum log de relé anexado a este teste.", S_VAZIO), L, pad=10))
        for j, log in enumerate(logs):
            if j:
                el.append(Spacer(1, 6))
            el.append(_bloco_log(_limpo(log.get("rele")).strip(), log.get("conteudo"), L))

        img_t = _decodificar_imagem(teste.get("imagem"))
        if img_t:
            fig = _imagem_ajustada(img_t, L * 0.62, 300)
            el.append(
                KeepTogether(
                    [
                        Paragraph("DIAGRAMA — ESTADO DOS EQUIPAMENTOS", S_MINI),
                        _moldura(fig, L),
                        Spacer(1, 3),
                        Paragraph(f"Estado dos equipamentos durante o teste {escape(ident)}", S_LEGENDA),
                    ]
                )
            )

    # ---------------- 4. Validação ----------------
    meia = (L - 8) / 2
    par = Table(
        [
            [
                _bloco_assinatura("EXECUÇÃO DOS ENSAIOS", "Responsável", val.get("execucao"), meia),
                _bloco_assinatura("APROVAÇÃO E LIBERAÇÃO", "Aprovador", val.get("aprovacao"), meia),
            ]
        ],
        colWidths=[meia + 8, meia],
    )
    par.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 8),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    el.append(
        KeepTogether([Paragraph("4. REGISTRO DE VALIDAÇÃO E APROVAÇÃO TÉCNICA", S_SECAO), par])
    )

    rodape = "Certificado de Ensaio de Proteção" + (f" — {nome_se}" if nome_se else "")
    doc.build(el, canvasmaker=_canvas_numerado(rodape))
    return buf.getvalue()
