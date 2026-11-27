"""A small, independent Windows window for the frozen maintenance launcher."""
import logging
from tkinter import Button, Frame, Label, Tk, TclError
from tkinter.ttk import Progressbar
from threading import Thread

from .branding import APPLICATION_ICON, asset
from .update_state import read_json

LOG = logging.getLogger(__name__)


def show_progress(directory, run):
    window = Tk()
    window.title("Adaptive Resource Monitor Update")
    window.resizable(False, False)
    icon = asset(APPLICATION_ICON)
    if icon.is_file():
        window.iconbitmap(str(icon))
    background, text, amber = "#211c19", "#f0e5d7", "#e9b46b"
    window.configure(background=background)
    panel = Frame(window, background=background, padx=20, pady=16)
    panel.pack(fill="both", expand=True)
    Label(panel, text="Adaptive Resource Monitor", font=("Georgia", 18, "bold"),
          background=background, foreground=amber, anchor="w").pack(fill="x")
    Label(panel, text="Design Creations", font=("Segoe UI", 10), background=background,
          foreground=text, anchor="w").pack(fill="x", pady=(0, 12))
    message = Label(panel, text="Preparing update…", wraplength=440, justify="left",
                    background=background, foreground=text, font=("Segoe UI", 11), anchor="w")
    message.pack(fill="x", pady=(0, 12))
    progress = Progressbar(panel, mode="indeterminate", length=440)
    progress.pack(fill="x")
    progress.start(15)
    window.protocol("WM_DELETE_WINDOW", lambda: None)
    result = []

    def perform():
        try:
            result.append((run(), ""))
        except Exception as exc:
            LOG.exception("Maintenance reporting failed")
            result.append((1, f"{exc}\nDiagnostics: {directory / 'maintenance.log'}"))

    def refresh():
        status = read_json(directory / "status.json", {})
        if text := status.get("message"):
            message.configure(text=text)
        if not result:
            window.after(140, refresh)
            return
        progress.stop()
        progress.pack_forget()
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        code, error = result[0]
        if error:
            message.configure(text=error)
        if code or status.get("state") == "rolled_back":
            Button(panel, text="Close", command=window.destroy).pack(anchor="e")
        else:
            window.after(2400, window.destroy)

    worker = Thread(target=perform, name="ARM update installation")
    worker.start()
    window.after(140, refresh)
    try:
        window.mainloop()
    except TclError:
        pass
    worker.join()
    return result[0][0]
