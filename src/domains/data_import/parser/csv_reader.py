import csv
import chardet
from pathlib import Path
from typing import Generator, Callable


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
        with open(self.file_path, "rb") as f:
            raw_data = f.read(1024 * 1024)
            result = chardet.detect(raw_data)
            encoding = result.get("encoding", "utf-8")
            if encoding is None or encoding.lower() in (
                "ascii",
                "macroman",
                "windows-1252",
            ):
                return "utf-8"
            return encoding

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
