"""HTML/Qt integration smoke using synthetic audio, images and a local fixture server."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QTWEBENGINE_CHROMIUM_FLAGS']='--no-sandbox --disable-gpu'
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
from contextlib import ExitStack
import threading
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock,patch
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from PyQt6.QtWidgets import QApplication,QWidget
from PyQt6.QtGui import QImage,QColor
from PyQt6.QtCore import QTimer
from PyQt6.QtTest import QTest
from src.workspace_store import WorkspaceStore
from src.pia.service import WorkspaceService
from src.pia import http
from src.desktop_ui import DesktopUI

app=QApplication(['pia-web-smoke'])
app.setQuitOnLastWindowClosed(False)
def wait(predicate,timeout=8000):
    for _ in range(timeout//25):
        QTest.qWait(25)
        if predicate():return
    raise AssertionError('Timeout waiting for web/native state')
def js(view,script):
    result=[]
    view.page().runJavaScript(script,lambda value:result.append(value))
    wait(lambda:bool(result))
    return result[0]

with tempfile.TemporaryDirectory() as folder:
    folder=Path(folder)
    store=WorkspaceStore(folder/'workspace.db')
    test_folder=store.save_folder('Folder fixture')
    finished=threading.Event()
    def reply(chat,text,on_delta):
        from src.chat_tools import ChatTools,image_intent
        if image_intent(text):
            result=ChatTools(root=folder/'data/chat-images',base_url=ui.url).execute(text)
            on_delta(result);store.append(chat,'assistant',result);return result
        on_delta('# Resposta\n\n')
        finished.wait(5)
        on_delta('**completa**')
        store.append(chat,'assistant','# Resposta\n\n**completa**')
    def dictate(deliver,**kwargs):
        deliver('texto ditado')
        kwargs['on_end']()
        return True
    backend=SimpleNamespace(store=store,reply=reply,speak=Mock(),secretary=SimpleNamespace(start=lambda:None,stop=lambda:None),shutdown=lambda:None,toggle_voice=dictate)
    service=WorkspaceService(backend=backend)
    seen=[]
    synthetic=QImage(640,480,QImage.Format.Format_ARGB32);synthetic.fill(QColor('#336699'))
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path=='/action/screen-all':
                seen.append(self.path)
                from Plugins.Apps.screenshots.native import png_data
                import base64
                raw=base64.b64decode(png_data(synthetic).split(',')[1])
                self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            else:http.route(self)
        def do_POST(self):
            seen.append(self.path)
            if self.path=='/v1/images/generations':
                from src.app_access import authorized
                assert authorized(self)
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert payload['response_format']=='b64_json'
                from Plugins.Apps.screenshots.native import png_data
                body=json.dumps({'created':1,'data':[{'b64_json':png_data(synthetic).split(',')[1]}]}).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            else:http.route(self)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    class Overlay(QWidget):
        user_hidden=False
        capture_hidden=False
        def should_stay_visible(self):return not self.user_hidden and not self.capture_hidden
        def blink(self):pass
    overlay=Overlay();overlay.resize(100,100)
    with patch.object(http,'get_service',return_value=service),patch('src.config_paths.BASE_DIR',folder):
        ui=DesktopUI(overlay,service=service,url='http://127.0.0.1:'+str(server.server_port))
        ui.set_main_visible(True)
        wait(lambda:js(ui.window.view,"!!document.querySelector('#prompt') && !!document.querySelector('#sidebar-content .sidebar-row')"))
        js(ui.window.view,"document.querySelector('.folder-heading button:last-child').click();document.querySelector('.conversation-menu [data-action=edit]').click()")
        assert js(ui.window.view,"!!document.querySelector('.rename-title')&&!document.querySelector('#modal[open]')")
        js(ui.window.view,"document.querySelector('.rename-title').value='Renamed folder';document.querySelector('.rename-title').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}))")
        wait(lambda:store.folders()[0]['name']=='Renamed folder')
        wait(lambda:js(ui.window.view,"!document.querySelector('.rename-title')"))
        before=len(store.chat_records())
        js(ui.window.view,"document.querySelector('#microphone').click()")
        wait(lambda:js(ui.window.view,"document.querySelector('#prompt').value.includes('texto ditado')"))
        assert len(store.chat_records())==before
        assert backend.speak.call_count==0
        js(ui.window.view,"document.querySelector('#send').click()")
        wait(lambda:js(ui.window.view,"document.querySelector('#prompt').value==='' && document.querySelector('#messages').textContent.includes('texto ditado')"))
        finished.set()
        wait(lambda:js(ui.window.view,"document.querySelectorAll('#messages .actions button').length>=12"))
        assert js(ui.window.view,"document.querySelector('#view-title').textContent.includes('texto ditado')")
        chat=js(ui.window.view,"localStorage.getItem('pia:chat')")
        assert js(ui.window.view,"!!document.querySelector('.message.assistant h1') && !!document.querySelector('.message.assistant strong')")
        # Rename uses the title itself, with Escape cancel and Enter commit.
        js(ui.window.view,"document.querySelector('#sidebar-content .more').click();document.querySelector('.conversation-menu [data-action=edit]').click()")
        assert js(ui.window.view,"!!document.querySelector('.rename-title') && !document.querySelector('#modal[open]')")
        js(ui.window.view,"document.querySelector('.rename-title').value='cancelled';document.querySelector('.rename-title').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
        assert store.chat_records()[0]['title']!='cancelled'
        js(ui.window.view,"document.querySelector('#sidebar-content .more').click();document.querySelector('.conversation-menu [data-action=edit]').click();document.querySelector('.rename-title').value='Conversa renomeada';document.querySelector('.rename-title').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}))")
        wait(lambda:store.chat_records()[0]['title']=='Conversa renomeada')
        wait(lambda:js(ui.window.view,"document.querySelector('#view-title').textContent==='Conversa renomeada'"))
        # Removed tooltip targets must never leave a floating tooltip behind.
        js(ui.window.view,"document.querySelector('#sidebar-content .more').click();document.querySelector('.conversation-menu [data-action=archive]').dispatchEvent(new PointerEvent('pointerover',{bubbles:true}))")
        assert js(ui.window.view,"!!document.querySelector('.pia-tooltip')")
        js(ui.window.view,"document.querySelector('.conversation-menu').remove()")
        wait(lambda:js(ui.window.view,"!document.querySelector('.pia-tooltip')"))

        # Clipboard goes through the native shell; success is an icon, not text.
        with patch('src.desktop_ui.QApplication.clipboard',return_value=Mock()) as clipboard:
            js(ui.window.view,"document.querySelector('.message.user [data-action=copy]').click()")
            wait(lambda:clipboard.return_value.setText.called)
            assert clipboard.return_value.setText.call_args.args[0].strip()=='texto ditado'
            assert js(ui.window.view,"document.querySelector('.message.user [data-action=copy]').classList.contains('success')")
        js(ui.window.view,"document.querySelector('.message.user [data-action=edit]').click()")
        wait(lambda:js(ui.window.view,"!!document.querySelector('.inline-message-editor textarea')"))
        js(ui.window.view,"document.querySelector('.inline-message-editor textarea').value='editado';document.querySelector('.inline-message-editor [data-action=check]').click()")
        wait(lambda:js(ui.window.view,"document.querySelector('#messages')?.textContent.includes('2/2')"))
        assert store.messages(chat)[0]['content']=='editado'
        wait(lambda:all(j.status!='running' for j in service.jobs.values()))
        QTest.qWait(150)
        js(ui.window.view,"document.querySelector('.message.user [data-action=speak]').click()")
        wait(lambda:backend.speak.called)
        wait(lambda:js(ui.window.view,"document.querySelector('.message.user [data-action=speak]').classList.contains('success')"))
        # Empty edit exercises the full red, copyable error alert.
        js(ui.window.view,"document.querySelector('.message.user [data-action=edit]').click()")
        wait(lambda:js(ui.window.view,"!!document.querySelector('.inline-message-editor textarea')"))
        js(ui.window.view,"document.querySelector('.inline-message-editor textarea').value='';document.querySelector('.inline-message-editor [data-action=check]').click()")
        wait(lambda:js(ui.window.view,"!!document.querySelector('#error-alert:not([hidden])')"))
        error=js(ui.window.view,"document.querySelector('#error-alert').textContent")
        assert 'Mensagem vazia' in error
        with patch('src.desktop_ui.QApplication.clipboard',return_value=Mock()) as clipboard:
            js(ui.window.view,"document.querySelector('#error-alert').click()")
            wait(lambda:clipboard.return_value.setText.called)
            assert clipboard.return_value.setText.call_args.args[0]==error
        js(ui.window.view,"document.querySelector('#error-alert').hidden=true;document.querySelector('.inline-message-editor [data-action=close]').click();document.querySelector('.message.assistant [data-action=delete]').click()")
        assert js(ui.window.view,"document.querySelector('.message.assistant [data-action=delete]').classList.contains('armed')")
        assert len(store.messages(chat))==2
        js(ui.window.view,"document.querySelector('.message.assistant [data-action=delete]').click()")
        wait(lambda:len(store.messages(chat))==1)
        # Conversation delete opens selection mode with that conversation already marked.
        js(ui.window.view,"document.querySelector('#sidebar-content .more').click()")
        wait(lambda:js(ui.window.view,"!!document.querySelector('.conversation-menu')"))
        js(ui.window.view,"document.querySelector('.conversation-menu [data-action=delete]').click()")
        assert js(ui.window.view,"!!document.querySelector('#sidebar-content input[type=checkbox]:checked')")
        js(ui.window.view,"[...document.querySelectorAll('#sidebar-footer button')].find(b=>b.textContent==='CANCELAR').click()")
        # Capture through the real app/native adapter, with a fake screen-all HTTP endpoint.
        service.apps.load('screenshots')
        from Plugins.Apps.screenshots.native import NativeApp,config,png_data
        native=NativeApp(ui,service);native.folder=folder/'raw'
        ui.native_apps['screenshots']=native
        prefs={**config(),'output_folder':str(folder/'saved'),'auto_save':True,'auto_copy':True}
        with patch('Plugins.Apps.screenshots.native.config',return_value=prefs),patch('Plugins.Apps.screenshots.native.foreground',return_value=('Fixture','',None)):
            future=native.capture('selection')
            assert ui.window.isVisible(), 'Main PIA should remain visible'
            assert overlay.capture_hidden
            wait(future.done)
            identity=future.result()['id']
            assert seen.count('/action/screen-all')==1
            wait(lambda:js(native.shell.view,"!!window.piaCapture?.ready"))
            assert js(native.shell.view,"!document.querySelector('#zoom')")
            assert js(native.shell.view,"document.querySelectorAll('.capture-star').length===32")
            assert js(native.shell.view,"document.querySelector('#stage').getBoundingClientRect().top===0")
            # Zoom changes coordinates but never changes left/right mouse roles.
            js(native.shell.view,"""(()=>{const c=document.querySelector('#canvas');c.dispatchEvent(new PointerEvent('pointermove',{clientX:200,clientY:200}));return true;})()""")
            initial=js(native.shell.view,"document.querySelector('#readout').textContent")
            js(native.shell.view,"""(()=>{const c=document.querySelector('#canvas');c.dispatchEvent(new WheelEvent('wheel',{ctrlKey:true,deltaY:-100,clientX:200,clientY:200}));return true;})()""")
            assert js(native.shell.view,"document.querySelector('#readout').textContent")!=initial
            js(native.shell.view,"document.querySelector('#canvas').setPointerCapture=()=>{};true")
            # Opposite button cancels either kind of gesture without finishing a crop.
            for button in (0,2):
                js(native.shell.view,f"""(()=>{{const c=document.querySelector('#canvas');c.dispatchEvent(new PointerEvent('pointerdown',{{pointerId:1,button:{button},buttons:{1 if button==0 else 2},clientX:180,clientY:180}}));c.dispatchEvent(new PointerEvent('pointermove',{{pointerId:1,buttons:{1 if button==0 else 2},clientX:260,clientY:260}}));c.dispatchEvent(new MouseEvent('mousedown',{{buttons:3}}));c.dispatchEvent(new PointerEvent('pointerup',{{pointerId:1,button:{button},buttons:0}}));return true;}})()""")
                assert native.shell.isVisible()
            with patch('Plugins.Apps.screenshots.native.QApplication.clipboard',return_value=Mock()) as clipboard:
                result=native.handle('finalize',{'data':png_data(synthetic),'format':'png','title':'Fixture'})
                assert (folder/'saved'/result['name']).exists()
                clipboard.return_value.setImage.assert_called_once()
            assert native.handle('status',{})['captures'][0]['name']==result['name']
            assert not native.shell.isVisible() and not overlay.capture_hidden
            # A new print starts at the original position/zoom, not the previous zoom.
            second=native.capture('selection')
            wait(second.done);second.result()
            wait(lambda:js(native.shell.view,"!!window.piaCapture?.ready"))
            js(native.shell.view,"document.querySelector('#canvas').dispatchEvent(new PointerEvent('pointermove',{clientX:200,clientY:200}));true")
            reset=js(native.shell.view,"document.querySelector('#readout').textContent")
            assert reset==initial,(reset,initial)
            assert seen.count('/action/screen-all')==2
            with patch('Plugins.Apps.screenshots.native.QApplication.clipboard',return_value=Mock()) as clipboard:
                js(native.shell.view,"""(()=>{const c=document.querySelector('#canvas');c.setPointerCapture=()=>{};c.dispatchEvent(new PointerEvent('pointerdown',{pointerId:1,button:1,buttons:4,clientX:200,clientY:200}));return true;})()""")
                wait(lambda:clipboard.return_value.setText.called)
                assert clipboard.return_value.setText.call_args.args[0]=='#336699'
                # Left selection at a zoomed view still finalizes/copies/saves immediately.
                js(native.shell.view,"""(()=>{const c=document.querySelector('#canvas');c.dispatchEvent(new WheelEvent('wheel',{ctrlKey:true,deltaY:-100,clientX:200,clientY:200}));c.dispatchEvent(new PointerEvent('pointerdown',{pointerId:1,button:0,buttons:1,ctrlKey:true,clientX:180,clientY:180}));c.dispatchEvent(new PointerEvent('pointermove',{pointerId:1,buttons:1,clientX:300,clientY:300}));c.dispatchEvent(new PointerEvent('pointerup',{pointerId:1,button:0,buttons:0}));return true;})()""")
                wait(lambda:not native.shell.isVisible())
                clipboard.return_value.setImage.assert_called_once()
                copied=clipboard.return_value.setImage.call_args.args[0]
                assert 1<copied.width()<synthetic.width()
            # Real gallery page, synthetic files only. First page is capped at 24.
            for index in range(30):synthetic.save(str(folder/'saved'/f'fixture-{index}.png'),'PNG')
            js(ui.window.view,"document.querySelector('#rail [data-app=screenshots]').click()")
            gallery=lambda script:js(ui.window.view,"(()=>{const document=window.document.querySelector('#app-frame').contentDocument;"+script+"})()")
            wait(lambda:gallery("return document?.querySelectorAll('.capture-card').length===24;"))
            calls=seen.count('/api/pia/apps/screenshots/list-saved')
            QTest.qWait(600)
            assert seen.count('/api/pia/apps/screenshots/list-saved')==calls
            gallery("document.defaultView.scrollTo(0,document.body.scrollHeight);return true;")
            wait(lambda:gallery("return document.querySelectorAll('.capture-card').length>24;"))
            with patch('Plugins.Apps.screenshots.native.QDesktopServices.openUrl',return_value=True) as opened:
                gallery("document.querySelector('.capture-card [data-action=open]').click();return true;")
                wait(lambda:opened.called)
            gallery("document.querySelector('.capture-card [data-action=select]').click();return true;")
            assert gallery("return !!document.querySelector('.capture-card.chosen');")
            before_count=len(list((folder/'saved').glob('*.png')))
            gallery("document.querySelector('.capture-card [data-action=delete]').click();return true;")
            assert gallery("return document.querySelector('.capture-card [data-action=delete]').classList.contains('armed');")
            assert len(list((folder/'saved').glob('*.png')))==before_count
            gallery("document.querySelector('.capture-card [data-action=delete]').click();return true;")
            wait(lambda:len(list((folder/'saved').glob('*.png')))==before_count-1)



        # Image requests make an actual local HTTP call and render persistent attachments.
        js(ui.window.view,"document.querySelector('#rail [data-view=chat]').click()")
        wait(lambda:js(ui.window.view,"!document.querySelector('#chat-view').hidden"))
        js(ui.window.view,"document.querySelector('#prompt').value='Gere a imagem de uma garota de anime';document.querySelector('#prompt').dispatchEvent(new Event('input'));document.querySelector('#send').click()")
        wait(lambda:js(ui.window.view,"!!document.querySelector('.chat-image')?.naturalWidth"))
        assert seen.count('/v1/images/generations')==1
        ui.window.view.reload()
        wait(lambda:js(ui.window.view,"!!document.querySelector('.chat-image')?.naturalWidth"))
        # Safe Markdown covers tables/lists/code without executing source HTML.
        sample='# Título\n\n**Forte** e *itálico*\n\n- Um\n- Dois\n\n| Coluna | Valor |\n| --- | --- |\n| A | B |\n\n```js\nalert(1)\n```\n\n<img src=x onerror=alert(1)>'
        js(ui.window.view,"import("+json.dumps(ui.url+'/pia/markdown.js')+").then(m=>{const root=document.createElement('div');root.id='markdown-fixture';document.body.append(root);m.renderMarkdown(root,"+json.dumps(sample)+");}).catch(e=>{window.markdownFixtureError=e.stack;})")
        wait(lambda:js(ui.window.view,"!!document.querySelector('#markdown-fixture h1')||!!window.markdownFixtureError"))
        assert not js(ui.window.view,"window.markdownFixtureError||null"),js(ui.window.view,"window.markdownFixtureError")
        assert js(ui.window.view,"!!document.querySelector('#markdown-fixture table') && document.querySelectorAll('#markdown-fixture li').length===2 && !!document.querySelector('#markdown-fixture pre code') && !document.querySelector('#markdown-fixture img')")
        js(ui.window.view,"document.querySelector('#markdown-fixture').remove()")
        # Bot SVG, friendly Gmail selector and color preferences belong to the bot plugin.
        from Plugins.Bot.secretaria import Secretary
        resources=Mock();resources.accounts.return_value=[{'id':'work','label':'Work','email':'fixture@example.invalid'}]
        backend.resources=resources;backend.secretary=Secretary(resources,store,Mock(),config_path=folder/'bot.json')
        js(ui.window.view,"document.querySelector('#rail [data-view=bots]').click()")
        wait(lambda:js(ui.window.view,"!!document.querySelector('#bot-email_filter') && !!document.querySelector('.bot-hero svg')"))
        assert js(ui.window.view,"document.querySelector('#bot-email_query').closest('.form-row').hidden")
        preview=Path(__file__).resolve().parents[1]/'cache/desktop-preview';preview.mkdir(parents=True,exist_ok=True)
        QTest.qWait(250)
        ui.window.view.grab().save(str(preview/'secretary-web.png'))

        js(ui.window.view,"document.querySelector('#bot-email_filter').value='all_unread';document.querySelector('#bot-avatar_primary').value='#123abc';document.querySelector('#bot-avatar_primary').dispatchEvent(new Event('input'));document.querySelector('#content-view form').requestSubmit()")
        wait(lambda:backend.secretary.config()['email_filter']=='all_unread')
        assert backend.secretary.config()['email_query']=='is:unread'
        assert backend.secretary.config()['avatar_primary']=='#123abc'
        assert js(ui.window.view,"getComputedStyle(document.querySelector('.bot-hero .secretary-body path[fill]')).fill==='rgb(18, 58, 188)'")


        fixture_logs=folder/'logs';fixture_logs.mkdir();(fixture_logs/'one.log').write_text('one');(fixture_logs/'two.log').write_text('two')
        with patch('src.pia.service.BASE_DIR',folder):
            js(ui.window.view,"document.querySelector('[data-view=settings]').click()")
            wait(lambda:js(ui.window.view,"[...document.querySelectorAll('#sidebar-content .name')].some(n=>n.textContent==='Inspeção e logs')"))
            js(ui.window.view,"[...document.querySelectorAll('#sidebar-content .name')].find(n=>n.textContent==='Inspeção e logs').click()")
            wait(lambda:js(ui.window.view,"document.querySelectorAll('#content-view .card-head [data-action=delete]').length===2"))
            js(ui.window.view,"document.querySelector('#content-view .card-head [data-action=delete]').click()")
            wait(lambda:(fixture_logs/'one.log').read_text()=='')
            js(ui.window.view,"document.querySelector('#content-view .row > [data-action=delete]').click()")
            wait(lambda:(fixture_logs/'two.log').read_text()=='')
        # New object manager and podcast options render using fake shared providers.
        storage_api=service.apps.load('object_storage');podcast_api=service.apps.load('podcast_automation')
        fake_storage=Mock();metadata=dict(id='fixture',name='Fixture Storage',bucket='bucket',endpoint='https://storage.example.invalid',region='auto',provider='s3',public_url='https://cdn.example.invalid')
        fake_storage.accounts.return_value=[metadata];fake_storage.config.return_value={'default':'fixture'};fake_storage.account.return_value=metadata
        fake_storage.list.return_value={'folders':['demo/'],'objects':[{'key':'file.txt','size':12,'modified':''}],'cursor':None}
        podcast_root=folder/'podcast';(podcast_root/'config').mkdir(parents=True)
        (podcast_root/'config/config.json').write_text(json.dumps({'outputs':{},'integrations':{}}))
        backend.resources=Mock()
        with ExitStack() as patches:
            patches.enter_context(patch.object(storage_api,'storage',return_value=fake_storage))
            patches.enter_context(patch.object(podcast_api,'ROOT',podcast_root))
            patches.enter_context(patch('Plugins.Plugins.google.drive.Drive.accounts',return_value=[{'id':'work','label':'Work','email':'fixture@example.invalid'}]))
            patches.enter_context(patch('Plugins.Plugins.google.drive.Drive.config',return_value={}))
            patches.enter_context(patch('Plugins.Plugins.google.drive.Drive.list',return_value={'files':[{'id':'recordings','name':'Recordings'}]}))
            js(ui.window.view,"document.querySelector('#rail [data-app=object_storage]').click()")
            frame=lambda script:js(ui.window.view,"(()=>{const document=window.document.querySelector('#app-frame').contentDocument;"+script+"})()")
            wait(lambda:frame("return document?.querySelectorAll('#objects tr').length===2;"))
            assert fake_storage.list.called
            assert js(ui.window.view,"!!document.querySelector('#header-actions [data-action=settings]') && document.querySelector('#sidebar-content .full').textContent==='Home'")
            frame("document.querySelector('#connections').click();return true;")
            assert frame("return !document.querySelector('#accounts-panel').hidden;")
            js(ui.window.view,"document.querySelector('#rail [data-app=podcast_automation]').click()")
            wait(lambda:frame("return document?.querySelector('#google-folder')?.options.length===1 && document.querySelectorAll('[data-format]').length===5;"))
            assert frame("return document.querySelector('[data-format=mp3]').checked&&document.querySelector('[data-format=mp3]').disabled;")
            frame("document.querySelector('[data-format=srt]').checked=false;document.querySelector('#save-options').click();return true;")
            wait(lambda:not json.loads((podcast_root/'config/config.json').read_text()).get('outputs',{}).get('srt',True))
            assert json.loads((podcast_root/'config/config.json').read_text())['integrations']['google_folder']=='recordings'
        ui.shutdown();ui.controls.timer.stop();ui.tray.hide();ui.window.hide();ui.composer.hide();overlay.hide()
        server.shutdown();server.server_close()
print('HTML chat, dictation, branching, screen-all capture, automatic save/copy and gallery: OK')
