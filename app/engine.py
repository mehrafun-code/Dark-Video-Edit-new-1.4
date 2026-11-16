"""Dark Video Edit engine: kill detection, reel building, YouTube section download."""
import base64, os, random, re, shutil, subprocess, sys, tempfile
import numpy as np

NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
def res(*p):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *p)

def _ffmpeg():
    p = shutil.which("ffmpeg")
    if p: return p
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()
FF = _ffmpeg()

def run(args, **kw):
    return subprocess.run([FF, "-v", "error", "-y", *args], capture_output=True, text=True, creationflags=NOWIN, **kw)

def info(path):
    return subprocess.run([FF, "-i", path], capture_output=True, text=True, creationflags=NOWIN).stderr

def duration(path):
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info(path))
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0

def video_size(path):
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", info(path))
    return (int(m[1]), int(m[2])) if m else (1920, 1080)

HAS_TEXT = "drawtext" in subprocess.run([FF, "-hide_banner", "-filters"], capture_output=True, text=True, creationflags=NOWIN).stdout

# ---------- kill detection (red skull badge, top centre) ----------
def detect_kills(path, fps=5, thr=6, gap=3.0):
    p = subprocess.run([FF, "-v", "error", "-i", path, "-vf",
        f"fps={fps},crop=iw*0.16:ih*0.14:iw*0.42:ih*0.093,scale=48:24:flags=area",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, creationflags=NOWIN)
    a = np.frombuffer(p.stdout, np.uint8).reshape(-1, 24, 48, 3).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    red = ((r > 170) & (g < 90) & (b < 100) & (r - g > 100)).sum((1, 2))
    ev, on = [], False
    for i, x in enumerate(red):
        if x >= thr and not on: on, s = True, i
        if x < thr and on: on = False; ev.append([s / fps, i / fps])
    if on: ev.append([s / fps, len(red) / fps])
    out = []
    for s, e in ev:
        if out and s - out[-1][1] < gap: out[-1][1] = e
        else: out.append([s, e])
    return out

def thumb(path, t):
    p = subprocess.run([FF, "-v", "error", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1", "-vf", "scale=160:-1",
                        "-f", "mjpeg", "-"], capture_output=True, creationflags=NOWIN)
    return "data:image/jpeg;base64," + base64.b64encode(p.stdout).decode() if p.stdout else ""

def make_shots(path, kills, dur):
    shots = []
    for s, e in kills:
        a, b = max(0, s - 2.5), min(dur - 0.1, max(e + 1.5, s + 2.0))
        if shots and a <= shots[-1]["end"] + 0.3: shots[-1]["end"] = b; shots[-1]["hits"].append(s)
        else: shots.append(dict(path=path, start=a, end=b, hits=[s]))
    for x in shots:
        x["k"] = len(x["hits"]); x["t"] = thumb(path, x["hits"][0] + 0.1)
    return shots

# ---------- reel builder ----------
def _ff_path(p): return p.replace("\\", "/").replace(":", "\\:")
def _txt(s): return re.sub(r"[:'%\\]", "", s)
MUSIC = {1: "phonk.mp3", 2: "bass.mp3", 3: "lofi.mp3"}   # drop royalty-free files into app/assets/music/

def build_reel(shots, out, opt, progress=lambda p, t: None):
    """shots: [{path,start,end,hits,cap,sp,fx{shake,flash,zoom,slow,neon,vig,glitch,boom,counter},au{gv,mu,mv,ms},voice}]"""
    tmp = tempfile.mkdtemp(prefix="dve_"); boom = os.path.join(tmp, "boom.wav")
    run(["-f", "lavfi", "-i", "aevalsrc='(sin(2*PI*55*t)*exp(-5*t)*1.1+sin(2*PI*1800*t)*exp(-40*t)*0.3)':d=0.9:s=44100", "-ac", "2", boom])
    F = _ff_path(res("assets", "Poppins-Bold.ttf")); n, files = 0, []
    for i, s in enumerate(shots):
        progress(int(100 * i / len(shots)), f"Building shot {i + 1}/{len(shots)}…")
        fx, au = s.get("fx") or {}, s.get("au") or {}
        sp = float(s.get("sp") or 1)
        if fx.get("slow") and sp == 1: sp = 0.5
        sp = min(2.0, max(0.5, sp))
        D = s["end"] - s["start"]; Do = D / sp
        hits = [(h - s["start"]) / sp for h in s.get("hits", []) if s["start"] <= h <= s["end"]]; k = len(hits)
        gv = 0.0 if au.get("mu") else au.get("gv", 80) / 100.0
        shake = "+".join(f"between(t,{h:.2f},{h + .4:.2f})" for h in hits) if fx.get("shake") and hits else ""
        flash = "+".join(f"between(t,{h:.2f},{h + .08:.2f})" for h in hits) if fx.get("flash") and hits else ""
        Z = 1360 if fx.get("zoom") else 1220; base = (Z - 1080) // 2
        dx = f"'{base}+if(gt({shake},0),sin(t*90)*35,0)'" if shake else str(base)
        dy = f"'{base}+if(gt({shake},0),cos(t*80)*35,0)'" if shake else str(base)
        parts = []
        if HAS_TEXT and s.get("cap"):
            parts.append(f"drawtext=fontfile='{F}':text='{_txt(s['cap'])}':fontsize=60:fontcolor=white:borderw=5:bordercolor=black:x=(w-text_w)/2:y=230:enable='between(t,0.2,{Do:.2f})'")
        if HAS_TEXT and fx.get("counter") and hits:
            for h in hits:
                n += 1
                parts.append(f"drawtext=fontfile='{F}':text='KILL {n}':fontsize=130:fontcolor=#ff2a2a:borderw=8:bordercolor=white:x='(w-text_w)/2+if(lt(t,{h + .5:.2f}),sin(t*100)*14,0)':y=1560:enable='between(t,{h:.2f},{h + 1.4:.2f})'")
        else: n += k
        if fx.get("glitch"): parts += ["hue=h='sin(t*50)*70'", "noise=alls=10:allf=t"]
        eq = ["contrast=1.18", "saturation=1.8"] if fx.get("neon") else []
        if flash: eq += [f"brightness='if(gt({flash},0),0.55,0)'", "eval=frame"]
        if eq: parts.append("eq=" + ":".join(eq))
        if fx.get("vig"): parts.append("vignette=PI/5")
        parts += ["fade=t=in:d=0.1", "setsar=1", "format=yuv420p"]
        vf = (f"[0:v]setpts=PTS/{sp:.3f},split[a][b];[a]scale=108:192:force_original_aspect_ratio=increase,crop=108:192,boxblur=5:2,eq=brightness=-0.2,scale=1080:1920:flags=bilinear[bg];"
              f"[b]scale=-2:1080,crop=1080:1080,scale={Z}:{Z},crop=1080:1080:{dx}:{dy}[fg];[bg][fg]overlay=0:420," + ",".join(parts) + "[v]")
        # ---- audio ----
        has_a = "Audio:" in info(s["path"])
        tempo = f",atempo={sp:.3f}" if sp != 1 else ""
        chains = [(f"[0:a]atrim=0:{D:.2f},asetpts=PTS-STARTPTS{tempo},volume={gv * 0.9:.2f}[ga]" if has_a else f"anullsrc=r=44100:cl=stereo,atrim=0:{Do:.2f}[ga]")]
        labels = ["[ga]"]; extra = []; idx = 2
        if fx.get("boom") and hits:
            if k == 1: chains.append(f"[1:a]adelay={int(hits[0] * 1000)}|{int(hits[0] * 1000)}[bd0]")
            else:
                chains.append(f"[1:a]asplit={k}" + "".join(f"[bs{j}]" for j in range(k)))
                chains += [f"[bs{j}]adelay={int(h * 1000)}|{int(h * 1000)}[bd{j}]" for j, h in enumerate(hits)]
            labels += [f"[bd{j}]" for j in range(k)]
        if s.get("voice") and os.path.exists(s["voice"]):
            extra += ["-i", s["voice"]]; chains.append(f"[{idx}:a]atrim=0:{Do:.2f},asetpts=PTS-STARTPTS,volume=1.4[vo]"); labels.append("[vo]"); idx += 1
        mp = res("assets", "music", MUSIC.get(int(au.get("ms", 0)), "none"))
        if os.path.exists(mp):
            extra += ["-stream_loop", "-1", "-i", mp]; chains.append(f"[{idx}:a]atrim=0:{Do:.2f},asetpts=PTS-STARTPTS,volume={au.get('mv', 40) / 100 * 0.6:.2f}[mu]"); labels.append("[mu]"); idx += 1
        chains.append("[ga]anull[aout]" if len(labels) == 1 else "".join(labels) + f"amix=inputs={len(labels)}:normalize=0,alimiter=limit=0.95[aout]")
        o = os.path.join(tmp, f"s{i:03d}.mp4"); files.append(o)
        r = run(["-ss", f"{s['start']:.2f}", "-t", f"{D:.2f}", "-i", s["path"], "-i", boom, *extra, "-filter_complex", vf + ";" + ";".join(chains),
                 "-map", "[v]", "-map", "[aout]", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                 "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-t", f"{Do:.2f}", o])
        if r.returncode: raise RuntimeError(r.stderr[-400:])
    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("".join("file '" + f.replace("\\", "/") + "'\n" for f in files))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    r = run(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", out])
    shutil.rmtree(tmp, ignore_errors=True)
    if r.returncode: raise RuntimeError(r.stderr[-400:])
    progress(100, "Reel ready"); return out

# ---------- crop ----------
RATIOS = {"9:16": (9, 16, 1080, 1920), "1:1": (1, 1, 1080, 1080), "4:5": (4, 5, 1080, 1350), "16:9": (16, 9, 1920, 1080)}
def crop_video(src, dst, r, z=1.0, cx=.5, cy=.5):
    W, H = video_size(src)
    if r in RATIOS:
        rw, rh, ow, oh = RATIOS[r]; ar = rw / rh; w, h = (W, W / ar) if ar >= W / H else (H * ar, H)
    else: w, h, ow, oh = W, H, 0, 0
    w, h = w * z, h * z; x, y = max(0, min(W - w, cx * W - w / 2)), max(0, min(H - h, cy * H - h / 2))
    w, h, x, y = [int(v) // 2 * 2 for v in (w, h, x, y)]
    vf = f"crop={w}:{h}:{x}:{y}" + (f",scale={ow}:{oh}" if ow else "")
    rr = run(["-i", src, "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy", dst])
    if rr.returncode: raise RuntimeError(rr.stderr[-400:])
    return dst

# ---------- YouTube (only the chosen part is downloaded) ----------
def yt_info(url, browser=None):
    from yt_dlp import YoutubeDL
    o = {"quiet": True, "noplaylist": True, "skip_download": True}
    if browser: o["cookiesfrombrowser"] = (browser,)
    with YoutubeDL(o) as y: i = y.extract_info(url, download=False)
    return {"title": i.get("title", ""), "dur": i.get("duration") or 0, "live": bool(i.get("is_live"))}

def yt_download(url, start, end, outdir, browser=None, crop=None, progress=lambda p, t: None):
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import download_range_func
    os.makedirs(outdir, exist_ok=True)
    def hook(d):
        if d["status"] == "downloading":
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
            progress(int(100 * d.get("downloaded_bytes", 0) / tot), "Downloading selected part…")
    o = {"quiet": True, "noplaylist": True, "download_ranges": download_range_func(None, [(start, end)]),
         "force_keyframes_at_cuts": True, "format": "bv*[height<=1080]+ba/b[height<=1080]", "merge_output_format": "mp4",
         "outtmpl": os.path.join(outdir, f"%(title).50s_%(id)s_{int(start)}-{int(end)}.%(ext)s"),
         "ffmpeg_location": FF, "progress_hooks": [hook]}
    if browser: o["cookiesfrombrowser"] = (browser,)
    with YoutubeDL(o) as y:
        i = y.extract_info(url, download=True); path = i["requested_downloads"][0]["filepath"]
    if crop:
        dst = path.rsplit(".", 1)[0] + "_" + crop["r"].replace(":", "x") + ".mp4"
        path = crop_video(path, dst, crop["r"], crop.get("z", 1), crop.get("x", .5), crop.get("y", .5))
    return path

# ---------- title / description ----------
TITLES = ["{n} KILLS in ek match - dushman ro pada", "Bhai ne lobby khaali kar di - {n} KILLS", "Ek ek karke sab gaye - {n} KILLS", "Paaji ka aim dekho - {n} KILLS GG"]
def make_title(n):
    return {"title": random.choice(TITLES).format(n=n), "desc": "Dark Video Edit se bani reel. Like aur follow karo!\n#gaming #reels #shorts #gamingreels #kills"}
