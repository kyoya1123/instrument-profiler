#!/usr/bin/env bash
set -euo pipefail

# SwiftUI Instruments Profiler - export_trace.sh
# xctrace export でトレースデータをXMLにエクスポートする

usage() {
    cat <<EOF
Usage: $(basename "$0") <trace_file> [output_dir]

Arguments:
    trace_file    Path to .trace file
    output_dir    Output directory (default: same as trace file)

Examples:
    $(basename "$0") /tmp/profile_20251231-120000.trace
    $(basename "$0") /tmp/profile_20251231-120000.trace /tmp/exported
EOF
    exit 0
}

if [[ $# -lt 1 ]]; then
    usage
fi

trace_file="$1"
output_dir="${2:-$(dirname "$trace_file")/exported}"

if [[ ! -e "$trace_file" ]]; then
    echo "Error: Trace file not found: $trace_file" >&2
    exit 1
fi

mkdir -p "$output_dir"

echo "Exporting trace data..."
echo "  Input: $trace_file"
echo "  Output: $output_dir"
echo ""

# Export TOC (Table of Contents)
toc_file="${output_dir}/toc.xml"
echo "Exporting TOC..."
xcrun xctrace export --input "$trace_file" --toc > "$toc_file"
echo "  -> $toc_file"

# Parse TOC to find available schemas
echo ""
echo "Available schemas:"
grep -oE 'schema="[^"]+"' "$toc_file" | sort -u | sed 's/schema="//;s/"$//' | while read -r schema; do
    echo "  - $schema"
done

echo ""
echo "Exporting main tables..."

# Core schemas to export
schemas=(
    # Time Profiler
    "time-profile"
    "time-sample"
    # App Launch
    "life-cycle-period"
    "dyld-library-load"
    "dyld-activity-interval"
    "thread-state"
    "process-info"
    # Hangs
    "potential-hangs"
    "hang-risks"
    # Hitches
    "hitches"
    "hitches-frame-lifetimes"
    "hitches-framewait"
    "hitches-gpu"
    "hitches-renders"
    "hitches-updates"
    # SwiftUI (explicit)
    "swiftui-updates"
    "swiftui-causes"
    "swiftui-changes"
    "swiftui-update-groups"
    "SwiftUIFilteredUpdates"
    # Energy Log
    "energy-impact"
    "energy-usage"
    "cpu-usage"
    "gpu-usage"
    "network-usage"
)

for schema in "${schemas[@]}"; do
    output_file="${output_dir}/${schema}.xml"
    echo "  Exporting $schema..."

    # Check if schema exists in trace
    if grep -q "schema=\"$schema\"" "$toc_file" 2>/dev/null; then
        xcrun xctrace export \
            --input "$trace_file" \
            --xpath "/trace-toc/run[@number=\"1\"]/data/table[@schema=\"${schema}\"]" \
            --output "$output_file" 2>/dev/null || true

        if [[ -s "$output_file" ]]; then
            echo "    -> $output_file"
        else
            rm -f "$output_file"
            echo "    (empty or not available)"
        fi
    else
        echo "    (not in trace)"
    fi
done

# Try to export SwiftUI-specific schemas
echo ""
echo "Checking for SwiftUI-specific schemas..."

# Extract all SwiftUI-related schemas from TOC
swiftui_schemas=$(grep -oE 'schema="[^"]*swiftui[^"]*"' "$toc_file" 2>/dev/null | sort -u | sed 's/schema="//;s/"$//' || true)

if [[ -n "$swiftui_schemas" ]]; then
    echo "$swiftui_schemas" | while read -r schema; do
        output_file="${output_dir}/${schema}.xml"
        echo "  Exporting $schema..."

        xcrun xctrace export \
            --input "$trace_file" \
            --xpath "/trace-toc/run[@number=\"1\"]/data/table[@schema=\"${schema}\"]" \
            --output "$output_file" 2>/dev/null || true

        if [[ -s "$output_file" ]]; then
            echo "    -> $output_file"
        else
            rm -f "$output_file"
            echo "    (empty)"
        fi
    done
else
    echo "  No SwiftUI-specific schemas found in trace."
    echo "  Use 'SwiftUI' template for SwiftUI-specific data."
fi

# Track-based exports (Leaks, Allocations)
# These use a different XML structure than schema-based exports
echo ""
echo "Checking for track-based instruments (Leaks, Allocations)..."

declare -A track_details=(
    ["Leaks"]="Leaks"
    ["Allocations"]="Allocations List,Statistics"
)

for track_name in "${!track_details[@]}"; do
    IFS=',' read -ra details <<< "${track_details[$track_name]}"

    # Check if track exists in TOC
    if grep -q "track.*name=\"$track_name\"" "$toc_file" 2>/dev/null; then
        echo "  Found track: $track_name"

        for detail_name in "${details[@]}"; do
            # Create safe filename (replace spaces with underscores)
            safe_name="${track_name// /_}-${detail_name// /_}"
            output_file="${output_dir}/${safe_name}.xml"
            echo "    Exporting $detail_name..."

            xcrun xctrace export \
                --input "$trace_file" \
                --xpath "/trace-toc/run[@number=\"1\"]/tracks/track[@name=\"${track_name}\"]/details/detail[@name=\"${detail_name}\"]" \
                --output "$output_file" 2>/dev/null || true

            if [[ -s "$output_file" ]]; then
                echo "      -> $output_file"
            else
                rm -f "$output_file"
                echo "      (empty or not available)"
            fi
        done
    else
        echo "  Track not found: $track_name"
    fi
done

echo ""
echo "Export complete!"
echo ""
echo "Files exported to: $output_dir"
ls -la "$output_dir"
echo ""
echo "Next step: parse_trace.py $output_dir"
