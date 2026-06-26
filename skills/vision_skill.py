"""Vision skill: capture a single webcam frame (or load a file) and analyze it.

On-demand only — triggered by a voice command, never continuous/always-on. The
camera is opened, used for one frame, and released immediately.
"""
import base64
import logging
import os
import time

import config
from skills.base import SkillResult

log = logging.getLogger("jarvis.vision")

# Tool the router exposes for vision-request intent + parameter extraction.
VISION_REQUEST_TOOL = {
    "name": "vision_request",
    "description": (
        "Look at something through the webcam (or an image file) and answer "
        "about it. Trigger for 'look at this', 'what does this say', 'can you "
        "see this', 'read this page', or 'help me with this problem' when the "
        "user is clearly showing something physical to the camera. Also use it "
        "when the user references an image file to look at."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "request": {
                "type": "string",
                "description": (
                    "The user's spoken request about what they're showing, "
                    "e.g. 'what does this say', 'help me solve this problem'."
                ),
            },
            "image_path": {
                "type": "string",
                "description": (
                    "Path to an existing image file IF the user asked to look "
                    "at a file (e.g. 'look at the image in photo.jpg'). Omit to "
                    "capture from the webcam."
                ),
            },
        },
        "required": ["request"],
    },
}

_DIRECT_SYSTEM_PROMPT = (
    "You are Jarvis looking at an image the user is showing you. Answer their "
    "request concisely and directly — they may be holding a book or page in an "
    "awkward position, so keep it short and spoken-friendly. No markdown."
)

# Appended to the tutoring prompt when analyzing an image in study mode.
_STUDY_VISION_NOTE = (
    "\n\nThe user is showing you something (likely a homework problem or page). "
    "Stay in your tutoring role: if it's a problem, lean toward a Socratic hint "
    "or leading question rather than reading out the full solution — unless they "
    "explicitly ask for the direct answer. Keep it concise; they're holding "
    "something up to the camera."
)


class VisionSkill:
    def __init__(self, notify=None):
        """notify: optional callable(str) to speak an interim cue (tts.speak)."""
        import cv2  # noqa: F401 - fail fast here if OpenCV is missing

        from anthropic import Anthropic

        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file."
            )
        self.client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.notify = notify
        log.info("Vision skill initialized.")

    def handle(self, tool_input, study_mode=False, tutor_system_prompt=None):
        """Capture/load an image and analyze it. Returns SkillResult. Never raises."""
        ti = tool_input or {}
        request = (ti.get("request") or "").strip()
        image_path = (ti.get("image_path") or "").strip()

        try:
            if image_path:
                jpg = self._load_file(image_path)
                if jpg is None:
                    return SkillResult(f"I couldn't open the image at {image_path}.")
            else:
                jpg = self._capture_webcam()
                if isinstance(jpg, SkillResult):  # camera error -> spoken message
                    return jpg
        except Exception as e:  # pragma: no cover
            log.warning("Vision capture error: %s", e)
            return SkillResult("Something went wrong getting the image.")

        try:
            return self._analyze(jpg, request, study_mode, tutor_system_prompt)
        except Exception as e:  # pragma: no cover
            log.warning("Vision analysis error: %s", e)
            return SkillResult("I got the image but had trouble analyzing it.")

    # -- image acquisition -------------------------------------------------
    def _capture_webcam(self):
        import cv2

        # Heads-up + brief pause so the user can position what they're showing.
        if self.notify:
            self.notify("Okay, hold it steady.")
        log.info("📸 Opening webcam...")
        cap = cv2.VideoCapture(config.WEBCAM_INDEX)
        if not cap.isOpened():
            cap.release()
            return SkillResult(
                "I couldn't access the webcam. Make sure one is connected and "
                "that this app has camera permission."
            )

        try:
            # Warm up / let the user position during the delay (discard frames).
            deadline = time.time() + config.CAPTURE_DELAY_SECONDS
            frame = None
            ok = False
            while time.time() < deadline:
                ok, frame = cap.read()
            if not ok or frame is None:
                # One more attempt after the loop.
                ok, frame = cap.read()
            if not ok or frame is None:
                return SkillResult(
                    "The webcam opened but I couldn't grab a clear frame. Try again."
                )
            ok, buf = cv2.imencode(".jpg", frame)
            if not ok:
                return SkillResult("I couldn't encode the captured image.")
            jpg = buf.tobytes()
        finally:
            cap.release()

        self._save_temp(jpg)
        log.info("📸 Captured frame (%d bytes).", len(jpg))
        return jpg

    def _load_file(self, path):
        path = os.path.expanduser(os.path.expandvars(path))
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            return f.read()

    def _save_temp(self, jpg):
        try:
            os.makedirs(config.JARVIS_TEMP_DIR, exist_ok=True)
            with open(config.CAPTURE_PATH, "wb") as f:
                f.write(jpg)
        except OSError as e:  # pragma: no cover
            log.warning("Could not save temp capture: %s", e)

    def _cleanup_temp(self):
        if config.KEEP_CAPTURES:
            return
        try:
            if os.path.exists(config.CAPTURE_PATH):
                os.remove(config.CAPTURE_PATH)
                log.info("🧹 Deleted temp capture.")
        except OSError as e:  # pragma: no cover
            log.warning("Could not delete temp capture: %s", e)

    # -- analysis ----------------------------------------------------------
    def _analyze(self, jpg, request, study_mode, tutor_system_prompt):
        log.info("👁️  Analyzing image%s...", " [study]" if study_mode else "")
        if study_mode and tutor_system_prompt:
            system = tutor_system_prompt + _STUDY_VISION_NOTE
            max_tokens = config.STUDY_MAX_TOKENS
        else:
            system = _DIRECT_SYSTEM_PROMPT
            max_tokens = config.CLAUDE_MAX_TOKENS

        b64 = base64.standard_b64encode(jpg).decode("ascii")
        context = (
            f"The user showed me this and said: {request}"
            if request else "The user showed me this."
        )
        message = self.client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": context},
                ],
            }],
        )
        answer = "".join(
            b.text for b in message.content if getattr(b, "type", None) == "text"
        ).strip()

        # Clean up the temp capture regardless of result.
        self._cleanup_temp()

        return SkillResult(answer or "I couldn't make out anything useful in that image.")
