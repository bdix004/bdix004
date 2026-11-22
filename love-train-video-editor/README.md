# The Love Train Nation: reusable FFmpeg + Python editor

This version is an **untested first build**, not a guaranteed professional edit. Review every exported clip before publishing. It is a deterministic video cutter with automatic silence detection, simple alternating punch-in zooms, Whisper speech-to-text captions, hook overlays and logo-text branding; it does **not** judge narrative coherence or optimize scenes like a human editor.

## Windows setup

1. Install **Python 3.10 or later** from python.org and make sure the `py` command works in Command Prompt.
2. Install a full **FFmpeg build including FFprobe and libass**, add its `bin` directory to your PATH, and restart Command Prompt. Verify `ffmpeg -version` and `ffprobe -version`.
3. Download **both** `lovetrain_editor.py` and `RUN_EDITOR_WINDOWS.bat` into the **same folder** on your PC. GitHub provides a Raw button on each file page.
4. Double-click `RUN_EDITOR_WINDOWS.bat`. It installs `faster-whisper` if necessary. The first transcription run also downloads the speech-recognition model, so it requires internet then.
5. Drag your source MP4 into the prompt and press Enter. Select **2** to test Short #1 first, or **1** for all four Shorts. Finished videos and SRTs appear under `LoveTrain_Exports`.

Do **not** close the terminal during rendering. The computer handles processing locally, and this does not call ChatGPT or a paid AI API.

## Command-line options

```bat
py lovetrain_editor.py --input "D:\Videos\Malate Market - Retention Edit 1080P.mp4" --short 1
py lovetrain_editor.py --input "D:\Videos\Malate Market - Retention Edit 1080P.mp4" --short all --threads 4
py lovetrain_editor.py --mode long --input "D:\Videos\long_video.mp4" --title "YOUR HOOK"
py lovetrain_editor.py --input "D:\Videos\my_video.mp4" --plan custom_jobs.json
```

`--no-captions` skips Whisper transcription; `--keep-silence` disables silence cuts in Shorts. Use `--dry-run` to inspect estimated cuts first. Change `--threads 4` to `--threads 2` for reduced load. `--model base` uses a lighter speech model but can lower accuracy.

## Custom cuts on any future video

Create `custom_jobs.json` beside the editor with this content (times are source timecodes):

```json
[
  {
    "name": "My_Short.mp4",
    "format": "vertical",
    "cuts": [["00:15", "00:43"], ["01:04", "01:18"]],
    "target": 40,
    "hook": "MY NEW HOOK"
  }
]
```

## Important caveats

- The four Malate cut points are those specified for the **10:41.87 retention-edit timeline**. They **must** match the actual source file's timeline. If you use another raw video, timestamps likely refer to different footage.
- Silence detection uses a signal threshold rather than speech understanding. Background sound can prevent cuts; low-volume speech can be mistaken for silence. Inspect each cut carefully.
- Target durations are advisory. The script does **not** automatically delete spoken material simply to force 45 seconds.
- Captions are automatically generated and may miss names or money amounts. Review the accompanying SRT and final burned-in captions.
- The source's black borders are estimated using sampled frames; preview to confirm correct framing and absence of cut-off faces.
- The script can make a basic **1920×1080 long-form** edit, but long-form storytelling and B-roll selection still require human review.
- Audio and visual quality are limited by the source file. No hardware encoder is implemented in this version (software x264 uses CPU).
- If a video has more than one audio track or unusually formatted media, adjust the source first.

## Project outputs

- `Short1_Manila_vs_Cebu.mp4`
- `Short2_Wild_vs_Farm_Fish.mp4`
- `Short3_Daily_Wage_Economy.mp4`
- `Short4_440_Peso_Seafood_Haul.mp4`

Each transcription-enabled Short also receives an accompanying .srt file.
