"""Headless test:  python cli.py scan clip.mp4  |  python cli.py reel out.mp4 clip1.mp4 clip2.mp4  |  python cli.py crop in.mp4 out.mp4 9:16"""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))
import engine as E
if sys.argv[1] == "scan":
    d = E.duration(sys.argv[2])
    for s in E.make_shots(sys.argv[2], E.detect_kills(sys.argv[2]), d):
        print(f"{s['start']:.1f}-{s['end']:.1f}s kills={s['k']} hits={[round(h, 1) for h in s['hits']]}")
elif sys.argv[1] == "reel":
    shots = []
    for p in sys.argv[3:]: shots += E.make_shots(p, E.detect_kills(p), E.duration(p))
    for i, s in enumerate(shots): s["cap"] = "Dushman bola - kon aaya idhar?" if i % 2 == 0 else "Ek shot ek kill"
    print(E.build_reel(shots, sys.argv[2], {}, lambda p, t: print(p, t)))
elif sys.argv[1] == "crop":
    print(E.crop_video(sys.argv[2], sys.argv[3], sys.argv[4]))
