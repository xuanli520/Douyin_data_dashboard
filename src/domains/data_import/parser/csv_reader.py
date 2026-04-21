import csv
from pathlib import Path
from typing import Callable, Generator

import chardet


class CSVParser:
    def __init__(
        self,
        file_path: str | Path,
        progress_callback: Callable[[int], None] | None = None,
    ):
        self.file_path = Path(file_path)
        self.progress_callback = progress_callback
        self._row_count: int | None = None

    def _detect_encoding(self) -> str:
        sample_size = min(4 * 1024 * 1024, self.file_path.stat().st_size)
        with open(self.file_path, "rb") as f:
            raw_data = f.read(sample_size)
            if not raw_data:
                return "utf-8"
            if raw_data.startswith(b"\xef\xbb\xbf"):
                return "utf-8-sig"
            result = chardet.detect(raw_data)
            detected = result.get("encoding")
            confidence = result.get("confidence") or 0
            detected_lower = detected.lower() if detected else ""
            ignored_detected = {
                "utf-8",
                "ascii",
                "macroman",
                "windows-1250",
                "windows-1252",
            }
            candidates: list[str] = []
            candidates.append("utf-8")
            if (
                detected
                and detected_lower not in ignored_detected
                and confidence >= 0.7
            ):
                if detected_lower == "gb2312":
                    candidates.extend(["gbk", "gb18030"])
                elif detected_lower == "gb18030":
                    try:
                        raw_data.decode("gbk")
                    except UnicodeDecodeError:
                        candidates.append("gb18030")
                    else:
                        candidates.extend(["gbk", "gb18030"])
                else:
                    candidates.append(detected_lower)
            candidates.extend(["gbk", "gb18030"])
            for encoding in candidates:
                try:
                    raw_data.decode(encoding)
                    return encoding
                except UnicodeDecodeError:
                    continue
            return "utf-8"

    def _count_rows(self, encoding: str) -> int:
        with open(self.file_path, encoding=encoding, newline="") as f:
            reader = csv.reader(f)
            next(reader, None)
            return sum(1 for _ in reader)

    def _read_rows(
        self,
        encoding: str,
        start_row: int = 0,
    ) -> Generator[dict[str, str], None, None]:
        with open(self.file_path, encoding=encoding, newline="") as f:
            reader = csv.DictReader(f)
            for row_index, row in enumerate(reader, start=1):
                if row_index < start_row:
                    continue
                yield row
                if self.progress_callback:
                    self.progress_callback(row_index)

    def parse(
        self,
        start_row: int = 0,
    ) -> tuple[Generator[dict[str, str], None, None], int]:
        encoding = self._detect_encoding()
        if start_row == 0:
            self._row_count = self._count_rows(encoding)
        return self._read_rows(encoding, start_row), self._row_count or 0

    def get_row_count(self) -> int:
        if self._row_count is None:
            encoding = self._detect_encoding()
            self._row_count = self._count_rows(encoding)
        return self._row_count

