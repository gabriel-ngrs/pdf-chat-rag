/**
 * Tradução de código de erro para uma frase pensada.
 *
 * O mapeamento é **por `code`, nunca por status HTTP**: a FEAT-0002 emitirá os
 * mesmos códigos por SSE, onde não existe status. Centralizar aqui é o que
 * garante que toda falha do sistema tenha título, explicação e uma ação — em
 * vez de cada componente inventar a sua mensagem.
 */

export type NoticeSeverity = 'info' | 'success' | 'error'

export type ErrorDescription = {
  /** Título curto, o que aconteceu. */
  title: string
  /** Uma frase explicando, sem jargão e sem detalhe interno. */
  message: string
  /** O que a pessoa pode fazer agora. Todo erro tem uma. */
  action: string
  severity: NoticeSeverity
}

/**
 * Os códigos da `FEAT-0001` §4.3, os do chat (`FEAT-0002` §4.3 e §4.4) e o de
 * falha de rede, que nasce no cliente.
 */
export const ERROR_CODES = [
  'arquivo_grande',
  'arquivo_invalido',
  'entrada_invalida',
  'nao_encontrado',
  'limite_de_uso',
  'erro_interno',
  'rede_indisponivel',
  'provedor',
  'documento_nao_pronto',
] as const

export type ErrorCode = (typeof ERROR_CODES)[number]

const DESCRIPTIONS: Record<ErrorCode, ErrorDescription> = {
  arquivo_grande: {
    title: 'Arquivo grande demais',
    message: 'O PDF ultrapassa o tamanho que o servidor aceita.',
    action: 'Envie um arquivo menor ou divida o documento em partes.',
    severity: 'error',
  },
  arquivo_invalido: {
    title: 'Arquivo não é um PDF válido',
    message: 'O conteúdo enviado não abre como PDF.',
    action: 'Confira se o arquivo abre no seu leitor e envie de novo.',
    severity: 'error',
  },
  entrada_invalida: {
    title: 'Pergunta longa demais',
    message: 'O servidor aceita perguntas de até 2.000 caracteres.',
    action: 'Encurte a pergunta para até 2.000 caracteres e envie de novo.',
    severity: 'error',
  },
  nao_encontrado: {
    title: 'Documento não encontrado',
    message: 'Este documento não existe mais no servidor.',
    action: 'Envie o PDF novamente para recomeçar.',
    severity: 'error',
  },
  limite_de_uso: {
    title: 'Limite de uso atingido',
    message: 'O provedor de IA recusou mais requisições por enquanto.',
    // Nem "um minuto" nem "amanhã": o servidor não sabe qual das duas cotas do
    // plano gratuito estourou — a por minuto ou a de 20 requisições por dia —,
    // e prometer a errada faz a pessoa esperar e falhar de novo (BUG-004).
    action:
      'Pode ser o limite por minuto ou o limite diário do plano gratuito. Espere um pouco e tente de novo; se persistir, a cota do dia acabou.',
    severity: 'error',
  },
  erro_interno: {
    title: 'Algo deu errado no servidor',
    message: 'A requisição não pôde ser concluída.',
    action: 'Tente de novo em alguns instantes.',
    severity: 'error',
  },
  rede_indisponivel: {
    title: 'Sem resposta do servidor',
    message: 'Não foi possível falar com a aplicação.',
    action: 'Verifique sua conexão e tente de novo.',
    severity: 'error',
  },
  provedor: {
    title: 'O provedor de IA falhou',
    message: 'A resposta não pôde ser gerada até o fim.',
    action: 'Refaça a pergunta em alguns instantes.',
    severity: 'error',
  },
  documento_nao_pronto: {
    title: 'Documento ainda não está pronto',
    message: 'A leitura do PDF não terminou, então ainda não dá para conversar sobre ele.',
    action: 'Espere a leitura terminar e tente de novo.',
    severity: 'info',
  },
}

function isKnownCode(code: string): code is ErrorCode {
  return code in DESCRIPTIONS
}

/**
 * Descreve um código de erro para o usuário.
 *
 * Código desconhecido cai em `erro_interno` de propósito: um código novo do
 * servidor não pode virar uma tela sem mensagem.
 */
export function describeError(code: string): ErrorDescription {
  return isKnownCode(code) ? DESCRIPTIONS[code] : DESCRIPTIONS.erro_interno
}
