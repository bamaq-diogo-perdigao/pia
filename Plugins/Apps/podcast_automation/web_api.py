"""Podcast's web API. The PIA host only discovers and dispatches app actions."""
import json
from pathlib import Path
import secrets
import threading
from src.pia.service import Job
from src.resource_plugins import save_json

ROOT = Path(__file__).resolve().parent
_latest = None
_tasks = {}
_lock = threading.Lock()


def handle(action, data, context):
    global _latest
    if action == 'status':
        task = _tasks.get(_latest)
        return {'job': _latest, 'running': bool(task and task['job'].status == 'running'),
                'lines': task['lines'][-2500:] if task else [],
                'result': task.get('result') if task else None}
    if action == 'config':
        path = ROOT / 'config/config.json'
        if not path.exists():
            path = ROOT / 'docs/examples/config.example.json'
        return json.loads(path.read_text(encoding='utf-8'))
    if action=='save-options':
        config=handle('config',{},context)
        outputs=data.get('outputs',{})
        if not isinstance(outputs,dict) or set(outputs)-{'mp3','resumo.json','srt','vtt','txt'} or any(not isinstance(v,bool) for v in outputs.values()):raise ValueError('Formatos de saída inválidos.')
        integrations=data.get('integrations',{})
        allowed={'google_account','google_folder','storage_account','storage_bucket','announce','discord_notify','discord_channel'}
        if not isinstance(integrations,dict) or set(integrations)-allowed:raise ValueError('Integrações inválidas.')
        for key,value in integrations.items():
            if key in ('announce','discord_notify'):
                if not isinstance(value,bool):raise ValueError('Preferência inválida.')
            elif not isinstance(value,str):raise ValueError('Integração inválida.')
        config['outputs']={**{name:True for name in ('resumo.json','srt','txt','vtt')},**outputs,'mp3':True}
        config['integrations']={**config.get('integrations',{}),**integrations}
        save_json(ROOT/'config/config.json',config)
        return {'ok':True}
    if action == 'save-config':
        value = data['value']
        if not isinstance(value, dict) or any(not isinstance(value.get(k), dict) for k in (
                'nomes_reais', 'campaign_details', 'publication', 'audio', 'processing')):
            raise ValueError('Configuração de campanhas inválida.')
        save_json(ROOT / 'config/config.json', value)
        return {'ok': True}
    if action == 'stop':
        context.backend.stop_podcast()
        return {'ok': True}
    if action != 'start':
        raise ValueError('Ação desconhecida do podcast.')
    with _lock:
        if _latest and _tasks[_latest]['job'].status == 'running':
            raise ValueError('Já há uma tarefa em execução.')
        task = data.get('task')
        args = []
        output = None
        if task == 'process':
            module = 'podcast_automation.main'
            args = [] if data.get('monitor') else ['--once']
        elif task == 'rebuild':
            module = 'utilities.rebuild_feeds'
        elif task in ('merge_srt', 'merge_vtt'):
            module = 'utilities.' + task
            kind = task.split('_')[1]
            directory = ROOT / 'data/web-tasks' / secrets.token_hex(8)
            directory.mkdir(parents=True)
            for key in ('first', 'second'):
                value = data.get(key)
                if not isinstance(value, str) or len(value) > 5 * 1024 * 1024:
                    raise ValueError('Selecione duas legendas válidas (até 5 MiB cada).')
                (directory / (key + '.' + kind)).write_text(value, encoding='utf-8-sig' if kind == 'srt' else 'utf-8')
            output = directory / ('merged.' + kind)
            args = [directory / ('first.' + kind), directory / ('second.' + kind), '-o', output]
        else:
            raise ValueError('Tarefa desconhecida.')
        process = context.backend.start_podcast_task(module, *args)
        job = Job()
        context.jobs[job.id] = job
        _latest = job.id
        record = {'job': job, 'lines': [], 'result': None}
        _tasks[job.id] = record
        def read():
            try:
                with process.stdout:
                    for line in process.stdout:
                        record['lines'].append(line.rstrip())
                        if len(record['lines']) > 2500:
                            del record['lines'][:500]
                        job.emit('log', text=line.rstrip())
                code = process.wait()
                if code:
                    job.emit('error', error=f'A tarefa terminou com código {code}. Consulte a saída.')
                else:
                    if output:
                        record['result'] = {'name': output.name, 'text': output.read_text(encoding='utf-8-sig')}
                    job.emit('done', result=record['result'])
            except Exception as exc:
                job.emit('error', error=str(exc))
        threading.Thread(target=read, daemon=True, name='pia-podcast-web').start()
        return {'job': job.id}
