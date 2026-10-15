import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

# 테스트가 일부러 일으키는 오류(디스크 꽉 참 등)가 실제 앱 로그(brain.log)에 섞이지 않도록 파일 핸들러 제거
logging.getLogger().removeHandler(main._log_handler)
main._log_handler.close()
