"""Code generation skill: generate code on request and open it in an editor.

Flow: Claude generates clean code -> we pick a filename/extension -> save it to
./jarvis_generated_code/ (never overwriting) -> open it in VS Code (or the OS
default editor). The generated code is NEVER executed — only written and opened.
"""
import logging
import os
import platform
import re
import shutil
import subprocess

import config
from skills.base import SkillResult

log = logging.getLogger("jarvis.code")

OUTPUT_DIR = "jarvis_generated_code"

# Tool the router exposes for code-generation intent + parameter extraction.
CODE_GENERATION_TOOL = {
    "name": "code_generation",
    "description": (
        "Generate a NEW piece of code/file and open it in the editor. Use this "
        "ONLY when the user wants new code written to a file — e.g. 'write me a "
        "Python script that renames files', 'create a Java function for "
        "bubble sort', 'write a webpage in HTML', 'make a script that scrapes a "
        "site'. Do NOT use it for explaining code, debugging help, or "
        "questions like 'what does this error mean' — those are general chat."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "request": {
                "type": "string",
                "description": (
                    "The full description of the code to generate, e.g. "
                    "'a Python script that downloads images from a URL'."
                ),
            },
            "language": {
                "type": "string",
                "description": (
                    "The programming language requested (e.g. 'python', "
                    "'javascript', 'html', 'java'). Infer it if implied."
                ),
            },
            "filename": {
                "type": "string",
                "description": (
                    "Optional desired base filename WITHOUT extension if the "
                    "user named one (e.g. 'scraper'). Omit if not specified."
                ),
            },
        },
        "required": ["request"],
    },
}

# language -> file extension
_EXT = {
    "python": "py", "py": "py",
    "javascript": "js", "js": "js", "node": "js",
    "typescript": "ts", "ts": "ts",
    "html": "html", "css": "css",
    "java": "java",
    "c": "c", "c++": "cpp", "cpp": "cpp",
    "c#": "cs", "csharp": "cs",
    "go": "go", "golang": "go",
    "rust": "rs", "rs": "rs",
    "ruby": "rb", "rb": "rb",
    "php": "php",
    "bash": "sh", "shell": "sh", "sh": "sh",
    "sql": "sql",
    "kotlin": "kt", "swift": "swift",
    "r": "r", "json": "json", "yaml": "yaml", "yml": "yaml",
}

_GEN_SYSTEM_PROMPT = (
    "You are a code generator. Output ONLY clean, working, complete code in the "
    "language requested, with brief, helpful inline comments. Do NOT include any "
    "conversational text, explanations, or apologies before or after the code. "
    "Do NOT wrap the code in markdown fences. Just return the raw source code."
)


class CodeSkill:
    def __init__(self):
        from anthropic import Anthropic

        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file."
            )
        self.client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.output_dir = os.path.abspath(OUTPUT_DIR)
        log.info("Code generation skill initialized (-> %s/).", OUTPUT_DIR)

    def handle(self, tool_input):
        """Generate code, save it, open it. Returns SkillResult. Never raises."""
        req = (tool_input or {}).get("request", "").strip()
        if not req:
            return SkillResult("What would you like me to write?")
        language = (tool_input.get("language") or "").strip().lower()

        log.info("⌨️  Generating code: %s", req)
        try:
            code = self._generate(req, language)
        except Exception as e:  # pragma: no cover - API/network issues
            log.warning("Code generation failed: %s", e)
            return SkillResult("I had trouble generating that code. Try again in a moment.")

        if not code:
            return SkillResult("I couldn't generate anything for that, sorry.")

        ext = _EXT.get(language, self._guess_ext(code))
        base = self._base_name(tool_input.get("filename"), req, ext)
        path = self._unique_path(base, ext)

        try:
            os.makedirs(self.output_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
        except OSError as e:
            log.warning("Could not write file: %s", e)
            return SkillResult("I generated the code but couldn't save the file.")

        log.info("💾 Saved %s", path)
        opened_in = self._open_in_editor(path)

        name = os.path.basename(path)
        if opened_in == "vscode":
            return SkillResult(f"Done, I've opened {name} in VS Code.")
        if opened_in == "editor":
            return SkillResult(f"Done, I've saved {name} and opened it in your editor.")
        return SkillResult(
            f"Done, I've saved {name} in the {OUTPUT_DIR} folder, "
            "but couldn't open an editor automatically."
        )

    # -- generation --------------------------------------------------------
    def _generate(self, request, language):
        user = request if not language else f"{request}\n\nLanguage: {language}"
        message = self.client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2000,  # code can be long; this is not a spoken reply
            system=_GEN_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            b.text for b in message.content if getattr(b, "type", None) == "text"
        ).strip()
        return _strip_fences(text)

    # -- filename handling -------------------------------------------------
    def _base_name(self, given, request, ext):
        if given:
            return _slug(given) or "generated"
        # Derive a sensible name from the request's key nouns.
        words = re.findall(r"[a-zA-Z]+", request.lower())
        stop = {
            "write", "me", "a", "an", "the", "create", "make", "script",
            "program", "function", "that", "does", "for", "in", "to", "with",
            "code", "please", "some", "of", "and", "python", "java",
            "javascript", "html", "webpage", "page", "file", "generate",
        }
        keep = [w for w in words if w not in stop and len(w) > 2][:2]
        if keep:
            return "_".join(keep)
        return {"html": "page", "css": "styles"}.get(ext, "script")

    def _unique_path(self, base, ext):
        """Return a non-existing path, appending _1, _2, ... if needed."""
        candidate = os.path.join(self.output_dir, f"{base}.{ext}")
        if not os.path.exists(candidate):
            return candidate
        i = 1
        while True:
            candidate = os.path.join(self.output_dir, f"{base}_{i}.{ext}")
            if not os.path.exists(candidate):
                return candidate
            i += 1

    def _guess_ext(self, code):
        head = code[:200].lower()
        if "<html" in head or "<!doctype html" in head:
            return "html"
        if "def " in code or "import " in code:
            return "py"
        if "function " in code or "const " in code or "=>" in code:
            return "js"
        return "txt"

    # -- opening (never executes) -----------------------------------------
    def _open_in_editor(self, path):
        """Open the file in VS Code, else the OS default editor. Never runs it."""
        code_cli = shutil.which("code")
        if code_cli:
            try:
                subprocess.Popen([code_cli, path])
                return "vscode"
            except OSError as e:
                log.warning("VS Code launch failed: %s", e)

        # Fall back to the OS default handler for the file.
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(path)  # noqa: S606 - opening a text file, not running
            elif system == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            return "editor"
        except OSError as e:
            log.warning("Default editor launch failed: %s", e)
            return None


def _strip_fences(text):
    """Remove a leading/trailing markdown code fence if the model added one."""
    fence = re.match(r"^```[a-zA-Z0-9+#]*\n(.*)\n```$", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text


def _slug(name):
    return re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip()).strip("_").lower()
