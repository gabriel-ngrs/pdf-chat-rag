# Documento de exemplo

`lgpd-capitulos-1-2.pdf` — 9 páginas, ~36 mil caracteres de texto extraível.

É o excerto dos **Capítulos I e II da Lei nº 13.709/2018 (LGPD)**, artigos 1º a
16, com a redação dada pela Lei nº 13.853/2019. O texto vem do Portal da
Legislação da Presidência da República (`planalto.gov.br`) e foi recomposto em
PDF para servir de documento de teste: tipografia limpa, uma página por bloco de
artigos e nenhuma imagem, para que a extração por página seja verificável.

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
| 1 | 1º, 2º | Objeto da Lei e fundamentos da disciplina |
| 2 | 3º, 4º | Âmbito de aplicação e hipóteses de não aplicação |
| 3 | 5º | Definições (dado pessoal, dado sensível, controlador, operador, encarregado…) |
| 4 | 6º | Princípios do tratamento |
| 5 | 7º | Hipóteses em que o tratamento pode ser realizado |
| 6 | 8º, 9º, 10 | Consentimento, acesso facilitado e legítimo interesse |
| 7 | 11 | Tratamento de dados pessoais sensíveis |
| 8 | 12, 13, 14 | Dados anonimizados, estudos em saúde pública e dados de crianças |
| 9 | 15, 16 | Término do tratamento e eliminação dos dados |

O mapa acima é o gabarito do `expected_page` em `backend/eval/dataset.json`.
