#!/usr/bin/env bash
# Usage: bash make_all.sh [name]
# Default name is 'example'; data lives in data/<name>/
set -e

NAME=${1:-example}
DATA="data/$NAME"
XML="$DATA/CCV.xml"
XML6="$DATA/CCV_last6yrs.xml"

echo "=== Building CV for: $NAME ==="

python3 scripts/bib_to_ccv.py   "$DATA"
python3 scripts/yaml_to_ccv.py  "$DATA"
python3 scripts/ccv_filter_6yrs.py "$XML" "$XML6"
# If a manually-corrected portal 6yr export exists, override supervision/service sections
if [ -f "$DATA/CCV_source_6yr.xml" ]; then
    python3 scripts/merge_portal_6yr.py "$XML6" "$DATA/CCV_source_6yr.xml" "$XML6"
fi
python3 scripts/ccv_to_pdf.py   "$XML"

echo "=== Done ==="
echo "  Full CCV XML : $XML"
echo "  6-yr CCV XML : $XML6"
echo "  PDF          : $DATA/CV_$NAME.pdf"
