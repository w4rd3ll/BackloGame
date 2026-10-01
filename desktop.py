"""Native window around the local game library; OS details live in desktop_platform."""
import argparse
import json
import logging
import multiprocessing
import sys
import threading
from pathlib import Path
import server
import desktop_platform
from desktop_close import CloseController


def run():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path)
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--smoke-test',type=Path,help='Load the real WebView window, report state, then close')
    parser.add_argument('--hidden',action='store_true')
    parser.add_argument('--smoke-close',choices=('clean','discard','cancel'),help='Exercise the real closing event (requires --smoke-test)')
    args=parser.parse_args()
    server.configure_data(args.data_dir)
    server.init_db()
    logging.basicConfig(filename=server.DATA/'desktop.log',encoding='utf-8',level=logging.WARNING,format='%(asctime)s %(levelname)s %(message)s')
    import webview
    webview.settings['ALLOW_DOWNLOADS']=True
    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER']=True
    webview.settings['OPEN_DEVTOOLS_IN_DEBUG']=False
    desktop_platform.prepare_application()
    http=None
    worker=None
    try:
        http=server.LocalServer(('127.0.0.1',args.port),server.Handler)
        address=f'http://127.0.0.1:{http.server_port}'
        worker=threading.Thread(target=http.serve_forever,daemon=True)
        worker.start()
    except OSError as exc:
        raise RuntimeError('The local port is busy. Close the previous instance or choose another port.') from exc
    window=webview.create_window('BackloGame',address,width=1440,height=900,min_size=(900,600),background_color='#10171c',hidden=args.hidden,text_select=True)
    closing=CloseController(window)
    close_app=closing.approve
    http.desktop_close=close_app
    window.events.closing+=closing.on_closing
    def save_smoke(data):
        args.smoke_test.parent.mkdir(parents=True,exist_ok=True)
        args.smoke_test.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        if args.smoke_close:
            def exercise_close():
                if args.smoke_close != 'clean':
                    window.run_js("dirty=true; window.closeConfirmCalls=0; window.confirm=()=>{window.closeConfirmCalls++;return "+('false' if args.smoke_close=='cancel' else 'true')+";};")
                window.destroy()  # Same native FormClosing event as the title-bar X.
                if args.smoke_close=='cancel':
                    def after_cancel():
                        observation=window.evaluate_js('({dirty:dirty,calls:window.closeConfirmCalls})')
                        data['cancelledAndResponsive']=observation=={'dirty':True,'calls':1}
                        args.smoke_test.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
                        window.run_js('window.confirm=()=>true;')
                        window.destroy()
                    threading.Timer(1,after_cancel).start()
            threading.Timer(.3,exercise_close).start()
        else:
            threading.Timer(.3,close_app).start()
    if args.smoke_test:
        http.desktop_smoke=save_smoke
        watchdog=threading.Timer(45,close_app)
        watchdog.start()
    def loaded():
        window.run_js('document.documentElement.dataset.desktop="true";')
        closing.ready.set()
        if args.smoke_test:
            window.run_js("""(async()=>{for(let i=0;i<100;i++){if(token&&document.querySelectorAll('.game').length===games.length)break;await new Promise(r=>setTimeout(r,100));}await api('/api/desktop-smoke',{title:document.title,rows:document.querySelectorAll('.game').length,games:games.length,iconLoaded:document.querySelector('.appIcon').complete&&document.querySelector('.appIcon').naturalWidth>0,view:document.getElementById('viewToggle').value,desktop:document.documentElement.dataset.desktop==='true',dirty:dirty,profileProbe:localStorage.getItem('desktopProfileProbe')});localStorage.setItem('desktopProfileProbe','persisted');})();""")
    window.events.loaded+=loaded
    try:
        webview.start(private_mode=False,storage_path=str(server.DATA/'webview'),localization={'global.quitConfirmation':'Close BackloGame?'},**desktop_platform.webview_options(server.ROOT))
    finally:
        if args.smoke_test:watchdog.cancel()
        if http:
            http.shutdown()
            http.server_close()
            worker.join(timeout=3)
    if args.smoke_test and not args.smoke_test.is_file():raise RuntimeError('Проверка окна не завершилась. Подробности: desktop.log')


if __name__=='__main__':
    multiprocessing.freeze_support()
    try:run()
    except Exception as exc:
        logging.exception('Desktop startup failed')
        if '--smoke-test' not in sys.argv:desktop_platform.show_error('Could not start BackloGame.\n'+str(exc)+'\n\n'+desktop_platform.startup_help()+'\nDetails: desktop.log in the data folder.')
        sys.exit(1)
