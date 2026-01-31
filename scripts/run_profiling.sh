#!/usr/bin/env bash
set -euo pipefail

# SwiftUI Instruments Profiler - run_profiling.sh
# xctrace record でプロファイリングを実行する

usage() {
    cat <<EOF
Usage: $(basename "$0") [options]

Options:
    --template <name>     Instruments template (default: SwiftUI)
                          Options: SwiftUI, "Time Profiler", Hangs, "Animation Hitches"
    --time-limit <sec>    Recording time limit (default: 30s)
    --output <dir>        Output directory (default: /tmp)
    --device <name>       Device name or UDID (required)
    --app-path <path>     Path to .app bundle (for launch mode)
    --bundle-id <id>      Bundle identifier (for attach mode)
    --attach              Use attach mode instead of launch mode
    -h, --help            Show this help

Examples:
    # Simulator (launch mode)
    $(basename "$0") --template SwiftUI --device "iPhone 17 Pro" --app-path /path/to/App.app

    # Device (attach mode)
    $(basename "$0") --template SwiftUI --device "00008..." --bundle-id com.example.app --attach
EOF
    exit 0
}

# Defaults
template="SwiftUI"
time_limit="30s"
output_dir="/tmp"
device=""
app_path=""
bundle_id=""
attach_mode=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --template)
            template="$2"
            shift 2
            ;;
        --time-limit)
            time_limit="$2"
            shift 2
            ;;
        --output)
            output_dir="$2"
            shift 2
            ;;
        --device)
            device="$2"
            shift 2
            ;;
        --app-path)
            app_path="$2"
            shift 2
            ;;
        --bundle-id)
            bundle_id="$2"
            shift 2
            ;;
        --attach)
            attach_mode=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            ;;
    esac
done

# Validate required arguments
if [[ -z "$device" ]]; then
    echo "Error: --device is required" >&2
    exit 1
fi

if [[ "$attach_mode" == false && -z "$app_path" ]]; then
    echo "Error: --app-path is required for launch mode" >&2
    exit 1
fi

if [[ "$attach_mode" == true && -z "$bundle_id" ]]; then
    echo "Error: --bundle-id is required for attach mode" >&2
    exit 1
fi

# Generate output filename
timestamp="$(date +"%Y%m%d-%H%M%S")"
trace_file="${output_dir}/profile_${timestamp}.trace"

echo "Starting profiling..."
echo "  Template: $template"
echo "  Time limit: $time_limit"
echo "  Device: $device"
echo "  Output: $trace_file"

if [[ "$attach_mode" == true ]]; then
    echo "  Mode: attach (bundle-id: $bundle_id)"
    xcrun xctrace record \
        --template "$template" \
        --device "$device" \
        --time-limit "$time_limit" \
        --output "$trace_file" \
        --attach "$bundle_id"
else
    echo "  Mode: launch (app-path: $app_path)"

    # Get the executable path inside the app bundle
    if [[ -d "$app_path" ]]; then
        # macOS app
        if [[ -d "$app_path/Contents/MacOS" ]]; then
            app_name=$(basename "$app_path" .app)
            executable="$app_path/Contents/MacOS/$app_name"
        else
            # iOS Simulator app - launch directly
            executable="$app_path"
        fi
    else
        echo "Error: App path does not exist: $app_path" >&2
        exit 1
    fi

    xcrun xctrace record \
        --template "$template" \
        --device "$device" \
        --time-limit "$time_limit" \
        --output "$trace_file" \
        --launch -- "$executable"
fi

echo ""
echo "Profiling complete!"
echo "Trace saved: $trace_file"
echo ""
echo "Next steps:"
echo "  1. Export: export_trace.sh $trace_file $output_dir/exported"
echo "  2. Analyze: parse_trace.py $output_dir/exported"
echo "  3. Open in Instruments: open -a Instruments $trace_file"
