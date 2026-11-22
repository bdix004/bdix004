#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
THE LOVE TRAIN NATION | Reusable Windows video editor
Creates four Malate Market Shorts or edits a long-form project.

Requirements: Python 3.10+, FFmpeg/FFprobe on PATH, pip install faster-whisper
Examples:
  py lovetrain_editor.py --input "raw Malate Market.mp4"
  py lovetrain_editor.py --input "Malate Market - Retention Edit 1080P.mp4" --short 1
  py lovetrain_editor.py --mode long --input "my_long_video.mp4" --title "My Video"
  py lovetrain_editor.py --plan custom_jobs.json --input "my_video.mp4"
  py lovetrain_editor.py --input "raw Malate Market.mp4" --no-captions

The program is a deterministic video editor, not a semantic AI director.
It removes measured silences but never deletes spoken content just to hit
an estimated duration. Review subtitles and factual claims before publishing.
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

SHORTS = [
    {
        "id": 1, "name": "Short1_Manila_vs_Cebu.mp4",
        "cuts": [["02:20", "03:25"], ["06:18", "06:28"]],
        "target": 45, "format": "vertical",
        "hook": "MANILA vs. CEBU WET MARKETS 🇵🇭",
    },
    {
        "id": 2, "name": "Short2_Wild_vs_Farm_Fish.mp4",
        "cuts": [["06:48", "07:42"]],
        "target": 40, "format": "vertical",
        "hook": "STOP BUYING FARM-RAISED FISH",
    },
    {
        "id": 3, "name": "Short3_Daily_Wage_Economy.mp4",
        "cuts": [["00:31", "00:54"]],
        "target": 22, "format": "vertical",
        "hook": "WHY FILIPINOS BUY FOOD EVERY SINGLE DAY",
    },
    {
        "id": 4, "name": "Short4_440_Peso_Seafood_Haul.mp4",
        "cuts": [["05:10", "05:22"], ["07:50", "08:12"], ["08:45", "09:05"]],
        "target": 45, "format": "vertical",
        "hook": "WHAT ₱440 ($7.50) BUYS AT A MANILA WET MARKET",
    },
]

KEYWORDS = (
    "manila", "cebu", "mandaue", "medellin", "farm-raised", "farm raised",
    "mercury", "lead", "daily", "₱440", "$7.50", "bangus", "bisugo",
)

def timestamp(value):
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).split(":")
    try:
        parts = [float(p) for p in parts]
    except ValueError as ex:
        raise ValueError("Invalid timestamp: " + str(value)) from ex
    if len(parts) > 3 or not parts:
        raise ValueError("Invalid timestamp: " + str(value))
    total = 0.0
    for p in parts:
        total = total * 60.0 + p
    return total

def run(cmd, cwd=None, allow_failure=False):
    p = subprocess.run([str(c) for c in cmd], cwd=cwd,
                       text=True, errors="replace", capture_output=True)
    if p.returncode and not allow_failure:
        print("\nCOMMAND FAILED:", " ".join(map(str, cmd[:10])), file=sys.stderr)
        print(p.stderr[-5000:], file=sys.stderr)
        raise RuntimeError("Command failed (exit code {})".format(p.returncode))
    return p

def check_tools(captions):
    for program in ("ffmpeg", "ffprobe"):
        if not shutil.which(program):
            raise RuntimeError(program + " not found. Install FFmpeg, restart terminal, and check PATH.")
    if captions:
        try:
            import faster_whisper  # noqa: F401
        except ImportError as e:
            raise RuntimeError("Install captions dependency: py -m pip install faster-whisper") from e
    ff = run(["ffmpeg", "-hide_banner", "-filters"])
    if " ass " not in ff.stdout:
        raise RuntimeError("This FFmpeg build lacks the ASS subtitle filter (libass). Install a full FFmpeg build.")

def probe(path):
    p = run(["ffprobe", "-v", "error", "-show_entries",
             "stream=index,codec_type,codec_name,width,height,r_frame_rate:format=duration",
             "-of", "json", str(path)])
    data = json.loads(p.stdout)
    video = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    audio = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
    if not video or not audio:
        raise RuntimeError("Input must contain both video and audio streams.")
    return {
        "width": int(video["width"]), "height": int(video["height"]),
        "duration": float(data["format"]["duration"]),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
    }

def even(n):
    return max(2, int(n) // 2 * 2)

def determine_crop(source, info, seek_at):
    """Sample footage; detect real portrait image in a black 16:9 frame."""
    w, h = info["width"], info["height"]
    if w / h < 0.8:
        desired_w = min(w, even(h * 9 / 16))
        return (desired_w, h // 2 * 2, even((w - desired_w) / 2), 0)
    candidates = []
    offsets = (0.0, 1.3, 3.0, 6.0)
    for offset in offsets:
        t = min(max(0, seek_at + offset), max(0, info["duration"] - 0.5))
        p = run([
            "ffmpeg", "-hide_banner", "-nostdin", "-ss", str(t),
            "-i", str(source), "-an", "-t", "0.9",
            "-vf", "fps=3,cropdetect=limit=28:round=2:reset=0",
            "-f", "null", os.devnull
        ], allow_failure=True)
        for a, b, x, y in re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", p.stderr):
            cw, ch, cx, cy = map(int, (a, b, x, y))
            ratio = cw / max(ch, 1)
            if ch >= h * 0.82 and 0.45 <= ratio <= 0.74:
                candidates.append((cw, ch, cx, cy))
    if candidates:
        # Prefer the largest detected real image rather than over-cropping to a face.
        cw, ch, cx, cy = sorted(candidates, key=lambda v: v[0] * v[1], reverse=True)[0]
        # Correct to exactly 9:16 without stretching.
        ideal_w = even(ch * 9 / 16)
        if ideal_w <= cw:
            cx += even((cw - ideal_w) / 2)
            cw = ideal_w
        else:
            ideal_h = even(cw * 16 / 9)
            if ideal_h <= ch:
                cy += even((ch - ideal_h) / 2)
                ch = ideal_h
        cw, ch = even(cw), even(ch)
        cx, cy = max(0, even(cx)), max(0, even(cy))
        print("  Detected portrait area:", cw, ch, cx, cy)
        return (cw, ch, cx, cy)
    cw = even(min(w, h * 9 / 16))
    ch = even(min(h, cw * 16 / 9))
    cx, cy = even((w - cw) / 2), even((h - ch) / 2)
    print("  Using centered 9:16 crop:", cw, ch, cx, cy)
    return (cw, ch, cx, cy)

def find_silences(source, start, end, threshold=-35, minimum=0.35):
    length = end - start
    p = run([
        "ffmpeg", "-hide_banner", "-nostdin", "-ss", str(start),
        "-t", str(length), "-i", str(source), "-vn",
        "-af", "silencedetect=noise={}dB:d={}".format(threshold, minimum),
        "-f", "null", os.devnull
    ], allow_failure=True)
    if p.returncode:
        raise RuntimeError("Silence detection failed:\n" + p.stderr[-2000:])
    silences = []
    active = None
    for line in p.stderr.splitlines():
        ms = re.search(r"silence_start:\s*([0-9.]+)", line)
        me = re.search(r"silence_end:\s*([0-9.]+)", line)
        if ms:
            active = max(0.0, float(ms.group(1)))
        if me and active is not None:
            stop = min(length, float(me.group(1)))
            if stop > active:
                silences.append((active, stop))
            active = None
    if active is not None:
        silences.append((active, length))
    return silences

def compact_spans(source, start, end, do_silence=True, threshold=-35):
    """Keep spoken material; reduce gaps over .35s to approx .12s."""
    length = end - start
    if not do_silence:
        return [(start, end)]
    silences = find_silences(source, start, end, threshold)
    if not silences:
        return [(start, end)]
    kept = []
    cursor = 0.0
    for s, e in silences:
        s, e = max(0.0, s), min(length, e)
        if e - s < 0.35:
            continue
        if s <= 0.08:
            # Leading dead air/breath: begin on the first intelligible audio.
            cursor = max(cursor, e - 0.015)
            continue
        keep_until = max(cursor, s + 0.06)
        if keep_until - cursor >= 0.075:
            kept.append((start + cursor, start + keep_until))
        if e >= length - 0.06:
            # No trailing pause after the final spoken material.
            cursor = length
            break
        cursor = max(cursor, e - 0.06)
    if length - cursor >= 0.075:
        kept.append((start + cursor, end))
    if not kept:
        raise RuntimeError("Entire selected interval appears silent; check audio.")
    return kept

def make_filter(crop, zoom, vertical):
    if not vertical:
        return ("scale=1920:1080:force_original_aspect_ratio=decrease:flags=lanczos,"
                "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30")
    cw, ch, cx, cy = crop
    target_w = even(cw / zoom)
    target_h = even(target_w * 16 / 9)
    if target_h > ch:
        target_h = even(ch / zoom)
        target_w = even(target_h * 9 / 16)
    x = even(cx + (cw - target_w) / 2)
    y = even(cy + (ch - target_h) / 2)
    return ("crop={}:{}:{}:{},scale=1080:1920:flags=lanczos,"
            "setsar=1,fps=30").format(target_w, target_h, x, y)

def create_roughcut(source, intervals, work, vertical, crop, threads, crf, zoom):
    pieces = []
    for idx, (start, end) in enumerate(intervals):
        piece = work / ("piece_{:03d}.mp4".format(idx))
        zoom_factor = 1.075 if zoom and idx % 2 else 1.0
        print("    Cut {:02d}/{:02d}: {:.2f}-{:.2f}s, zoom {:.1f}%".format(
            idx + 1, len(intervals), start, end, zoom_factor * 100))
        vf = make_filter(crop, zoom_factor, vertical)
        run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-nostdin", "-ss", "{:.3f}".format(start), "-i", str(source),
            "-t", "{:.3f}".format(end - start),
            "-map", "0:v:0", "-map", "0:a:0",
            "-vf", vf, "-af", "aresample=async=1:first_pts=0",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
            "-threads", str(threads),
            "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", str(piece)
        ])
        pieces.append(piece)
    concat_path = work / "pieces.txt"
    # Paths are created in a simple, temporary directory; escape apostrophes.
    concat_path.write_text(
        "\n".join("file '{}'".format(str(p.as_posix()).replace("'", "'\\''")) for p in pieces) + "\n",
        encoding="utf-8",
    )
    rough = work / "roughcut.mp4"
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-nostdin", "-f", "concat", "-safe", "0", "-i", str(concat_path),
         "-c", "copy", "-movflags", "+faststart", str(rough)])
    return rough

def transcribe_words(media, model_name, cpu_threads):
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("Install dependency: py -m pip install faster-whisper") from e
    print("  Transcribing locally using faster-whisper ({}; CPU)...".format(model_name))
    model = WhisperModel(model_name, device="cpu", compute_type="int8",
                         cpu_threads=cpu_threads, num_workers=1)
    segments, _ = model.transcribe(str(media), beam_size=3,
                                  word_timestamps=True, vad_filter=False,
                                  condition_on_previous_text=False,
                                  initial_prompt="Manila, Cebu, Mandaue, Medellin, bangus, bisugo, pesos, wet market.")
    words = []
    for seg in segments:
        for item in (seg.words or []):
            word = item.word.strip()
            if word and item.start is not None and item.end is not None:
                words.append({"word": word, "start": max(0, float(item.start)),
                              "end": max(float(item.start) + 0.02, float(item.end))})
    del model
    if not words:
        raise RuntimeError("No words transcribed. Check the source audio.")
    return words

def group_words(words):
    groups = []
    current = []
    for word in words:
        if current:
            duration = word["end"] - current[0]["start"]
            chars = len(" ".join(x["word"] for x in current + [word]))
            if (len(current) >= 4 or chars > 25 or duration > 2.1
                    or current[-1]["word"].endswith((".", "?", "!"))):
                groups.append(current)
                current = []
        current.append(word)
    if current:
        groups.append(current)
    return groups

def ass_time(t):
    n = max(0, round(t * 100))
    return "{}:{:02d}:{:02d}.{:02d}".format(
        n // 360000, n // 6000 % 60, n // 100 % 60, n % 100)

def srt_time(t):
    n = max(0, round(t * 1000))
    return "{:02d}:{:02d}:{:02d},{:03d}".format(
        n // 3600000, n // 60000 % 60, n // 1000 % 60, n % 1000)

def escape_ass(s):
    return str(s).replace("\\", " ").replace("{", "(").replace("}", ")")

def is_keyword(token):
    normalized = token.casefold().strip(".,!?;:()[]\"' ")
    return any(k.casefold() in normalized for k in KEYWORDS)

def save_srt(groups, dest):
    lines = []
    for i, grp in enumerate(groups, 1):
        text = " ".join(x["word"] for x in grp)
        lines.extend([str(i),
                      "{} --> {}".format(srt_time(grp[0]["start"]),
                                        srt_time(grp[-1]["end"] + 0.08)),
                      text, ""])
    dest.write_text("\n".join(lines), encoding="utf-8-sig")

def ass_header(vertical):
    width, height = (1080, 1920) if vertical else (1920, 1080)
    hook_font = 60 if vertical else 70
    cap_font = 78 if vertical else 56
    cap_margin = 580 if vertical else 100
    brand_font = 30 if vertical else 29
    return ("""[Script Info]
Title: The Love Train Nation Retention Edit
ScriptType: v4.00+
Collisions: Normal
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,Arial,{hook_font},&H00FFFFFF,&H00FFFFFF,&H00151515,&HA8111111,-1,0,0,0,100,100,1,0,3,4,1,8,50,50,340,1
Style: Caption,Arial,{cap_font},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,1,2,54,54,{cap_margin},1
Style: Brand,Arial,{brand_font},&H00FFFFFF,&H00FFFFFF,&H00303030,&H90000000,-1,0,0,0,100,100,0,0,1,2,1,9,30,48,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""").format(width=width, height=height, hook_font=hook_font,
            cap_font=cap_font, cap_margin=cap_margin, brand_font=brand_font)

def create_ass(path, hook, words, duration, vertical=True, branding=True):
    lines = [ass_header(vertical)]
    if hook:
        # Keep banner beneath the top ~15% interface overlay on vertical Shorts.
        wrapped = textwrap.wrap(hook, width=21 if vertical else 35,
                                break_long_words=False, break_on_hyphens=False)
        overlay = r"\N".join(escape_ass(x) for x in wrapped)
        lines.append("Dialogue: 2,{}, {},Hook,,0,0,0,,{{\\c&H00FFFFFF&}}{}\n".format(
            ass_time(0), ass_time(min(duration, 3)), overlay))
    if branding and duration > 3:
        lines.append("Dialogue: 1,{}, {},Brand,,0,0,0,,THE LOVE TRAIN NATION\n".format(
            ass_time(3), ass_time(duration)))
    groups = group_words(words)
    for grp in groups:
        for i, w in enumerate(grp):
            t0 = max(grp[0]["start"], w["start"])
            t1 = grp[i + 1]["start"] if i + 1 < len(grp) else grp[-1]["end"] + 0.075
            t1 = min(duration, max(t1, t0 + 0.06))
            if t0 >= duration:
                continue
            pieces = []
            for j, token in enumerate(grp):
                # Current word pulses yellow; key subject terms stay yellow.
                color = r"{\c&H0000FFFF&}" if j == i or is_keyword(token["word"]) else r"{\c&H00FFFFFF&}"
                pieces.append(color + escape_ass(token["word"]))
            caption_text = " ".join(pieces)
            lines.append("Dialogue: 3,{}, {},Caption,,0,0,0,,{}\n".format(
                ass_time(t0), ass_time(t1), caption_text))
    path.write_text("".join(lines), encoding="utf-8-sig")
    return groups

def burn_overlays(rough, output, ass_file, duration, threads, crf, work):
    # Use relative ASS path; this avoids Windows C:\ drive-colon filter escaping.
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-i", str(rough), "-map", "0:v:0", "-map", "0:a:0",
        "-vf", "ass={}".format(ass_file.name),
        "-t", "{:.3f}".format(duration),
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
        "-threads", str(threads), "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", str(output)
    ], cwd=str(work))

def verify_output(path, vertical):
    info = probe(path)
    expected = (1080, 1920) if vertical else (1920, 1080)
    actual = (info["width"], info["height"])
    if actual != expected or info["video_codec"] != "h264" or info["audio_codec"] != "aac":
        raise RuntimeError("Export QC failed. Found {} {} / {}; expected {} H.264/AAC.".format(
            actual, info["video_codec"], info["audio_codec"], expected))
    if path.stat().st_size < 50_000:
        raise RuntimeError("Output unexpectedly small: " + str(path))
    print("  PASS: {} | {}x{} | {:.2f}s | {:.1f} MB".format(
        path.name, *actual, info["duration"], path.stat().st_size / 1_000_000))
    return info

def edit_job(source, job, info, args, output_dir):
    name = job["name"]
    vertical = job.get("format", "vertical") == "vertical"
    cuts = [(timestamp(a), timestamp(b)) for a, b in job["cuts"]]
    for start, end in cuts:
        if start < 0 or end <= start or end > info["duration"] + 0.3:
            raise ValueError("Invalid/out-of-range cut {}-{} for {:.2f}s source".format(
                start, end, info["duration"]))
    print("\n=== {} ===".format(name))
    print("  Source cuts:", cuts)
    crop = determine_crop(source, info, cuts[0][0]) if vertical else None
    intervals = []
    do_silence = args.remove_silence if args.mode == "long" else not args.keep_silence
    for start, end in cuts:
        intervals.extend(compact_spans(source, start, end, do_silence, args.threshold))
    estimated = sum(e - s for s, e in intervals)
    print("  {} retained segments; estimated {:.1f}s".format(len(intervals), estimated))
    target = job.get("target")
    if target and abs(estimated - float(target)) > 3:
        print("  NOTE: requested ~{}s; cannot safely reach it by silence removal alone."
              " Spoken words will NOT be arbitrarily discarded.".format(target))
    if args.dry_run:
        return None
    output_path = output_dir / name
    work_handle = None
    if args.keep_work:
        work = Path(tempfile.mkdtemp(prefix="LoveTrain_", dir=output_dir))
        print("  Working files:", work)
    else:
        work_handle = tempfile.TemporaryDirectory(prefix="LoveTrain_", dir=output_dir)
        work = Path(work_handle.name)
    try:
        rough = create_roughcut(source, intervals, work, vertical, crop,
                                args.threads, args.crf, not args.no_zoom and vertical)
        duration = probe(rough)["duration"]
        words = transcribe_words(rough, args.model, args.threads) if not args.no_captions else []
        if words:
            # Cut exactly after the final transcribed spoken word, without an outro.
            final_word = min(duration, words[-1]["end"] + 0.03)
            if duration - final_word <= 3.0:
                duration = max(0.3, final_word)
        ass_file = work / "overlays.ass"
        groups = create_ass(ass_file, job.get("hook", ""), words, duration,
                            vertical=vertical, branding=not args.no_branding)
        if groups:
            srt_path = output_dir / (Path(name).stem + ".srt")
            save_srt(groups, srt_path)
            print("  Captions:", srt_path.name)
        burn_overlays(rough, output_path, ass_file, duration,
                      args.threads, args.crf, work)
        verified = verify_output(output_path, vertical)
        if target and abs(verified["duration"] - float(target)) > 3:
            print("  Runtime note: {:.1f}s versus ~{}s target.".format(
                verified["duration"], target))
        return output_path
    finally:
        if work_handle:
            work_handle.cleanup()

def detect_input(requested):
    p = Path(requested).expanduser().resolve()
    if p.exists():
        return p
    preferred = ["Malate Market - Retention Edit 1080P.mp4",
                 "Malate Market - Retention Edit 1080p.mp4",
                 "raw Malate Market.mp4"]
    for name in preferred:
        candidate = (Path.cwd() / name).resolve()
        if candidate.exists():
            print("Using detected input:", candidate)
            return candidate
    options = list(Path.cwd().glob("*.mp4"))
    if len(options) == 1:
        print("Using only MP4 in current folder:", options[0])
        return options[0].resolve()
    raise FileNotFoundError("Input not found: {}. Pass --input FULL_PATH.".format(requested))

def main():
    p = argparse.ArgumentParser(description="The Love Train Nation: Shorts + long-form editor")
    p.add_argument("--input", default="Malate Market - Retention Edit 1080P.mp4")
    p.add_argument("--out", default="LoveTrain_Exports", help="Output folder")
    p.add_argument("--mode", choices=["shorts", "long"], default="shorts")
    p.add_argument("--short", choices=["all", "1", "2", "3", "4"], default="all")
    p.add_argument("--plan", help="Optional JSON array of custom jobs")
    p.add_argument("--title", default="", help="3-second title for long-form")
    p.add_argument("--long-vertical", action="store_true",
                   help="Make 9:16 vertical long-form instead of 16:9")
    p.add_argument("--remove-silence", action="store_true",
                   help="For long-form only; off by default to protect B-roll")
    p.add_argument("--keep-silence", action="store_true",
                   help="For Shorts; disable automated silence cuts")
    p.add_argument("--no-captions", action="store_true",
                   help="Skip local Whisper (output will not have spoken captions)")
    p.add_argument("--no-zoom", action="store_true")
    p.add_argument("--no-branding", action="store_true")
    p.add_argument("--threshold", type=int, default=-35,
                   help="Silence threshold dB; default -35")
    p.add_argument("--model", default="small",
                   help="Whisper model: base, small, medium etc.; default small")
    p.add_argument("--threads", type=int, default=4,
                   help="CPU thread budget for FFmpeg/Whisper")
    p.add_argument("--crf", type=int, default=20,
                   help="H.264 output quality: 18 higher quality, 23 smaller")
    p.add_argument("--keep-work", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    args.threads = max(1, min(32, args.threads))
    if not 15 <= args.crf <= 30:
        p.error("--crf must be 15..30")
    os.environ["OMP_NUM_THREADS"] = str(args.threads)
    source = detect_input(args.input)
    check_tools(captions=not args.no_captions and not args.dry_run)
    info = probe(source)
    output_dir = Path(args.out).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    print("Input:", source)
    print("Source: {width}x{height}, {duration:.2f}s, video={video_codec}, audio={audio_codec}".format(**info))
    if args.plan:
        jobs = json.loads(Path(args.plan).read_text(encoding="utf-8-sig"))
        if isinstance(jobs, dict):
            jobs = jobs.get("jobs", [])
        if not isinstance(jobs, list) or not jobs:
            raise ValueError("Custom plan must be a non-empty array or {\"jobs\": [...]}")
    elif args.mode == "long":
        stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", source.stem).strip("_")
        jobs = [{
            "name": stem + "_LoveTrain_Edit.mp4",
            "format": "vertical" if args.long_vertical else "landscape",
            "cuts": [[0, info["duration"]]],
            "hook": args.title,
        }]
    else:
        jobs = [s for s in SHORTS if args.short == "all" or str(s["id"]) == args.short]
    successes, failures = [], []
    for job in jobs:
        try:
            result = edit_job(source, job, info, args, output_dir)
            if result:
                successes.append(str(result))
        except Exception as exc:
            failures.append((job.get("name", "unnamed"), str(exc)))
            print("FAILED:", job.get("name", "unnamed"), exc, file=sys.stderr)
    print("\nDONE: {} successful, {} failed.".format(len(successes), len(failures)))
    for filename in successes:
        print("  OUTPUT:", filename)
    for name, why in failures:
        print("  ERROR:", name, why, file=sys.stderr)
    if failures:
        sys.exit(1)

if __name__ == "__main__":
    main()
