"""Server side speech to text (faster-whisper) for browsers without their own,
mainly Firefox. Optional, raises Unavailable if it isn't installed.

Get the model once with:
    python speech_to_text.py download
"""

import os
import sys
import tempfile
import threading

MODEL = os.environ.get("WHISPER_MODEL", "small")
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "whisper")

# initial_prompt, so whisper spells the place and crop names right
HINTS = {
    "hi": "रुद्रपुर, किच्छा, हरिद्वार, विकासनगर, हल्द्वानी। गेहूं, धान, मक्का, चना, सरसों, बाजरा। "
          "क्विंटल। आज, कल, परसों। सुबह, दोपहर। हां, नहीं।",
    "bn": "রুদ্রপুর, কিচ্ছা, হরিদ্বার, বিকাশনগর, হলদোয়ানি। গম, ধান, ভুট্টা, ছোলা, সরষে, বাজরা। "
          "কুইন্টাল। আজ, আগামীকাল, পরশু। সকাল, দুপুর। হ্যাঁ, না।",
    "en": "Rudrapur, Kichha, Haridwar, Vikasnagar, Haldwani. Wheat, paddy, maize, gram, mustard, bajra. "
          "Quintals. Today, tomorrow. Morning, afternoon. Yes, no.",
}

_model = None
_lock = threading.Lock()


class Unavailable(Exception):
    pass


def get_model():
    global _model
    with _lock:
        if _model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError:
                raise Unavailable("faster-whisper is not installed")
            try:
                _model = WhisperModel(MODEL, device="cpu", compute_type="int8",
                                      download_root=MODEL_DIR, local_files_only=True)
            except Exception as e:
                raise Unavailable("the whisper %s model is not in %s (%s)" % (MODEL, MODEL_DIR, e))
        return _model


def warm():
    def load():
        try:
            get_model()
        except Unavailable:
            pass
    threading.Thread(target=load, daemon=True).start()


def transcribe(audio, lang="hi", suffix=".webm"):
    model = get_model()
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(audio)
        # vad_filter, otherwise whisper hallucinates words in the silence
        segments, _info = model.transcribe(path, language=lang if lang in HINTS else None,
                                           beam_size=5, vad_filter=True,
                                           initial_prompt=HINTS.get(lang))
        return " ".join(s.text.strip() for s in segments).strip()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


if __name__ == "__main__":
    if sys.argv[1:] != ["download"]:
        print(__doc__)
        sys.exit(1)
    from faster_whisper import WhisperModel
    WhisperModel(MODEL, device="cpu", compute_type="int8", download_root=MODEL_DIR)
    print("whisper %s model ready in %s" % (MODEL, MODEL_DIR))
