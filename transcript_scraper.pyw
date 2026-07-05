import html
import json
import queue
import re
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path
from tkinter import END, INSERT, LEFT, BOTH, RIGHT, SEL, X, Y, Button, Entry, Frame, Label, Listbox, Menu, Scrollbar, StringVar, Text, Tk, filedialog


APP_NAME = "Transcript Scraper"
ROOT = Path(__file__).resolve().parent
LOG_PATH = ROOT / "transcript-scraper.log"

vendor = ROOT / "vendor"
if vendor.exists():
    sys.path.insert(0, str(vendor))

try:
    from yt_dlp import YoutubeDL
except Exception:
    YoutubeDL = None


def log(message):
    try:
        LOG_PATH.write_text("", encoding="utf-8") if LOG_PATH.stat().st_size > 500000 else None
    except Exception:
        pass
    try:
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except Exception:
        pass


TAG_RE = re.compile(r"<[^>]+>")
TIMING_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3}")


def clean_text(value):
    value = html.unescape(value or "")
    value = TAG_RE.sub("", value)
    value = value.replace("\u200b", "")
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def collapse_lines(lines):
    collapsed = []
    previous = None
    for line in lines:
        line = re.sub(r"\s+", " ", line).strip()
        if not line or line == previous:
            continue
        collapsed.append(line)
        previous = line
    return "\n".join(collapsed)


def parse_json3(raw):
    data = json.loads(raw)
    lines = []
    for event in data.get("events", []):
        parts = [seg.get("utf8", "") for seg in event.get("segs", []) or []]
        line = clean_text("".join(parts))
        if line:
            lines.append(line)
    return collapse_lines(lines)


def parse_vtt(raw):
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line == "WEBVTT" or line.startswith(("Kind:", "Language:", "NOTE")):
            continue
        if TIMING_RE.search(line) or line.isdigit():
            continue
        line = clean_text(line)
        if line:
            lines.append(line)
    return collapse_lines(lines)


def parse_xmlish(raw):
    return parse_vtt(raw.replace("</p>", "\n").replace("<br />", "\n"))


def usable_track(track):
    return track.get("url") and track.get("ext") in {"json3", "vtt", "ttml", "srv1", "srv2", "srv3"}


def best_track(tracks):
    priority = {"json3": 0, "vtt": 1, "ttml": 2, "srv3": 3, "srv2": 4, "srv1": 5}
    good = [t for t in tracks if usable_track(t)]
    return sorted(good, key=lambda t: priority.get(t.get("ext"), 99))[0] if good else None


def read_info(video_url):
    log(f"scan start: {video_url}")
    if YoutubeDL is None:
        raise RuntimeError("yt-dlp is not available. Run install.bat once, or install yt-dlp for your Python.")
    if not video_url.startswith(("http://", "https://")):
        raise ValueError("Paste a full video link that starts with http:// or https://.")

    options = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }
    with tempfile.TemporaryDirectory() as tmp:
        options["paths"] = {"home": tmp}
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(video_url, download=False)
    log(f"scan info loaded: {info.get('title') or 'untitled'}")

    tracks = []
    for kind, source in (("Manual", info.get("subtitles") or {}), ("Auto", info.get("automatic_captions") or {})):
        for language, variants in source.items():
            track = best_track([dict(v, language=language, kind=kind) for v in variants])
            if track:
                tracks.append(track)

    tracks.sort(key=lambda t: (0 if t["kind"] == "Manual" else 1, 0 if t["language"].lower().startswith("en") else 1, t["language"]))
    log(f"scan tracks: {len(tracks)}")
    return info, tracks


def fetch_track(track):
    log(f"extract start: {track.get('kind')} {track.get('language')} {track.get('ext')}")
    request = urllib.request.Request(track["url"], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8", errors="replace")

    ext = track.get("ext", "")
    if ext == "json3":
        text = parse_json3(raw)
    elif ext == "vtt":
        text = parse_vtt(raw)
    else:
        text = parse_xmlish(raw)

    if not text.strip():
        raise RuntimeError("That caption track exists, but it did not contain readable text.")
    log(f"extract done: {len(text)} chars")
    return text


class TranscriptScraper:
    def __init__(self):
        self.root = Tk()
        self.root.title(APP_NAME)
        self.root.geometry("980x680")
        self.root.minsize(820, 560)
        self.root.report_callback_exception = self.handle_callback_error

        self.jobs = queue.Queue()
        self.tracks = []
        self.last_title = "transcript"
        self.status = StringVar(value="Paste a video URL, scan tracks, then extract.")
        self.meta = StringVar(value="No video loaded")
        self.counts = StringVar(value="0 lines / 0 words")

        self.build_ui()
        self.bind_shortcuts()
        self.root.after(100, self.pump_jobs)

    def handle_callback_error(self, exc_type, exc_value, exc_traceback):
        log(f"ui error: {exc_type.__name__}: {exc_value}")
        self.set_ready()
        self.show_error(f"UI error: {exc_value}")

    def build_ui(self):
        root = Frame(self.root, padx=14, pady=12)
        root.pack(fill=BOTH, expand=True)

        header = Frame(root)
        header.pack(fill=X, pady=(0, 10))
        Label(header, text=APP_NAME, font=("Segoe UI", 18, "bold")).pack(side=LEFT)
        Label(header, textvariable=self.status, anchor="e").pack(side=RIGHT, fill=X, expand=True)

        url_row = Frame(root)
        url_row.pack(fill=X, pady=(0, 10))
        Label(url_row, text="Video URL").pack(side=LEFT, padx=(0, 8))
        self.url_entry = Entry(url_row)
        self.url_entry.pack(side=LEFT, fill=X, expand=True)
        self.url_entry.bind("<Return>", lambda _event: self.scan_tracks())
        self.scan_button = Button(url_row, text="Scan tracks", command=self.scan_tracks)
        self.scan_button.pack(side=LEFT, padx=(8, 0))
        self.extract_button = Button(url_row, text="Extract", command=self.extract_selected)
        self.extract_button.pack(side=LEFT, padx=(6, 0))
        Button(url_row, text="Paste URL", command=self.paste_url).pack(side=LEFT, padx=(6, 0))

        middle = Frame(root)
        middle.pack(fill=BOTH, expand=True)

        left = Frame(middle)
        left.pack(side=LEFT, fill=Y, padx=(0, 12))
        Label(left, text="Caption tracks", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        track_frame = Frame(left)
        track_frame.pack(fill=BOTH, expand=True)
        self.track_list = Listbox(track_frame, width=36, exportselection=False)
        self.track_list.pack(side=LEFT, fill=BOTH, expand=True)
        self.track_list.bind("<Double-Button-1>", lambda _event: self.extract_selected())
        track_scroll = Scrollbar(track_frame, command=self.track_list.yview)
        track_scroll.pack(side=RIGHT, fill=Y)
        self.track_list.configure(yscrollcommand=track_scroll.set)

        right = Frame(middle)
        right.pack(side=LEFT, fill=BOTH, expand=True)
        top = Frame(right)
        top.pack(fill=X)
        Label(top, text="Transcript", font=("Segoe UI", 10, "bold")).pack(side=LEFT)
        Label(top, textvariable=self.counts).pack(side=RIGHT)
        Label(right, textvariable=self.meta, anchor="w").pack(fill=X, pady=(2, 6))

        text_frame = Frame(right)
        text_frame.pack(fill=BOTH, expand=True)
        self.output = Text(text_frame, wrap="word", undo=True)
        self.output.pack(side=LEFT, fill=BOTH, expand=True)
        self.output.bind("<KeyRelease>", lambda _event: self.update_counts())
        output_scroll = Scrollbar(text_frame, command=self.output.yview)
        output_scroll.pack(side=RIGHT, fill=Y)
        self.output.configure(yscrollcommand=output_scroll.set)

        bottom = Frame(root)
        bottom.pack(fill=X, pady=(10, 0))
        Button(bottom, text="Copy transcript", command=self.copy_text).pack(side=LEFT)
        Button(bottom, text="Copy selection", command=self.copy_selection).pack(side=LEFT, padx=(8, 0))
        Button(bottom, text="Save as .txt", command=self.save_text).pack(side=LEFT, padx=(8, 0))
        Button(bottom, text="Clear", command=self.clear).pack(side=LEFT, padx=(8, 0))
        Button(bottom, text="Open log", command=self.open_log).pack(side=RIGHT)

        self.url_menu = Menu(self.root, tearoff=0)
        self.url_menu.add_command(label="Cut", command=lambda: self.url_entry.event_generate("<<Cut>>"))
        self.url_menu.add_command(label="Copy", command=lambda: self.url_entry.event_generate("<<Copy>>"))
        self.url_menu.add_command(label="Paste", command=lambda: self.url_entry.event_generate("<<Paste>>"))
        self.url_menu.add_separator()
        self.url_menu.add_command(label="Select all", command=self.select_all_url)
        self.url_menu.add_command(label="Paste and scan", command=self.paste_and_scan)
        self.url_entry.bind("<Button-3>", lambda event: self.show_menu(event, self.url_menu))

        self.output_menu = Menu(self.root, tearoff=0)
        self.output_menu.add_command(label="Cut", command=lambda: self.output.event_generate("<<Cut>>"))
        self.output_menu.add_command(label="Copy", command=lambda: self.output.event_generate("<<Copy>>"))
        self.output_menu.add_command(label="Paste", command=lambda: self.output.event_generate("<<Paste>>"))
        self.output_menu.add_separator()
        self.output_menu.add_command(label="Copy selection", command=self.copy_selection)
        self.output_menu.add_command(label="Copy all", command=self.copy_text)
        self.output_menu.add_command(label="Select all", command=self.select_all_output)
        self.output_menu.add_separator()
        self.output_menu.add_command(label="Save as .txt", command=self.save_text)
        self.output_menu.add_command(label="Clear transcript", command=self.clear_output)
        self.output.bind("<Button-3>", lambda event: self.show_menu(event, self.output_menu))

    def bind_shortcuts(self):
        self.url_entry.bind("<Control-a>", lambda event: self.select_all_url())
        self.url_entry.bind("<Control-A>", lambda event: self.select_all_url())
        self.output.bind("<Control-a>", lambda event: self.select_all_output())
        self.output.bind("<Control-A>", lambda event: self.select_all_output())
        self.output.bind("<Control-s>", lambda event: self.save_text())
        self.output.bind("<Control-S>", lambda event: self.save_text())

    def show_menu(self, event, menu):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def show_error(self, message):
        self.status.set(message)
        self.output.delete("1.0", END)
        self.output.insert(INSERT, f"Error\n\n{message}")
        self.update_counts()

    def select_all_url(self):
        self.url_entry.selection_range(0, END)
        self.url_entry.icursor(END)
        return "break"

    def select_all_output(self):
        self.output.tag_add(SEL, "1.0", END)
        self.output.mark_set(INSERT, "1.0")
        self.output.see(INSERT)
        return "break"

    def selected_output_text(self):
        try:
            return self.output.get(SEL + ".first", SEL + ".last").strip()
        except Exception:
            return ""

    def paste_url(self):
        try:
            text = self.root.clipboard_get().strip()
        except Exception:
            self.status.set("Clipboard does not contain text.")
            return
        self.url_entry.delete(0, END)
        self.url_entry.insert(0, text)
        self.status.set("Pasted URL.")

    def paste_and_scan(self):
        self.paste_url()
        self.scan_tracks()

    def set_busy(self, message):
        self.status.set(message)
        self.scan_button.configure(state="disabled")
        self.extract_button.configure(state="disabled")

    def set_ready(self):
        self.scan_button.configure(state="normal")
        self.extract_button.configure(state="normal")

    def scan_tracks(self):
        url = self.url_entry.get().strip()
        if not url:
            self.status.set("Paste a video URL first.")
            return

        def work():
            try:
                return "tracks", ("ok", read_info(url))
            except Exception as exc:
                log(f"scan error: {exc}")
                return "tracks", ("error", str(exc))

        self.set_busy("Scanning tracks...")
        threading.Thread(target=lambda: self.jobs.put(work()), daemon=True).start()

    def extract_selected(self):
        selection = self.track_list.curselection()
        if not selection:
            self.status.set("Choose a caption track first.")
            return
        track = self.tracks[selection[0]]

        def work():
            try:
                return "extract", ("ok", fetch_track(track))
            except Exception as exc:
                log(f"extract error: {exc}")
                return "extract", ("error", str(exc))

        self.set_busy(f"Extracting {track['kind'].lower()} {track['language']} captions...")
        threading.Thread(target=lambda: self.jobs.put(work()), daemon=True).start()

    def pump_jobs(self):
        try:
            while True:
                kind, result = self.jobs.get_nowait()
                self.set_ready()
                status, payload = result
                if status == "error":
                    self.show_error(payload)
                    continue

                if kind == "tracks":
                    info, self.tracks = payload
                    self.last_title = info.get("title") or "transcript"
                    self.track_list.delete(0, END)
                    self.output.delete("1.0", END)
                    self.update_counts()
                    self.meta.set(self.last_title)
                    if not self.tracks:
                        self.status.set("No captions found for this video.")
                    else:
                        for track in self.tracks:
                            self.track_list.insert(END, f"{track['kind']:<6} {track['language']:<12} .{track['ext']}")
                        self.track_list.selection_set(0)
                        self.status.set(f"Found {len(self.tracks)} track(s). Choose one and extract.")

                elif kind == "extract":
                    self.output.delete("1.0", END)
                    self.output.insert(INSERT, payload)
                    self.update_counts()
                    self.status.set("Transcript extracted.")
        except queue.Empty:
            pass
        self.root.after(100, self.pump_jobs)

    def update_counts(self):
        text = self.output.get("1.0", END).strip()
        lines = len([line for line in text.splitlines() if line.strip()]) if text else 0
        words = len(re.findall(r"\S+", text))
        self.counts.set(f"{lines} lines / {words} words")

    def copy_text(self):
        text = self.output.get("1.0", END).strip()
        if not text:
            self.status.set("No transcript to copy.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.set("Copied transcript.")

    def copy_selection(self):
        text = self.selected_output_text()
        if not text:
            self.status.set("No transcript text selected.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.set("Copied selected text.")

    def save_text(self):
        text = self.output.get("1.0", END).strip()
        if not text:
            self.status.set("No transcript to save.")
            return
        safe = re.sub(r"[^a-zA-Z0-9]+", "-", self.last_title).strip("-").lower()[:70] or "transcript"
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=f"{safe}.txt", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            Path(path).write_text(text, encoding="utf-8")
            self.status.set(f"Saved {Path(path).name}.")

    def clear(self):
        self.url_entry.delete(0, END)
        self.track_list.delete(0, END)
        self.clear_output()
        self.tracks = []
        self.last_title = "transcript"
        self.meta.set("No video loaded")
        self.status.set("Cleared.")

    def clear_output(self):
        self.output.delete("1.0", END)
        self.update_counts()

    def open_log(self):
        if not LOG_PATH.exists():
            LOG_PATH.write_text("", encoding="utf-8")
        try:
            import os
            os.startfile(LOG_PATH)
        except Exception as exc:
            self.status.set(f"Could not open log: {exc}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    TranscriptScraper().run()
