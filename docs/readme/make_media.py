#!/usr/bin/env python3
"""Regenerate the README's pictures in the badge simulator.

    python3 docs/readme/make_media.py            # needs Pillow and ./setup_simulator.sh
    python3 docs/readme/make_media.py --keep DIR # also keep every captured frame in DIR

Runs Super Mona Kart with capture.py driving it (seeded, so the same races
every run) and two simulated badges for the Party lobby, then writes the
images next to this script. The moments below are frame offsets into those
seeded races; if a change to the game alters the races, rerun with --keep,
look at the frames and pick again. The two Party badges run on the wall
clock, so the lobby quarter of modes.png can differ slightly between runs;
every other image is the same byte for byte.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
APP = REPO / "super_mona_kart"

# race shots are every 3rd frame (20 fps); k is the frame count from the
# race's first frame (the countdown), so GO is at k=180
HERO = [(0, 144, 300),      # Octocat Meadow: the countdown and the pack leaving the line
        (2, 492, 588),      # Frost Fork: Tux takes the lead with a bee alongside
        (1, 432, 528),      # Merge Conflict Canyon: a pile-up
        (3, 516, 744)]      # Deploy Volcano: a scrape, then Ferris in the lava
SCREENS = ["title", "chars5_0042", "t0_race_0504", "podium_0012"]
TRACKS = ["t0_race_0372", "t1_race_0468", "t2_race_0600", "t3_race_0348"]
MODES = ["gp_standings", "tt_results", "tt_ghost_0720", "party"]
RADIUS = 18     # corner radius of the stills at 2x
GAP = 24


def run(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], cwd=REPO, capture_output=True, text=True, **kw)


def capture(tmp: Path) -> Path:
    """Run capture.py in the simulator; return a folder of named frames."""
    app = tmp / "apps" / "smk_capture"
    shutil.copytree(APP, app, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy(HERE / "capture.py", app / "__init__.py")
    result = run([sys.executable, "badgesim.py", app, "--frames", "80000",
                  "--state", tmp / "state", "--out", tmp / "raw"], timeout=900)
    log = tmp / "state" / "shots.txt"
    if "Traceback" in result.stdout + result.stderr or not log.exists():
        sys.exit("capture failed:\n" + (result.stdout + result.stderr)[-3000:])
    named = tmp / "named"
    named.mkdir()
    for line in log.read_text().splitlines():
        name, frame = line.split()
        shutil.copy(tmp / "raw" / ("frame-%05d.png" % int(frame)), named / (name + ".png"))

    # the Party lobby needs two badges talking, on the wall clock
    presses = ["--press", "30-32:SELECT", "--press", "50-52:DOWN", "--press", "56-58:DOWN",
               "--press", "62-64:DOWN", "--press", "75-77:SELECT"]
    procs = [subprocess.Popen([sys.executable, "badgesim.py", APP, "--frames", "260", "--realtime",
                               "--port-offset", str(i), "--shots", "230", "--out", tmp / ("party%d" % i)]
                              + presses, cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
             for i in (0, 1)]
    for p in procs:
        p.wait(timeout=120)
    # badge ids are random and the lowest one hosts; keep the host's view, the
    # one whose first slot reads "YOU *" in gold
    shots = [tmp / ("party%d" % i) / "frame-00230.png" for i in (0, 1)]
    hosts = [s for s in shots if s.exists() and gold_pixels(Image.open(s), (20, 107, 70, 123)) > 20]
    if len(hosts) != 1:
        sys.exit("party capture failed: expected one host view, got %d" % len(hosts))
    shutil.copy(hosts[0], named / "party.png")
    return named


def gold_pixels(im: Image.Image, box) -> int:
    """Pixels of the game's GOLD text colour (255, 208, 64) inside box."""
    px = im.convert("RGB").crop(box).tobytes()
    return sum(1 for i in range(0, len(px), 3) if px[i] > 230 and 180 < px[i + 1] < 235 and px[i + 2] < 120)


def x2(im: Image.Image) -> Image.Image:
    return im.convert("RGB").resize((im.width * 2, im.height * 2), Image.NEAREST)


def rounded(im: Image.Image, r: int = RADIUS) -> Image.Image:
    """Antialiased round corners: the mask is drawn at 4x and scaled down."""
    big = Image.new("L", (im.width * 4, im.height * 4), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, big.width - 1, big.height - 1), r * 4, fill=255)
    out = im.convert("RGBA")
    out.putalpha(big.resize(im.size, Image.LANCZOS))
    return out


def grid(ims: list[Image.Image], cols: int = 2) -> Image.Image:
    w, h = ims[0].size
    rows = (len(ims) + cols - 1) // cols
    out = Image.new("RGBA", (cols * w + (cols - 1) * GAP, rows * h + (rows - 1) * GAP), (0, 0, 0, 0))
    for i, im in enumerate(ims):
        out.alpha_composite(im, ((i % cols) * (w + GAP), (i // cols) * (h + GAP)))
    return out


def gif(frames: list[Image.Image], out: Path, ms: int):
    pal = [f.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    pal[0].save(out, save_all=True, append_images=pal[1:], duration=ms, loop=0, optimize=True, disposal=1)


def logo(out: Path):
    """Mona's kart, front view, on a rounded navy tile."""
    sheet = Image.open(APP / "assets" / "kart_mona.png").convert("RGBA")
    kart = sheet.crop((96, 0, 128, 32)).resize((96, 96), Image.NEAREST)
    tile = Image.new("RGBA", (128 * 4, 128 * 4), (0, 0, 0, 0))
    ImageDraw.Draw(tile).rounded_rectangle((0, 0, 511, 511), 28 * 4, fill=(20, 24, 60, 255))
    tile = tile.resize((128, 128), Image.LANCZOS)
    tile.alpha_composite(kart, (16, 14))
    tile.save(out, optimize=True)


def compose(named: Path):
    def shot(name):
        return Image.open(named / (name + ".png"))

    logo(HERE / "logo.png")
    gif([x2(shot("t%d_race_%04d" % (t, k))) for t, a, b in HERO for k in range(a, b, 3)],
        HERE / "race.gif", 50)
    # each racer for 1.3 s; the first frame after a switch still shows the last one
    gif([x2(shot("chars%d_%04d" % (i, k))) for i in range(9) for k in range(6, 84, 6)],
        HERE / "racers.gif", 100)
    for out, names in (("screens.png", SCREENS), ("tracks.png", TRACKS), ("modes.png", MODES)):
        grid([rounded(x2(shot(n))) for n in names]).save(HERE / out, optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep", type=Path, help="copy every captured frame here")
    args = parser.parse_args()
    sim = Path(os.environ.get("BADGEWARE_SIMULATOR", Path.home() / "badgeware-simulator"))
    if not (sim / "build-pv3-headless" / "micropython").is_file() or not (sim / "universe26").is_dir():
        sys.exit("error: needs the simulator; run ./setup_simulator.sh")
    with tempfile.TemporaryDirectory(prefix="smk-media-") as tmp:
        named = capture(Path(tmp))
        if args.keep:
            shutil.copytree(named, args.keep, dirs_exist_ok=True)
        compose(named)
    for f in sorted(HERE.glob("*.png")) + sorted(HERE.glob("*.gif")):
        print("%-14s %5d KB" % (f.name, f.stat().st_size // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
