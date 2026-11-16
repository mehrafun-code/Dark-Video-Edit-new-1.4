"""Dark Video Edit - desktop app entry point.
A pywebview window shows the UI (app/ui/index.html); this file is the bridge to the Python/FFmpeg engine.
Run:  python app/main.py
"""
import base64, hashlib, http.server, json, mimetypes, os, socketserver, tempfile, threading, time
import webview
import engine as E

OUT = os.path.join(os.path.expanduser("~"), "Videos", "DarkVideoEdit")
FILES = {}   # token -> local file path (served to the preview <video> with Range support)


class MediaHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        p = FILES.get(self.path.lstrip("/").split("?")[0])
        if not p or not os.path.exists(p): return self.send_error(404)
        size = os.path.getsize(p); start, end = 0, size - 1; rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            a, b = rng[6:].split("-"); start = int(a) if a else 0; end = int(b) if b else size - 1
            end = min(end, size - 1); self.send_response(206); self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else: self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(p)[0] or "video/mp4")
        self.send_header("Accept-Ranges", "bytes"); self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()
        try:
            with open(p, "rb") as f:
                f.seek(start); left = end - start + 1
                while left > 0:
                    d = f.read(min(1 << 20, left))
                    if not d: break
                    self.wfile.write(d); left -= len(d)
        except (BrokenPipeError, ConnectionResetError, OSError): pass


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer): daemon_threads = True
SRV = Server(("127.0.0.1", 0), MediaHandler)
threading.Thread(target=SRV.serve_forever, daemon=True).start()

def media_url(path):
    key = hashlib.md5(path.encode()).hexdigest() + os.path.splitext(path)[1]
    FILES[key] = path
    return f"http://127.0.0.1:{SRV.server_address[1]}/{key}"


class Api:
    """Every public method here can be called from the UI as pywebview.api.<name>(...)"""
    def __init__(self): self.win = None; self.browser = None

    # ---- helpers ----
    def _emit(self, ev, data):
        self.win.evaluate_js(f"window.onEvent({json.dumps(ev)},{json.dumps(data)})")
    def _bg(self, fn, *a):
        def w():
            try: fn(*a)
            except Exception as e: self._emit("error", {"msg": str(e)[-300:]})
        threading.Thread(target=w, daemon=True).start()

    # ---- clips ----
    def pick_files(self):
        kind = webview.FileDialog.OPEN if hasattr(webview, "FileDialog") else webview.OPEN_DIALOG
        r = self.win.create_file_dialog(kind, allow_multiple=True, file_types=("Video files (*.mp4;*.mov;*.mkv;*.webm)",))
        return [{"path": p, "name": os.path.basename(p), "dur": E.duration(p), "url": media_url(p)} for p in (r or [])]

    def scan(self, paths): self._bg(self._scan, paths)
    def _scan(self, paths):
        shots = []
        for i, p in enumerate(paths):
            self._emit("progress", {"p": int(100 * i / len(paths)), "t": f"Scanning {os.path.basename(p)}…"})
            ss = E.make_shots(p, E.detect_kills(p), E.duration(p))
            for s in ss: s["url"] = media_url(p)
            shots += ss
        self._emit("scan_done", {"shots": shots, "kills": sum(s["k"] for s in shots)})

    # ---- reel ----
    def export(self, shots, opt): self._bg(self._export, shots, opt or {})
    def _export(self, shots, opt):
        out = os.path.join(OUT, time.strftime("reel_%Y%m%d_%H%M%S.mp4"))
        E.build_reel(shots, out, opt, lambda p, t: self._emit("progress", {"p": p, "t": t}))
        self._emit("export_done", {"path": out})

    def save_voice(self, b64):
        p = os.path.join(tempfile.gettempdir(), f"dve_voice_{int(time.time() * 1000)}.webm")
        open(p, "wb").write(base64.b64decode(b64)); return p

    # ---- YouTube ----
    def info(self, url):
        try: return E.yt_info(url, self.browser)
        except Exception as e: return {"error": str(e)[-200:]}

    def download(self, req): self._bg(self._download, req)
    def _download(self, req):
        p = E.yt_download(req["url"], req["start"], req["end"], os.path.join(OUT, "downloads"), self.browser, req.get("crop"),
                          lambda p, t: self._emit("progress", {"p": p, "t": t}))
        d = E.duration(p)
        self._emit("dl_done", {"path": p, "dur": d, "thumb": E.thumb(p, min(1, d / 2)), "url": media_url(p)})

    def set_browser(self, b): self.browser = b or None; return True

    # ---- misc ----
    def title(self, n): return E.make_title(n)
    def open_folder(self):
        os.makedirs(OUT, exist_ok=True)
        if hasattr(os, "startfile"): os.startfile(OUT)


if __name__ == "__main__":
    api = Api()
    api.win = webview.create_window("Dark Video Edit", E.res("ui", "index.html"), js_api=api,
                                    width=1480, height=920, min_size=(1100, 700), background_color="#09080b")
    webview.start(http_server=True, private_mode=False, storage_path=os.path.join(os.path.expanduser("~"), ".darkvideoedit"))
