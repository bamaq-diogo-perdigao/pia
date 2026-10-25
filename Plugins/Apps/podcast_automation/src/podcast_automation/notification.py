"""Optional publication announcements through shared PIA/Discord integrations."""
import requests
from src.app_access import current,headers
from .settings import get_config

def announce_publication(episode,campaign):
    options=get_config().get('integrations',{})
    text=f"Episódio '{episode}' da mesa {campaign} publicado."
    ok=True
    if options.get('announce'):
        try:
            response=requests.post(current()['url']+'/tts/speak',json={'text':text},headers=headers(),timeout=30)
            ok=response.status_code==200
        except requests.RequestException:ok=False
    if options.get('discord_notify'):
        try:
            from Plugins.Plugins.discord.service import Discord
            Discord().send(text,options.get('discord_channel'))
        except Exception:
            print('Aviso: Discord não confirmou a notificação; os arquivos continuam publicados.')
            ok=False
    return ok
