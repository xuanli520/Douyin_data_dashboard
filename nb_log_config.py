import sys


import logging
import os


from pathlib import Path
import socket
from pythonjsonlogger.jsonlogger import JsonFormatter

PRINT_WRTIE_FILE_NAME = (
    os.environ.get("PRINT_WRTIE_FILE_NAME") or Path(sys.path[1]).name + ".print"
)

SYS_STD_FILE_NAME = (
    os.environ.get("SYS_STD_FILE_NAME") or Path(sys.path[1]).name + ".std"
)

USE_BULK_STDOUT_ON_WINDOWS = False

DEFAULUT_USE_COLOR_HANDLER = True
DEFAULUT_IS_USE_LOGURU_STREAM_HANDLER = False
DISPLAY_BACKGROUD_COLOR_IN_CONSOLE = True
AUTO_PATCH_PRINT = True

SHOW_PYCHARM_COLOR_SETINGS = True
SHOW_NB_LOG_LOGO = True
SHOW_IMPORT_NB_LOG_CONFIG_PATH = True

WHITE_COLOR_CODE = 37

DEFAULT_ADD_MULTIPROCESSING_SAFE_ROATING_FILE_HANDLER = False
AUTO_WRITE_ERROR_LEVEL_TO_SEPARATE_FILE = False
LOG_FILE_SIZE = 3
LOG_FILE_BACKUP_COUNT = 1

LOG_PATH = os.getenv("LOG_PATH")
if not LOG_PATH:
    LOG_PATH = "/pythonlogs"

    if os.name == "posix":
        home_path = os.environ.get("HOME", "/")
        LOG_PATH = Path(home_path) / Path("pythonlogs")


LOG_FILE_HANDLER_TYPE = 6

LOG_LEVEL_FILTER = logging.DEBUG


ROOT_LOGGER_LEVEL = logging.INFO
ROOT_LOGGER_FILENAME = "root.log"
ROOT_LOGGER_FILENAME_ERROR = "root.error.log"


FILTER_WORDS_PRINT = []


def get_host_ip():
    ip = ""
    host_name = ""

    try:
        sc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sc.connect(("8.8.8.8", 80))
        ip = sc.getsockname()[0]
        host_name = socket.gethostname()
        sc.close()
    except Exception:
        pass
    return ip, host_name


computer_ip, computer_name = get_host_ip()


class JsonFormatterJumpAble(JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        log_record[
            f"{record.__dict__.get('pathname')}:{record.__dict__.get('lineno')}"
        ] = ""
        log_record["ip"] = computer_ip
        log_record["host_name"] = computer_name
        super().add_fields(log_record, record, message_dict)
        if "for_segmentation_color" in log_record:
            del log_record["for_segmentation_color"]


DING_TALK_TOKEN = "3dd0eexxxxxadab014bd604XXXXXXXXXXXX"

EMAIL_HOST = ("smtp.sohu.com", 465)
EMAIL_FROMADDR = "aaa0509@sohu.com"
EMAIL_TOADDRS = (
    "cccc.cheng@silknets.com",
    "yan@dingtalk.com",
)
EMAIL_CREDENTIALS = ("aaa0509@sohu.com", "abcdefg")

ELASTIC_HOST = "127.0.0.1"
ELASTIC_PORT = 9200

KAFKA_BOOTSTRAP_SERVERS = ["192.168.199.202:9092"]
ALWAYS_ADD_KAFKA_HANDLER_IN_TEST_ENVIRONENT = False

MONGO_URL = "mongodb://myUserAdmin:mimamiama@127.0.0.1:27016/admin"

RUN_ENV = "test"

FORMATTER_DICT = {
    1: logging.Formatter(
        "log_time: %(asctime)s - logger: %(name)s - file: %(filename)s - line: %(lineno)d - %(levelname)s - %(message)s",
        "%Y-%m-%d %H:%M:%S",
    ),
    2: logging.Formatter(
        "%(asctime)s - %(name)s - %(filename)s - %(funcName)s - %(lineno)d - %(levelname)s - %(message)s",
        "%Y-%m-%d %H:%M:%S",
    ),
    3: logging.Formatter(
        '%(asctime)s - %(name)s - 銆?File "%(pathname)s", line %(lineno)d, in %(funcName)s 銆?- %(levelname)s - %(message)s',
        "%Y-%m-%d %H:%M:%S",
    ),
    4: logging.Formatter(
        '%(asctime)s - %(name)s - "%(filename)s" - %(funcName)s - %(lineno)d - %(levelname)s - %(message)s -               File "%(pathname)s", line %(lineno)d ',
        "%Y-%m-%d %H:%M:%S",
    ),
    5: logging.Formatter(
        '%(asctime)s - %(name)s - "%(pathname)s:%(lineno)d" - %(funcName)s - %(levelname)s - %(message)s',
        "%Y-%m-%d %H:%M:%S",
    ),
    6: logging.Formatter(
        "%(name)s - %(asctime)-15s - %(filename)s - %(lineno)d - %(levelname)s: %(message)s",
        "%Y-%m-%d %H:%M:%S",
    ),
    7: logging.Formatter(
        '%(asctime)s - %(name)s - "%(filename)s:%(lineno)d" - %(levelname)s - %(message)s',
        "%Y-%m-%d %H:%M:%S",
    ),
    8: JsonFormatterJumpAble(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(filename)s %(lineno)d  %(process)d %(thread)d",
        "%Y-%m-%d %H:%M:%S.%f",
        json_ensure_ascii=False,
    ),
    9: logging.Formatter(
        '[p%(process)d_t%(thread)d] %(asctime)s - %(name)s - "%(pathname)s:%(lineno)d" - %(funcName)s - %(levelname)s - %(message)s',
        "%Y-%m-%d %H:%M:%S",
    ),
    10: logging.Formatter(
        '[p%(process)d_t%(thread)d] %(asctime)s - %(name)s - "%(filename)s:%(lineno)d" - %(levelname)s - %(message)s',
        "%Y-%m-%d %H:%M:%S",
    ),
    11: logging.Formatter(
        f'%(asctime)s-({computer_ip},{computer_name})-[p%(process)d_t%(thread)d] - %(name)s - "%(filename)s:%(lineno)d" - %(funcName)s - %(levelname)s - %(message)s',
        "%Y-%m-%d %H:%M:%S",
    ),
}

FORMATTER_KIND = 5
