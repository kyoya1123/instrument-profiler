# Output Format Reference

テンプレート別の出力フォーマット例。

## SwiftUIテンプレート使用時

```markdown
## プロファイリング結果

- **Total Samples:** 868
- **Total Time:** 868.00 ms

## Hot Frames - Total Time (Top 10)

| Rank | Function | Count | Total (ms) | Binary |
|------|----------|-------|------------|--------|
| 1 | __CFRunLoopRun | 494 | 494.00 | CoreFoundation |
| 2 | AudioRecorder.processAudioBuffer | 17 | 17.00 | MyApp |

## App Code (MyApp)

| Function | Count | Total (ms) |
|----------|-------|------------|
| AudioRecorder.processAudioBuffer | 17 | 17.00 |
| ContentView.body.getter | 6 | 6.00 |

## SwiftUI View Body Updates (Top 10)

| View | Count | Avg (µs) | Total (µs) |
|------|-------|----------|------------|
| MainContentView | 1 | 419.3 | 419.3 |
| ContentView | 1 | 263.0 | 263.0 |

## Potential Hangs

**Total:** 0
**Status:** ✅ OK - No hangs detected

## Animation Hitches

**Total:** 0
**Status:** ✅ OK - No hitches detected
```

## App Launchテンプレート使用時

```markdown
## App Launch - Life Cycle Phases

**Total Launch Time:** 1234.56 ms (1.23 s)

| Phase | Duration (ms) | % | Description |
|-------|---------------|---|-------------|
| Initializing - Process Creation | 50.00 | 4.0% | Creating the process... |
| Initializing - System Interface | 200.00 | 16.2% | Initializing system interface... |
| Launching - Static Runtime Init | 150.00 | 12.2% | Running static initializers... |
| Launching - UIKit Init | 300.00 | 24.3% | Initializing UIKit... |
| Launching - Initial Frame Rendering | 400.00 | 32.4% | Rendering initial frame... |
| Running | 134.56 | 10.9% | App is running... |

### Launch Performance Assessment

**Status:** ⚠️ Acceptable - Consider optimizing launch time

## App Launch - Library Loading

**Total Libraries:** 245
**Total Load Time:** 89.45 ms

### Slowest Libraries (>1ms)

| Library | Duration (ms) |
|---------|---------------|
| SwiftUI | 12.34 |
| Foundation | 8.76 |
| UIKit | 7.89 |
```

## Leaksテンプレート使用時

```markdown
## Memory Leaks

**Status:** ❌ Leaks detected!
**Total Leaks:** 15
**Total Leaked Memory:** 2.45 KB (2508 bytes)

### Leaks by Library

| Library | Count | Bytes |
|---------|-------|-------|
| MyApp | 10 | 1920 |
| Foundation | 3 | 384 |
| CoreFoundation | 2 | 204 |

### Leaks by Responsible Frame (Top 15)

| Function | Count | Bytes |
|----------|-------|-------|
| MyViewController.loadData() | 5 | 1024 |
| NetworkManager.fetch(_:) | 3 | 512 |

### Largest Leaks (Top 10)

| Address | Size (bytes) | Responsible Frame |
|---------|--------------|-------------------|
| 0x600000c12340 | 256 | MyViewController.loadData() |
| 0x600000c12380 | 128 | NetworkManager.fetch(_:) |
```

## Allocationsテンプレート使用時

```markdown
## Memory Allocations - Statistics

**Persistent Memory:** 45.67 MB
**Total Allocated:** 123.45 MB

### Top Categories by Persistent Memory

| Category | Persistent | Count | Total |
|----------|------------|-------|-------|
| VM: ImageIO_PNG_Data | 12.34 MB | 45 | 24.56 MB |
| malloc | 8.90 MB | 12345 | 56.78 MB |
| CFString (immutable) | 5.67 MB | 8901 | 12.34 MB |
```

## Energy Logテンプレート使用時

```markdown
## Energy Usage

**Status:** ⚠️ Moderate - Some optimization may help

### Average Usage

- **Energy Impact:** 7.5 (max: 18.2)
- **CPU Usage:** 12.3% (max: 85.6%)
- **GPU Usage:** 5.2% (max: 45.0%)

### High Energy Impact Periods (5 samples)

| Time | Energy Impact | CPU | GPU |
|------|---------------|-----|-----|
| 00:15.234 | 18.2 | 85.6% | 12.3% |
| 00:16.567 | 15.7 | 72.1% | 8.9% |
```
