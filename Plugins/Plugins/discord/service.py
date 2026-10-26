"""Discord bot plugin. Sends only when explicitly called by an app or skill."""
from pathlib import Path
import re
from urllib.parse import urlsplit
from dotenv import dotenv_values
import requests
ROOT=Path(__file__).resolve().parent
class Discord:
    def __init__(self,root=ROOT,session=None):self.root=Path(root);self.session=session or requests.Session()
    def config(self):return dotenv_values(self.root/'.env')
    def public(self):
        value=self.config()
        return {'id':value.get('DISCORD_BOT_ID',''),'invite_url':value.get('DISCORD_BOT_URL',''),'community_url':value.get('DISCORD_LINK',''),'configured':bool(value.get('DISCORD_BOT_TOKEN')),'channel':value.get('DISCORD_CHANNEL_ID','')}
    def send(self,text,channel=None):
        value=self.config();channel=channel or value.get('DISCORD_CHANNEL_ID')
        if not channel or not re.fullmatch('[0-9]+',str(channel)):raise ValueError('Configure o canal do Discord para notificações.')
        if not value.get('DISCORD_BOT_TOKEN'):raise ValueError('Configure o token do bot Discord.')
        response=self.session.post('https://discord.com/api/v10/channels/'+str(channel)+'/messages',headers={'Authorization':'Bot '+value['DISCORD_BOT_TOKEN']},json={'content':str(text)[:2000],'allowed_mentions':{'parse':[]}},timeout=30)
        if response.status_code>=400:raise RuntimeError(f'Discord retornou HTTP {response.status_code}. Verifique o canal e as permissões do bot.')
        return {'id':response.json()['id']}
