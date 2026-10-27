#!/usr/bin/env python3
"""Breach wallpaper maker.

Turns ANY video / GIF / image into a Flipper Zero desktop animation (128x64, 1-bit)
and writes it as an asset-pack animation folder.

Needs: python3, pip install pillow numpy heatshrink2, and ffmpeg in PATH.

Simplest use (whole video, auto center-crop to the Flipper aspect ratio):
    python3 make_wallpaper.py my_video.mp4 --name MyWall

Typical use (cut a piece, choose crop, remove a watermark, text panel on the left):
    python3 make_wallpaper.py clip.mp4 --name Teto --start 0 --end 1.95 \
        --crop 0,80,480,300 --delogo 2,280,70,66 --layout center --mode lines --fps 30

Result goes to  <out>/Anims/<Name>_128x64/  (default out = assets/packs/Breach)
Then see breach/WALLPAPER.md for how to put it on the Flipper.
"""
import argparse
import os
import random
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 128, 64


def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        sys.exit("ffmpeg failed:\n" + r.stderr)
    return r


def probe_size(src):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", src],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0 or "," not in r.stdout:
        sys.exit("Cannot read video size. Is the file a video/gif/image?")
    w, h = r.stdout.strip().split(",")[:2]
    return int(w), int(h)


def auto_crop(w, h):
    """Largest 2:1 box centered horizontally, vertically a bit above center."""
    if w / h >= 2:
        cw, ch = h * 2, h
        return ((w - cw) // 2, 0, cw, ch)
    cw, ch = w, w // 2
    y = int((h - ch) * 0.4)
    return (0, y, cw, ch)


SS = 4  # ffmpeg renders SS times bigger, we shrink it ourselves for sharper 1-bit edges


def to_1bit(img, size, threshold, mode):
    """img is SS times bigger than size. Fixed levels on purpose: auto-contrast would flicker."""
    if mode == "toon":
        # dark = black, strongly colored areas (hair, clothes accents) = dot pattern, rest = white
        a = np.asarray(img.convert("RGB"), dtype=float)
        lum = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
        colored = (a.max(axis=2) - a.min(axis=2) > 70) & (lum < 200)
        dark = Image.fromarray(((lum < threshold) * 255).astype("uint8")).filter(ImageFilter.MaxFilter(3))
        v = np.ones_like(lum)
        v[colored] = 0.6
        v[np.asarray(dark) > 0] = 0.0
        small = np.asarray(
            Image.fromarray((v * 255).astype("uint8")).resize(size, Image.BOX), dtype=float) / 255
        bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16
        w, h = size
        th = np.tile(bayer, (h // 4 + 1, w // 4 + 1))[:h, :w]
        return Image.fromarray(((small > th) * 255).astype("uint8")).convert("1")
    g = img.convert("L")
    if mode == "solid":
        # dark areas (hair, outlines) grow slightly so they survive shrinking -> crisp shapes
        g = g.filter(ImageFilter.MinFilter(3)).resize(size, Image.BOX)
        return g.point(lambda p: 255 if p >= threshold else 0).convert("1")
    g = g.resize(size, Image.LANCZOS)
    if mode == "fs":
        return g.convert("1", dither=Image.FLOYDSTEINBERG)
    return g.point(lambda p: 255 if p >= threshold else 0).convert("1")  # lines


def side_panel(width, text, frame_idx, glitch):
    """Left panel with vertical wordmark (+ optional glitch slices)."""
    panel = Image.new("L", (width, H), 255)
    if not text:
        return panel
    size = 15
    font = ImageFont.load_default(size=size)
    tw = int(ImageDraw.Draw(panel).textlength(text, font=font)) + 2
    txt = Image.new("L", (max(tw, 1), size + 6), 255)
    ImageDraw.Draw(txt).text((1, 0), text, font=font, fill=0)
    txt = txt.point(lambda p: 0 if p < 140 else 255).rotate(90, expand=True)
    x0, y0 = 3, max(0, (H - txt.height) // 2)
    panel.paste(txt, (x0, y0))
    d = ImageDraw.Draw(panel)
    d.line([(width - 4, 4), (width - 4, H - 5)], fill=0)
    for y in range(6, H - 6, 6):
        d.point((width - 8, y), fill=0)
    if glitch:
        rnd = random.Random(frame_idx * 7919 + 13)
        if rnd.random() < 0.45:
            for _ in range(rnd.randint(1, 2)):
                h = rnd.randint(2, 6)
                y = rnd.randint(0, H - h)
                dx = rnd.choice([-3, -2, 2, 3, 4])
                band = panel.crop((0, y, width - 6, y + h))
                panel.paste(255, (0, y, width - 6, y + h))
                panel.paste(band, (dx, y))
    return panel


def make_sd_copy(pack_dir, sd_out):
    """Compile the pack with the firmware's own asset packer -> folder to copy to the SD card."""
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    packer = os.path.join(here, "..", "..", "scripts", "asset_packer.py")
    if not os.path.isfile(packer):
        print("note: scripts/asset_packer.py not found, skipping SD folder")
        return
    try:
        spec = importlib.util.spec_from_file_location("asset_packer", packer)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except ImportError as e:
        print(f"note: SD folder skipped ({e}). Run:  pip install pillow heatshrink2")
        return
    import pathlib
    pack_dir = pathlib.Path(pack_dir).resolve()
    stage = pathlib.Path(tempfile.mkdtemp(prefix="breach_pack_"))
    try:
        shutil.copytree(pack_dir, stage / pack_dir.name)
        out = pathlib.Path(sd_out).resolve() / "asset_packs"
        out.mkdir(parents=True, exist_ok=True)
        mod.pack(stage, out, logger=lambda m: None)
        print(f"SD card folder ready: {out / pack_dir.name}")
        print(f"  -> copy it to the SD card as  /ext/asset_packs/{pack_dir.name}")
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("--name", default="Wallpaper", help="animation name, letters/digits only")
    ap.add_argument("--out", default=os.path.join("assets", "packs", "Breach"),
                    help="pack folder (default assets/packs/Breach)")
    ap.add_argument("--start", type=float, default=0.0, help="start second")
    ap.add_argument("--end", type=float, default=None, help="end second")
    ap.add_argument("--fps", type=int, default=10, help="frames per second, 1..30 (default 10)")
    ap.add_argument("--crop", default=None, help="x,y,w,h in source pixels (default: auto)")
    ap.add_argument("--delogo", default=None, help="x,y,w,h rectangle to erase (watermark)")
    ap.add_argument("--threshold", type=int, default=None,
                    help="0..255, lower = less black (default: 140 toon, 165 solid, 150 lines)")
    ap.add_argument("--mode", choices=["toon", "solid", "lines", "fs"], default="toon",
                    help="toon = black outlines + dot pattern for colored areas (default), "
                         "solid = crisp black shapes, lines = thin line-art, fs = photo-like dots")
    ap.add_argument("--layout", choices=["fill", "center", "side"], default="fill",
                    help="fill = stretch crop to the screen (default); "
                         "center = keep proportions, centered, whole picture visible; "
                         "side = keep proportions on the right, text panel on the left")
    ap.add_argument("--text", default="", help="wordmark for --layout side")
    ap.add_argument("--no-glitch", action="store_true")
    ap.add_argument("--sd-out", default=os.path.join("breach", "sd_ready"),
                    help="ready-to-copy SD card folder (default breach/sd_ready)")
    ap.add_argument("--no-sd", action="store_true", help="do not create the SD card folder")
    ap.add_argument("--invert", action="store_true")
    ap.add_argument("--keep", action="store_true",
                    help="do not delete other animations already in the pack")
    a = ap.parse_args()

    if not a.name.isalnum():
        sys.exit("--name: only letters and digits")
    fps = max(1, min(a.fps, 30))
    if a.threshold is None:
        a.threshold = {"toon": 140, "solid": 165, "lines": 150, "fs": 128}[a.mode]
    sw, sh = probe_size(a.input)
    cx, cy, cw, ch = (int(v) for v in a.crop.split(",")) if a.crop else auto_crop(sw, sh)

    filters = []
    if a.delogo:
        dx, dy, dw, dh = (int(v) for v in a.delogo.split(","))
        filters.append(f"delogo=x={dx}:y={dy}:w={dw}:h={dh}")
    if a.layout in ("side", "center"):
        pw = max(8, min(W - (20 if a.layout == "side" else 0), round(cw * H / ch)))
    else:
        pw = W
    filters += [f"crop={cw}:{ch}:{cx}:{cy}", f"fps={fps}", f"scale={pw * SS}:{H * SS}:flags=lanczos"]

    tmp = tempfile.mkdtemp(prefix="breach_")
    try:
        cmd = ["ffmpeg", "-v", "error", "-y"]
        if a.start:
            cmd += ["-ss", str(a.start)]
        if a.end is not None:
            cmd += ["-t", str(max(0.1, a.end - a.start))]
        cmd += ["-i", a.input, "-vf", ",".join(filters), os.path.join(tmp, "f_%04d.png")]
        run(cmd)
        names = sorted(n for n in os.listdir(tmp) if n.startswith("f_"))
        if not names:
            sys.exit("No frames produced - check --start/--end")
        if len(names) > 70:
            print(f"warning: {len(names)} frames is a lot of memory for the Flipper, consider a lower --fps or a shorter clip")

        anim = f"{a.name}_{W}x{H}"
        anims_dir = os.path.join(a.out, "Anims")
        dest = os.path.join(anims_dir, anim)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.makedirs(dest)

        for i, n in enumerate(names):
            im = to_1bit(Image.open(os.path.join(tmp, n)), (pw, H), a.threshold, a.mode)
            if a.layout == "side":
                full = Image.new("L", (W, H), 255)
                full.paste(side_panel(W - pw, a.text, i, not a.no_glitch), (0, 0))
                full.paste(im.convert("L"), (W - pw, 0))
                im = full.point(lambda p: 255 if p >= 128 else 0).convert("1")
            elif a.layout == "center":
                full = Image.new("L", (W, H), 255)
                full.paste(im.convert("L"), ((W - pw) // 2, 0))
                im = full.point(lambda p: 255 if p >= 128 else 0).convert("1")
            if a.invert:
                im = ImageOps.invert(im.convert("L")).convert("1")
            im.save(os.path.join(dest, f"frame_{i}.png"))

        count = len(names)
        with open(os.path.join(dest, "meta.txt"), "w", newline="\n") as f:
            f.write("Filetype: Flipper Animation\nVersion: 1\n\n")
            f.write(f"Width: {W}\nHeight: {H}\n")
            f.write(f"Passive frames: {count}\nActive frames: 0\n")
            f.write("Frames order: " + " ".join(str(i) for i in range(count)) + "\n")
            f.write(f"Active cycles: 0\nFrame rate: {fps}\nDuration: 3600\nActive cooldown: 0\n\n")
            f.write("Bubble slots: 0\n")

        # manifest lists every animation folder of the pack
        found = sorted(d for d in os.listdir(anims_dir) if os.path.isdir(os.path.join(anims_dir, d)))
        if not a.keep:
            for d in found:
                if d != anim:
                    shutil.rmtree(os.path.join(anims_dir, d))
            found = [anim]
        with open(os.path.join(anims_dir, "manifest.txt"), "w", newline="\n") as f:
            f.write("Filetype: Flipper Animation Manifest\nVersion: 1\n")
            for d in found:
                f.write(f"\nName: {d}\nMin butthurt: 0\nMax butthurt: 18\n"
                        f"Min level: 1\nMax level: 30\nWeight: 3\n")

        print(f"OK: {count} frames @ {fps} fps -> {dest}")
        if not a.no_sd:
            make_sd_copy(a.out, a.sd_out)
        print("Next steps: see breach/WALLPAPER.md")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
