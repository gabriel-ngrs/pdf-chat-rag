# Documento de exemplo

`lgpd-capitulos-1-2.pdf` — 12 páginas, ~30 mil caracteres de texto extraível.

É o excerto dos **Capítulos I e II da Lei nº 13.709/2018 (LGPD)**, artigos 1º a
16, com a redação dada pela Lei nº 13.853/2019. O texto vem do Portal da
Legislação da Presidência da República (`planalto.gov.br`) e foi recomposto em
PDF para servir de documento de teste: tipografia limpa, quebra de página
declarada antes dos artigos longos e nenhuma imagem, para que a extração por
página seja verificável.

## Por que este documento

Um projeto de RAG precisa de um documento de referência que qualquer pessoa
possa abrir e conferir. Este serve bem por quatro razões:

- **Domínio público.** Textos de lei não são objeto de proteção autoral
  (Lei nº 9.610/1998, art. 8º, IV), então o arquivo pode ser redistribuído aqui
  sem ressalva nenhuma.
- **Estrutura que casa com a citação por página.** Cada página concentra um
  punhado de artigos, o que torna a resposta "isto está na página 5" fácil de
  auditar contra o PDF aberto ao lado.
- **Densidade de termos exatos.** "Art. 7º", "dado pessoal sensível",
  "encarregado" — termos que a busca vetorial sozinha borra e que a fusão com a
  busca lexical recupera. É o caso de teste da busca híbrida, não um exemplo
  decorativo.
- **Vocabulário fechado.** O que a lei não trata (sanções, transferência
  internacional, atribuições da ANPD) está fora destes dois capítulos, o que dá
  negativas difíceis de verdade para calibrar o limiar de fundamentação.

## Mapa de páginas

| Página | Artigos | Assunto |
|---|---|---|
| 1 | 1º, 2º, 3º | Objeto da Lei, fundamentos e âmbito de aplicação |
| 2 | 4º | Hipóteses em que a Lei não se aplica |
| 3 | 5º | Definições — dado pessoal, dado sensível, consentimento, controlador, operador, encarregado, banco de dados |
| 4 | 5º (cont.) | Últimas definições, entre elas a de autoridade nacional |
| 5 | 6º | Princípios do tratamento |
| 6 | 7º | Hipóteses em que o tratamento pode ser realizado |
| 7 | 8º, 9º | Consentimento e acesso facilitado à informação |
| 8 | 10, 11 | Legítimo interesse e tratamento de dados sensíveis |
| 9 | 11 (cont.) | Vedações e comunicação de dados sensíveis |
| 10 | 12, 13 | Dados anonimizados e estudos em saúde pública |
| 11 | 14 | Dados pessoais de crianças e adolescentes |
| 12 | 15, 16 | Término do tratamento e eliminação dos dados |

Este mapa é o gabarito do `expected_page` em `backend/eval/dataset.json`, e ele
**não foi presumido pelo desenho da página**: cada resposta foi localizada por
busca literal no texto que o `pypdf` extrai de cada página — o mesmo texto que a
ingestão recebe. Gabarito tirado do layout, e não do texto extraído, mede o
gerador de PDF, não o retrieval.
