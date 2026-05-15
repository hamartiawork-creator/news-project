import threading
from app import app, presentation_manager_loop, background_news_fetcher, PORT

# 클라우드 환경(gunicorn 등 WSGI 서버)에서 애플리케이션이 로드될 때 
# 백그라운드 스레드들이 한 번만 실행되도록 래핑합니다.
# 로컬에서 직접 실행하는 경우(__main__)에는 app.py가 담당하므로 간섭하지 않습니다.

pm_thread = threading.Thread(target=presentation_manager_loop, daemon=True)
pm_thread.start()

news_thread = threading.Thread(target=background_news_fetcher, daemon=True)
news_thread.start()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=PORT, debug=False)
