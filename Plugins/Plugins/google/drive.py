"""Shared Drive adapter for OAuth accounts and migrated service accounts."""
from pathlib import Path
import json
from urllib.parse import quote
from dotenv import dotenv_values
from src.resource_plugins import get_resources
ROOT=Path(__file__).resolve().parent
class Drive:
    def __init__(self,resources=None,root=ROOT):self.resources=resources or get_resources();self.root=Path(root);self._credentials=None
    def config(self):return dotenv_values(self.root/'.env')
    @property
    def default_folder(self):return self.config().get('GOOGLE_DRIVE_FOLDER_ID','')
    def accounts(self):
        result=self.resources.accounts('google')
        path=self.config().get('GOOGLE_APPLICATION_CREDENTIALS')
        if path:
            file=Path(path);file=file if file.is_absolute() else self.root/file
            if file.is_file():
                info=json.loads(file.read_text(encoding='utf-8'))
                result=[{'id':'service-account','label':'Conta de serviço','email':info.get('client_email','')},*result]
        return result
    def account(self,identity=None):
        accounts=self.accounts();identity=identity or (accounts[0]['id'] if accounts else '')
        if not any(a['id']==identity for a in accounts):raise ValueError('Conecte uma conta Google nas configurações da PIA.')
        return identity
    def headers(self,identity):
        identity=self.account(identity)
        if identity!='service-account':return {'Authorization':'Bearer '+self.resources._access_token('google',identity)}
        from google.oauth2.service_account import Credentials
        from google.auth.transport.requests import Request
        if self._credentials is None:
            path=Path(self.config()['GOOGLE_APPLICATION_CREDENTIALS']);path=path if path.is_absolute() else self.root/path
            self._credentials=Credentials.from_service_account_file(str(path),scopes=['https://www.googleapis.com/auth/drive'])
        if not self._credentials.valid:self._credentials.refresh(Request())
        return {'Authorization':'Bearer '+self._credentials.token}
    def request(self,method,path,account=None,**kwargs):
        response=self.resources.session.request(method,'https://www.googleapis.com/drive/v3/files'+path,headers=self.headers(account),timeout=60,**kwargs)
        if response.status_code>=400:
            response.close();raise RuntimeError(f'Google Drive retornou HTTP {response.status_code}. Verifique as permissões da conta.')
        return response
    @staticmethod
    def escape(value):return str(value).replace('\\','\\\\').replace("'","\\'")
    def list(self,account=None,folder=None,folders_only=False,cursor=None,search=None):
        query=['trashed = false']
        if folder:query.append("'"+self.escape(folder)+"' in parents")
        if folders_only:query.append("mimeType = 'application/vnd.google-apps.folder'")
        if search:query.append("name contains '"+self.escape(search)+"'")
        params=dict(q=' and '.join(query),pageSize=100,fields='nextPageToken,files(id,name,mimeType,size,createdTime,modifiedTime)',supportsAllDrives=True,includeItemsFromAllDrives=True)
        if cursor:params['pageToken']=cursor
        with self.request('GET','',account,params=params) as response:return response.json()
    def download(self,identity,destination,account=None):
        destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
        temporary=destination.with_suffix(destination.suffix+'.part')
        try:
            with self.request('GET','/'+quote(identity,safe=''),account,params={'alt':'media','supportsAllDrives':True},stream=True) as response, temporary.open('wb') as output:
                for chunk in response.iter_content(1024*1024):output.write(chunk)
            temporary.replace(destination)
        finally:temporary.unlink(missing_ok=True)
        return destination
    def rename(self,identity,name,account=None):
        with self.request('PATCH','/'+quote(identity,safe=''),account,params={'supportsAllDrives':True},json={'name':name}) as response:return response.json()
