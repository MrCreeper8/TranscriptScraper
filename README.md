# Transcript Scraper

A desktop transcript getter for YouTube, TikTok, Shorts, Reels, and other video sites supported by `yt-dlp`.

Transcript Scraper reads existing caption/subtitle tracks. If a video has no captions, it reports that directly rather than inventing text.

## Run

Double-click `Transcript Scraper.vbs`.

## Use

1. Paste a video URL.
2. Click `Scan tracks`.
3. Pick one of the caption tracks found on the video.
4. Click `Extract`.
5. Copy or save the transcript.

## Quality of life

- Right-click the URL field for cut/copy/paste/select all.
- Right-click the transcript box for cut/copy/paste/select all/save/clear.
- Press Enter in the URL field to scan tracks.
- Double-click a caption track to extract it.
- Use Ctrl+A in the URL or transcript field to select all.
- Use Ctrl+S in the transcript field to save.
- Use `Paste URL` to paste from the clipboard.
- Use `Open log` if something fails and you want to inspect the app log.

## Dependency

The app uses `yt-dlp`. If it ever says `yt-dlp is not available`, run `install.bat` once.

## Development

```powershell
python -m pip install -r requirements.txt
python transcript_scraper.pyw
```
