import os
import logging
from logging.handlers import RotatingFileHandler

def setupLogger(log_folder, log_filename, log_level=logging.INFO) -> logging.Logger:
    if not os.path.exists(log_folder):
        os.mkdir(log_folder)
    logfile = os.path.join(log_folder, log_filename)

    stream_handler = logging.StreamHandler()
    file_handler = RotatingFileHandler(logfile, maxBytes=100000, backupCount=10)

    formatter = logging.Formatter('[%(asctime)s] [%(name)s:%(filename)s:%(lineno)d] [%(levelname)s] %(message)s')

    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    logger = logging.getLogger(__name__)
    logger.handlers.clear()
    logger.setLevel(log_level)
    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    return logger