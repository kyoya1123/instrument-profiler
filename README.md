# Instruments Profiler

[日本語版はこちら / Read in Japanese](README.ja.md)

A Claude Code Skill that fully automates Xcode Instruments profiling for iOS/macOS apps — from recording to analysis to actionable recommendations.

## What It Does

This skill automates the entire Instruments profiling workflow:

1. **Device Selection** — Automatically detects simulators and connected devices
2. **Release Build** — Builds optimized Release configuration (Debug builds give inaccurate measurements)
3. **Profiling** — Runs `xctrace record` with SwiftUI or App Launch templates
4. **Symbolication** — Resolves your app's symbols using dSYM for readable stack traces
5. **Analysis** — Parses trace data and generates detailed Markdown reports
6. **Recommendations** — Identifies hot frames, hangs, hitches, and suggests fixes

## Why This Matters

Xcode Instruments is powerful but painful:

- Complex GUI with steep learning curve
- Manual template selection and configuration
- Raw trace data requires expertise to interpret
- No automatic actionable insights

**This skill eliminates all of that.** Just say "profile this app" and get a complete performance report with specific optimization recommendations.

## Installation

### Quick Install (3 steps)

```bash
# 1. Clone to your Skills directory
git clone https://github.com/YOUR_USERNAME/instruments-profiler.git ~/.claude/skills/instruments-profiler

# 2. Verify installation
ls ~/.claude/skills/instruments-profiler/SKILL.md

# 3. Restart Claude Code
```

### Alternative: Add as Plugin

Add to your project's `.claude/plugins/` directory or global `~/.claude/plugins/`.

## Usage

### Basic Commands

Just tell Claude what you want to measure:

```
Profile this app with Instruments
```

```
Measure the app launch time
```

```
Run Instruments profiling
```

### Profiling Modes

| Mode | Template | Best For |
|------|----------|----------|
| **SwiftUI** | SwiftUI + Time Profiler + Hangs + Hitches | View updates, CPU usage, UI responsiveness |
| **App Launch** | App Launch | Startup time, library loading, initialization |
| **Time Profiler** | Time Profiler | General CPU profiling |
| **Leaks** | Leaks | Memory leak detection |
| **Allocations** | Allocations | Memory allocation analysis |
| **Animation Hitches** | Animation Hitches | Frame drop detection, scroll performance |
| **Energy Log** | Energy Log | Battery consumption analysis (physical device only) |

### Example Output

#### App Launch Report

```markdown
## App Launch - Life Cycle Phases

**Total Launch Time:** 1234.56 ms (1.23 s)

| Phase | Duration (ms) | % |
|-------|---------------|---|
| Static Runtime Init | 150.00 | 12.2% |
| UIKit Init | 300.00 | 24.3% |
| Initial Frame Rendering | 400.00 | 32.4% |

**Status:** ⚠️ Acceptable - Consider optimizing launch time
```

#### SwiftUI Performance Report

```markdown
## Hot Frames - Total Time (Top 10)

| Rank | Function | Total (ms) | Binary |
|------|----------|------------|--------|
| 1 | ContentView.body.getter | 45.00 | MyApp |
| 2 | ListView.body.getter | 32.00 | MyApp |

## Potential Hangs
**Total:** 0
**Status:** ✅ OK - No hangs detected

## Animation Hitches
**Total:** 2
**Status:** ⚠️ Minor issues
```

## Requirements

- macOS 14.0+
- Xcode 16.0+
- Claude Code with XcodeBuildMCP
- iOS Simulator or connected iOS device

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Device Selection                                             │
│     list_sims / list_devices → AskUserQuestion                  │
├─────────────────────────────────────────────────────────────────┤
│  2. Release Build                                                │
│     build_sim or build_device → install if physical device      │
├─────────────────────────────────────────────────────────────────┤
│  3. Profiling                                                    │
│     xctrace record --template SwiftUI/AppLaunch                 │
├─────────────────────────────────────────────────────────────────┤
│  4. Symbolication                                                │
│     xctrace symbolicate --dsym <path>                           │
├─────────────────────────────────────────────────────────────────┤
│  5. Export & Analysis                                            │
│     export_trace.sh → parse_trace.py → Markdown report          │
└─────────────────────────────────────────────────────────────────┘
```

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Permission denied | Developer tools not authorized | System Settings → Privacy → Developer Tools |
| Device not found | Invalid device name/UDID | Run `xctrace list devices` |
| Empty trace | Recording too short | Interact with the app during profiling |
| Symbols show as "unknown" | Missing dSYM | Ensure Release build includes dSYM |
| Cannot find process | Process search failed | Use `--launch` instead of `--attach` |

## Files

```
instruments-profiler/
├── SKILL.md                    # Skill definition (Claude reads this)
├── scripts/
│   ├── run_profiling.sh        # xctrace record wrapper
│   ├── export_trace.sh         # xctrace export automation
│   └── parse_trace.py          # Trace data parser & report generator
├── references/
│   └── xctrace-commands.md     # xctrace command reference
├── README.md                   # This file (English)
└── README.ja.md                # Japanese README
```

## Contributing

Issues and pull requests welcome! Please file issues in both English or Japanese.

## License

MIT License - see [LICENSE](LICENSE)

## Related Skills

- `swiftui-performance-audit` — Code review-based performance analysis
- `ios-debugger-agent` — Runtime debugging with XcodeBuildMCP
