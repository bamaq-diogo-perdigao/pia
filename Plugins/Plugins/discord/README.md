# Plugin Discord

Guarda a configuração do bot no `.env` deste plugin, migrada do podcast. `DISCORD_BOT_ID`, `DISCORD_BOT_PUBLIC_KEY`, `DISCORD_BOT_TOKEN`, `DISCORD_BOT_PERMISSIONS`, `DISCORD_BOT_URL` e `DISCORD_LINK` pertencem aqui. `DISCORD_CHANNEL_ID` escolhe o canal padrão de notificações.

A URL OAuth do bot instala/autoriza o bot; ela não é uma URL de webhook. `Discord().send(text,channel=None)` usa o token de bot na API oficial de mensagens, com menções automáticas desabilitadas. `public()` retorna somente metadados e o estado de configuração. O bot precisa das permissões de visualizar e enviar mensagens no canal.

Skills: `piaPlugins('discord','status')` e `piaPlugins('discord','message.send',text='texto',channel='ID')`. O podcast só envia quando a opção de notificação estiver habilitada. A PIA não envia uma mensagem de teste durante a migração.

Configure em Configurações → Plugins · discord. [Portal de desenvolvedores](https://discord.com/developers/applications), [documentação oficial de mensagens](https://discord.com/developers/docs/resources/message#create-message).
