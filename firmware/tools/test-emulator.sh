#!/bin/sh
# Executes real ESP32-S3 code. Test images must not be flashed onto hardware.
set -eu
SF_ROOT=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
cd "$SF_ROOT"
restore_release() {
  SF_TEST_EXIT=$?
  trap - EXIT
  python3 firmware/tools/variant.py release
  if ! firmware/tools/idf.sh build merge-bin > firmware/test-results/release-build.log 2>&1; then
    tail -35 firmware/test-results/release-build.log
    exit 1
  fi
  exit "$SF_TEST_EXIT"
}
mkdir -p firmware/test-assets firmware/test-results
trap restore_release EXIT
python3 firmware/tools/ensure-sdk.py
python3 firmware/tools/test-dhcp-parser.py
node firmware/tools/web-test.mjs
python3 firmware/tools/variant.py runtime
firmware/tools/idf.sh build merge-bin > firmware/test-results/runtime-build.log 2>&1
cp firmware/build/Stillframe.elf firmware/test-assets/runtime.elf
cp firmware/build/merged-binary.bin firmware/test-assets/runtime-flash.bin
python3 emulator/run.py firmware/test-assets/runtime-flash.bin --name stillframe-runtime-regression --fresh --ap-password 12345678 --elf firmware/test-assets/runtime.elf --seconds 600 --exit-on "REAL DRIVER RUNTIME TEST PASSED" > firmware/test-results/runtime-regression.log 2>&1
python3 - <<'PYTEST'
from pathlib import Path
s=Path('firmware/test-results/runtime-regression.log').read_text()
assert 'REAL DRIVER RUNTIME TEST PASSED' in s
assert 'FAIL:' not in s and 'Task watchdog got triggered' not in s
assert 'bus quarantined until reboot' in s
print('PASS: real SPI timeout releases worker; HTTP remains responsive beyond 90 seconds')
PYTEST
python3 firmware/tools/make-recovery-fixture.py
python3 emulator/run.py firmware/test-assets/recovery-flash.bin --name stillframe-recovery --fresh --ap-password 12345678 --elf firmware/test-assets/runtime.elf --seconds 180 --exit-on "RECOVERY PORTAL TEST PASSED" > firmware/test-results/recovery.log 2>&1
python3 - <<'RECOVERY'
from pathlib import Path
s=Path('firmware/test-results/recovery.log').read_text()
assert 'RECOVERY PORTAL TEST PASSED' in s
assert 'FAIL:' not in s
print('PASS: corrupt configuration boots a recovery portal and refuses to overwrite NVS')
RECOVERY
python3 firmware/tools/make-startup-fixture.py
python3 emulator/run.py firmware/test-assets/startup-stall-flash.bin --name stillframe-startup-stall --fresh --ap-password 12345678 --elf firmware/test-assets/runtime.elf --seconds 240 --exit-on "STARTUP WORKER ROLLBACK TEST PASSED" > firmware/test-results/startup-stall.log 2>&1
python3 - <<'STARTUP'
from pathlib import Path
s=Path('firmware/test-results/startup-stall.log').read_text()
assert 'STARTUP WORKER ROLLBACK TEST PASSED' in s
assert 'startup worker not ready; rolling back' in s
assert 'FAIL:' not in s
print('PASS: a stuck startup worker cannot qualify OTA firmware; prior slot recovers')
STARTUP
python3 emulator/run.py firmware/test-assets/slow-setup-flash.bin --name stillframe-slow-setup --fresh --ap-password 12345678 --elf firmware/test-assets/runtime.elf --seconds 120 --exit-on "SLOW SETUP OTA TEST PASSED" > firmware/test-results/slow-setup.log 2>&1
python3 - <<'SLOWSETUP'
from pathlib import Path
s=Path('firmware/test-results/slow-setup.log').read_text()
assert 'SLOW SETUP OTA TEST PASSED' in s
assert 'INTENTIONAL 40-SECOND SETUP DISPLAY' in s
assert 'rolling back unverified app' not in s and 'FAIL:' not in s
print('PASS: a 40-second first setup display cannot make valid OTA firmware roll back')
SLOWSETUP
python3 emulator/run.py firmware/test-assets/early-crash-flash.bin --name stillframe-early-crash --fresh --ap-password 12345678 --elf firmware/test-assets/runtime.elf --allow-panic-reboot --seconds 180 --exit-on "EARLY RESET SAFE MODE TEST PASSED" > firmware/test-results/early-crash.log 2>&1
python3 - <<'EARLYCRASH'
from pathlib import Path
s=Path('firmware/test-results/early-crash.log').read_text()
assert s.count('INTENTIONAL EARLY WORKER CRASH') == 3
assert 'EARLY RESET SAFE MODE TEST PASSED' in s
assert 'three consecutive early resets; safe mode active' in s
assert 'Task watchdog got triggered' not in s and 'FAIL:' not in s
print('PASS: three early crashes enter managed safe mode instead of rebooting forever')
EARLYCRASH
python3 emulator/run.py firmware/test-assets/safe-ota-flash.bin --name stillframe-safe-ota --fresh --ap-password 12345678 --elf firmware/test-assets/runtime.elf --allow-panic-reboot --seconds 240 --exit-on "SAFE MODE OTA RECOVERY TEST PASSED" > firmware/test-results/safe-ota.log 2>&1
python3 - <<'SAFEOTA'
from pathlib import Path
s=Path('firmware/test-results/safe-ota.log').read_text()
assert s.count('INTENTIONAL SAFE-MODE PRE-OTA CRASH') == 3
assert 'three consecutive early resets; safe mode active' in s
assert 'SAFE MODE OTA WRITTEN; CLEARING OLD BOOT FAILURES' in s
assert 'SAFE MODE OTA RECOVERY TEST PASSED' in s
assert 'rolling back unverified app' not in s and 'FAIL:' not in s
print('PASS: OTA launched from safe mode clears old failures and becomes valid')
SAFEOTA
python3 emulator/run.py firmware/test-assets/panel-rollback-flash.bin --name stillframe-panel-rollback --fresh --ap-password 12345678 --elf firmware/test-assets/runtime.elf --seconds 180 --exit-on "PENDING OTA PANEL ROLLBACK TEST PASSED" > firmware/test-results/panel-rollback.log 2>&1
python3 - <<'PANELROLLBACK'
from pathlib import Path
s=Path('firmware/test-results/panel-rollback.log').read_text()
assert 'INTENTIONAL PENDING-OTA PANEL FAILURE' in s
assert 'previously healthy panel failed during first OTA cycle; rolling back app' in s
assert 'PENDING OTA PANEL ROLLBACK TEST PASSED' in s
assert 'FAIL:' not in s
print('PASS: a pending image rolls back when a previously healthy panel fails')
PANELROLLBACK
python3 emulator/run.py firmware/test-assets/panel-prebroken-flash.bin --name stillframe-panel-prebroken --fresh --ap-password 12345678 --elf firmware/test-assets/runtime.elf --seconds 180 --exit-on "PREEXISTING PANEL OTA ACCEPTANCE TEST PASSED" > firmware/test-results/panel-prebroken.log 2>&1
python3 - <<'PANELPREBROKEN'
from pathlib import Path
s=Path('firmware/test-results/panel-prebroken.log').read_text()
assert 'INTENTIONAL PREEXISTING PANEL FAILURE' in s
assert 'panel was already unverified or unhealthy; keep OTA image' in s
assert 'PREEXISTING PANEL OTA ACCEPTANCE TEST PASSED' in s
assert 'rolling back app' not in s and 'FAIL:' not in s
print('PASS: a preexisting panel fault does not block a repair firmware')
PANELPREBROKEN
python3 emulator/run.py firmware/test-assets/power-reset-flash.bin --name stillframe-power-reset --fresh --ap-password 12345678 --elf firmware/test-assets/runtime.elf --allow-panic-reboot --seconds 180 --exit-on "POWER RESET DISPLAY QUARANTINE TEST PASSED" > firmware/test-results/power-reset.log 2>&1
python3 - <<'POWERRESET'
from pathlib import Path
s=Path('firmware/test-results/power-reset.log').read_text()
assert s.count('INTENTIONAL RESET DURING HIGH-VOLTAGE REFRESH') == 3
assert 'three refresh resets detected; automatic display disabled' in s
assert 'POWER RESET DISPLAY QUARANTINE TEST PASSED' in s
assert 'FAIL:' not in s
print('PASS: three resets during refresh stop further automatic display attempts')
POWERRESET
python3 emulator/run.py firmware/test-assets/safe-retry-flash.bin --name stillframe-safe-retry --fresh --ap-password 12345678 --elf firmware/test-assets/runtime.elf --allow-panic-reboot --seconds 180 --exit-on "SAFE MODE AUTOMATIC RETRY TEST PASSED" > firmware/test-results/safe-retry.log 2>&1
python3 - <<'SAFERETRY'
from pathlib import Path
s=Path('firmware/test-results/safe-retry.log').read_text()
assert s.count('INTENTIONAL SAFE-RETRY PRE-STABLE CRASH') == 3
assert 'three consecutive early resets; safe mode active' in s
assert 'SAFE RETRY WRITE OPERATION HELD' in s
assert 'SAFE RETRY WRITE OPERATION RELEASED' in s
assert s.index('SAFE RETRY WRITE OPERATION RELEASED') < s.index('SAFE MODE AUTOMATIC RETRY TEST PASSED')
assert 'SAFE MODE AUTOMATIC RETRY TEST PASSED' in s
assert 'FAIL:' not in s
print('PASS: safe-mode retry waits for an active write, then retries normally')
SAFERETRY
python3 firmware/tools/variant.py panic
firmware/tools/idf.sh build > firmware/test-results/panic-build.log 2>&1
cp firmware/build/Stillframe.bin firmware/test-assets/panic.bin
python3 firmware/tools/variant.py test
firmware/tools/idf.sh build merge-bin > firmware/test-results/test-build.log 2>&1
cp firmware/build/Stillframe.elf firmware/test-assets/safety.elf
cp firmware/build/Stillframe.bin firmware/test-assets/safety.bin
python3 firmware/tools/seed-ota.py firmware/build/merged-binary.bin firmware/test-assets/safety-replay-flash.bin
python3 emulator/run.py firmware/test-assets/safety-replay-flash.bin \
  --name stillframe-safety-replay --fresh --ap-password test-12345678 \
  --elf firmware/test-assets/safety.elf --allow-panic-reboot --seconds 360 --exit-on "ALL FIRMWARE SAFETY TESTS PASSED" \
  > firmware/test-results/safety-replay.log 2>&1
python3 - <<'PY'
from pathlib import Path
log=Path('firmware/test-results/safety-replay.log').read_text()
assert 'ALL FIRMWARE SAFETY TESTS PASSED' in log
import hashlib
assert 'RUNNING_ROM_SHA256 '+hashlib.sha256(Path('firmware/test-assets/safety.bin').read_bytes()).hexdigest() in log
for evidence in ('device independently rejects remote ROM for a wrong board','remote ROM checksum mismatch preserves boot slot and reports failure','remote OTA bad startup rolled back','failed remote task never re-downloads or reflashes after rollback'):
    assert evidence in log,evidence
assert 'FAIL:' not in log
for evidence in ('INTENTIONAL STARTUP FAILURE','failed startup marked ABORTED','valid web OTA writes inactive slot','HTTP 401 preserves','second sync downloads 960000 bytes','NVS configuration survives reset'):
    assert evidence in log,evidence
print('PASS: protocol, HTTP, NVS, complete frame, rejected downloads, authenticated web OTA and real bootloader rollback')
PY
