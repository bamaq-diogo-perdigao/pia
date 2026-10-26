# Plugin Google

## Drive compartilhado com apps

`drive.py` concentra contas OAuth e a conta de serviço migrada do podcast. `GOOGLE_APPLICATION_CREDENTIALS` e `GOOGLE_DRIVE_FOLDER_ID` ficam no `.env` deste plugin; a cópia local das credenciais fica em `secrets/` e não é versionada. O podcast guarda apenas a conta e a pasta escolhidas no seu config.json.

API: `Drive(resources).accounts()`, `.list(account,folder,folders_only,cursor,search)`, `.download(file_id,destination,account)` e `.rename(file_id,name,account)`. A listagem suporta paginação e drives compartilhados; download grava em arquivo temporário e só substitui o destino quando termina. Skills podem listar pastas com `piaPlugins('google','drive.folders',account='ID')`.

Para marcar gravações processadas, a conta OAuth precisa do escopo Drive de leitura e escrita. Contas autorizadas antes dessa mudança precisam ser reconectadas para conceder o novo escopo. Contas de serviço precisam de acesso à pasta, concedido ao client_email da credencial. [Arquivos e pastas no Drive](https://developers.google.com/workspace/drive/api/reference/rest/v3/files).
