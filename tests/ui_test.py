"""Verify page switching (Settings / Generate / About), settings DPAPI save, and window render."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from localsub import settings as cfgmod
from localsub import ui

tmp = tempfile.mkdtemp()
cfgmod.CONFIG_DIR = tmp
cfgmod.CONFIG_PATH = os.path.join(tmp, "settings.json")

app = ui.App()
app.update()

for name in ("settings", "generate", "about", "settings"):
    app.show(name)
    app.update()
    mapped = {k: bool(p.winfo_ismapped()) for k, p in app.pages.items()}
    print(f"show({name!r}) -> mapped={mapped}")
    assert mapped[name] is True
    for k, v in mapped.items():
        if k != name:
            assert v is False

sp = app.pages["settings"]
sp.select_provider("Groq")
sp.key_var.set("gsk_test_123456")
sp.save()
app.update()

raw_disk = open(cfgmod.CONFIG_PATH, encoding="utf-8").read()
assert "gsk_test_123456" not in raw_disk and "dpapi:" in raw_disk
saved = cfgmod.load()
assert saved["providers"]["Groq"]["api_key"] == "gsk_test_123456"
assert saved["stt_provider"] == "Groq"
assert saved["translate_provider"] == "Groq"

sp_req_w = sp.winfo_reqwidth()
win_w = app.winfo_width()
print(f"Settings req_width={sp_req_w}, window_width={win_w}")
assert sp_req_w <= win_w

app.destroy()
print("UI TEST OK")
