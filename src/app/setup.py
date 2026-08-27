import sys
from cx_Freeze import setup, Executable

base = None
if sys.platform == "win32":
    base = "Win32GUI"

executables = [
    Executable("Map-Concator-App.py", base=base, icon='media/dev_logo.ico')
]

build_options = {
    "packages" : [],
    "include_files": ["media/", 'core/', 'kataho/', 'utils/']
}

setup(
    name="Map-Concator-App",
    version="0.0.8",
    description="Map-Concator-App",
    options={"build_exe":build_options},
    executables=executables
)