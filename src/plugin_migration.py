"""Move legacy podcast integration settings without logging secret values."""
from pathlib import Path
import shutil
from dotenv import dotenv_values,set_key,unset_key
from .config_paths import BASE_DIR

def migrate(root=BASE_DIR):
    root=Path(root)
    app=root/'Plugins/Apps/podcast_automation'
    source=app/'.env'
    if not source.exists():return
    values=dotenv_values(source)
    for prefix,plugin in [('OBJECT_STORAGE_','object_storage'),('GOOGLE_','google'),('DISCORD_','discord')]:
        target=root/'Plugins/Plugins'/plugin/'.env'
        target.parent.mkdir(parents=True,exist_ok=True)
        existing=dotenv_values(target) if target.exists() else {}
        for name,value in values.items():
            if not name.startswith(prefix):continue
            if name=='GOOGLE_APPLICATION_CREDENTIALS' and value:
                credential=Path(value)
                if not credential.is_absolute():credential=app/credential
                if credential.is_file():
                    destination=target.parent/'secrets/service-account.json'
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    if not destination.exists():shutil.copy2(credential,destination)
                    value=str(destination.resolve())
            if existing.get(name) and existing[name]!=value:
                # Retain conflicts rather than silently replace configured credentials.
                continue
            set_key(target,name,value or '',quote_mode='always')
            unset_key(source,name)
        if target.exists():target.chmod(0o600)
    for name in values:
        if name.startswith(('LLM_','PIA_','WHISPER_')) or name in ('TRANSCRIPTION_PROVIDER','HF_HOME'):
            unset_key(source,name)
