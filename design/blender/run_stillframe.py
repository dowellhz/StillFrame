import runpy
import sys
import traceback

LOG = "/Volumes/ACASIS/e-ink/design/blender-run.log"
SCRIPT = "/Volumes/ACASIS/e-ink/design/blender/stillframe_protector.py"

with open(LOG, "w", buffering=1) as log:
    sys.stdout = log
    sys.stderr = log
    try:
        print("Starting Stillframe Blender render")
        runpy.run_path(SCRIPT, run_name="__main__")
        print("Render complete")
    except Exception:
        traceback.print_exc(file=log)
        raise
