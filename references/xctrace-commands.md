# xctrace Command Reference

## Templates

利用可能なテンプレート一覧:
```bash
xcrun xctrace list templates
```

### パフォーマンス関連

| Template | Description |
|----------|-------------|
| `SwiftUI` | SwiftUI View Body更新、依存関係グラフ |
| `Time Profiler` | CPU時間プロファイリング |
| `Hangs` | メインスレッドハング検出 |
| `Animation Hitches` | フレームドロップ・ヒッチ検出 |
| `App Launch` | アプリ起動時間 |
| `Swift Concurrency` | Swift Actors/Tasks分析 |

### メモリ関連

| Template | Description |
|----------|-------------|
| `Leaks` | メモリリーク検出 |
| `Allocations` | メモリ割り当て分析 |

### エネルギー関連

| Template | Description |
|----------|-------------|
| `Energy Log` | バッテリー・電力消費分析（**実機のみ**） |

## Record Commands

### 基本構文

```bash
xcrun xctrace record \
  --template '<template>' \
  --device '<device>' \
  --time-limit <duration> \
  --output <path.trace> \
  [--launch -- <app>] | [--attach <target>]
```

### オプション

| Option | Description |
|--------|-------------|
| `--template '<name>'` | 使用するテンプレート |
| `--device '<name or UDID>'` | ターゲットデバイス |
| `--time-limit <duration>` | 記録時間制限 (例: 30s, 5m) |
| `--output <path>` | 出力.traceファイルパス |
| `--launch -- <app>` | アプリを起動して記録 |
| `--attach <pid or bundle-id>` | 実行中アプリにアタッチ |
| `--instrument '<name>'` | 追加インストゥルメント |
| `--target-stdout -` | 標準出力をキャプチャ |

### 例

**シミュレータでSwiftUIテンプレート:**
```bash
xcrun xctrace record \
  --template 'SwiftUI' \
  --device 'iPhone 17 Pro' \
  --time-limit 30s \
  --output /tmp/profile.trace \
  --launch -- /path/to/App.app
```

**実機にアタッチ:**
```bash
xcrun xctrace record \
  --template 'Time Profiler' \
  --device '00008101-...' \
  --time-limit 60s \
  --output /tmp/profile.trace \
  --attach com.example.app
```

**複数インストゥルメント:**
```bash
xcrun xctrace record \
  --template 'SwiftUI' \
  --instrument 'Time Profiler' \
  --instrument 'Hangs' \
  --time-limit 30s \
  --output /tmp/combined.trace \
  --launch -- /path/to/App.app
```

## Export Commands

### TOC (Table of Contents)

```bash
xcrun xctrace export --input <trace> --toc
```

### 特定テーブルのエクスポート

```bash
xcrun xctrace export \
  --input <trace> \
  --xpath '/trace-toc/run[@number="1"]/data/table[@schema="<schema>"]' \
  --output <output.xml>
```

### よく使うスキーマ

| Schema | Description |
|--------|-------------|
| `time-profile` | Time Profilerサンプル |
| `time-sample` | Time Profilerスタック |
| `hang` | ハング検出結果 |
| `hitch` | ヒッチ検出結果 |
| `swiftui-*` | SwiftUI関連データ |
| `energy-impact` | エネルギー消費データ |

### Track-Based Export (Leaks/Allocations)

Leaks, Allocationsはschema-basedではなくtrack-basedのXPathを使用:

```bash
# Leaks
xcrun xctrace export \
  --input <trace> \
  --xpath '/trace-toc/run[@number="1"]/tracks/track[@name="Leaks"]/details/detail[@name="Leaks"]' \
  --output leaks.xml

# Allocations List
xcrun xctrace export \
  --input <trace> \
  --xpath '/trace-toc/run[@number="1"]/tracks/track[@name="Allocations"]/details/detail[@name="Allocations List"]' \
  --output allocations.xml

# Allocations Statistics
xcrun xctrace export \
  --input <trace> \
  --xpath '/trace-toc/run[@number="1"]/tracks/track[@name="Allocations"]/details/detail[@name="Statistics"]' \
  --output alloc-stats.xml
```

**注意**: Track-based exportはXcode 13以降で対応。

## Device Commands

**デバイス一覧:**
```bash
xcrun xctrace list devices
```

**インストゥルメント一覧:**
```bash
xcrun xctrace list instruments
```

## Troubleshooting

### Permission denied

```
xctrace requires authorization to record.
```

**解決:** システム設定 > プライバシーとセキュリティ > 開発者ツール で許可

### Device not found

**解決:** `xcrun xctrace list devices` でデバイス名/UDIDを確認

### Template not found

**解決:** `xcrun xctrace list templates` でテンプレート名を確認

### Empty trace

**原因:** 計測時間が短い、またはアプリ操作なし

**解決:**
- `--time-limit` を延長
- 計測中にアプリを操作

### Wrong app profiled

**原因:** LaunchServicesが別のアプリを起動

**解決:**
- .appバンドルの完全パスを使用
- または `--attach` モードを使用

### Large XML export

**原因:** 長時間計測で大量データ

**解決:**
- `--time-limit` を短く
- XPathでフィルタリング
- ファイル出力してから処理

## Best Practices

1. **Releaseビルドを使用** - Debugビルドは最適化なしで不正確
2. **適切な計測時間** - 30秒〜1分が目安
3. **計測中にアプリ操作** - ワークロードがないと有用なデータが取れない
4. **dSYMを保持** - シンボル解決に必要
5. **シミュレータより実機** - 正確なパフォーマンス計測には実機推奨
