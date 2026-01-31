#!/usr/bin/env python3
"""
SwiftUI Instruments Profiler - parse_trace.py
xctrace exportで出力されたXMLをパースしてMarkdownレポートを生成

改善点:
- backtrace内のframe要素を正しく解析
- ref属性による参照ノードを解決
- アプリ固有コードのフィルタリング
- Self Time / Total Timeの区別
- Flame Graph用collapsed stack出力
"""

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import argparse


@dataclass
class Frame:
    """スタックフレーム"""
    name: str
    addr: str
    binary: Optional[str] = None


@dataclass
class Sample:
    """プロファイルサンプル"""
    time: str
    thread: str
    process: str
    weight_ms: float
    backtrace: list[Frame]


@dataclass
class SwiftUIUpdate:
    """SwiftUI View更新"""
    start_time: str
    duration_us: float
    description: str
    category: str
    severity: str
    view_name: str


@dataclass
class Hang:
    """ハング情報"""
    start_time: str
    duration_ms: float
    hang_type: str
    thread: str
    process: str


@dataclass
class Hitch:
    """ヒッチ情報"""
    start_time: str
    duration_ms: float
    process: str
    is_system: bool
    description: str


@dataclass
class LifeCyclePeriod:
    """App Launchライフサイクルフェーズ"""
    start_time: str
    duration_ms: float
    period: str
    narrative: str
    process: str


@dataclass
class DyldLibraryLoad:
    """ダイナミックライブラリロード情報"""
    start_time: str
    duration_ms: float
    library_name: str
    library_path: str


@dataclass
class MemoryLeak:
    """メモリリーク情報"""
    address: str
    size_bytes: int
    responsible_frame: str
    responsible_library: str
    backtrace: list[Frame]
    leak_type: str


@dataclass
class AllocationStatistics:
    """メモリ割り当て統計"""
    category: str
    persistent_bytes: int
    persistent_count: int
    total_bytes: int
    total_count: int


@dataclass
class EnergyUsage:
    """エネルギー使用量"""
    timestamp: str
    cpu_usage: float
    gpu_usage: float
    energy_impact: float
    process: str


class TimeProfileParser:
    """Time Profile XMLパーサー"""

    def __init__(self, xml_path: Path):
        self.xml_path = xml_path
        self.id_cache: dict[str, ET.Element] = {}
        self.samples: list[Sample] = []

    def parse(self) -> list[Sample]:
        """XMLをパースしてサンプルリストを返す"""
        tree = ET.parse(self.xml_path)
        root = tree.getroot()

        # IDキャッシュを構築（ref解決用）
        self._build_id_cache(root)

        # 各rowをパース
        for row in root.iter("row"):
            sample = self._parse_row(row)
            if sample:
                self.samples.append(sample)

        return self.samples

    def _build_id_cache(self, root: ET.Element):
        """id属性を持つ全要素をキャッシュ"""
        for elem in root.iter():
            elem_id = elem.get("id")
            if elem_id:
                self.id_cache[elem_id] = elem

    def _resolve_ref(self, elem: ET.Element) -> ET.Element:
        """ref属性を解決して元の要素を返す"""
        ref = elem.get("ref")
        if ref and ref in self.id_cache:
            return self.id_cache[ref]
        return elem

    def _parse_row(self, row: ET.Element) -> Optional[Sample]:
        """行をパースしてSampleを返す"""
        # 時間
        time_elem = row.find(".//sample-time")
        time_str = ""
        if time_elem is not None:
            time_elem = self._resolve_ref(time_elem)
            time_str = time_elem.get("fmt", "")

        # スレッド
        thread_elem = row.find(".//thread")
        thread_str = ""
        if thread_elem is not None:
            thread_elem = self._resolve_ref(thread_elem)
            thread_str = thread_elem.get("fmt", "")

        # プロセス
        process_elem = row.find(".//process")
        process_str = ""
        if process_elem is not None:
            process_elem = self._resolve_ref(process_elem)
            process_str = process_elem.get("fmt", "")

        # Weight
        weight_elem = row.find(".//weight")
        weight_ms = 1.0
        if weight_elem is not None:
            weight_elem = self._resolve_ref(weight_elem)
            fmt = weight_elem.get("fmt", "1 ms")
            try:
                weight_ms = float(fmt.replace("ms", "").replace(",", "").strip())
            except ValueError:
                pass

        # Backtrace
        backtrace = []
        bt_elem = row.find(".//backtrace")
        if bt_elem is not None:
            bt_elem = self._resolve_ref(bt_elem)
            for frame_elem in bt_elem.iter("frame"):
                frame_elem = self._resolve_ref(frame_elem)
                name = frame_elem.get("name", "")
                addr = frame_elem.get("addr", "")

                # バイナリ名を取得（ref解決を含む）
                binary = None
                for child in frame_elem:
                    if child.tag == "binary":
                        # refがあれば解決
                        ref = child.get("ref")
                        if ref and ref in self.id_cache:
                            binary = self.id_cache[ref].get("name", "")
                        else:
                            binary = child.get("name", "")
                        break

                if name:  # 名前がある場合のみ追加
                    backtrace.append(Frame(name=name, addr=addr, binary=binary))

        if not backtrace:
            return None

        return Sample(
            time=time_str,
            thread=thread_str,
            process=process_str,
            weight_ms=weight_ms,
            backtrace=backtrace
        )


class ProfileAnalyzer:
    """プロファイルデータの分析"""

    def __init__(self, samples: list[Sample]):
        self.samples = samples

    def get_hot_frames(self, top_n: int = 30,
                       filter_binary: Optional[str] = None,
                       exclude_system: bool = False) -> list[tuple[str, int, float, Optional[str]]]:
        """
        Total Timeでソートしたホットフレームを返す

        Returns: [(function_name, count, total_weight_ms, binary_name), ...]
        """
        frame_counts: dict[str, int] = defaultdict(int)
        frame_weights: dict[str, float] = defaultdict(float)
        frame_binary: dict[str, str] = {}

        for sample in self.samples:
            seen_in_sample: set[str] = set()
            for frame in sample.backtrace:
                # アドレスのみはスキップ
                if frame.name.startswith("0x"):
                    continue

                # フィルタリング
                if filter_binary and frame.binary != filter_binary:
                    continue
                if exclude_system and self._is_system_frame(frame):
                    continue

                # 同一サンプル内の重複はカウントしない（Total Time計算）
                if frame.name not in seen_in_sample:
                    frame_counts[frame.name] += 1
                    frame_weights[frame.name] += sample.weight_ms
                    seen_in_sample.add(frame.name)
                    if frame.binary:
                        frame_binary[frame.name] = frame.binary

        sorted_frames = sorted(frame_weights.items(), key=lambda x: x[1], reverse=True)
        return [
            (name, frame_counts[name], weight, frame_binary.get(name))
            for name, weight in sorted_frames[:top_n]
        ]

    def get_self_time_frames(self, top_n: int = 30,
                             filter_binary: Optional[str] = None) -> list[tuple[str, int, float, Optional[str]]]:
        """
        Self Time（リーフフレーム）でソートしたフレームを返す
        スタックの一番上（最初のフレーム）のみカウント
        """
        frame_counts: dict[str, int] = defaultdict(int)
        frame_weights: dict[str, float] = defaultdict(float)
        frame_binary: dict[str, str] = {}

        for sample in self.samples:
            # スタックの一番上（リーフ）を取得
            leaf_frame = None
            for frame in sample.backtrace:
                if not frame.name.startswith("0x"):
                    if filter_binary and frame.binary != filter_binary:
                        continue
                    leaf_frame = frame
                    break

            if leaf_frame:
                frame_counts[leaf_frame.name] += 1
                frame_weights[leaf_frame.name] += sample.weight_ms
                if leaf_frame.binary:
                    frame_binary[leaf_frame.name] = leaf_frame.binary

        sorted_frames = sorted(frame_weights.items(), key=lambda x: x[1], reverse=True)
        return [
            (name, frame_counts[name], weight, frame_binary.get(name))
            for name, weight in sorted_frames[:top_n]
        ]

    def get_app_frames(self, app_binary: str, top_n: int = 30) -> list[tuple[str, int, float]]:
        """アプリ固有のフレームを返す"""
        frame_counts: dict[str, int] = defaultdict(int)
        frame_weights: dict[str, float] = defaultdict(float)

        for sample in self.samples:
            seen_in_sample: set[str] = set()
            for frame in sample.backtrace:
                if frame.name.startswith("0x"):
                    continue
                # アプリバイナリでフィルタリング
                if not frame.binary or app_binary.lower() not in frame.binary.lower():
                    continue
                if frame.name not in seen_in_sample:
                    frame_counts[frame.name] += 1
                    frame_weights[frame.name] += sample.weight_ms
                    seen_in_sample.add(frame.name)

        sorted_frames = sorted(frame_weights.items(), key=lambda x: x[1], reverse=True)
        return [
            (name, frame_counts[name], weight)
            for name, weight in sorted_frames[:top_n]
        ]

    def get_swiftui_frames(self, top_n: int = 20) -> list[tuple[str, int, float]]:
        """SwiftUI関連のフレームを返す"""
        swiftui_keywords = ["SwiftUI", "AG::", "View", "Layout", "DisplayList", "Attribute"]
        results = []

        for name, count, weight, binary in self.get_hot_frames(top_n=100):
            if any(kw in name for kw in swiftui_keywords) or (binary and "SwiftUI" in binary):
                results.append((name, count, weight))
                if len(results) >= top_n:
                    break

        return results

    def generate_collapsed_stacks(self, filter_binary: Optional[str] = None) -> str:
        """
        Flame Graph用のcollapsed stack形式を生成
        Format: frame1;frame2;frame3 weight
        """
        lines = []
        for sample in self.samples:
            stack = []
            for frame in reversed(sample.backtrace):  # 逆順（rootからleafへ）
                if frame.name.startswith("0x"):
                    continue
                if filter_binary and frame.binary and filter_binary.lower() not in frame.binary.lower():
                    continue
                # セミコロンとスペースをエスケープ
                clean_name = frame.name.replace(";", ":").replace(" ", "_")
                stack.append(clean_name)

            if stack:
                lines.append(f"{';'.join(stack)} {int(sample.weight_ms)}")

        return "\n".join(lines)

    def _is_system_frame(self, frame: Frame) -> bool:
        """システムフレームかどうか判定"""
        system_prefixes = [
            "dyld", "libsystem", "libobjc", "libdispatch",
            "CoreFoundation", "Foundation", "UIKit", "QuartzCore",
            "_CF", "_NS", "objc_"
        ]
        return any(frame.name.startswith(p) or (frame.binary and frame.binary.startswith(p))
                   for p in system_prefixes)


class SwiftUIUpdatesParser:
    """SwiftUI Updates XMLパーサー"""

    def __init__(self, xml_path: Path):
        self.xml_path = xml_path
        self.id_cache: dict[str, ET.Element] = {}
        self.updates: list[SwiftUIUpdate] = []

    def parse(self) -> list[SwiftUIUpdate]:
        """XMLをパースしてSwiftUI更新リストを返す"""
        try:
            tree = ET.parse(self.xml_path)
            root = tree.getroot()
        except Exception as e:
            print(f"Warning: Could not parse SwiftUI updates: {e}", file=sys.stderr)
            return []

        # IDキャッシュを構築
        for elem in root.iter():
            elem_id = elem.get("id")
            if elem_id:
                self.id_cache[elem_id] = elem

        for row in root.iter("row"):
            update = self._parse_row(row)
            if update:
                self.updates.append(update)

        return self.updates

    def _resolve_ref(self, elem: ET.Element) -> ET.Element:
        ref = elem.get("ref")
        if ref and ref in self.id_cache:
            return self.id_cache[ref]
        return elem

    def _parse_row(self, row: ET.Element) -> Optional[SwiftUIUpdate]:
        # start-time
        start_elem = row.find(".//start-time")
        start_time = ""
        if start_elem is not None:
            start_elem = self._resolve_ref(start_elem)
            start_time = start_elem.get("fmt", "")

        # duration (nanoseconds -> microseconds)
        duration_elem = row.find(".//duration")
        duration_us = 0.0
        if duration_elem is not None:
            duration_elem = self._resolve_ref(duration_elem)
            try:
                duration_ns = int(duration_elem.text or "0")
                duration_us = duration_ns / 1000.0
            except ValueError:
                pass

        # description (string element with description info)
        desc_elem = row.find(".//string[@id]")
        description = ""
        if desc_elem is not None:
            desc_elem = self._resolve_ref(desc_elem)
            description = desc_elem.get("fmt", "")

        # category
        category = ""
        for string_elem in row.iter("string"):
            resolved = self._resolve_ref(string_elem)
            fmt = resolved.get("fmt", "")
            if fmt in ["Update", "Layout", "Render"]:
                category = fmt
                break

        # severity
        severity_elem = row.find(".//event-concept")
        severity = ""
        if severity_elem is not None:
            severity_elem = self._resolve_ref(severity_elem)
            severity = severity_elem.get("fmt", "")

        # view-name (look for specific pattern in description)
        view_name = ""
        if "ViewBodyAccessor<" in description:
            start = description.find("ViewBodyAccessor<") + len("ViewBodyAccessor<")
            end = description.find(">", start)
            if end > start:
                view_name = description[start:end]

        if not description:
            return None

        return SwiftUIUpdate(
            start_time=start_time,
            duration_us=duration_us,
            description=description,
            category=category,
            severity=severity,
            view_name=view_name
        )

    def get_view_body_stats(self) -> list[tuple[str, int, float, float]]:
        """View Body別の統計を返す: [(view_name, count, avg_duration_us, total_duration_us)]"""
        stats: dict[str, list[float]] = defaultdict(list)

        for update in self.updates:
            if update.view_name:
                stats[update.view_name].append(update.duration_us)

        results = []
        for view_name, durations in stats.items():
            count = len(durations)
            total = sum(durations)
            avg = total / count if count > 0 else 0
            results.append((view_name, count, avg, total))

        return sorted(results, key=lambda x: x[3], reverse=True)

    def get_slow_updates(self, threshold_us: float = 1000.0) -> list[SwiftUIUpdate]:
        """閾値より遅い更新を返す（デフォルト1ms以上）"""
        return [u for u in self.updates if u.duration_us >= threshold_us]


class HangParser:
    """Potential Hangs XMLパーサー"""

    def __init__(self, xml_path: Path):
        self.xml_path = xml_path
        self.id_cache: dict[str, ET.Element] = {}
        self.hangs: list[Hang] = []

    def parse(self) -> list[Hang]:
        """XMLをパースしてハングリストを返す"""
        try:
            tree = ET.parse(self.xml_path)
            root = tree.getroot()
        except Exception as e:
            print(f"Warning: Could not parse hangs: {e}", file=sys.stderr)
            return []

        # IDキャッシュを構築
        for elem in root.iter():
            elem_id = elem.get("id")
            if elem_id:
                self.id_cache[elem_id] = elem

        for row in root.iter("row"):
            hang = self._parse_row(row)
            if hang:
                self.hangs.append(hang)

        return self.hangs

    def _resolve_ref(self, elem: ET.Element) -> ET.Element:
        ref = elem.get("ref")
        if ref and ref in self.id_cache:
            return self.id_cache[ref]
        return elem

    def _parse_row(self, row: ET.Element) -> Optional[Hang]:
        # start-time
        start_elem = row.find(".//start-time")
        start_time = ""
        if start_elem is not None:
            start_elem = self._resolve_ref(start_elem)
            start_time = start_elem.get("fmt", "")

        # duration (nanoseconds -> milliseconds)
        duration_elem = row.find(".//duration")
        duration_ms = 0.0
        if duration_elem is not None:
            duration_elem = self._resolve_ref(duration_elem)
            try:
                duration_ns = int(duration_elem.text or "0")
                duration_ms = duration_ns / 1_000_000.0
            except ValueError:
                pass

        # hang-type
        hang_type_elem = row.find(".//hang-type")
        hang_type = ""
        if hang_type_elem is not None:
            hang_type_elem = self._resolve_ref(hang_type_elem)
            hang_type = hang_type_elem.get("fmt", "")

        # thread
        thread_elem = row.find(".//thread")
        thread = ""
        if thread_elem is not None:
            thread_elem = self._resolve_ref(thread_elem)
            thread = thread_elem.get("fmt", "")

        # process
        process_elem = row.find(".//process")
        process = ""
        if process_elem is not None:
            process_elem = self._resolve_ref(process_elem)
            process = process_elem.get("fmt", "")

        return Hang(
            start_time=start_time,
            duration_ms=duration_ms,
            hang_type=hang_type,
            thread=thread,
            process=process
        )


class HitchParser:
    """Hitches XMLパーサー"""

    def __init__(self, xml_path: Path):
        self.xml_path = xml_path
        self.id_cache: dict[str, ET.Element] = {}
        self.hitches: list[Hitch] = []

    def parse(self) -> list[Hitch]:
        """XMLをパースしてヒッチリストを返す"""
        try:
            tree = ET.parse(self.xml_path)
            root = tree.getroot()
        except Exception as e:
            print(f"Warning: Could not parse hitches: {e}", file=sys.stderr)
            return []

        # IDキャッシュを構築
        for elem in root.iter():
            elem_id = elem.get("id")
            if elem_id:
                self.id_cache[elem_id] = elem

        for row in root.iter("row"):
            hitch = self._parse_row(row)
            if hitch:
                self.hitches.append(hitch)

        return self.hitches

    def _resolve_ref(self, elem: ET.Element) -> ET.Element:
        ref = elem.get("ref")
        if ref and ref in self.id_cache:
            return self.id_cache[ref]
        return elem

    def _parse_row(self, row: ET.Element) -> Optional[Hitch]:
        # start-time
        start_elem = row.find(".//start-time")
        start_time = ""
        if start_elem is not None:
            start_elem = self._resolve_ref(start_elem)
            start_time = start_elem.get("fmt", "")

        # duration (nanoseconds -> milliseconds)
        duration_elem = row.find(".//duration")
        duration_ms = 0.0
        if duration_elem is not None:
            duration_elem = self._resolve_ref(duration_elem)
            try:
                duration_ns = int(duration_elem.text or "0")
                duration_ms = duration_ns / 1_000_000.0
            except ValueError:
                pass

        # process
        process_elem = row.find(".//process")
        process = ""
        if process_elem is not None:
            process_elem = self._resolve_ref(process_elem)
            process = process_elem.get("fmt", "")

        # is-system
        is_system_elem = row.find(".//boolean")
        is_system = False
        if is_system_elem is not None:
            is_system_elem = self._resolve_ref(is_system_elem)
            is_system = is_system_elem.get("fmt", "").lower() == "true"

        # narrative-description
        desc_elem = None
        for string_elem in row.iter("string"):
            resolved = self._resolve_ref(string_elem)
            if "Potential Issue" in str(resolved.get("fmt", "") or ""):
                desc_elem = resolved
                break
        description = desc_elem.get("fmt", "") if desc_elem is not None else ""

        return Hitch(
            start_time=start_time,
            duration_ms=duration_ms,
            process=process,
            is_system=is_system,
            description=description
        )


class LifeCyclePeriodParser:
    """App Launch Life Cycle Period XMLパーサー"""

    def __init__(self, xml_path: Path):
        self.xml_path = xml_path
        self.id_cache: dict[str, ET.Element] = {}
        self.periods: list[LifeCyclePeriod] = []

    def parse(self) -> list[LifeCyclePeriod]:
        """XMLをパースしてライフサイクルフェーズリストを返す"""
        try:
            tree = ET.parse(self.xml_path)
            root = tree.getroot()
        except Exception as e:
            print(f"Warning: Could not parse life-cycle-period: {e}", file=sys.stderr)
            return []

        # IDキャッシュを構築
        for elem in root.iter():
            elem_id = elem.get("id")
            if elem_id:
                self.id_cache[elem_id] = elem

        for row in root.iter("row"):
            period = self._parse_row(row)
            if period:
                self.periods.append(period)

        return self.periods

    def _resolve_ref(self, elem: ET.Element) -> ET.Element:
        ref = elem.get("ref")
        if ref and ref in self.id_cache:
            return self.id_cache[ref]
        return elem

    def _parse_row(self, row: ET.Element) -> Optional[LifeCyclePeriod]:
        # start-time
        start_elem = row.find(".//start-time")
        start_time = ""
        if start_elem is not None:
            start_elem = self._resolve_ref(start_elem)
            start_time = start_elem.get("fmt", "")

        # duration (nanoseconds -> milliseconds)
        duration_elem = row.find(".//duration")
        duration_ms = 0.0
        if duration_elem is not None:
            duration_elem = self._resolve_ref(duration_elem)
            try:
                duration_ns = int(duration_elem.text or "0")
                duration_ms = duration_ns / 1_000_000.0
            except ValueError:
                # fmt属性から取得を試みる
                fmt = duration_elem.get("fmt", "")
                if "ms" in fmt:
                    try:
                        duration_ms = float(fmt.replace("ms", "").replace(",", "").strip())
                    except ValueError:
                        pass
                elif "s" in fmt:
                    try:
                        duration_ms = float(fmt.replace("s", "").replace(",", "").strip()) * 1000
                    except ValueError:
                        pass

        # app-period
        period_elem = row.find(".//app-period")
        period = ""
        if period_elem is not None:
            period_elem = self._resolve_ref(period_elem)
            period = period_elem.get("fmt", "") or period_elem.text or ""

        # narrative
        narrative_elem = row.find(".//narrative-text")
        narrative = ""
        if narrative_elem is not None:
            narrative_elem = self._resolve_ref(narrative_elem)
            narrative = narrative_elem.get("fmt", "") or narrative_elem.text or ""

        # process
        process_elem = row.find(".//process")
        process = ""
        if process_elem is not None:
            process_elem = self._resolve_ref(process_elem)
            process = process_elem.get("fmt", "")

        if not period:
            return None

        return LifeCyclePeriod(
            start_time=start_time,
            duration_ms=duration_ms,
            period=period,
            narrative=narrative,
            process=process
        )


class DyldLibraryLoadParser:
    """dyld-library-load XMLパーサー"""

    def __init__(self, xml_path: Path):
        self.xml_path = xml_path
        self.id_cache: dict[str, ET.Element] = {}
        self.loads: list[DyldLibraryLoad] = []

    def parse(self) -> list[DyldLibraryLoad]:
        """XMLをパースしてライブラリロードリストを返す"""
        try:
            tree = ET.parse(self.xml_path)
            root = tree.getroot()
        except Exception as e:
            print(f"Warning: Could not parse dyld-library-load: {e}", file=sys.stderr)
            return []

        # IDキャッシュを構築
        for elem in root.iter():
            elem_id = elem.get("id")
            if elem_id:
                self.id_cache[elem_id] = elem

        for row in root.iter("row"):
            load = self._parse_row(row)
            if load:
                self.loads.append(load)

        return self.loads

    def _resolve_ref(self, elem: ET.Element) -> ET.Element:
        ref = elem.get("ref")
        if ref and ref in self.id_cache:
            return self.id_cache[ref]
        return elem

    def _parse_row(self, row: ET.Element) -> Optional[DyldLibraryLoad]:
        # start-time
        start_elem = row.find(".//start-time")
        start_time = ""
        if start_elem is not None:
            start_elem = self._resolve_ref(start_elem)
            start_time = start_elem.get("fmt", "")

        # duration (nanoseconds -> milliseconds)
        duration_elem = row.find(".//duration")
        duration_ms = 0.0
        if duration_elem is not None:
            duration_elem = self._resolve_ref(duration_elem)
            try:
                duration_ns = int(duration_elem.text or "0")
                duration_ms = duration_ns / 1_000_000.0
            except ValueError:
                fmt = duration_elem.get("fmt", "")
                if "ms" in fmt:
                    try:
                        duration_ms = float(fmt.replace("ms", "").replace(",", "").strip())
                    except ValueError:
                        pass
                elif "µs" in fmt:
                    try:
                        duration_ms = float(fmt.replace("µs", "").replace(",", "").strip()) / 1000
                    except ValueError:
                        pass

        # library name/path (look for file-path or string elements)
        library_name = ""
        library_path = ""

        file_path_elem = row.find(".//file-path")
        if file_path_elem is not None:
            file_path_elem = self._resolve_ref(file_path_elem)
            library_path = file_path_elem.get("fmt", "") or file_path_elem.text or ""
            # Extract library name from path
            if library_path:
                library_name = library_path.split("/")[-1]

        # Fallback to string elements
        if not library_name:
            for string_elem in row.iter("string"):
                resolved = self._resolve_ref(string_elem)
                fmt = resolved.get("fmt", "")
                if fmt and ("/" in fmt or ".dylib" in fmt or ".framework" in fmt):
                    library_path = fmt
                    library_name = fmt.split("/")[-1]
                    break

        if not library_name:
            return None

        return DyldLibraryLoad(
            start_time=start_time,
            duration_ms=duration_ms,
            library_name=library_name,
            library_path=library_path
        )


class LeaksParser:
    """Memory Leaks XMLパーサー"""

    def __init__(self, xml_path: Path):
        self.xml_path = xml_path
        self.id_cache: dict[str, ET.Element] = {}
        self.leaks: list[MemoryLeak] = []

    def parse(self) -> list[MemoryLeak]:
        """XMLをパースしてリークリストを返す"""
        try:
            tree = ET.parse(self.xml_path)
            root = tree.getroot()
        except Exception as e:
            print(f"Warning: Could not parse leaks: {e}", file=sys.stderr)
            return []

        # IDキャッシュを構築
        for elem in root.iter():
            elem_id = elem.get("id")
            if elem_id:
                self.id_cache[elem_id] = elem

        for row in root.iter("row"):
            leak = self._parse_row(row)
            if leak:
                self.leaks.append(leak)

        return self.leaks

    def _resolve_ref(self, elem: ET.Element) -> ET.Element:
        ref = elem.get("ref")
        if ref and ref in self.id_cache:
            return self.id_cache[ref]
        return elem

    def _parse_row(self, row: ET.Element) -> Optional[MemoryLeak]:
        # address
        addr_elem = row.find(".//address")
        address = ""
        if addr_elem is not None:
            addr_elem = self._resolve_ref(addr_elem)
            address = addr_elem.get("fmt", "") or addr_elem.text or ""

        # size
        size_elem = row.find(".//size")
        size_bytes = 0
        if size_elem is not None:
            size_elem = self._resolve_ref(size_elem)
            try:
                size_bytes = int(size_elem.text or "0")
            except ValueError:
                fmt = size_elem.get("fmt", "")
                if "bytes" in fmt.lower():
                    try:
                        size_bytes = int(fmt.split()[0].replace(",", ""))
                    except (ValueError, IndexError):
                        pass

        # responsible-frame
        frame_elem = row.find(".//symbol")
        responsible_frame = ""
        if frame_elem is not None:
            frame_elem = self._resolve_ref(frame_elem)
            responsible_frame = frame_elem.get("name", "") or frame_elem.get("fmt", "")

        # responsible-library
        binary_elem = row.find(".//binary")
        responsible_library = ""
        if binary_elem is not None:
            binary_elem = self._resolve_ref(binary_elem)
            responsible_library = binary_elem.get("name", "") or binary_elem.get("fmt", "")

        # leak-type
        type_elem = row.find(".//leak-type")
        leak_type = "Leak"
        if type_elem is not None:
            type_elem = self._resolve_ref(type_elem)
            leak_type = type_elem.get("fmt", "") or type_elem.text or "Leak"

        # backtrace
        backtrace = []
        bt_elem = row.find(".//backtrace")
        if bt_elem is not None:
            bt_elem = self._resolve_ref(bt_elem)
            for frame_elem in bt_elem.iter("frame"):
                frame_elem = self._resolve_ref(frame_elem)
                name = frame_elem.get("name", "")
                addr = frame_elem.get("addr", "")
                if name:
                    backtrace.append(Frame(name=name, addr=addr, binary=None))

        if not address:
            return None

        return MemoryLeak(
            address=address,
            size_bytes=size_bytes,
            responsible_frame=responsible_frame,
            responsible_library=responsible_library,
            backtrace=backtrace,
            leak_type=leak_type
        )

    def get_leak_summary(self) -> dict:
        """リークのサマリー統計を取得"""
        total_bytes = sum(l.size_bytes for l in self.leaks)
        by_library: dict[str, list[MemoryLeak]] = defaultdict(list)
        by_frame: dict[str, list[MemoryLeak]] = defaultdict(list)

        for leak in self.leaks:
            if leak.responsible_library:
                by_library[leak.responsible_library].append(leak)
            if leak.responsible_frame:
                by_frame[leak.responsible_frame].append(leak)

        return {
            "total_count": len(self.leaks),
            "total_bytes": total_bytes,
            "by_library": {k: (len(v), sum(l.size_bytes for l in v))
                          for k, v in sorted(by_library.items(),
                                            key=lambda x: sum(l.size_bytes for l in x[1]),
                                            reverse=True)},
            "by_frame": {k: (len(v), sum(l.size_bytes for l in v))
                        for k, v in sorted(by_frame.items(),
                                          key=lambda x: sum(l.size_bytes for l in x[1]),
                                          reverse=True)[:20]}
        }


class AllocationStatisticsParser:
    """Allocations Statistics XMLパーサー"""

    def __init__(self, xml_path: Path):
        self.xml_path = xml_path
        self.id_cache: dict[str, ET.Element] = {}
        self.statistics: list[AllocationStatistics] = []

    def parse(self) -> list[AllocationStatistics]:
        """XMLをパースして統計リストを返す"""
        try:
            tree = ET.parse(self.xml_path)
            root = tree.getroot()
        except Exception as e:
            print(f"Warning: Could not parse allocation statistics: {e}", file=sys.stderr)
            return []

        for elem in root.iter():
            elem_id = elem.get("id")
            if elem_id:
                self.id_cache[elem_id] = elem

        for row in root.iter("row"):
            stat = self._parse_row(row)
            if stat:
                self.statistics.append(stat)

        return self.statistics

    def _resolve_ref(self, elem: ET.Element) -> ET.Element:
        ref = elem.get("ref")
        if ref and ref in self.id_cache:
            return self.id_cache[ref]
        return elem

    def _parse_bytes(self, elem: Optional[ET.Element]) -> int:
        """バイト数をパース"""
        if elem is None:
            return 0
        elem = self._resolve_ref(elem)
        try:
            return int(elem.text or "0")
        except ValueError:
            fmt = elem.get("fmt", "")
            try:
                parts = fmt.lower().replace(",", "").split()
                if len(parts) >= 2:
                    val = float(parts[0])
                    unit = parts[1]
                    multipliers = {"bytes": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3}
                    return int(val * multipliers.get(unit, 1))
                return int(float(parts[0]))
            except (ValueError, IndexError):
                return 0

    def _parse_row(self, row: ET.Element) -> Optional[AllocationStatistics]:
        # category
        cat_elem = row.find(".//category")
        category = ""
        if cat_elem is not None:
            cat_elem = self._resolve_ref(cat_elem)
            category = cat_elem.get("fmt", "") or cat_elem.text or ""

        # persistent bytes/count
        persistent_bytes = self._parse_bytes(row.find(".//persistent-bytes"))
        persistent_count_elem = row.find(".//persistent-count")
        persistent_count = 0
        if persistent_count_elem is not None:
            try:
                persistent_count = int(self._resolve_ref(persistent_count_elem).text or "0")
            except ValueError:
                pass

        # total bytes/count
        total_bytes = self._parse_bytes(row.find(".//total-bytes"))
        total_count_elem = row.find(".//total-count")
        total_count = 0
        if total_count_elem is not None:
            try:
                total_count = int(self._resolve_ref(total_count_elem).text or "0")
            except ValueError:
                pass

        if not category:
            return None

        return AllocationStatistics(
            category=category,
            persistent_bytes=persistent_bytes,
            persistent_count=persistent_count,
            total_bytes=total_bytes,
            total_count=total_count
        )

    def get_top_categories(self, top_n: int = 20, by: str = "persistent") -> list[AllocationStatistics]:
        """上位カテゴリを取得"""
        if by == "persistent":
            return sorted(self.statistics, key=lambda x: x.persistent_bytes, reverse=True)[:top_n]
        else:
            return sorted(self.statistics, key=lambda x: x.total_bytes, reverse=True)[:top_n]


class EnergyUsageParser:
    """Energy Usage XMLパーサー"""

    def __init__(self, xml_path: Path):
        self.xml_path = xml_path
        self.id_cache: dict[str, ET.Element] = {}
        self.samples: list[EnergyUsage] = []

    def parse(self) -> list[EnergyUsage]:
        """XMLをパースしてエネルギー使用量リストを返す"""
        try:
            tree = ET.parse(self.xml_path)
            root = tree.getroot()
        except Exception as e:
            print(f"Warning: Could not parse energy usage: {e}", file=sys.stderr)
            return []

        for elem in root.iter():
            elem_id = elem.get("id")
            if elem_id:
                self.id_cache[elem_id] = elem

        for row in root.iter("row"):
            sample = self._parse_row(row)
            if sample:
                self.samples.append(sample)

        return self.samples

    def _resolve_ref(self, elem: ET.Element) -> ET.Element:
        ref = elem.get("ref")
        if ref and ref in self.id_cache:
            return self.id_cache[ref]
        return elem

    def _parse_percentage(self, elem: Optional[ET.Element]) -> float:
        """パーセンテージ値をパース"""
        if elem is None:
            return 0.0
        elem = self._resolve_ref(elem)
        fmt = elem.get("fmt", "") or elem.text or ""
        try:
            return float(fmt.replace("%", "").strip())
        except ValueError:
            return 0.0

    def _parse_row(self, row: ET.Element) -> Optional[EnergyUsage]:
        # timestamp
        time_elem = row.find(".//sample-time")
        timestamp = ""
        if time_elem is not None:
            time_elem = self._resolve_ref(time_elem)
            timestamp = time_elem.get("fmt", "")

        # cpu-usage
        cpu_usage = self._parse_percentage(row.find(".//cpu-usage"))

        # gpu-usage
        gpu_usage = self._parse_percentage(row.find(".//gpu-usage"))

        # energy-impact
        impact_elem = row.find(".//energy-impact")
        energy_impact = 0.0
        if impact_elem is not None:
            impact_elem = self._resolve_ref(impact_elem)
            try:
                energy_impact = float(impact_elem.get("fmt", "") or impact_elem.text or "0")
            except ValueError:
                pass

        # process
        process_elem = row.find(".//process")
        process = ""
        if process_elem is not None:
            process_elem = self._resolve_ref(process_elem)
            process = process_elem.get("fmt", "")

        return EnergyUsage(
            timestamp=timestamp,
            cpu_usage=cpu_usage,
            gpu_usage=gpu_usage,
            energy_impact=energy_impact,
            process=process
        )

    def get_average_usage(self) -> dict:
        """平均使用量統計を取得"""
        if not self.samples:
            return {}

        n = len(self.samples)
        return {
            "avg_cpu": sum(s.cpu_usage for s in self.samples) / n,
            "avg_gpu": sum(s.gpu_usage for s in self.samples) / n,
            "avg_energy_impact": sum(s.energy_impact for s in self.samples) / n,
            "max_cpu": max(s.cpu_usage for s in self.samples),
            "max_gpu": max(s.gpu_usage for s in self.samples),
            "max_energy_impact": max(s.energy_impact for s in self.samples)
        }

    def get_high_energy_samples(self, threshold: float = 10.0) -> list[EnergyUsage]:
        """閾値以上のエネルギー消費サンプルを取得"""
        return [s for s in self.samples if s.energy_impact >= threshold]


def parse_toc(toc_path: Path) -> list[str]:
    """TOCからスキーマ一覧を抽出"""
    schemas = []
    try:
        tree = ET.parse(toc_path)
        root = tree.getroot()
        for table in root.iter("table"):
            schema = table.get("schema")
            if schema:
                schemas.append(schema)
    except Exception as e:
        print(f"Warning: Could not parse TOC: {e}", file=sys.stderr)
    return schemas


def generate_report(export_dir: Path, app_name: Optional[str] = None) -> str:
    """レポートを生成"""
    lines = []
    lines.append("# Instruments Profiling Report")
    lines.append("")

    # TOC解析
    toc_path = export_dir / "toc.xml"
    if toc_path.exists():
        schemas = parse_toc(toc_path)
        lines.append("## Available Schemas")
        lines.append("")
        for schema in schemas:
            lines.append(f"- {schema}")
        lines.append("")

    # App Launch - Life Cycle Periods
    life_cycle_path = export_dir / "life-cycle-period.xml"
    if life_cycle_path.exists():
        lc_parser = LifeCyclePeriodParser(life_cycle_path)
        periods = lc_parser.parse()

        if periods:
            lines.append("## App Launch - Life Cycle Phases")
            lines.append("")

            # 合計時間を計算
            total_ms = sum(p.duration_ms for p in periods)
            lines.append(f"**Total Launch Time:** {total_ms:.2f} ms ({total_ms/1000:.2f} s)")
            lines.append("")

            lines.append("| Phase | Duration (ms) | % | Description |")
            lines.append("|-------|---------------|---|-------------|")

            for period in periods:
                pct = (period.duration_ms / total_ms * 100) if total_ms > 0 else 0
                desc = period.narrative[:50] + "..." if len(period.narrative) > 50 else period.narrative
                lines.append(f"| {period.period} | {period.duration_ms:.2f} | {pct:.1f}% | {desc} |")
            lines.append("")

            # 起動パフォーマンス評価
            lines.append("### Launch Performance Assessment")
            lines.append("")
            if total_ms < 400:
                lines.append("**Status:** ✅ Excellent - App launches in under 400ms")
            elif total_ms < 1000:
                lines.append("**Status:** ✅ Good - App launches in under 1 second")
            elif total_ms < 2000:
                lines.append("**Status:** ⚠️ Acceptable - Consider optimizing launch time")
            else:
                lines.append(f"**Status:** ❌ Slow - Launch time ({total_ms/1000:.2f}s) exceeds 2 seconds")
            lines.append("")

    # App Launch - dyld Library Loads
    dyld_path = export_dir / "dyld-library-load.xml"
    if dyld_path.exists():
        dyld_parser = DyldLibraryLoadParser(dyld_path)
        loads = dyld_parser.parse()

        if loads:
            lines.append("## App Launch - Library Loading")
            lines.append("")

            total_load_ms = sum(l.duration_ms for l in loads)
            lines.append(f"**Total Libraries:** {len(loads)}")
            lines.append(f"**Total Load Time:** {total_load_ms:.2f} ms")
            lines.append("")

            # 遅いライブラリをソートして表示
            sorted_loads = sorted(loads, key=lambda x: x.duration_ms, reverse=True)
            slow_loads = [l for l in sorted_loads if l.duration_ms > 1.0]  # 1ms以上

            if slow_loads:
                lines.append("### Slowest Libraries (>1ms)")
                lines.append("")
                lines.append("| Library | Duration (ms) |")
                lines.append("|---------|---------------|")
                for load in slow_loads[:15]:
                    lines.append(f"| {load.library_name} | {load.duration_ms:.2f} |")
                lines.append("")

    # Time Profile
    time_profile_path = export_dir / "time-profile.xml"
    if time_profile_path.exists():
        parser = TimeProfileParser(time_profile_path)
        samples = parser.parse()

        if samples:
            analyzer = ProfileAnalyzer(samples)

            # サマリー
            total_weight = sum(s.weight_ms for s in samples)
            lines.append("## Summary")
            lines.append("")
            lines.append(f"- **Total Samples:** {len(samples)}")
            lines.append(f"- **Total Time:** {total_weight:.2f} ms")
            lines.append("")

            # Hot Frames (Total Time)
            lines.append("## Hot Frames - Total Time (Top 25)")
            lines.append("")
            lines.append("| Rank | Function | Count | Total (ms) | Binary |")
            lines.append("|------|----------|-------|------------|--------|")

            for i, (func, count, weight, binary) in enumerate(analyzer.get_hot_frames(25), 1):
                display_name = func[:60] + "..." if len(func) > 60 else func
                binary_name = binary[:20] if binary else "-"
                lines.append(f"| {i} | {display_name} | {count} | {weight:.2f} | {binary_name} |")
            lines.append("")

            # Self Time
            lines.append("## Hot Frames - Self Time (Top 15)")
            lines.append("")
            lines.append("| Rank | Function | Count | Self (ms) |")
            lines.append("|------|----------|-------|-----------|")

            for i, (func, count, weight, _) in enumerate(analyzer.get_self_time_frames(15), 1):
                display_name = func[:60] + "..." if len(func) > 60 else func
                lines.append(f"| {i} | {display_name} | {count} | {weight:.2f} |")
            lines.append("")

            # SwiftUI関連
            swiftui_frames = analyzer.get_swiftui_frames(15)
            if swiftui_frames:
                lines.append("## SwiftUI / AttributeGraph Frames")
                lines.append("")
                lines.append("| Function | Count | Total (ms) |")
                lines.append("|----------|-------|------------|")

                for func, count, weight in swiftui_frames:
                    display_name = func[:70] + "..." if len(func) > 70 else func
                    lines.append(f"| {display_name} | {count} | {weight:.2f} |")
                lines.append("")

            # アプリ固有コード
            if app_name:
                app_frames = analyzer.get_app_frames(app_name, 20)
                if app_frames:
                    lines.append(f"## App Code ({app_name})")
                    lines.append("")
                    lines.append("| Function | Count | Total (ms) |")
                    lines.append("|----------|-------|------------|")

                    for func, count, weight in app_frames:
                        display_name = func[:70] + "..." if len(func) > 70 else func
                        lines.append(f"| {display_name} | {count} | {weight:.2f} |")
                    lines.append("")

            # Collapsed stacks出力
            collapsed_path = export_dir / "collapsed.txt"
            collapsed_data = analyzer.generate_collapsed_stacks()
            with open(collapsed_path, "w") as f:
                f.write(collapsed_data)
            lines.append(f"## Flame Graph Data")
            lines.append("")
            lines.append(f"Collapsed stack format saved to: `{collapsed_path}`")
            lines.append("")
            lines.append("To generate flame graph:")
            lines.append("```bash")
            lines.append(f"# Install: git clone https://github.com/brendangregg/FlameGraph")
            lines.append(f"./FlameGraph/flamegraph.pl {collapsed_path} > flamegraph.svg")
            lines.append("```")
            lines.append("")

    # SwiftUI Updates
    swiftui_updates_path = export_dir / "swiftui-updates.xml"
    if swiftui_updates_path.exists():
        swiftui_parser = SwiftUIUpdatesParser(swiftui_updates_path)
        updates = swiftui_parser.parse()

        if updates:
            lines.append("## SwiftUI View Body Updates")
            lines.append("")
            lines.append(f"**Total Updates:** {len(updates)}")
            lines.append("")

            # View Body統計
            view_stats = swiftui_parser.get_view_body_stats()
            if view_stats:
                lines.append("### View Body Statistics (Top 15)")
                lines.append("")
                lines.append("| View | Count | Avg (µs) | Total (µs) |")
                lines.append("|------|-------|----------|------------|")
                for view_name, count, avg, total in view_stats[:15]:
                    lines.append(f"| {view_name} | {count} | {avg:.1f} | {total:.1f} |")
                lines.append("")

            # 遅い更新
            slow_updates = swiftui_parser.get_slow_updates(1000.0)  # 1ms以上
            if slow_updates:
                lines.append("### Slow Updates (>1ms)")
                lines.append("")
                lines.append("| Time | Duration (µs) | Description | Severity |")
                lines.append("|------|---------------|-------------|----------|")
                for update in slow_updates[:10]:
                    desc = update.description[:50] + "..." if len(update.description) > 50 else update.description
                    lines.append(f"| {update.start_time} | {update.duration_us:.1f} | {desc} | {update.severity} |")
                lines.append("")

    # Hangs
    potential_hangs_path = export_dir / "potential-hangs.xml"
    if potential_hangs_path.exists():
        hang_parser = HangParser(potential_hangs_path)
        hangs = hang_parser.parse()

        lines.append("## Potential Hangs")
        lines.append("")
        if hangs:
            lines.append(f"**Total:** {len(hangs)}")
            lines.append("**Status:** ⚠️ Warning")
            lines.append("")
            lines.append("| Time | Duration (ms) | Type | Thread |")
            lines.append("|------|---------------|------|--------|")
            for hang in hangs[:10]:
                thread_short = hang.thread[:30] + "..." if len(hang.thread) > 30 else hang.thread
                lines.append(f"| {hang.start_time} | {hang.duration_ms:.1f} | {hang.hang_type} | {thread_short} |")
            lines.append("")
        else:
            lines.append("**Total:** 0")
            lines.append("**Status:** ✅ OK - No hangs detected")
            lines.append("")

    # Hitches
    hitches_path = export_dir / "hitches.xml"
    if hitches_path.exists():
        hitch_parser = HitchParser(hitches_path)
        hitches = hitch_parser.parse()

        lines.append("## Animation Hitches")
        lines.append("")
        if hitches:
            app_hitches = [h for h in hitches if not h.is_system]
            system_hitches = [h for h in hitches if h.is_system]

            lines.append(f"**Total:** {len(hitches)} (App: {len(app_hitches)}, System: {len(system_hitches)})")
            if len(app_hitches) == 0:
                lines.append("**Status:** ✅ OK - No app hitches")
            elif len(app_hitches) <= 5:
                lines.append("**Status:** ⚠️ Minor issues")
            else:
                lines.append(f"**Status:** ❌ {len(app_hitches)} app hitches detected")
            lines.append("")

            if app_hitches:
                lines.append("### App Hitches")
                lines.append("")
                lines.append("| Time | Duration (ms) | Description |")
                lines.append("|------|---------------|-------------|")
                for hitch in app_hitches[:10]:
                    desc = hitch.description[:40] + "..." if len(hitch.description) > 40 else hitch.description
                    lines.append(f"| {hitch.start_time} | {hitch.duration_ms:.1f} | {desc} |")
                lines.append("")
        else:
            lines.append("**Total:** 0")
            lines.append("**Status:** ✅ OK - No hitches detected")
            lines.append("")

    # Memory Leaks
    leaks_path = export_dir / "Leaks-Leaks.xml"
    if leaks_path.exists():
        leaks_parser = LeaksParser(leaks_path)
        leaks = leaks_parser.parse()

        lines.append("## Memory Leaks")
        lines.append("")

        if leaks:
            summary = leaks_parser.get_leak_summary()
            total_kb = summary["total_bytes"] / 1024

            lines.append(f"**Status:** ❌ Leaks detected!")
            lines.append(f"**Total Leaks:** {summary['total_count']}")
            lines.append(f"**Total Leaked Memory:** {total_kb:.2f} KB ({summary['total_bytes']} bytes)")
            lines.append("")

            # By responsible library
            if summary["by_library"]:
                lines.append("### Leaks by Library")
                lines.append("")
                lines.append("| Library | Count | Bytes |")
                lines.append("|---------|-------|-------|")
                for lib, (count, bytes_) in list(summary["by_library"].items())[:10]:
                    lines.append(f"| {lib} | {count} | {bytes_} |")
                lines.append("")

            # By responsible frame
            if summary["by_frame"]:
                lines.append("### Leaks by Responsible Frame (Top 15)")
                lines.append("")
                lines.append("| Function | Count | Bytes |")
                lines.append("|----------|-------|-------|")
                for frame, (count, bytes_) in list(summary["by_frame"].items())[:15]:
                    display = frame[:60] + "..." if len(frame) > 60 else frame
                    lines.append(f"| {display} | {count} | {bytes_} |")
                lines.append("")

            # Largest leaks
            lines.append("### Largest Leaks (Top 10)")
            lines.append("")
            lines.append("| Address | Size (bytes) | Responsible Frame |")
            lines.append("|---------|--------------|-------------------|")
            for leak in sorted(leaks, key=lambda x: x.size_bytes, reverse=True)[:10]:
                frame = leak.responsible_frame[:40] + "..." if len(leak.responsible_frame) > 40 else leak.responsible_frame
                lines.append(f"| {leak.address} | {leak.size_bytes} | {frame} |")
            lines.append("")
        else:
            lines.append("**Status:** ✅ No memory leaks detected")
            lines.append("")

    # Memory Allocations - Statistics
    alloc_stats_path = export_dir / "Allocations-Statistics.xml"
    if alloc_stats_path.exists():
        stats_parser = AllocationStatisticsParser(alloc_stats_path)
        stats = stats_parser.parse()

        if stats:
            lines.append("## Memory Allocations - Statistics")
            lines.append("")

            total_persistent = sum(s.persistent_bytes for s in stats)
            total_all = sum(s.total_bytes for s in stats)

            lines.append(f"**Persistent Memory:** {total_persistent / (1024*1024):.2f} MB")
            lines.append(f"**Total Allocated:** {total_all / (1024*1024):.2f} MB")
            lines.append("")

            lines.append("### Top Categories by Persistent Memory")
            lines.append("")
            lines.append("| Category | Persistent | Count | Total |")
            lines.append("|----------|------------|-------|-------|")

            for stat in stats_parser.get_top_categories(15, by="persistent"):
                persistent_mb = stat.persistent_bytes / (1024*1024)
                total_mb = stat.total_bytes / (1024*1024)
                lines.append(f"| {stat.category} | {persistent_mb:.2f} MB | {stat.persistent_count} | {total_mb:.2f} MB |")
            lines.append("")

    # Energy Usage
    energy_path = export_dir / "energy-impact.xml"
    if energy_path.exists():
        energy_parser = EnergyUsageParser(energy_path)
        samples = energy_parser.parse()

        if samples:
            lines.append("## Energy Usage")
            lines.append("")

            avg = energy_parser.get_average_usage()

            # Energy impact assessment
            avg_impact = avg.get("avg_energy_impact", 0)
            if avg_impact < 5:
                status = "✅ Low - Good energy efficiency"
            elif avg_impact < 10:
                status = "⚠️ Moderate - Some optimization may help"
            else:
                status = "❌ High - Significant energy drain"

            lines.append(f"**Status:** {status}")
            lines.append("")
            lines.append("### Average Usage")
            lines.append("")
            lines.append(f"- **Energy Impact:** {avg.get('avg_energy_impact', 0):.1f} (max: {avg.get('max_energy_impact', 0):.1f})")
            lines.append(f"- **CPU Usage:** {avg.get('avg_cpu', 0):.1f}% (max: {avg.get('max_cpu', 0):.1f}%)")
            lines.append(f"- **GPU Usage:** {avg.get('avg_gpu', 0):.1f}% (max: {avg.get('max_gpu', 0):.1f}%)")
            lines.append("")

            # High energy samples
            high_energy = energy_parser.get_high_energy_samples(10.0)
            if high_energy:
                lines.append(f"### High Energy Impact Periods ({len(high_energy)} samples)")
                lines.append("")
                lines.append("| Time | Energy Impact | CPU | GPU |")
                lines.append("|------|---------------|-----|-----|")
                for sample in high_energy[:10]:
                    lines.append(f"| {sample.timestamp} | {sample.energy_impact:.1f} | {sample.cpu_usage:.1f}% | {sample.gpu_usage:.1f}% |")
                lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Parse xctrace exported XML and generate profiling report"
    )
    parser.add_argument("export_dir", type=Path, help="Directory containing exported XML files")
    parser.add_argument("--app", type=str, help="App binary name to filter (e.g., 'MyApp')")
    parser.add_argument("--collapsed-only", action="store_true",
                        help="Only output collapsed stack format for flame graphs")

    args = parser.parse_args()

    if not args.export_dir.exists():
        print(f"Error: Directory not found: {args.export_dir}", file=sys.stderr)
        sys.exit(1)

    time_profile_path = args.export_dir / "time-profile.xml"

    if args.collapsed_only:
        if not time_profile_path.exists():
            print("Error: time-profile.xml not found", file=sys.stderr)
            sys.exit(1)

        parser_obj = TimeProfileParser(time_profile_path)
        samples = parser_obj.parse()
        analyzer = ProfileAnalyzer(samples)
        print(analyzer.generate_collapsed_stacks(args.app))
        return

    report = generate_report(args.export_dir, args.app)
    print(report)

    # レポートをファイルにも保存
    report_path = args.export_dir / "report.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
