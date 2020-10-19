from pathlib import Path
from subprocess import run, Popen, PIPE

files = [p for p in Path("./vector").iterdir() if p.is_file()]

actions = ""
for file in files:
    actions += "file-open:{:s}; export-filename:raster\\{:s}.png; export-dpi:96; export-do;\n".format(str(file), file.stem)

process = Popen([
    "inkscape",
    "--shell"
], stdin=PIPE, stdout=PIPE, stderr=PIPE)

out, err = process.communicate(input=actions.encode("utf-8"), timeout=10)

if out:
    print(out.decode("utf-8"))

if err:
    print(err.decode("utf-8"))