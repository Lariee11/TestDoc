"""TestDoc — servidor web (somente biblioteca padrão do Python).

Uso:
    python app.py            # http://localhost:8000
    python app.py --port 9000 --host 0.0.0.0
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import traceback
import unicodedata
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from pdf_generator import gerar_pdf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
MAX_BODY = 80 * 1024 * 1024  # 80 MB (imagens chegam em base64)


def _nome_arquivo(titulo: str) -> str:
    base = unicodedata.normalize("NFKD", titulo or "").encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_")
    return f"Certificado_Ensaios_{base[:80]}.pdf" if base else "Certificado_Ensaios.pdf"


class Handler(BaseHTTPRequestHandler):
    server_version = "TestDoc/1.0"

    # ------------------------------------------------------------- util
    def _enviar(self, status, corpo: bytes, tipo: str, extras: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for chave, valor in (extras or {}).items():
            self.send_header(chave, valor)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _json(self, status, objeto):
        self._enviar(status, json.dumps(objeto, ensure_ascii=False).encode("utf-8"),
                     "application/json; charset=utf-8")

    # ------------------------------------------------------------- GET
    def do_GET(self):
        caminho = unquote(urlsplit(self.path).path)
        if caminho == "/":
            caminho = "/index.html"
        alvo = os.path.realpath(os.path.join(STATIC_DIR, caminho.lstrip("/")))
        if os.path.commonpath([alvo, STATIC_DIR]) != STATIC_DIR or not os.path.isfile(alvo):
            self._json(HTTPStatus.NOT_FOUND, {"erro": "Recurso não encontrado."})
            return
        tipo = mimetypes.guess_type(alvo)[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo in ("application/javascript", "text/javascript"):
            tipo += "; charset=utf-8"
        with open(alvo, "rb") as arq:
            self._enviar(HTTPStatus.OK, arq.read(), tipo, {"Cache-Control": "no-cache"})

    do_HEAD = do_GET

    # ------------------------------------------------------------- POST
    def do_POST(self):
        if urlsplit(self.path).path != "/api/gerar-pdf":
            self._json(HTTPStatus.NOT_FOUND, {"erro": "Recurso não encontrado."})
            return
        try:
            tamanho = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            tamanho = 0
        if tamanho <= 0:
            self._json(HTTPStatus.BAD_REQUEST, {"erro": "Requisição vazia."})
            return
        if tamanho > MAX_BODY:
            self.close_connection = True
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                       {"erro": "Os arquivos enviados excedem o limite de 80 MB."})
            return
        try:
            dados = json.loads(self.rfile.read(tamanho).decode("utf-8"))
            if not isinstance(dados, dict):
                raise ValueError("formato inesperado")
        except (ValueError, UnicodeDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"erro": "Dados inválidos."})
            return
        try:
            pdf = gerar_pdf(dados)
        except ValueError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"erro": str(exc)})
            return
        except Exception:
            traceback.print_exc()
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR,
                       {"erro": "Falha interna ao gerar o PDF. Consulte o terminal do servidor."})
            return
        capa = dados.get("capa")
        nome = _nome_arquivo(str(capa.get("titulo", "")) if isinstance(capa, dict) else "")
        self._enviar(HTTPStatus.OK, pdf, "application/pdf",
                     {"Content-Disposition": f'attachment; filename="{nome}"'})

    def log_message(self, formato, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), formato % args))


def main():
    parser = argparse.ArgumentParser(description="TestDoc — gerador de certificados de ensaios de automação")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    servidor = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"TestDoc em execução: http://{args.host}:{args.port}  (Ctrl+C para encerrar)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
