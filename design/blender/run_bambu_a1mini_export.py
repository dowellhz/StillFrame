import runpy
import sys
import traceback

LOG = "/Volumes/ACASIS/e-ink/design/bambu-a1mini-export.log"
SCRIPT = "/Volumes/ACASIS/e-ink/design/blender/export_bambu_a1mini_parts.py"

with open(LOG, "w", buffering=1) as log:
    sys.stdout = log
    sys.stderr = log
    try:
        print("Starting four-plate Stillframe export")
        runpy.run_path(SCRIPT, run_name="__main__")
        print("Export complete")
    except Exception:
        traceback.print_exc(file=log)
        raise
