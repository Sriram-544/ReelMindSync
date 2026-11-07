"""
extractor.py — Content extraction for ReelMind.

For each downloaded .mp4:
  1. Transcribe audio → text with OpenAI Whisper (local, offline)
  2. Sample frames → extract on-screen text with EasyOCR
  3. Load caption from _meta.json
  4. Consolidate into a processed JSON in the output directory
  5. Extract a JPEG thumbnail (first frame)
"""

import json
import ssl
import subprocess
import threading
import os
from pathlib import Path
from typing import Callable, Optional

import easyocr
import torch
import whisper

# Fix for macOS Python SSL Certificate Error when downloading Whisper models
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# Lazy singletons — loaded once on first use
_whisper_model = None
_ocr_reader = None


def _get_whisper(model_size: str = "base"):
    global _whisper_model
    if _whisper_model is None:
        import whisper
        _whisper_model = whisper.load_model(model_size)
    return _whisper_model


def _get_ocr():
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        _ocr_reader = easyocr.Reader(["en"], verbose=False)
    return _ocr_reader


class ReelExtractor:
    def __init__(self, whisper_model: str = "base", frame_interval_sec: int = 5):
        self.whisper_model = whisper_model
        self.frame_interval_sec = frame_interval_sec

    # ── Batch processing ─────────────────────────────────────────────────────
    def process_all(
        self,
        reels_dir: str,
        output_dir: str,
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
        thumbs_dir: Optional[str] = None,
    ) -> int:
        """
        Process all .mp4 files in reels_dir.
        Writes consolidated JSON to output_dir.
        Returns number of reels processed.
        """
        reels_path = Path(reels_dir)
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        mp4_files = sorted(reels_path.glob("*.mp4"))
        total = len(mp4_files)

        if total == 0:
            _report(progress_cb, 0, 0, "No video files found to process.")
            return 0

        # Pre-load models so first reel doesn't appear slow
        _report(progress_cb, 0, total, "Loading Whisper model…")
        _get_whisper(self.whisper_model)
        _report(progress_cb, 0, total, "Loading EasyOCR model…")
        _get_ocr()

        processed = 0
        for mp4 in mp4_files:
            shortcode = mp4.stem
            meta_file = reels_path / f"{shortcode}_meta.json"
            out_file = out_path / f"{shortcode}.json"

            if out_file.exists():
                processed += 1
                _report(progress_cb, processed, total,
                        f"Skipping extraction (already processed): {shortcode}")
                # Update metadata (like timestamp) without re-transcribing
                if meta_file.exists():
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                        with open(out_file, "r", encoding="utf-8") as f:
                            existing_data = json.load(f)
                        
                        existing_data["timestamp"] = meta.get("timestamp", "")
                        existing_data["caption"] = meta.get("caption", existing_data.get("caption", ""))
                        existing_data["username"] = meta.get("username", existing_data.get("username", ""))
                        
                        with open(out_file, "w", encoding="utf-8") as f:
                            json.dump(existing_data, f, indent=2, ensure_ascii=False)
                    except Exception as e:
                        print(f"Warning: Failed to update metadata for {shortcode}: {e}")
                continue

            _report(progress_cb, processed, total,
                    f"Processing {processed + 1}/{total}: {shortcode}")

            try:
                data = self.process_one(str(mp4), str(meta_file), thumbs_dir)
                with open(out_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                processed += 1
            except Exception as e:
                print(f"[Extractor] Warning: failed to process {shortcode}: {e}")
                processed += 1

        _report(progress_cb, total, total,
                f"Extraction complete — {processed} reels processed")
        return processed

    # ── Single reel ──────────────────────────────────────────────────────────
    def process_one(
        self,
        mp4_path: str,
        meta_path: str,
        thumbs_dir: Optional[str] = None,
    ) -> dict:
        """
        Extracts all text content from a single reel.
        Returns a consolidated dict ready for indexing.
        """
        mp4 = Path(mp4_path)
        shortcode = mp4.stem

        # ── Load metadata ────────────────────────────────────────────────────
        caption = ""
        meta = {}
        if Path(meta_path).exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            caption = meta.get("caption", "")

        # ── Whisper transcription ────────────────────────────────────────────
        transcript = ""
        try:
            model = _get_whisper(self.whisper_model)
            # `task="translate"` forces Whisper to translate non-English audio (like Hindi) directly to English text!
            result = model.transcribe(str(mp4), fp16=False, task="translate")
            transcript = result.get("text", "").strip()
        except Exception as e:
            print(f"[Extractor] Whisper failed on {shortcode}: {e}")

        # ── EasyOCR frame extraction ─────────────────────────────────────────
        screen_text = ""
        try:
            screen_text = self._extract_screen_text(str(mp4))
        except Exception as e:
            print(f"[Extractor] OCR failed on {shortcode}: {e}")

        # ── Extract thumbnail ────────────────────────────────────────────────
        thumb_filename = None
        if thumbs_dir:
            try:
                thumb_filename = self._extract_thumbnail(str(mp4), thumbs_dir, shortcode)
            except Exception as e:
                print(f"[Extractor] Thumbnail failed on {shortcode}: {e}")

        # ── Consolidate ──────────────────────────────────────────────────────
        combined_content = (
            f"CAPTION: {caption}\n"
            f"SPOKEN CONTENT: {transcript}\n"
            f"ON-SCREEN TEXT: {screen_text}"
        ).strip()

        return {
            "shortcode":    shortcode,
            "filename":     mp4.name,
            "content":      combined_content,
            "caption":      caption,
            "transcript":   transcript,
            "screen_text":  screen_text,
            "timestamp":    meta.get("timestamp", ""),
            "username":     meta.get("username", ""),
            "like_count":   meta.get("like_count", 0),
            "hashtags":     meta.get("hashtags", []),
            "thumbnail":    thumb_filename,
        }

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _extract_screen_text(self, mp4_path: str) -> str:
        """Samples frames and runs OCR on each sampled frame."""
        import cv2

        reader = _get_ocr()
        cap = cv2.VideoCapture(mp4_path)

        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_interval = max(1, int(fps * self.frame_interval_sec))

        all_text: list[str] = []
        frame_count = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_count % frame_interval == 0:
                try:
                    texts = reader.readtext(frame, detail=0, paragraph=True)
                    all_text.extend(texts)
                except Exception:
                    pass
            frame_count += 1

        cap.release()

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for t in all_text:
            t = t.strip()
            if t and t not in seen:
                seen.add(t)
                unique.append(t)

        return " ".join(unique)

    def _extract_thumbnail(self, mp4_path: str, thumbs_dir: str, shortcode: str) -> str:
        """Grabs the first frame of the video and saves it as a JPEG."""
        import cv2

        Path(thumbs_dir).mkdir(parents=True, exist_ok=True)
        thumb_name = f"{shortcode}.jpg"
        thumb_path = Path(thumbs_dir) / thumb_name

        if thumb_path.exists():
            return thumb_name

        cap = cv2.VideoCapture(mp4_path)
        ret, frame = cap.read()
        cap.release()

        if ret:
            cv2.imwrite(str(thumb_path), frame)
            return thumb_name

        return None


# ── Helpers ──────────────────────────────────────────────────────────────────
def _report(cb, current, total, msg=""):
    if cb:
        cb(current, total, msg)
    else:
        print(f"[Extract] {msg} ({current}/{total})")
