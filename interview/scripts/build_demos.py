#!/usr/bin/env python3
"""Build the interview's silent demo montages from their official source videos.

Install: python -m pip install av Pillow imageio-ffmpeg
Run: python interview/scripts/build_demos.py --project unigeo
The source cache and intermediate encodes stay outside the repository by default.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

import av
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "C:/Windows/Fonts/msyh.ttc",
)


def fonts(font_path, size):
    chinese = ImageFont.truetype(font_path, size)
    # Droid's CJK fallback intentionally omits Latin glyphs; Pillow has no
    # automatic fallback. Use a separate Latin font for project names/digits.
    for candidate in ("DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf", "C:/Windows/Fonts/arial.ttf"):
        try:
            return chinese, ImageFont.truetype(candidate, size)
        except OSError:
            pass
    return chinese, ImageFont.load_default(size=size)


def text_runs(text, pair):
    runs = []
    for char in text:
        font = pair[1] if ord(char) < 0x2E80 else pair[0]
        if runs and runs[-1][1] is font:
            runs[-1] = (runs[-1][0] + char, font)
        else:
            runs.append((char, font))
    return runs


def text_width(text, pair):
    return sum(font.getlength(run) for run, font in text_runs(text, pair))


def draw_text(draw, position, text, pair, fill):
    x, y = position
    for run, font in text_runs(text, pair):
        draw.text((x, y), run, font=font, fill=fill)
        x += font.getlength(run)


def probe(path):
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        duration = (float(stream.duration * stream.time_base)
                    if stream.duration is not None else container.duration / av.time_base)
        return {"width": stream.width, "height": stream.height, "duration": duration}


def download(clip, cache):
    url = clip["url"]
    if not url.startswith("https://"):
        raise ValueError(f"Official source must use HTTPS: {url}")
    path = cache / (hashlib.sha256(url.encode()).hexdigest()[:16] + ".mp4")
    if not path.exists():
        partial = path.with_suffix(".part")
        print(f"Download {url}", flush=True)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "InterviewDemoBuilder/1.0"})
            with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as target:
                shutil.copyfileobj(response, target)
            probe(partial)
            partial.replace(path)
        finally:
            partial.unlink(missing_ok=True)
    info = probe(path)
    if [info["width"], info["height"]] != clip["source_size"]:
        raise ValueError(f"Source dimensions changed for {url}: {info}")
    if not 0 <= clip["start"] < clip["end"] <= info["duration"] + 0.08:
        raise ValueError(f"Invalid time range for {url}: {clip['start']}–{clip['end']}; {info}")
    if clip.get("sha256") and hashlib.sha256(path.read_bytes()).hexdigest() != clip["sha256"]:
        raise ValueError(f"Source checksum changed for {url}; review it before updating the manifest")
    return path, info


def run(ffmpeg, arguments):
    result = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *arguments],
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())


def title_card(path, project, clip, index, settings, font_path):
    width, height = settings["width"], settings["height"]
    image = Image.new("RGB", (width, height), "#0c1424")
    draw = ImageDraw.Draw(image)
    font = fonts(font_path, 38)
    small = fonts(font_path, 28)
    accent = "#8db8ff"
    draw_text(draw, (36, 23), clip["label"], font, "#f3f6fc")
    right = f"{project['title']}  ·  {index + 1:02d}/{len(project['clips']):02d}"
    draw_text(draw, (width - 36 - text_width(right, small), 30), right, small, accent)
    draw.line((0, 91, width, 91), fill="#29405e", width=2)
    if clip["layout"] == "grid" and len(clip["panels"]) == 3:
        lines = clip.get("empty_cell_label", clip["label"]).split("\n")
        cell_font = fonts(font_path, 40)
        for number, line in enumerate(lines):
            draw_text(draw, (width * .75 - text_width(line, cell_font) / 2, 750 + number * 64), line,
                      cell_font, "#d7e6ff" if number == 0 else accent)
    image.save(path)


def filter_graph(clip, settings):
    width, height, fps = settings["width"], settings["height"], settings["fps"]
    content_height = height - 92
    filters = [f"[0:v]setpts=PTS-STARTPTS,fps={fps},setsar=1,format=yuv420p[src]",
               "[1:v]format=yuv420p[bg]"]
    if clip["layout"] == "contain":
        filters.extend([
            f"[src]scale={width}:{content_height}:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos[fit]",
            f"[bg][fit]overlay=x=(W-w)/2:y=92+({content_height}-h)/2:shortest=1[out]",
        ])
    elif clip["layout"] == "grid":
        panels = clip["panels"]
        if not 1 <= len(panels) <= 4:
            raise ValueError("Grid requires one to four source panels")
        cell_w, cell_h = width // 2, content_height // 2
        filters.append(f"[src]split={len(panels)}" + "".join(f"[p{i}]" for i in range(len(panels))))
        for index, panel in enumerate(panels):
            x, y, w, h = (panel[key] for key in ("x", "y", "width", "height"))
            source_w, source_h = clip["source_size"]
            if min(x, y) < 0 or min(w, h) <= 0 or x + w > source_w or y + h > source_h:
                raise ValueError(f"Panel lies outside source: {panel}")
            filters.append(f"[p{index}]crop={w}:{h}:{x}:{y},scale={cell_w-32}:{cell_h-32}:"
                           f"force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos[c{index}]")
            background = "bg" if index == 0 else f"b{index-1}"
            output = "out" if index == len(panels) - 1 else f"b{index}"
            filters.append(f"[{background}][c{index}]overlay=x={index%2*cell_w}+({cell_w}-w)/2:"
                           f"y={92+index//2*cell_h}+({cell_h}-h)/2:shortest=1[{output}]")
    else:
        raise ValueError(f"Unknown layout: {clip['layout']}")
    return ";".join(filters)


def build(project_id, project, settings, args, ffmpeg, font_path):
    cache = args.cache_dir.expanduser().resolve()
    cache.mkdir(parents=True, exist_ok=True)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{project_id}-demo.mp4"
    poster = output_dir / f"{project_id}-poster.jpg"
    with tempfile.TemporaryDirectory(prefix=f"{project_id}-", dir=cache) as work_name:
        work = Path(work_name)
        parts = []
        expected_duration = 0
        for index, clip in enumerate(project["clips"]):
            source, info = download(clip, cache)
            duration = min(clip["end"], info["duration"]) - clip["start"]
            expected_duration += duration
            header = work / f"header-{index}.png"
            title_card(header, project, clip, index, settings, font_path)
            part = work / f"clip-{index}.mp4"
            print(f"{project_id} {index+1}/{len(project['clips'])}: {clip['label']} ({duration:.2f}s)", flush=True)
            run(ffmpeg, ["-ss", str(clip["start"]), "-i", str(source),
                         "-loop", "1", "-framerate", str(settings["fps"]), "-i", str(header),
                         "-filter_complex_threads", str(args.threads), "-filter_complex", filter_graph(clip, settings),
                         "-map", "[out]", "-t", str(duration), "-an", "-c:v", "libx264",
                         "-preset", "medium", "-crf", str(settings["crf"]), "-pix_fmt", "yuv420p",
                         "-threads", str(args.threads), "-movflags", "+faststart", str(part)])
            parts.append(part)
        concat = work / "concat.txt"
        concat.write_text("".join(f"file '{part.name}'\n" for part in parts), encoding="utf-8")
        pending = work / "montage.mp4"
        run(ffmpeg, ["-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy",
                     "-movflags", "+faststart", str(pending)])
        info = probe(pending)
        tolerance = (len(parts) + 1) / settings["fps"]
        if abs(info["duration"] - expected_duration) > tolerance:
            raise ValueError(f"Unexpected output duration: {info['duration']} vs {expected_duration}")
        # Decode every frame: rejects truncated/corrupt source files and output encodes.
        run(ffmpeg, ["-xerror", "-i", str(pending), "-f", "null", "-"])
        shutil.copyfile(pending, output)
        run(ffmpeg, ["-ss", str(project.get("poster_time", 2)), "-i", str(output),
                     "-frames:v", "1", "-q:v", "2", "-update", "1", str(poster)])
        print(f"Saved {output} ({info['duration']:.2f}s, {output.stat().st_size/1e6:.1f} MB)", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "demo-manifest.json")
    parser.add_argument("--project", action="append", help="Project id; repeat to select several. Default: all.")
    parser.add_argument("--cache-dir", type=Path, default=Path(tempfile.gettempdir()) / "interview-demo-cache")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "assets")
    parser.add_argument("--font", help="Chinese font path (auto-detected on common Linux/macOS/Windows installs)")
    parser.add_argument("--ffmpeg", help="FFmpeg executable (default: PATH or imageio-ffmpeg bundled binary)")
    parser.add_argument("--threads", type=int, default=4, help="Encoder/filter threads; default: 4")
    parser.add_argument("--check", action="store_true", help="Download and validate selected sources without rendering")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest["version"] != 1:
        parser.error("Unsupported manifest version")
    selected = args.project or list(manifest["projects"])
    for name in selected:
        if name not in manifest["projects"]:
            parser.error(f"Unknown project: {name}")
    if args.check:
        args.cache_dir.mkdir(parents=True, exist_ok=True)
        for name in selected:
            for clip in manifest["projects"][name]["clips"]:
                path, info = download(clip, args.cache_dir)
                print(f"OK {name}: {clip['label']} {info}")
        return
    font_path = args.font or next((path for path in FONT_CANDIDATES if Path(path).exists()), None)
    if not font_path or not Path(font_path).exists():
        parser.error("No Chinese font found. Supply --font /path/to/a/CJK-font.ttf")
    ffmpeg = args.ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    if args.threads < 1:
        parser.error("--threads must be positive")
    for name in selected:
        build(name, manifest["projects"][name], manifest["output"], args, ffmpeg, font_path)


if __name__ == "__main__":
    main()
