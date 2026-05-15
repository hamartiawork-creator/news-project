import json
import sqlite3
import os
import urllib.request
import urllib.error
import time
import threading
import news_collector
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# 설정
DB_PATH = "news.db"
COMFY_URL = "http://127.0.0.1:8188"
OUT_DIR = "out"
LATEST_JSON = os.path.join(OUT_DIR, "latest.json")

import sys
import os
# Windows cp949 콘솔 인코딩 에러 방지
os.environ['PYTHONIOENCODING'] = 'utf-8'

def safe_str(s):
    """Windows 콘솔에서 출력 안전한 문자열로 변환"""
    if not isinstance(s, str):
        return str(s)
    return s.encode('ascii', errors='replace').decode('ascii')

def load_env():
    env = {}
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    env[k] = v
    return env

ENV = load_env()
OPENAI_API_KEY = ENV.get("OPENAI_API_KEY", "")

class PresentationState:
    status = "ready" # "generating" or "ready"
    news = None
    image_url = ""
    movement_text = ""
    guid = ""
    force_next = False

class RequestHandler(BaseHTTPRequestHandler):
    IS_ACTIVE = True
    UPDATE_INTERVAL = 60

    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type")
        self.end_headers()
        
    def _send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        
    def do_GET(self):
        from urllib.parse import urlparse
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/current_display':
            self.send_response(200)
            self._send_cors_headers()
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            data = {
                "status": PresentationState.status,
                "news": PresentationState.news,
                "image_url": PresentationState.image_url,
                "movement_text": PresentationState.movement_text,
                "guid": PresentationState.guid
            }
            try:
                self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                print("Error sending current_display:", e)

        elif path == '/api/settings':
            self.send_response(200)
            self._send_cors_headers()
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "api_key": OPENAI_API_KEY,
                "is_active": RequestHandler.IS_ACTIVE,
                "update_interval": RequestHandler.UPDATE_INTERVAL
            }, ensure_ascii=False).encode('utf-8'))

        elif path in ['/', '/index', '/screen1', '/screen2', '/screen3']:
            page = path[1:] if path != '/' else 'index'
            filepath = os.path.join('templates', f"{page}.html")
            
            if os.path.exists(filepath):
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.end_headers()
                with open(filepath, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "File Not Found")
                
        elif path.startswith('/static/'):
            filepath = os.path.join(".", path.lstrip('/'))
            if os.path.exists(filepath):
                self.send_response(200)
                if filepath.endswith('.css'):
                    self.send_header('Content-type', 'text/css')
                elif filepath.endswith('.js'):
                    self.send_header('Content-type', 'application/javascript')
                self.end_headers()
                with open(filepath, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "File Not Found")
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path == '/api/settings':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            global OPENAI_API_KEY
            if "api_key" in data:
                OPENAI_API_KEY = data["api_key"]
                
                env_content = ""
                if os.path.exists(".env"):
                    with open(".env", "r", encoding="utf-8") as f:
                        env_content = f.read()
                
                lines = env_content.split('\n')
                new_lines = []
                found = False
                for line in lines:
                    if line.startswith("OPENAI_API_KEY="):
                        new_lines.append(f"OPENAI_API_KEY={OPENAI_API_KEY}")
                        found = True
                    elif line.strip():
                        new_lines.append(line)
                if not found:
                    new_lines.append(f"OPENAI_API_KEY={OPENAI_API_KEY}")
                
                with open(".env", "w", encoding="utf-8") as f:
                    f.write("\n".join(new_lines))
                    
            if "is_active" in data:
                RequestHandler.IS_ACTIVE = data["is_active"]
                if not RequestHandler.IS_ACTIVE:
                    print("사용자가 생성을 비활성화 했습니다 (토글 OFF).")
                else:
                    print("사용자가 생성을 활성화 했습니다 (토글 ON).")
                    
            if "update_interval" in data:
                try:
                    RequestHandler.UPDATE_INTERVAL = int(data["update_interval"])
                    print(f"새로운 뉴스 업데이트 주기: {RequestHandler.UPDATE_INTERVAL}초")
                except ValueError:
                    pass
                
            self.send_response(200)
            self._send_cors_headers()
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            
        elif self.path == '/api/reset_news':
            try:
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute("UPDATE articles SET is_used = 0")
                conn.commit()
                conn.close()
                
                PresentationState.force_next = True
                
                print("사용자 요청으로 뉴스 기사 출력 내역이 초기화되었습니다.")
                self.send_response(200)
                self._send_cors_headers()
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return

def presentation_manager_loop():
    print("Presentation Manager Started.")
    while True:
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            cur.execute("SELECT * FROM articles WHERE is_used = 0 ORDER BY published_utc DESC LIMIT 1")
            row = cur.fetchone()
            
            if not row:
                cur.execute("UPDATE articles SET is_used = 0")
                conn.commit()
                cur.execute("SELECT * FROM articles WHERE is_used = 0 ORDER BY published_utc DESC LIMIT 1")
                row = cur.fetchone()
                
            if row:
                cur.execute("UPDATE articles SET is_used = 1 WHERE id = ?", (row['id'],))
                conn.commit()
                news = dict(row)
                conn.close()
                
                start_time = time.time()
                
                PresentationState.status = "generating"
                
                mov_text = ""
                
                if OPENAI_API_KEY and RequestHandler.IS_ACTIVE:
                    print(f"[PM] 생성을 시작합니다... [{safe_str(news.get('title'))}]")
                    import re
                    # HTML 태그 제거 및 길이 제한
                    raw_summary = news.get('summary') or ""
                    clean_summary = re.sub('<[^<]+?>', '', raw_summary)[:1000]
                    clean_title = (news.get('title') or "")[:500]
                    
                    # GPT 움직임 텍스트 생성
                    try:
                        prompt = f"다음은 실시간 뉴스 기사입니다.\n제목: {clean_title}\n요약: {clean_summary}\n\n이 기사의 분위기와 내용을 바탕으로, 사람에게 전달하는 매우 짧고 파격적인 무용/행위 예술 관점의 '움직임 지시문'을 한국어로 작성해주세요. (예: '갑자기 모든걸 멈춰. 손끝, 어깨, 호흡까지 천천히 무게를 분산시키며'). 특수문자 없이 강렬하고 시적인 명령조로 작성하며, **핵심 조건: 반드시 공백 포함 총 100글자를 넘지 않게 짧게 작성하세요.**"
                        req_data = json.dumps({
                            "model": "gpt-4o-mini",
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": 90,
                            "temperature": 0.5
                        }).encode('utf-8')
                        
                        req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=req_data)
                        req.add_header("Content-Type", "application/json")
                        req.add_header("Authorization", f"Bearer {OPENAI_API_KEY}")
                        
                        with urllib.request.urlopen(req, timeout=30) as response:
                            res_body = json.loads(response.read())
                            mov_text = res_body['choices'][0]['message']['content'].strip()
                            print(f"[PM] 움직임 지시문 생성 완료!")
                    except Exception as e:
                        print(f"[PM] GPT API error: {e}")
                        mov_text = "침묵 속에서\\n천천히 호흡을 고르며\\n다음 움직임을 기다린다"
                        
                else:
                    if not OPENAI_API_KEY:
                        mov_text = "갑자기 모든걸 멈춰.\\n손끝, 어깨, 호흡까지\\n천천히\\n무게를 분산시키며"
                    else:
                        print(f"[PM] 생성 비활성화 상태입니다. [{safe_str(news.get('title'))}]")
                        mov_text = "기본 움직임"
                
                # Ready To Display
                PresentationState.news = news
                PresentationState.image_url = ""
                PresentationState.movement_text = mov_text
                PresentationState.guid = news.get("guid")
                PresentationState.status = "ready"
                print(f"[PM] 상태가 Ready로 전환되었습니다.")
                
                elapsed = time.time() - start_time
                sleep_sec = max(30.0, RequestHandler.UPDATE_INTERVAL - elapsed)
                
                for _ in range(int(sleep_sec)):
                    if PresentationState.force_next:
                        break
                    time.sleep(1)
                
                PresentationState.force_next = False
            else:
                conn.close()
                time.sleep(1)
        except Exception as e:
            print(f"[PM] Error in presentation manager loop: {e}")
            # 에러 발생 시 status를 ready로 복구하여 화면이 멈추지 않도록
            PresentationState.status = "ready"
            time.sleep(5)

def background_news_fetcher():
    cfg = news_collector.load_config()
    conn = news_collector.init_db()
    print("Background News Fetcher Started.")
    
    rss_interval = int(cfg.get("poll_seconds", 60))
    
    while True:
        try:
            count = news_collector.fetch_once(cfg, conn)
            if count > 0:
                print(f"[News Fetcher] Collected {count} new article(s).")
        except Exception as e:
            print(f"[News Fetcher Error]: {e}")
            
        for _ in range(rss_interval):
            time.sleep(1)

def run(port=5000):
    t1 = threading.Thread(target=background_news_fetcher, daemon=True)
    t1.start()
    
    t2 = threading.Thread(target=presentation_manager_loop, daemon=True)
    t2.start()

    server_address = ('', port)
    httpd = ThreadingHTTPServer(server_address, RequestHandler)
    print(f"==========================================")
    print(f"[>] Dashboard & Server on: http://localhost:{port}/")
    print(f"==========================================")
    httpd.serve_forever()

if __name__ == '__main__':
    run()
