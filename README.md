# TestDoc

Gerador de **Certificado de Ensaios de Automação** em PDF: interface em HTML/CSS/JS
e backend 100% Python (servidor com a biblioteca padrão + ReportLab para o PDF).

## Como usar

```bash
pip install -r requirements.txt
```

```bash
python app.py
```

Abra <http://localhost:8000>, preencha as seções e clique em **Gerar PDF**.
Opções: `python app.py --host 0.0.0.0 --port 9000`.

## Estrutura do documento gerado

| Seção | Conteúdo |
| --- | --- |
| Cabeçalho | Fixo: logos de `static/logos/` e as duas linhas de texto, repetidos em todas as páginas |
| Identificação | Título do documento fixo ("Certificado de Ensaios de Automação"); título, subestação, distribuidora, data, responsável técnico e revisão |
| 1. Diagrama Unifilar | Imagem |
| 2. Requisitos Funcionais | Tabela N° / Requisito |
| 3. Metodologia | Objetivo e escopo, topologia (imagem) e equipamentos, comunicação, execução |
| 4. Plano de Testes | Tabela montada automaticamente a partir dos testes (ID, cenário, resultado esperado, status) |
| 5. Detalhamento dos Testes | Por teste: pré-condição (texto + imagem), procedimento, resultados esperados (imagem + itens), comentários, logs dos relés (SER) e logs SCADA |
| 6. Controle de Revisões | Tabela Revisão / Descrição / Responsável |

O cabeçalho e o título do documento não são editáveis pela interface; para alterá-los,
troque as imagens em `static/logos/` ou as constantes `DOCUMENTO` e `CABECALHO_LINHAS`
em `pdf_generator.py`.

## Interface

- **Modo claro / escuro (azul-marinho)**: botão no topo; sem escolha salva, segue a preferência do sistema.
- **Rascunho automático**: o formulário é guardado no navegador a cada alteração.
- **Salvar / Abrir**: exporta e importa o projeto completo (textos e imagens) em `.json`.
- **Logs dos relés**: *Importar .txt* separa o arquivo em um log por relé (blocos entre
  linhas `=====`, veja `exemplos/T1 - SER.txt`); também é possível colar o log manualmente.
- **Logs SCADA**: um evento por linha, no formato `Timestamp; Tag Name; Message`
  (também aceita TAB ou colunas alinhadas por espaços).
- Em *Procedimento*, *Resultados esperados* e nos itens 3.3/3.4, cada linha vira um item da lista.

## Arquivos

| Arquivo | Função |
| --- | --- |
| `app.py` | Servidor HTTP: serve a interface e expõe `POST /api/gerar-pdf` |
| `pdf_generator.py` | Monta o PDF (ReportLab) |
| `static/` | Interface (`index.html`, `style.css`, `app.js`, `logo.png`) e `logos/` (logos do cabeçalho do PDF) |
| `exemplos/` | Log e diagrama de exemplo |
