#!/bin/bash
# make_release.sh <exe> [display folder] - rebuild every Sandstorm release output from scratch (package worker, 11-23):
#   A      Desktop/IGI2/Sandstorm TEST - fly mode/   full test copy for the owner's laptop (fly mode, no Python needed)
#   NOFLY  Desktop/IGI2/Sandstorm TEST/              the same without fly mode
#   B      dist/Sandstorm_v1.0/ + .zip               public delta package (Sandstorm only, no Patch file; exe/ part separate)
# Each gets MD5SUMS.txt and is checked back. Only READS the live game and C:\igi2noclip.
#   bash work/release/make_release.sh work/menu/menufix/igi2_menufix_v22c_6b309074.exe work/release/display
# env: BUILD=f1123_1 MD5=86c04c0d96a61c7e02159e82d3a52b3b ONLY=A,NOFLY,B
set -e
cd "$(dirname "$0")/../.."
EXE="${1:?usage: make_release.sh <igi2.exe> [display folder]}"
DISP="${2:-work/release/display}"
python -P work/release/patch_files.py
python -P work/release/make_endscreen_sandstorm.py
python -P work/release/release.py --exe "$EXE" --display "$DISP" --build "${BUILD:-f1123_1}" \
    --md5 "${MD5:-86c04c0d96a61c7e02159e82d3a52b3b}" --only "${ONLY:-A,NOFLY,B}"
