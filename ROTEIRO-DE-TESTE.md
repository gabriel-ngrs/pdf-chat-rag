# Roteiro de teste de ponta a ponta — TalkDoc

Antes da `B.5`. A ordem importa: cada bloco depende do anterior ter funcionado.

Os casos foram escolhidos pelo que as avaliações das 11 fases mostraram ser
frágil, não pelo que é fácil de testar. Onde um caminho já tem prova automatizada
está dito — nesses, você está confirmando a experiência, não a corretude.

**Como anotar:** marque `[ok]`, `[falhou]` ou `[estranho]`. "Estranho" é uma
categoria de verdade — coisa que funciona mas parece errada é o que mais
atrapalha numa demonstração.

---

## 0. Ponto de partida

- [ ] `docker compose up --build` a partir de um estado limpo
- [ ] Cronometre o primeiro build. Se passar de ~4 min, é informação para o README
- [ ] `curl -s http://localhost:8000/api/health` → `{"status":"ok","database":"ok"}`
- [ ] Abrir `http://localhost:5173` (ou a porta que o compose publica)

---

## 1. Upload e ingestão

O caminho mais exercitado, mas é onde a primeira impressão acontece.

- [ ] Subir o `Exemplo-YAITEC.pdf`. A barra de progresso **avança** e não pula do 0 ao 100
- [ ] Ao terminar, a UI leva sozinha até o chat (sem precisar clicar em nada)
- [ ] **Subir o mesmo PDF de novo** — deve reaproveitar, não reprocessar
- [ ] Subir um arquivo que **não** é PDF → mensagem clara, em pt-BR, sem stack trace
- [ ] Subir um PDF acima de 25 MB ou com mais de 20 páginas → recusa explicando o limite

---

## 2. O caminho feliz do chat

- [ ] `Quem fundou a YAITEC?`
  - resposta aparece **token a token**, não de uma vez
  - o "pensando" aparece antes do primeiro token e some quando ele chega
  - primeiro token em menos de 5 s
- [ ] Abrir o chip de citação → mostra o trecho e a página
- [ ] **Conferir a página à mão contra o PDF.** É o item mais importante da lista: é
      a fundamentação que o desafio avalia
- [ ] Resposta sem citação nenhuma? Não deveria acontecer numa pergunta fundamentada

---

## 3. Pergunta de continuação *(o coração do requisito)*

O enunciado cobra isso explicitamente. Sem a condensação, a busca não recupera
nada — o pronome não carrega semântica.

- [ ] `Quem fundou a YAITEC?` → esperar a resposta
- [ ] `e a formação dele?` → **precisa** responder sobre a formação, não algo genérico
- [ ] `Onde o time se reúne?` → depois `e quem mora longe de lá?`
- [ ] A citação da segunda pergunta aponta para a página certa

Se a continuação falhar, o problema é a condensação, e é sério.

---

## 4. Recusa *(o segundo mais importante)*

Prova que o sistema não inventa. Numa demonstração, leva dez segundos e vale mais
que qualquer resposta certa.

- [ ] `Qual a receita do bolo de cenoura?`
  - responde "não encontrei essa informação no documento"
  - **aparece como mensagem normal do assistente**, não como banner vermelho de erro
  - **não** mostra área de citações vazia
  - vem rápido (não chama o modelo)
- [ ] `Quantos gols o Pelé marcou?` → mesma coisa
- [ ] Uma pergunta *quase* do assunto, ex.: `A YAITEC faz consultoria tributária?`
      → observe se recusa ou inventa. É a fronteira do limiar

---

## 5. Busca por termo exato *(o que a A.7 acabou de entregar)*

> **Leia antes de rodar.** Eu conferi a tokenização no banco e a expectativa
> original desta seção estava errada. A via lexical usa `plainto_tsquery`, que
> liga os termos com **E** (`AND`): a pergunta `O que é a UFPB no documento?`
> vira `'é' & 'ufpb' & 'document'`, e só casa com um trecho que contenha **todas
> as três**. Num chunk de 500 caracteres isso quase nunca acontece.
>
> Consequência: **em pergunta escrita em linguagem natural, a via lexical
> devolve vazio e quem responde é a busca densa sozinha.** A fusão só morde
> quando o termo entra praticamente sozinho.
>
> Então: aqui você está testando **a busca densa**, não a híbrida. Se a citação
> vier certa, ótimo — mas o mérito é da densa. Não é motivo para rework da A.7.

- [ ] `Qual o e-mail de contato?` → a citação deve apontar para a página 3
- [ ] `O que é a UFPB no documento?`
- [ ] `A YAITEC trabalha com a StartStak?`

Agora o caso em que a fusão **realmente** entra — cole o termo sozinho, sem
pergunta em volta:

- [ ] `contato@yaitec.com`
- [ ] `UFPB`
- [ ] `StartStak`

- [ ] **Anote se as respostas dos dois grupos diferem.** É a informação que
      decide como o README da `B.5` vai descrever a busca híbrida — e o escopo
      travado da `B.5` proíbe prometer no README o que não foi implementado.

---

## 6. Erros e limites *(onde o free tier morde)*

- [ ] Mandar 4–5 perguntas seguidas, rápido, até estourar a quota
  - aparece aviso claro com **ação de repetir**
  - **a pergunta digitada não se perde**
  - clicar em "tentar de novo" **não duplica a pergunta** na conversa
- [ ] Enviar pergunta vazia ou só espaços → botão desabilitado ou recusa limpa
- [ ] Colar um texto gigante (uns 3.000 caracteres) → recusa educada, sem quebrar

---

## 7. Interrupção e recuperação

Os quatro caminhos que só aparecem sob falha. Todos têm teste automatizado — aqui
você confirma a *experiência*.

- [ ] Enviar pergunta e **cancelar no meio** → para de verdade, UI volta a usável
- [ ] **F5 no meio de um streaming** → ao voltar, o histórico está lá e a resposta
      interrompida aparece marcada, não como se estivesse completa
- [ ] **F5 com a conversa parada** → documento e histórico restaurados, **sem**
      criar conversa nova
- [ ] Desligar a rede (DevTools → offline), enviar → aviso decente, não tela branca
- [ ] Religar e continuar → volta a funcionar sem recarregar

---

## 8. Teclado e leitura *(NFR-10)*

- [ ] Navegar só de `Tab`: campo, botão de enviar, chips de citação — todos alcançáveis
- [ ] `Enter` envia · `Shift+Enter` quebra linha
- [ ] Acionar um chip por teclado abre o trecho
- [ ] Foco visível em tudo que recebe foco
- [ ] Alternar tema claro/escuro → nada ilegível, contraste mantido

---

## 9. Conversa longa

Testa a janela de histórico (`HISTORY_WINDOW=6`).

- [ ] 8–10 perguntas na mesma conversa
- [ ] A rolagem acompanha a última mensagem — **mas** se você subir para reler,
      ela **não** te arrasta de volta para baixo
- [ ] Nada estranho no meio da conversa (balão vazio, mensagem duplicada, ordem trocada)

---

## 10. Olhar de avaliador

- [ ] Reler a conversa inteira como se você não conhecesse o projeto. Alguma
      resposta parece inventada?
- [ ] `docker compose logs backend | grep -i "AIza"` → **tem que voltar vazio**
- [ ] Nenhuma mensagem de erro técnica vazou para a tela (stack trace, nome de exceção)
- [ ] Todo texto de interface em pt-BR

---

## Depois

Bug encontrado aqui **não** se conserta dentro da `B.5`. Volta como `/bugfix` ou
como rework da fase dona — é a pré-condição registrada na spec.

Quando esta lista estiver limpa (ou com os problemas encaminhados), a `B.5`
destrava: README, `demo.sh`, vídeo, ensaio de clone limpo e o convite ao
`ygorbalves`.
