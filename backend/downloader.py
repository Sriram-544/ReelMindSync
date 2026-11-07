"""
downloader.py — yt-dlp wrapper for ReelMind.

Instead of scraping Instagram directly, we receive a list of URLs from
our Chrome extension and use yt-dlp to download the videos locally.
"""

import json
import threading
import time
from pathlib import Path
from typing import Callable, Optional, List
import yt_dlp

REELS_DIR = Path(__file__).parent / "data" / "reels"

class ReelDownloader:
    def __init__(self, reels_dir: str):
        self.reels_dir = Path(reels_dir)
        self.reels_dir.mkdir(parents=True, exist_ok=True)

    def download_reels(
        self,
        reels: List[dict],
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
    ) -> int:
        """
        Downloads the list of reels provided by the extension.
        `reels` is expected to be a list of dicts: [{"url": "...", "shortcode": "..."}, ...]
        """
        total = len(reels)
        _report(progress_cb, 0, total, f"Starting download of {total} reels...")

        success_count = 0

    def download_one(self, ydl, reel: dict, fake_timestamp: str) -> bool:
        """Downloads a single reel using a provided yt_dlp context."""
        url = reel.get("url")
        shortcode = reel.get("shortcode")
        if not url or not shortcode:
            return False
            
        expected_mp4 = self.reels_dir / f"{shortcode}.mp4"
        meta_out = self.reels_dir / f"{shortcode}_meta.json"
        
        if not expected_mp4.exists():
            try:
                ydl.download([url])
            except Exception as e:
                print(f"[Downloader] Failed to download {url}: {e}")
                return False

        meta = {}
        if meta_out.exists():
            with open(meta_out, "r", encoding="utf-8") as f:
                try:
                    meta = json.load(f)
                except json.JSONDecodeError:
                    pass
        
        meta.update({
            "shortcode": shortcode,
            "filename": f"{shortcode}.mp4",
            "url": url,
            "thumbnail_url": reel.get("thumbnail_url", ""),
            "timestamp": fake_timestamp,
        })
        if "caption" not in meta: meta["caption"] = ""
        if "username" not in meta: meta["username"] = ""
        if "like_count" not in meta: meta["like_count"] = 0
        if "hashtags" not in meta: meta["hashtags"] = []

        with open(meta_out, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        
        return expected_mp4.exists()

    def get_ydl_opts(self):
        return {
            'outtmpl': str(self.reels_dir / '%(id)s.%(ext)s'),
            'format': 'best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
        }

    def download_reels(
        self,
        reels: List[dict],
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
    ) -> int:
        total = len(reels)
        _report(progress_cb, 0, total, f"Starting download of {total} reels...")
        success_count = 0
        base_time = int(time.time() * 1000)

        with yt_dlp.YoutubeDL(self.get_ydl_opts()) as ydl:
            for i, reel in enumerate(reels, 1):
                if not reel.get("url") or not reel.get("shortcode"):
                    continue
                
                shortcode = reel.get("shortcode")
                expected_mp4 = self.reels_dir / f"{shortcode}.mp4"
                if not expected_mp4.exists():
                    _report(progress_cb, i - 1, total, f"Downloading reel {i}/{total}: {shortcode}")
                
                fake_timestamp = str(base_time - i)
                if self.download_one(ydl, reel, fake_timestamp):
                    success_count += 1

        _report(progress_cb, success_count, total, f"Download complete — {success_count}/{total} successful")
        return success_count


def _report(cb, current, total, msg=""):
    if cb:
        cb(current, total, msg)
    else:
        print(f"[Download] {msg} ({current}/{total})")
