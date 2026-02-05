from pathlib import Path
from typing import Generator, Callable


class FileParser:
    SUPPORTED_FORMATS = {".csv", ".xlsx"}

    def __init__(
        self,
        file_path: str,
        progress_callback: Callable[[int], None] | None = None,
        sheet_name: str | None = None,
    ):
        self.file_path = Path(file_path)
        self.progress_callback = progress_callback
        self.sheet_name = sheet_name
        self._parser = self._create_parser()

    def _create_parser(self):
        ext = Path(self.file_path).suffix.lower()
        if ext == ".csv":
            from .csv_reader import CSVParser

            return CSVParser(self.file_path, self.progress_callback)
        elif ext == ".xlsx":
            from .excel_reader import ExcelParser

            return ExcelParser(
                self.file_path,
                self.sheet_name,
                self.progress_callback,
            )
        raise ValueError(f"Unsupported file format: {ext}")

    def parse(
        self,
        start_row: int = 0,
    ) -> Generator[dict[str, str], None, None]:
        generator, _ = self._parser.parse(start_row)
        yield from generator

    def get_row_count(self) -> int:
        return self._parser.get_row_count()

    def get_sheets(self) -> list[str] | None:
        if hasattr(self._parser, "get_sheets"):
            return self._parser.get_sheets()
        return None

    @staticmethod
    def validate_file(file_path: str) -> tuple[bool, str]:
        ext = Path(file_path).suffix.lower()
        if ext not in FileParser.SUPPORTED_FORMATS:
            return (
                False,
                f"Unsupported file format: {ext}. Supported: {', '.join(FileParser.SUPPORTED_FORMATS)}",
            )
        if not Path(file_path).exists():
            return False, f"File not found: {file_path}"
        return True, ""
