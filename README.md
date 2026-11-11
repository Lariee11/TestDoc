# TestDoc

Gerador de **Certificado de Ensaio de Proteção** em PDF: interface em HTML/CSS/JS
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

## Seções do documento

1. **Informações Gerais** — nome da SE, equipamentos simulados, norma de referência,
   modelos de relés, data de emissão e resultado (Aprovado, Aprovado com Ressalvas,
   Não Aprovado, Testes Não Realizados).
2. **Informações da Subestação** — imagem do diagrama ao lado das tensões de alta/baixa
   e da mala de testes.
3. **Condições de Teste e Resultados** — uma subseção por teste, com condição simulada,
   resultado, selo de aprovação, log de eventos de cada relé e a imagem `.png` do
   diagrama com o estado dos equipamentos.
4. **Registro de Validação e Aprovação Técnica** — execução dos ensaios e aprovação/liberação.

## Logs dos relés (.txt)

Em cada teste, **Importar .txt** lê o arquivo exportado (veja `exemplos/T1 - SER.txt`):
cada bloco delimitado por linhas `=====` vira o log de um relé, e os campos
"Teste", "Condição simulada" e "Resultado esperado" do cabeçalho preenchem o teste
quando ainda estão vazios. Também é possível adicionar um relé manualmente e colar o log.

## Estrutura

| Arquivo | Função |
| --- | --- |
| `app.py` | Servidor HTTP: serve a interface e expõe `POST /api/gerar-pdf` |
| `pdf_generator.py` | Monta o PDF (ReportLab) |
| `static/` | Interface (`index.html`, `style.css`, `app.js`, `logo.png`) |
| `exemplos/` | Log e diagrama de exemplo |
