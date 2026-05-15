import os
from app import run

if __name__ == '__main__':
    # Render.com 환경 변수 PORT를 읽어오고, 없으면 기본값 5000 사용
    port = int(os.environ.get("PORT", 5000))
    run(port=port)
