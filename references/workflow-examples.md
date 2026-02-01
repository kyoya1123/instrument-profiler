# 完全ワークフロー例

## App Launchの場合（全自動）

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

## SwiftUIの場合（ユーザー操作が必要）

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

## Leaks/Allocationsの場合

```bash
# 1-6. SwiftUIと同様

# 7. バックグラウンドでプロファイリング
Bash(run_in_background: true):
  xctrace record --template "Leaks" --device "<デバイス>" --output $TRACE_FILE --launch <bundleId>

# 8. ユーザーに操作を促す（AskUserQuestion）
#    "アプリを操作してメモリを使用してください。完了したら停止してください"

# 9. 停止・シンボル化・解析
pkill -INT -f "xctrace record"
xctrace symbolicate --input $TRACE_FILE --output $TRACE_SYM_FILE --dsym <dSYMパス>
<skill_dir>/scripts/export_trace.sh $TRACE_SYM_FILE $EXPORT_DIR
<skill_dir>/scripts/parse_trace.py $EXPORT_DIR --app "<アプリ名>"
```

## Energy Logの場合（実機のみ）

```bash
# 1-6. SwiftUIと同様（ただし実機を選択）

# 7. バックグラウンドでプロファイリング
Bash(run_in_background: true):
  xctrace record --template "Energy Log" --device "<実機UDID>" --output $TRACE_FILE --launch <bundleId>

# 8. ユーザーに操作を促す（AskUserQuestion）
#    "アプリを通常使用してください（ネットワーク操作、バックグラウンド処理など）。完了したら停止してください"

# 9. 停止・解析
pkill -INT -f "xctrace record"
<skill_dir>/scripts/export_trace.sh $TRACE_FILE $EXPORT_DIR
<skill_dir>/scripts/parse_trace.py $EXPORT_DIR --app "<アプリ名>"
```
