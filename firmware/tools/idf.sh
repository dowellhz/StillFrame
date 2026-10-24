#!/bin/sh
set -eu
SF_ROOT=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
export IDF_PATH="$SF_ROOT/.tools/esp-idf"
export IDF_TOOLS_PATH="$SF_ROOT/.tools/idf-tools"
export IDF_PYTHON_ENV_PATH="$SF_ROOT/.tools/idf-python"
export PATH="$IDF_PYTHON_ENV_PATH/bin:$IDF_TOOLS_PATH/tools/xtensa-esp-elf/esp-14.2.0_20251107/xtensa-esp-elf/bin:$IDF_TOOLS_PATH/tools/esp32ulp-elf/2.38_20240113/esp32ulp-elf/bin:/opt/homebrew/bin:$PATH"
export ESP_ROM_ELF_DIR="$IDF_TOOLS_PATH/tools/esp-rom-elfs/20241011/"
export IDF_TARGET=esp32s3
export IDF_COMPONENT_MANAGER=0
"$IDF_PYTHON_ENV_PATH/bin/python" "$SF_ROOT/firmware/tools/ensure-sdk.py"
cd "$SF_ROOT/firmware"
exec "$IDF_PYTHON_ENV_PATH/bin/python" "$IDF_PATH/tools/idf.py" "$@"
