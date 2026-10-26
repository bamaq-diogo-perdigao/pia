# Secretária PIA


## Avatar e interface

avatar.svg é um personagem vetorial animado com corpo, olhos, calendário e estrelas. web/panel.js é servido pela PIA em /bots/secretaria/web/panel.js; a PIA importa esse módulo e fornece o contêiner, navegação e notificações. O painel usa /pia/sdk.js, /pia/ui.js e o componente genérico /pia/bot-avatar.js.

Cores persistidas: avatar_primary, avatar_accent e avatar_eyes, sempre em #RRGGBB. O componente injeta essas cores como variáveis CSS no SVG; os grupos secretary-body, secretary-eyes e secretary-star permitem futuras animações e estados. Há suporte a prefers-reduced-motion.

Os filtros legíveis de Gmail são compilados pelo próprio bot. email_filter aceita important_unread, all_unread, inbox_unread, starred_unread ou custom. email_query continua compatível e só é mostrado no painel ao selecionar Personalizado. Prefira expor novas preferências aqui em vez de colocar código de bot na interface principal.
