from __future__ import annotations

import os
import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_VALUE_NAME = "YouTubeAutomatizador"


def set_startup(enabled: bool) -> None:
    if os.name != "nt":
        raise OSError("El inicio automático del sistema solo está disponible en Windows.")

    import winreg

    if enabled:
        executable = Path(sys.executable)
        if getattr(sys, "frozen", False):
            command = f'"{executable}"'
        else:
            pythonw = executable.with_name("pythonw.exe")
            runner = pythonw if pythonw.exists() else executable
            command = f'"{runner}" -m youtube_automatizador'
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, APP_VALUE_NAME, 0, winreg.REG_SZ, command)
        return

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, APP_VALUE_NAME)
    except FileNotFoundError:
        pass
