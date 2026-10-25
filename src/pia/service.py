"""Local web workspace service. No Qt imports; HTTP and native shells share state."""
from __future__ import annotations
from concurrent.futures import Future
import importlib.util
import json
from pathlib import Path
import re
import secrets
import sys
import threading
import time
import tomllib
import types

from src.config_paths import BASE_DIR, CONFIG_DIR
from src.desktop_backend import DesktopBackend, environment_fields


class Job:
    def __init__(self, chat=None):
        self.id = secrets.token_hex(16)
        self.chat = chat
        self.status, self.error, self.text = 'running', None, ''
        self.events = []
        self.cancelled = threading.Event()
        self.changed = threading.Condition()

    def emit(self, kind, **data):
        with self.changed:
            if kind == 'delta':
                self.text += data['text']
            if kind in ('done', 'error'):
                self.status = kind
                self.error = data.get('error')
            self.events.append({'type': kind, **data})
            self.changed.notify_all()


class Apps:
    def __init__(self, root=None):
        self.root = Path(root or BASE_DIR / 'Plugins' / 'Apps')
        self.modules = {}

    def records(self):
        result = []
        for file in sorted(self.root.glob('*/plugin.toml')):
            data = tomllib.loads(file.read_text(encoding='utf-8'))
            if data.get('enabled', True) and re.fullmatch('[a-z][a-z0-9_]*', data.get('id', '')) and data.get('web'):
                result.append({**data, 'folder': file.parent})
        return result

    def find(self, identity):
        for app in self.records():
            if app['id'] == identity:
                return app
        raise ValueError('Aplicativo não encontrado.')

    def public(self):
        return [{'id': a['id'], 'name': a['name'], 'icon': a.get('icon', 'app'),
                 'url': '/apps/' + a['id'] + '/' + a['web']['entrypoint']} for a in self.records()]

    def load(self, identity):
        app = self.find(identity)
        if identity not in self.modules:
            path = (app['folder'] / app['web']['api']).resolve()
            if not path.is_relative_to(app['folder'].resolve()) or path.suffix != '.py':
                raise ValueError('API do aplicativo inválida.')
            package = '_pia_web_app_' + identity
            module = types.ModuleType(package)
            module.__path__ = [str(app['folder'])]
            sys.modules[package] = module
            spec = importlib.util.spec_from_file_location(package + '.api', path)
            api = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = api
            spec.loader.exec_module(api)
            self.modules[identity] = api
        return self.modules[identity]

    def call(self, identity, action, payload, context):
        return self.load(identity).handle(action, payload, context)


class WorkspaceService:
    def __init__(self, backend=None, apps=None):
        self.native_handler = None
        self.jobs = {}
        self.requests = {}
        self.lock = threading.RLock()
        self.backend = backend or DesktopBackend(self.notify)
        self.store = self.backend.store
        self.apps = apps or Apps()

    def notify(self, title, text, speak=False):
        if self.native_handler:
            self.native_handler('notify', dict(title=title, text=text, speak=speak))

    def native(self, action, payload=None):
        if not self.native_handler:
            raise RuntimeError('Esta operação exige a PIA aberta na sessão gráfica.')
        result = self.native_handler(action, payload or {})
        return result.result(timeout=180) if isinstance(result, Future) else result

    def state(self):
        return {'chats': self.store.chat_records(), 'folders': self.store.folders(), 'apps': self.apps.public(),
                'jobs': [{'id': j.id, 'chat': j.chat, 'status': j.status} for j in self.jobs.values() if j.status == 'running'],
                'native': self.native_handler is not None}

    def send(self, chat, text, request=None):
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Mensagem vazia.')
        if len(text) > 100000:
            raise ValueError('Mensagem muito longa.')
        with self.lock:
            if request and request in self.requests:
                return self.requests[request]
            if not any(c['id'] == chat for c in self.store.chat_records()):
                raise ValueError('Conversa não encontrada.')
            if any(j.chat == chat and j.status == 'running' for j in self.jobs.values()):
                raise ValueError('Aguarde a resposta desta conversa.')
            # Persist the user message before returning 202; the UI never waits for the model.
            history = self.store.messages(chat)
            if not history or history[-1] != {'role': 'user', 'content': text.strip()}:
                self.store.append(chat, 'user', text.strip())
            self.store.set('draft:' + chat, '')
            job = Job(chat)
            self.jobs[job.id] = job
            if request:
                self.requests[request] = job.id
            def work():
                try:
                    def delta(value):
                        if job.cancelled.is_set():
                            raise InterruptedError('Resposta interrompida.')
                        job.emit('delta', text=value)
                    self.backend.reply(chat, text.strip(), on_delta=delta)
                    job.emit('done')
                except InterruptedError:
                    if job.text:
                        self.store.append(chat, 'assistant', job.text)
                    job.emit('done', cancelled=True)
                except Exception as exc:
                    job.emit('error', error=str(exc))
            threading.Thread(target=work, daemon=True, name='pia-web-chat').start()
            return job.id

    def plugin_folders(self):
        result = []
        for kind in ('Apps', 'Bot', 'Plugins', 'Skills', 'Browser'):
            for folder in sorted((BASE_DIR / 'Plugins' / kind).glob('*')):
                if folder.is_dir() and not folder.name.startswith(('.', '_')):
                    result.append((kind + '/' + folder.name, folder))
        return result

    def settings(self):
        from dotenv import dotenv_values
        def field(name, value, link, sensitive):
            return dict(name=name, value='' if sensitive else value, sensitive=sensitive,
                        configured=bool(value), link=link)
        sections = [{'id': 'general', 'name': 'PIA · Geral', 'fields': [field(*row) for row in environment_fields()]}]
        for identity, folder in self.plugin_folders():
            example = folder / '.env.example'
            if not example.exists():
                example = folder / 'docs' / 'examples' / '.env.example'
            defaults = dotenv_values(example) if example.exists() else {}
            values = dotenv_values(folder / '.env') if (folder / '.env').exists() else {}
            rows = []
            for name in dict.fromkeys([*defaults, *values]):
                value = values.get(name, defaults.get(name)) or ''
                sensitive = any(part in name for part in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL'))
                link = ('https://console.cloud.google.com/apis/credentials' if name.startswith('GOOGLE') else
                        'https://dash.cloudflare.com/' if name.startswith('OBJECT_STORAGE') else
                        'https://huggingface.co/settings/tokens' if name.startswith('HF_') else
                        'https://discord.com/developers/applications' if name.startswith('DISCORD_') else
                        'https://github.com/oouo-diogo-perdigao/pia#readme')
                rows.append(field(name, value, link, sensitive))
            if rows:sections.append(dict(id=identity, name=identity.replace('/', ' · '), fields=rows))
        return sections

    def save_settings(self, section, values):
        from dotenv import set_key
        available = next((s for s in self.settings() if s['id'] == section), None)
        if available is None:
            raise ValueError('Seção desconhecida.')
        path = CONFIG_DIR / '.env' if section == 'general' else dict(self.plugin_folders())[section] / '.env'
        fields = {f['name']: f for f in available['fields']}
        for name, value in values.items():
            if name not in fields or not isinstance(value, str) or '\x00' in value:
                raise ValueError('Variável inválida.')
        for name, value in values.items():
            if fields[name]['sensitive'] and value == '':
                continue  # An empty password field preserves the configured secret.
            set_key(path, name, value, quote_mode='always')
        return {'ok': True, 'restart_required': True}

    def dispatch(self, method, path, data, query):
        if path == '/state':
            return self.state()
        if path == '/chat/new':
            chat = self.store.new_chat()
            if data.get('folder'):
                self.store.update_chat(chat, folder=data['folder'], move=True)
            return {'id': chat}
        if path == '/chat/messages':
            chat = query.get('chat', [''])[0]
            return {'messages': self.store.message_records(chat), 'draft': self.store.get('draft:' + chat, '')}
        if path == '/chat/send':
            return {'job': self.send(data['chat'], data['text'], data.get('request'))}
        if path == '/chat/cancel':
            self.jobs[data['job']].cancelled.set()
            return {'ok': True}
        if path == '/chat/draft':
            self.store.set('draft:' + data['chat'], str(data.get('text', ''))[:100000])
            return {'ok': True}
        if path == '/chat/update':
            self.store.update_chat(data['chat'], title=data.get('title'), folder=data.get('folder'), move='folder' in data, pinned=data.get('pinned'), archived=data.get('archived'))
            return {'ok': True}
        if path in ('/chat/message', '/chat/delete-many'):
            targets = data.get('chats', []) if path.endswith('delete-many') else [data['chat']]
            with self.lock:
                if (path.endswith('delete-many') or data.get('action') not in ('speak','fork')) and any(j.chat in targets and j.status == 'running' for j in self.jobs.values()):
                    raise ValueError('Interrompa a resposta e aguarde antes de alterar esta conversa.')
                if path.endswith('delete-many'):
                    for chat in targets: self.store.delete_chat(chat)
                    return {'ok': True}
                chat, identity, action = data['chat'], int(data['id']), data['action']
                node = next((n for n in self.store.message_records(chat) if n['id']==identity), None)
                if action == 'select':
                    self.store.select_message(chat, identity)
                    return {'ok': True}
                if node is None: raise ValueError('Mensagem não encontrada na ramificação atual.')
                if action == 'fork': return {'chat': self.store.fork(chat,identity)}
                if action == 'delete':
                    self.store.remove_message(chat,identity)
                    return {'ok': True}
                if action == 'speak':
                    threading.Thread(target=self.backend.speak,args=(node['content'],),daemon=True).start()
                    return {'ok': True}
                if action == 'edit':
                    text = data.get('text','').strip()
                    if not text: raise ValueError('Mensagem vazia.')
                    self.store.select_message(chat,node['parent'],descendants=False)
                    self.store.append(chat,node['role'],text)
                    if node['role']=='assistant': return {'ok': True}
                elif action == 'retry':
                    if node['role']=='assistant':
                        self.store.select_message(chat,node['parent'],descendants=False)
                    else:
                        self.store.select_message(chat,identity,descendants=False)
                    history = self.store.messages(chat)
                    if not history or history[-1]['role']!='user': raise ValueError('Não há mensagem para gerar novamente.')
                    text = history[-1]['content']
                else: raise ValueError('Ação desconhecida.')
                return {'job': self.send(chat,text)}
        if path == '/chat/delete':
            if any(j.chat == data['chat'] and j.status == 'running' for j in self.jobs.values()):
                raise ValueError('Aguarde a resposta antes de excluir.')
            self.store.delete_chat(data['chat'])
            return {'ok': True}
        if path == '/folder/save':
            return {'id': self.store.save_folder(data['name'], data.get('id'))}
        if path == '/folder/delete':
            self.store.remove_folder(data['id'])
            return {'ok': True}
        if path == '/settings':
            return self.settings()
        if path == '/settings/save':
            return self.save_settings(data['section'], data['values'])
        if path == '/accounts':
            return {'providers': self.backend.resources.manifests(), 'accounts': self.backend.resources.accounts(),
                    'clients': {p['id']: self.backend.resources.config(p['id']).get('client_id', '') for p in self.backend.resources.manifests()}}
        if path == '/accounts/connect':
            resources = self.backend.resources
            job = Job()
            self.jobs[job.id] = job
            def connect():
                try:
                    resources.configure(data['plugin'], data['client_id'], data.get('client_secret') or None)
                    resources.connect(data['plugin'], data.get('label', ''))
                    job.emit('done')
                except Exception as exc:
                    job.emit('error', error=str(exc))
            threading.Thread(target=connect, daemon=True).start()
            return {'job': job.id}
        if path == '/accounts/disconnect':
            self.backend.resources.disconnect(data['plugin'], data['account'])
            return {'ok': True}
        if path == '/bots':
            return [{'id': 'secretaria', 'name': 'Secretária', 'avatar':'/bots/secretaria/avatar.svg', 'description': 'Agenda, lembretes e e-mails importantes'}]
        if path == '/bots/secretaria':
            if method == 'POST':
                self.backend.secretary.configure(data)
            from Plugins.Bot.secretaria.bot import MAIL_FILTERS
            return {'filters':[{'id':key,'name':label} for key,(label,_) in MAIL_FILTERS.items()], 'config': self.backend.secretary.config(), 'accounts': self.backend.resources.accounts('google'),
                    'status': [self.store.get('secretary:status:' + a['id'], {}) for a in self.backend.resources.accounts('google')]}
        if path == '/bots/secretaria/poll':
            threading.Thread(target=self.backend.secretary.poll, daemon=True).start()
            return {'ok': True}
        if path.startswith('/integrations/'):
            _,_,plugin,action=path.split('/',3)
            if plugin=='google':
                from Plugins.Plugins.google.drive import Drive
                drive=Drive(self.backend.resources)
                if action=='accounts':return {'accounts':drive.accounts(),'folder':drive.config().get('GOOGLE_DRIVE_FOLDER_ID','')}
                if action=='folders':return drive.list(account=data.get('account'),folders_only=True,cursor=data.get('cursor'),search=data.get('search'))
            if plugin=='discord':
                from Plugins.Plugins.discord.service import Discord
                if action=='status':return Discord().public()
                if action=='send':return Discord().send(data['text'],data.get('channel'))
            raise ValueError('Integração desconhecida.')
        if path.startswith('/apps/'):
            _, _, identity, action = path.split('/', 3)
            return self.apps.call(identity, action, data, self)
        if path == '/native':
            return self.native(data['action'], data.get('payload', {}))
        if path=='/logs/clear':
            directory=(BASE_DIR/'logs').resolve()
            if data.get('all') is True:files=list(directory.glob('*.log'))
            else:
                name=data.get('name','')
                if not isinstance(name,str) or Path(name).name!=name or not name.endswith('.log'):raise ValueError('Log inválido.')
                files=[directory/name]
            cleared=[]
            for file in files:
                if not file.resolve().is_relative_to(directory) or not file.is_file():raise ValueError('Log não encontrado.')
                with file.open('wb'):pass
                cleared.append(file.name)
            return {'cleared':cleared}
        if path == '/logs':
            result = []
            for file in sorted((BASE_DIR / 'logs').glob('*.log')):
                with file.open('rb') as stream:
                    stream.seek(max(0, file.stat().st_size - 32000))
                    result.append({'name': file.name, 'text': stream.read().decode('utf-8', errors='replace')})
            return result
        raise ValueError('Operação não encontrada.')


_service = None
_service_lock = threading.Lock()


def get_service():
    global _service
    with _service_lock:
        if _service is None:
            _service = WorkspaceService()
        return _service
