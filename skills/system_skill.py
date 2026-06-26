"""System control skill: open apps, open websites/search, basic file ops.

Destructive operations (delete) return a SkillResult with a `pending` callable
so the router can require a spoken confirmation before anything happens.

Platform handling is isolated in the small helpers near the top so Mac/Linux
support can be added later without touching the action logic. Defaults assume
Windows.
"""
import logging
import os
import platform
import subprocess
import urllib.parse
import webbrowser

import config
from skills.base import SkillResult

log = logging.getLogger("jarvis.system")

_IS_WINDOWS = platform.system() == "Windows"

# Tool schema given to Claude for system-control intent + parameter extraction.
SYSTEM_CONTROL_TOOL = {
    "name": "system_control",
    "description": (
        "Control the user's computer: open applications, open websites, search "
        "the web, and do basic file operations (list a folder's contents, "
        "create a folder, open a file, or delete a file/folder). Use this for "
        "requests like 'open Chrome', 'open youtube.com', 'search Google for "
        "cat videos', 'list files in Downloads', 'make a folder called notes', "
        "'open report.txt', 'delete old.txt'. Not for music or chit-chat."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "open_app",
                    "open_website",
                    "web_search",
                    "list_files",
                    "create_folder",
                    "open_file",
                    "delete_path",
                ],
                "description": "The system action to perform.",
            },
            "app_name": {
                "type": "string",
                "description": "For 'open_app': the app nickname, e.g. 'Chrome', 'VS Code'.",
            },
            "url": {
                "type": "string",
                "description": "For 'open_website': the site, e.g. 'youtube.com'.",
            },
            "query": {
                "type": "string",
                "description": "For 'web_search': what to search the web for.",
            },
            "path": {
                "type": "string",
                "description": (
                    "For file actions: the folder/file path or a known folder "
                    "nickname like 'Downloads'. For 'create_folder' this is the "
                    "new folder's path or name."
                ),
            },
        },
        "required": ["action"],
    },
}


# --- platform helpers -----------------------------------------------------
def _launch(command):
    """Launch an executable/command. Returns True on success."""
    try:
        if _IS_WINDOWS:
            # os.startfile resolves PATH commands and file associations.
            os.startfile(command)  # noqa: S606 - intended app launch
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", command])
        else:
            subprocess.Popen([command])
        return True
    except FileNotFoundError:
        return False
    except OSError as e:
        log.warning("Launch failed for %s: %s", command, e)
        return False


def _open_in_browser(url):
    webbrowser.open(url)


class SystemSkill:
    def __init__(self):
        cfg = config.load_system_config()
        # Normalize app keys to lowercase for loose matching.
        self.apps = {k.lower(): v for k, v in cfg.get("apps", {}).items()}
        self.folders = {k.lower(): v for k, v in cfg.get("folders", {}).items()}
        log.info(
            "System skill initialized (%d apps, %d folder shortcuts).",
            len(self.apps),
            len(self.folders),
        )

    # -- dispatch ----------------------------------------------------------
    def handle(self, tool_input):
        """Route a system_control tool call. Returns SkillResult. Never raises."""
        action = tool_input.get("action")
        try:
            if action == "open_app":
                return self.open_app(tool_input.get("app_name"))
            if action == "open_website":
                return self.open_website(tool_input.get("url"))
            if action == "web_search":
                return self.web_search(tool_input.get("query"))
            if action == "list_files":
                return self.list_files(tool_input.get("path"))
            if action == "create_folder":
                return self.create_folder(tool_input.get("path"))
            if action == "open_file":
                return self.open_file(tool_input.get("path"))
            if action == "delete_path":
                return self.delete_path(tool_input.get("path"))
            return SkillResult("I'm not sure how to do that on your computer.")
        except Exception as e:  # pragma: no cover - graceful catch-all
            log.warning("System action error: %s", e)
            return SkillResult("Something went wrong with that system command.")

    # -- apps & web --------------------------------------------------------
    def open_app(self, name):
        if not name:
            return SkillResult("Which app would you like me to open?")
        key = name.strip().lower()
        # Exact, then loose (substring) match against configured nicknames.
        target = self.apps.get(key)
        if target is None:
            for nick, path in self.apps.items():
                if key in nick or nick in key:
                    target = path
                    break
        # Fall back to trying the spoken name as a bare command.
        command = target or key
        if _launch(command):
            return SkillResult(f"Opening {name}.")
        if target is None:
            return SkillResult(
                f"I don't have {name} configured, and couldn't launch it "
                "directly. Add it to system_config.json with its path."
            )
        return SkillResult(f"I couldn't open {name}. Check its path in system_config.json.")

    def open_website(self, url):
        if not url:
            return SkillResult("Which website should I open?")
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        _open_in_browser(url)
        return SkillResult(f"Opening {url}.")

    def web_search(self, query):
        if not query:
            return SkillResult("What would you like me to search for?")
        q = urllib.parse.quote_plus(query)
        _open_in_browser(f"https://www.google.com/search?q={q}")
        return SkillResult(f"Searching Google for {query}.")

    # -- file operations ---------------------------------------------------
    def _resolve(self, path):
        """Resolve a folder nickname or expand user/env vars in a path."""
        if not path:
            return None
        key = path.strip().lower()
        if key in self.folders:
            return self.folders[key]
        return os.path.expandvars(os.path.expanduser(path.strip()))

    def list_files(self, path):
        target = self._resolve(path)
        if not target:
            return SkillResult("Which folder should I list?")
        if not os.path.isdir(target):
            return SkillResult(f"I couldn't find a folder at {path}.")
        entries = sorted(os.listdir(target))
        if not entries:
            return SkillResult(f"{path} is empty.")
        shown = entries[:10]
        speech = f"{len(entries)} items in {path}. " + ", ".join(shown)
        if len(entries) > len(shown):
            speech += f", and {len(entries) - len(shown)} more"
        return SkillResult(speech + ".")

    def create_folder(self, path):
        target = self._resolve(path)
        if not target:
            return SkillResult("What should I name the folder?")
        if os.path.exists(target):
            return SkillResult(f"{path} already exists.")
        os.makedirs(target, exist_ok=True)
        return SkillResult(f"Created folder {path}.")

    def open_file(self, path):
        target = self._resolve(path)
        if not target:
            return SkillResult("Which file should I open?")
        if not os.path.exists(target):
            return SkillResult(f"I couldn't find {path}.")
        if _launch(target):
            return SkillResult(f"Opening {path}.")
        return SkillResult(f"I couldn't open {path}.")

    def delete_path(self, path):
        target = self._resolve(path)
        if not target:
            return SkillResult("Which file or folder should I delete?")
        if not os.path.exists(target):
            return SkillResult(f"I couldn't find {path} to delete.")

        kind = "folder" if os.path.isdir(target) else "file"

        def _do_delete():
            try:
                if os.path.isdir(target):
                    import shutil

                    shutil.rmtree(target)
                else:
                    os.remove(target)
                return SkillResult(f"Deleted the {kind} {path}.")
            except Exception as e:  # pragma: no cover
                log.warning("Delete failed: %s", e)
                return SkillResult(f"I couldn't delete {path}.")

        # Destructive: hand back a pending action requiring confirmation.
        return SkillResult(
            speech=f"Are you sure you want to delete the {kind} {path}? Say yes to confirm.",
            pending=_do_delete,
        )
