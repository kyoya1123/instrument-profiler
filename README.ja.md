# Instruments Profiler

[English version / Read in English](README.md)

iOS/macOSアプリのXcode Instrumentsプロファイリングを全自動化するClaude Codeスキル。計測から分析、改善提案まですべて自動で実行します。

## このスキルでできること

Instrumentsのワークフロー全体を自動化:

1. **デバイス選択** — シミュレータと接続デバイスを自動検出
2. **Releaseビルド** — 最適化されたRelease構成でビルド（Debugビルドは計測が不正確）
3. **プロファイリング** — `xctrace record`でSwiftUIまたはApp Launchテンプレートを実行
4. **シンボル化** — dSYMを使ってアプリのシンボルを解決し、読みやすいスタックトレースを生成
5. **分析** — トレースデータをパースして詳細なMarkdownレポートを生成
6. **改善提案** — ホットフレーム、ハング、ヒッチを特定し、具体的な修正方法を提案

## なぜこのスキルが必要か

Xcode Instrumentsは強力だが使いづらい:

- 複雑なGUIと急な学習曲線
- 手動でのテンプレート選択と設定
- 生のトレースデータを解釈するには専門知識が必要
- 自動的なアクション提案がない

**このスキルがすべて解決します。** 「このアプリをプロファイリングして」と言うだけで、具体的な最適化提案を含む完全なパフォーマンスレポートが得られます。

## インストール

### クイックインストール（3ステップ）

```bash
# 1. Skillsディレクトリにクローン
git clone https://github.com/YOUR_USERNAME/instruments-profiler.git ~/.claude/skills/instruments-profiler

# 2. インストールを確認
ls ~/.claude/skills/instruments-profiler/SKILL.md

# 3. Claude Codeを再起動
```

### 別の方法: プラグインとして追加

プロジェクトの `.claude/plugins/` ディレクトリまたはグローバルの `~/.claude/plugins/` に追加します。

## 使い方

### 基本コマンド

Claudeに計測したいことを伝えるだけ:

```
Instrumentsでプロファイリングして
```

```
アプリの起動時間を計測して
```

```
パフォーマンス計測を実行して
```

### プロファイリングモード

| モード | テンプレート | 用途 |
|--------|-------------|------|
| **SwiftUI** | SwiftUI + Time Profiler + Hangs + Hitches | View更新、CPU使用率、UIレスポンス |
| **App Launch** | App Launch | 起動時間、ライブラリロード、初期化 |
| **Time Profiler** | Time Profiler | 汎用CPUプロファイリング |
| **Leaks** | Leaks | メモリリーク検出 |
| **Allocations** | Allocations | メモリ割り当て分析 |
| **Animation Hitches** | Animation Hitches | フレームドロップ検出、スクロール性能 |
| **Energy Log** | Energy Log | バッテリー消費分析（実機のみ） |

### 出力例

#### App Launchレポート

```markdown
## App Launch - ライフサイクルフェーズ

**合計起動時間:** 1234.56 ms (1.23 s)

| フェーズ | 所要時間 (ms) | % |
|---------|--------------|---|
| Static Runtime Init | 150.00 | 12.2% |
| UIKit Init | 300.00 | 24.3% |
| Initial Frame Rendering | 400.00 | 32.4% |

**ステータス:** ⚠️ 許容範囲 - 起動時間の最適化を検討
```

#### SwiftUIパフォーマンスレポート

```markdown
## Hot Frames - Total Time (Top 10)

| 順位 | 関数 | Total (ms) | バイナリ |
|------|------|------------|---------|
| 1 | ContentView.body.getter | 45.00 | MyApp |
| 2 | ListView.body.getter | 32.00 | MyApp |

## Potential Hangs
**合計:** 0
**ステータス:** ✅ OK - ハングなし

## Animation Hitches
**合計:** 2
**ステータス:** ⚠️ 軽微な問題あり
```

## 動作要件

- macOS 14.0以上
- Xcode 16.0以上
- XcodeBuildMCPがインストールされたClaude Code
- iOSシミュレータまたは接続されたiOSデバイス

## 仕組み

```
┌─────────────────────────────────────────────────────────────────┐
│  1. デバイス選択                                                 │
│     list_sims / list_devices → AskUserQuestion                  │
├─────────────────────────────────────────────────────────────────┤
│  2. Releaseビルド                                                │
│     build_sim or build_device → 実機の場合はインストール         │
├─────────────────────────────────────────────────────────────────┤
│  3. プロファイリング                                             │
│     xctrace record --template SwiftUI/AppLaunch                 │
├─────────────────────────────────────────────────────────────────┤
│  4. シンボル化                                                   │
│     xctrace symbolicate --dsym <path>                           │
├─────────────────────────────────────────────────────────────────┤
│  5. エクスポート & 分析                                          │
│     export_trace.sh → parse_trace.py → Markdownレポート         │
└─────────────────────────────────────────────────────────────────┘
```

## トラブルシューティング

| 問題 | 原因 | 解決策 |
|------|------|--------|
| Permission denied | 開発者ツールが未許可 | システム設定 → プライバシー → 開発者ツール |
| Device not found | デバイス名/UDIDが不正 | `xctrace list devices`で確認 |
| Empty trace | 計測時間が短すぎる | プロファイリング中にアプリを操作 |
| シンボルが"unknown" | dSYMがない | ReleaseビルドでdSYMが生成されることを確認 |
| Cannot find process | プロセス検索失敗 | `--attach`の代わりに`--launch`を使用 |

## ファイル構成

```
instruments-profiler/
├── SKILL.md                    # スキル定義（Claudeが読む）
├── scripts/
│   ├── run_profiling.sh        # xctrace recordラッパー
│   ├── export_trace.sh         # xctrace exportの自動化
│   └── parse_trace.py          # トレースデータパーサー & レポート生成
├── references/
│   └── xctrace-commands.md     # xctraceコマンドリファレンス
├── README.md                   # 英語版README
└── README.ja.md                # このファイル（日本語）
```

## コントリビューション

IssueやPull Requestは日本語・英語どちらでも歓迎です！

## ライセンス

MIT License - [LICENSE](LICENSE)を参照

## 関連スキル

- `swiftui-performance-audit` — コードレビューベースのパフォーマンス分析
- `ios-debugger-agent` — XcodeBuildMCPを使ったランタイムデバッグ
