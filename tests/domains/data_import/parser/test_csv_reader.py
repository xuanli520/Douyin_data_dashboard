import tempfile
import os


def test_csv_parser_detects_encoding():
    from src.domains.data_import.parser.csv_reader import CSVParser

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("id,name\n1,测试\n")
        temp_path = f.name

    try:
        parser = CSVParser(temp_path)
        encoding = parser._detect_encoding()
        assert encoding in ("utf-8", "gbk", "ascii")
    finally:
        os.unlink(temp_path)


def test_csv_parser_counts_rows():
    from src.domains.data_import.parser.csv_reader import CSVParser

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("id,name\n1,Alice\n2,Bob\n3,Charlie\n")
        temp_path = f.name

    try:
        parser = CSVParser(temp_path)
        encoding = parser._detect_encoding()
        count = parser._count_rows(encoding)
        assert count == 3
    finally:
        os.unlink(temp_path)


def test_csv_parser_reads_rows():
    from src.domains.data_import.parser.csv_reader import CSVParser

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("id,name\n1,Alice\n2,Bob\n3,Charlie\n")
        temp_path = f.name

    try:
        parser = CSVParser(temp_path)
        encoding = parser._detect_encoding()
        rows = list(parser._read_rows(encoding))

        assert len(rows) == 3
        assert rows[0] == {"id": "1", "name": "Alice"}
        assert rows[1] == {"id": "2", "name": "Bob"}
        assert rows[2] == {"id": "3", "name": "Charlie"}
    finally:
        os.unlink(temp_path)


def test_csv_parser_start_row():
    from src.domains.data_import.parser.csv_reader import CSVParser

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("id,name\n1,Alice\n2,Bob\n3,Charlie\n")
        temp_path = f.name

    try:
        parser = CSVParser(temp_path)
        encoding = parser._detect_encoding()
        rows = list(parser._read_rows(encoding, start_row=2))

        assert len(rows) == 2
        assert rows[0] == {"id": "2", "name": "Bob"}
    finally:
        os.unlink(temp_path)


def test_csv_parser_parse_returns_generator_and_count():
    from src.domains.data_import.parser.csv_reader import CSVParser

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("id,name\n1,Alice\n2,Bob\n")
        temp_path = f.name

    try:
        parser = CSVParser(temp_path)
        generator, count = parser.parse()

        rows = list(generator)
        assert count == 2
        assert len(rows) == 2
    finally:
        os.unlink(temp_path)


def test_csv_parser_get_row_count_caches():
    from src.domains.data_import.parser.csv_reader import CSVParser

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("id,name\n1,Alice\n")
        temp_path = f.name

    try:
        parser = CSVParser(temp_path)
        count1 = parser.get_row_count()
        count2 = parser.get_row_count()

        assert count1 == 1
        assert count2 == 1
    finally:
        os.unlink(temp_path)


def test_csv_parser_with_gbk_encoding():
    from src.domains.data_import.parser.csv_reader import CSVParser

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="gbk"
    ) as f:
        f.write("id,name\n1,test\n")
        temp_path = f.name

    try:
        parser = CSVParser(temp_path)
        encoding = parser._detect_encoding()
        rows = list(parser._read_rows(encoding))

        assert len(rows) == 1
        assert rows[0]["name"] == "test"
    finally:
        os.unlink(temp_path)
