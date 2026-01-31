---
name: instruments-profiler
description: xctrace CLIでiOS/macOSアプリをInstrumentsプロファイリングし、パフォーマンス問題を特定・修正するワークフロー。「Instrumentsで計測」「プロファイリング」「パフォーマンス計測」で使用。
---

# Instruments Profiler

## Overview

xctrace CLIを使ってiOS/macOSアプリをInstrumentsでプロファイリングし、パフォーマンス問題を特定・修正する。

## Core Workflow

### 1) デバイス選択

1. **デバイス一覧を並列で取得**
   ```
   # 同時に実行
   mcp__XcodeBuildMCP__list_sims
   mcp__XcodeBuildMCP__list_devices
   ```

2. **具体的なデバイスをユーザーに確認**（AskUserQuestionを使用）

   シミュレータと実機の両方を選択肢に含める:
   ```
   questions: [{
     question: "プロファイリングを実行するデバイスを選択してください",
     header: "デバイス",
     options: [
       { label: "iPhone 17 Pro (Simulator)", description: "シミュレータ" },
       { label: "<実機名1>", description: "実機 - UDID: xxx" },
       { label: "<実機名2>", description: "実機 - UDID: yyy" }
     ],
     multiSelect: false
   }]
   ```

   **ポイント**: 起動中のシミュレータがあれば先頭に、有線接続の実機を優先的に表示

3. **実機の場合**: xctrace用のUDIDを取得

   **重要**: Xcodeの`list_devices`で得られるUDIDとxctraceのUDIDは**異なる**

   ```bash
   xctrace list devices | grep "<選択されたデバイス名>"
   ```

   例: `John's iPhone (26.0) (00008101-XXXXXXXXXXXX)` → UDIDは `00008101-XXXXXXXXXXXX`

### 2) Releaseビルド

**重要**: Debugビルドは最適化なしで計測不正確。必ずReleaseビルドを使用。

```
mcp__XcodeBuildMCP__session-set-defaults({
  scheme: "<スキーム名>",
  configuration: "Release",
  deviceId: "<Xcode UDID>"  // 実機の場合
})
```

**シミュレータの場合:**
```
mcp__XcodeBuildMCP__build_sim
mcp__XcodeBuildMCP__get_sim_app_path({ platform: "iOS Simulator" })
```

**実機の場合:**
```
mcp__XcodeBuildMCP__build_device
mcp__XcodeBuildMCP__get_device_app_path
mcp__XcodeBuildMCP__install_app_device({ appPath: "<ビルドされたappパス>" })
# → bundleIDとinstallationURLを控える
```

### 3) プロファイリングモード選択

**ユーザーに計測モードを確認**（AskUserQuestionを使用）:
```
questions: [{
  question: "計測モードを選択してください",
  header: "計測モード",
  options: [
    { label: "SwiftUI", description: "Time Profiler + View Body + Hangs + Hitches" },
    { label: "App Launch", description: "起動時間 + フェーズ分析" },
    { label: "Time Profiler", description: "CPU時間プロファイリング（汎用）" },
    { label: "Leaks", description: "メモリリーク検出" },
    { label: "Allocations", description: "メモリ割り当て分析" },
    { label: "Animation Hitches", description: "フレームドロップ検出" },
    { label: "Energy Log", description: "バッテリー消費分析（実機のみ）" }
  ],
  multiSelect: false
}]
```

**注意**: Energy Logは実機でのみ正確なデータが取得可能。シミュレータでは意味のあるデータが得られない。

### 4) プロファイリング実行

**トレースファイル名の生成**（ファイル名衝突を防ぐためタイムスタンプを使用）:
```bash
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
TRACE_FILE="/tmp/profile_${TIMESTAMP}.trace"
TRACE_SYM_FILE="/tmp/profile_${TIMESTAMP}_sym.trace"
EXPORT_DIR="/tmp/exported_${TIMESTAMP}"
```

#### App Launchテンプレートの場合（全自動）

App Launchは起動完了を自動検出して終了するため、確認なしで直接実行する。

```bash
# 同期実行（自動終了を待つ）
xctrace record \
  --template "App Launch" \
  --device "<デバイス>" \
  --output $TRACE_FILE \
  --launch <bundleId>
```

- バックグラウンド実行不要
- ユーザーによる停止確認不要
- 開始確認も不要
- 起動完了後、自動的にシンボル化・解析へ進む

#### SwiftUIテンプレートの場合（ユーザー操作が必要）

**起動方法の選択**（AskUserQuestionを使用）:
```
questions: [{
  question: "アプリの起動方法を選択してください",
  header: "起動方法",
  options: [
    { label: "起動中のアプリに接続", description: "既に起動中のアプリにアタッチ（--attach）" },
    { label: "アプリを起動して計測", description: "アプリを新規起動してプロファイリング（--launch）" }
  ],
  multiSelect: false
}]
```

**「起動中のアプリに接続」を選択した場合:**
```bash
# PIDを検索
ps aux | grep <アプリ名>
# または xcrun devicectl で実機のプロセス一覧を取得
```

**実行フロー:**

1. `run_in_background: true`でxctraceを実行（`--time-limit`なし）
2. AskUserQuestionで停止を待つ
3. ユーザーが停止を選択したら、xctraceプロセスをkill
4. 通常通りシンボル化・解析を続行

```bash
# バックグラウンドで実行（time-limitなし）
Bash(run_in_background: true):
  # --attach の場合
  xctrace record --template "SwiftUI" --device "<デバイス>" --output $TRACE_FILE --attach <PID>
  # --launch の場合
  xctrace record --template "SwiftUI" --device "<デバイス>" --output $TRACE_FILE --launch <bundleId>
# → shell_idを控える

# ユーザーに停止タイミングを確認
AskUserQuestion:
  question: "アプリを操作してください。完了したら停止してください"
  options: [
    { label: "停止", description: "計測を終了して解析を開始" },
    { label: "もう少し待つ", description: "計測を継続" }
  ]

# 「停止」が選択されたら
pkill -INT -f "xctrace record"

# TaskOutputで完了を確認
TaskOutput(task_id: "<shell_id>", block: false)
```

#### Time Profilerテンプレートの場合

汎用CPUプロファイリング。SwiftUIテンプレートと同様のフローを使用。

```bash
# バックグラウンドで実行
Bash(run_in_background: true):
  xctrace record --template "Time Profiler" --device "<デバイス>" --output $TRACE_FILE --launch <bundleId>

# ユーザーに停止タイミングを確認（SwiftUIと同様）
```

#### Leaks / Allocationsテンプレートの場合

メモリ関連テンプレートはユーザー操作が必要で、SwiftUIテンプレートと同様のフローを使用。

```bash
# バックグラウンドで実行
Bash(run_in_background: true):
  xctrace record --template "Leaks" --device "<デバイス>" --output $TRACE_FILE --launch <bundleId>
  # または --template "Allocations"

# ユーザーに停止タイミングを確認
AskUserQuestion:
  question: "アプリを操作してメモリを使用してください。完了したら停止してください"
  options: [
    { label: "停止", description: "計測を終了して解析を開始" },
    { label: "もう少し待つ", description: "計測を継続" }
  ]

# 「停止」が選択されたら
pkill -INT -f "xctrace record"
```

**注意**: Leaks/Allocationsは十分なメモリ操作（画面遷移、データ読み込み等）を行ってから停止すること。

#### Animation Hitchesテンプレートの場合

フレームドロップ検出。スクロールやアニメーション操作が必要。

```bash
# バックグラウンドで実行
Bash(run_in_background: true):
  xctrace record --template "Animation Hitches" --device "<デバイス>" --output $TRACE_FILE --launch <bundleId>

# ユーザーに停止タイミングを確認
AskUserQuestion:
  question: "スクロールやアニメーション操作を行ってください。完了したら停止してください"
  options: [
    { label: "停止", description: "計測を終了して解析を開始" },
    { label: "もう少し待つ", description: "計測を継続" }
  ]
```

#### Energy Logテンプレートの場合

**重要**: Energy Logは**実機のみ**で正確なデータが取得可能。シミュレータでは意味のあるデータが得られない。

デバイス選択時にシミュレータが選択された場合は警告を表示し、実機を選択するよう促す。

```bash
# 実機でバックグラウンド実行
Bash(run_in_background: true):
  xctrace record --template "Energy Log" --device "<実機UDID>" --output $TRACE_FILE --launch <bundleId>

# ユーザーに停止タイミングを確認
AskUserQuestion:
  question: "アプリを通常使用してください（ネットワーク操作、バックグラウンド処理など）。完了したら停止してください"
  options: [
    { label: "停止", description: "計測を終了して解析を開始" },
    { label: "もう少し待つ", description: "計測を継続" }
  ]
```

---

#### xctrace recordコマンド（内部参照用）

**--attach（起動中のアプリに接続）:**
```bash
xctrace record --template "<テンプレート>" --device "<デバイス名 or UDID>" --output $TRACE_FILE --attach <PID>
```

**--launch（アプリを起動して計測）:**
```bash
xctrace record --template "<テンプレート>" --device "<デバイス名 or UDID>" --output $TRACE_FILE --launch <bundleId>
```

**注意**:
- `--launch`や`--attach`引数はコマンドの最後に配置
- 実機・シミュレータ共通でbundleIdを使用可能

### 5) シンボル化（重要）

アプリコードのシンボルを解決するために、dSYMを使ってトレースをシンボル化:

```bash
xctrace symbolicate \
  --input $TRACE_FILE \
  --output $TRACE_SYM_FILE \
  --dsym ~/Library/Developer/Xcode/DerivedData/<project>/Build/Products/Release-iphoneos/
```

**シンボル化しないと**: アプリのコードが`unknown`や`<deduplicated_symbol>`として表示される。

### 6) データエクスポート

```bash
<skill_dir>/scripts/export_trace.sh $TRACE_SYM_FILE $EXPORT_DIR
```

出力:
- `$EXPORT_DIR/toc.xml` - テーブル一覧
- `$EXPORT_DIR/time-profile.xml` - Time Profilerデータ
- `$EXPORT_DIR/report.md` - 解析レポート

### 7) 解析・診断

```bash
# 基本的な解析
<skill_dir>/scripts/parse_trace.py $EXPORT_DIR

# アプリ固有コードをフィルタリング
<skill_dir>/scripts/parse_trace.py $EXPORT_DIR --app "MyApp"

# Flame Graph用データのみ出力
<skill_dir>/scripts/parse_trace.py $EXPORT_DIR --collapsed-only
```

**出力内容:**
- **Summary** - サンプル数、合計時間
- **Hot Frames - Total Time** - 関数の総実行時間（呼び出し先含む）
- **Hot Frames - Self Time** - 関数自身の実行時間（リーフフレーム）
- **SwiftUI / AttributeGraph Frames** - SwiftUI関連の処理
- **App Code** - アプリ固有のコード（--app指定時）
- **SwiftUI View Body Updates** - View更新統計（SwiftUIテンプレート使用時）
- **Potential Hangs** - ハング検出（SwiftUIテンプレート使用時）
- **Animation Hitches** - フレームドロップ（SwiftUIテンプレート使用時）
- **Flame Graph Data** - collapsed stack形式

**解析観点:**
| パターン | 意味 | 対処 |
|---------|------|------|
| Self Time高 | その関数自体が重い | アルゴリズム改善、キャッシュ |
| Total Time高 / Self Time低 | 呼び出し先に問題 | 呼び出し先を調査 |
| SwiftUI関連が多い | View更新が頻繁 | 状態スコープ縮小 |

### 8) 改善計画の確認

解析結果を表示した後、ユーザーに改善計画を立てるかどうかを確認する（AskUserQuestionを使用）:

```
questions: [{
  question: "解析が完了しました。改善計画を立てますか？",
  header: "次のステップ",
  options: [
    { label: "改善計画を立てる", description: "問題箇所を特定し、具体的な修正プランを作成" },
    { label: "結果の確認のみ", description: "今回は計測結果の確認だけで終了" }
  ],
  multiSelect: false
}]
```

**「改善計画を立てる」を選択した場合:**
1. 解析結果から問題の優先度を特定
2. 各問題に対する具体的な修正方針を提案
3. 影響範囲と修正のリスクを説明
4. 必要に応じて `EnterPlanMode` で詳細な実装計画を作成

**「結果の確認のみ」を選択した場合:**
- 解析結果のサマリーを表示して終了
- 後から `/instruments-profiler` で再度計測可能であることを伝える

### 9) Flame Graph生成（オプション）

```bash
git clone https://github.com/brendangregg/FlameGraph
./FlameGraph/flamegraph.pl $EXPORT_DIR/collapsed.txt > flamegraph.svg
```

### 10) 修正提案

問題特定後、以下のパターンを適用:

| 問題 | 解決策 |
|------|--------|
| ループ内のData.append | `withUnsafeMutableBytes`で直接書き込み |
| Array.removeFirst (O(n)) | リングバッファまたはインデックス管理 |
| View invalidation storms | 状態スコープの縮小 |
| Heavy work in body | 事前計算・キャッシュ |
| Large images | ダウンサンプリング |

詳細は `swiftui-performance-audit` スキルを参照。

## Output Format

### SwiftUIテンプレート使用時

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

### App Launchテンプレート使用時

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

### Leaksテンプレート使用時

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

### Allocationsテンプレート使用時

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

### Energy Logテンプレート使用時

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

## Troubleshooting

| エラー | 原因 | 対処 |
|-------|------|------|
| Permission denied | 開発者ツールアクセス未許可 | システム設定で許可 |
| Device not found | デバイス名/UDIDが不正 | `xctrace list devices`で確認 |
| Template not found | テンプレート名が不正 | `xctrace list templates`で確認 |
| Empty trace | 操作なし/すぐ停止した | 十分にアプリを操作してから停止 |
| シンボルがunknown | dSYMがない | `xctrace symbolicate`でシンボル化 |
| Cannot find process | プロセス検索失敗 | `--launch`オプションを使用 |
| Leaks/Allocationsが空 | track-based exportが必要 | export_trace.shが最新か確認 |
| Energy Logデータなし | シミュレータ非対応 | 実機で計測（シミュレータでは取得不可） |
| No energy data | Xcode 13以前の制限 | Xcode 13以降にアップデート |

## 完全ワークフロー例

### App Launchの場合（全自動）

```bash
# 1. デバイス一覧取得（並列実行）
mcp__XcodeBuildMCP__list_sims
mcp__XcodeBuildMCP__list_devices
# → AskUserQuestionでデバイス選択

# 2. 実機の場合: xctrace UDID取得（Xcode UDIDと異なる場合がある）
xctrace list devices | grep "<デバイス名>"

# 3. Releaseビルド
mcp__XcodeBuildMCP__session-set-defaults({ scheme: "...", configuration: "Release", ... })
# 実機: build_device → install_app_device → bundleIdを控える
# シミュレータ: build_sim → get_app_bundle_id → bundleIdを控える

# 4. 計測モード選択（AskUserQuestion）→ App Launchを選択

# 5. トレースファイル名を生成
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
TRACE_FILE="/tmp/profile_${TIMESTAMP}.trace"
EXPORT_DIR="/tmp/exported_${TIMESTAMP}"

# 6. プロファイリング実行（同期・全自動）
xctrace record --template "App Launch" --device "<デバイス>" --output $TRACE_FILE --launch <bundleId>

# 7. エクスポート・解析
<skill_dir>/scripts/export_trace.sh $TRACE_FILE $EXPORT_DIR
<skill_dir>/scripts/parse_trace.py $EXPORT_DIR --app "<アプリ名>"
```

### SwiftUIの場合（ユーザー操作が必要）

```bash
# 1. デバイス一覧取得（並列実行）
mcp__XcodeBuildMCP__list_sims
mcp__XcodeBuildMCP__list_devices
# → AskUserQuestionでデバイス選択

# 2. 実機の場合: xctrace UDID取得（Xcode UDIDと異なる場合がある）
xctrace list devices | grep "<デバイス名>"

# 3. Releaseビルド
mcp__XcodeBuildMCP__session-set-defaults({ scheme: "...", configuration: "Release", ... })
# 実機: build_device → install_app_device → bundleIdを控える
# シミュレータ: build_sim → get_app_bundle_id → bundleIdを控える

# 4. 計測モード選択（AskUserQuestion）→ SwiftUIを選択

# 5. 起動方法選択（AskUserQuestion）
#    - 「起動中のアプリに接続」→ PIDを検索して --attach <PID>
#    - 「アプリを起動して計測」→ --launch <bundleId>

# 6. トレースファイル名を生成
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
TRACE_FILE="/tmp/profile_${TIMESTAMP}.trace"
TRACE_SYM_FILE="/tmp/profile_${TIMESTAMP}_sym.trace"
EXPORT_DIR="/tmp/exported_${TIMESTAMP}"

# 7. バックグラウンドでプロファイリング
Bash(run_in_background: true):
  # --attach の場合
  xctrace record --template "SwiftUI" --device "<デバイス>" --output $TRACE_FILE --attach <PID>
  # --launch の場合
  xctrace record --template "SwiftUI" --device "<デバイス>" --output $TRACE_FILE --launch <bundleId>

# 8. ユーザーに停止タイミング確認（AskUserQuestion）
pkill -INT -f "xctrace record"

# 9. シンボル化・エクスポート・解析
xctrace symbolicate --input $TRACE_FILE --output $TRACE_SYM_FILE --dsym <dSYMパス>
<skill_dir>/scripts/export_trace.sh $TRACE_SYM_FILE $EXPORT_DIR
<skill_dir>/scripts/parse_trace.py $EXPORT_DIR --app "<アプリ名>"
```

## References

- xctraceコマンドの詳細は `references/xctrace-commands.md` を参照
- [Creating Flame Graphs from Time Profiler Data](https://benromano.com/blog/instruments-flame-graphs)
- [xctrace man page](https://keith.github.io/xcode-man-pages/xctrace.1.html)
