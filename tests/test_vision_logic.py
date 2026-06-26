"""Vision skill logic test — offline (no cv2, webcam, or API key).

    python tests/test_vision_logic.py

Bypasses __init__ (so OpenCV/Anthropic aren't needed) and fakes the Claude
client to test file loading, the analyze path, study-mode prompt selection, and
temp-capture cleanup. The live webcam path is tested on your machine via
`python main.py` ("look at this").
"""
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from skills.vision_skill import VisionSkill, _STUDY_VISION_NOTE  # noqa: E402

FAILS = []
def check(label, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILS.append(label)


class Block:
    def __init__(self, **kw): self.__dict__.update(kw)


class FakeClient:
    def __init__(self): self.last = None
    def _create(self, **kw):
        self.last = kw
        return Block(content=[Block(type="text", text="It says hello.")])
    @property
    def messages(self): return types.SimpleNamespace(create=self._create)


def make_skill():
    v = object.__new__(VisionSkill)  # skip __init__ (no cv2 / anthropic)
    v.client = FakeClient()
    v.notify = None
    return v


def main():
    tmp = Path(tempfile.mkdtemp())
    config.JARVIS_TEMP_DIR = str(tmp)
    config.CAPTURE_PATH = str(tmp / "capture.jpg")
    config.KEEP_CAPTURES = False

    v = make_skill()

    # File loading
    img = tmp / "photo.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0fakejpegdata")
    check("loads existing file", v._load_file(str(img)) is not None)
    check("missing file -> None", v._load_file(str(tmp / "nope.jpg")) is None)

    # Direct (non-study) analysis + temp cleanup
    Path(config.CAPTURE_PATH).write_bytes(b"temp")
    out = v.handle({"request": "what does this say", "image_path": str(img)})
    check("returns spoken analysis", out.speech == "It says hello.")
    check("uses direct prompt when not studying",
          "tutoring" not in v.client.last["system"].lower())
    check("temp capture deleted by default",
          not os.path.exists(config.CAPTURE_PATH))

    # Study-mode analysis uses tutor prompt + study note
    out2 = v.handle({"request": "solve this", "image_path": str(img)},
                    study_mode=True, tutor_system_prompt="TUTOR-PROMPT")
    check("study mode uses tutor prompt",
          v.client.last["system"].startswith("TUTOR-PROMPT"))
    check("study mode appends vision note",
          _STUDY_VISION_NOTE.strip()[:20] in v.client.last["system"])

    # KEEP_CAPTURES=true preserves the file
    config.KEEP_CAPTURES = True
    Path(config.CAPTURE_PATH).write_bytes(b"temp")
    v.handle({"request": "x", "image_path": str(img)})
    check("KEEP_CAPTURES keeps the temp file",
          os.path.exists(config.CAPTURE_PATH))

    # Missing image path -> graceful spoken error
    config.KEEP_CAPTURES = False
    out3 = v.handle({"request": "look", "image_path": str(tmp / "gone.jpg")})
    check("missing image -> spoken error",
          "couldn't open" in out3.speech.lower())

    print(f"\n{'ALL PASS' if not FAILS else f'{len(FAILS)} FAILURES: {FAILS}'}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
