import { Toaster } from '@/components/ui/sonner'

/**
 * Ponto único onde os avisos aparecem.
 *
 * Montado uma vez na raiz: qualquer parte do app fala com ele por
 * `useNotices()`, sem passar callback por props e sem inventar um segundo lugar
 * onde mensagens possam surgir.
 */
export function Notices() {
  return (
    <Toaster
      position="bottom-right"
      closeButton
      // Região `aria-live` do sonner e rótulo do botão de fechar: os defaults
      // são em inglês, e texto lido em voz alta é texto de interface.
      containerAriaLabel="Avisos"
      // `richColors` pintaria o toast com a paleta do sonner; os tokens do
      // projeto já vêm do popover, e é assim que erro e sucesso ficam com a
      // mesma temperatura do resto da interface.
      richColors={false}
      toastOptions={{
        closeButtonAriaLabel: 'Fechar aviso',
        classNames: { description: 'text-muted-foreground' },
      }}
    />
  )
}
