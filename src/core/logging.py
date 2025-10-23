import logging
import sys

LOG_LEVEL = logging.getLevelName("INFO")
logging.basicConfig(stream=sys.stdout, level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("adaptive")
