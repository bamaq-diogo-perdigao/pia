# Podcast Automation / Craig · app da PIA

Este aplicativo existe exclusivamente dentro da PIA. A instalação, o ambiente
Python e as dependências são preparados por `bash install.sh` na raiz da PIA.
O instalador já abre a PIA. Para reabrir depois, use `bash start.sh`.

Abra o botão Podcast na barra esquerda. Processamento, união de SRT/VTT, feeds,
saída das tarefas e configurações ficam no painel à direita. Não há instalador,
ambiente virtual, interface gráfica avulsa ou contêiner próprios deste app.

```text
plugin.toml              # registro do app e da integração de voz
voice/                   # comandos PIA e acompanhamento do processamento
src/podcast_automation/  # processamento e integrações
utilities/               # operações usadas pelo painel
tests/                   # testes offline
docs/                    # guias e exemplos
config/config.json       # configuração pessoal, ignorada no Git
.env                     # variáveis deste app, ignoradas no Git
```

Configure campanhas e formatos no painel do app; as credenciais ficam nas seções dos plugins em Configurações. Exemplos ficam em
`docs/examples/`. Não use `Plugins/Skills/podcast_automation`: o carregador lê a
seção `[voice]` deste `plugin.toml`, sem cópia instalada em outra pasta.

Voz: **comando podcast**, depois **iniciar**, **status**, **parar processamento**,
**abrir RSS**, **abrir transcrições** ou **finalizar**. Processar pode publicar no
armazenamento configurado e marcar ZIPs; apenas ativar a interação não inicia isso.

[Configuração e uso](docs/INSTALACAO.md) · [Áudio](docs/AUDIO.md) · [Publicação](docs/PUBLICACAO.md)

## Integrações na PIA

O app usa o modelo padrão, a transcrição e a voz da PIA. Não configure LLM_*, PIA_* ou WHISPER_* no app. O processo iniciado pela PIA recebe automaticamente uma identidade interna temporária; não precisa de API key. Essa identidade só autoriza as rotas necessárias em loopback, não aceita Origin de navegador e é revogada quando o processo termina. Execução manual não recebe dispensa de autenticação.

Credenciais Google, Discord e Object Storage são migradas do .env do podcast para `Plugins/Plugins/<integração>/.env`. A migração é idempotente e não sobrescreve configurações conflitantes já existentes. Novas contas de storage podem usar o cofre do sistema. Não há comunicação com esses serviços durante a migração.

No painel, escolha a conta e a pasta do Google Drive, a conta/bucket do Object Storage e as notificações opcionais do Discord/voz. As contas e pastas são retornadas pelos plugins compartilhados. Formatos padrão: MP3 (obrigatório), resumo.json, SRT, TXT e VTT (opcionais, inicialmente habilitados). Somente os selecionados são publicados; MP3 sozinho dispensa transcrição e LLM. Quando só resumo.json precisa do texto, o roteiro é temporário e não é exportado.
