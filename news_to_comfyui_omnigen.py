import json
import requests
import time
import re
import random
from datetime import datetime

# ======================
# 기본 설정
# ======================
COMFY_URL = "http://127.0.0.1:8188"
LATEST_JSON_PATH = "out/latest.json"

FILENAME_PREFIX = "Omnigen2_LiveNews"
WIDTH, HEIGHT = 1024, 1024

UNET_MODEL = "omnigen2_fp16.safetensors"
CLIP_MODEL = "qwen_2.5_vl_fp16.safetensors"
VAE_MODEL = "ae.safetensors"


# ======================
# 유틸 함수
# ======================
def clean_text(html_text: str) -> str:
    """HTML 태그 제거"""
    return re.sub(r"<[^>]*>", "", html_text or "")


def random_variation() -> str:
    """프롬프트 변주 문구"""
    phrases = [
        "in a fragmented surreal dreamscape",
        "seen through a distorted cosmic lens",
        "reflected in liquid mirrors",
        "emerging from a field of light particles",
        "under shifting alien skies",
        "ethereal fog of memory",
        "echoing ancient digital ruins",
        "metaphysical horizon",
        "dreamlike refraction of reality",
        "hyperreal spectral world"
    ]
    return random.choice(phrases)


# ======================
# ComfyUI 워크플로 생성
# ======================
def build_omnigen2_prompt(prompt_text: str):
    seed = random.randint(1, 2**32 - 1)
    filename = f"{FILENAME_PREFIX}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{seed}"

    return {
        # UNET
        "12": {"inputs": {"unet_name": UNET_MODEL, "weight_dtype": "default"}, "class_type": "UNETLoader"},
        # CLIP
        "10": {"inputs": {"clip_name": CLIP_MODEL, "type": "omnigen2", "mode": "default"}, "class_type": "CLIPLoader"},
        # VAE
        "13": {"inputs": {"vae_name": VAE_MODEL}, "class_type": "VAELoader"},
        # Noise
        "21": {"inputs": {"noise_seed": seed}, "class_type": "RandomNoise"},
        # Sampler
        "20": {"inputs": {"sampler_name": "euler"}, "class_type": "KSamplerSelect"},
        # Scheduler
        "23": {
            "inputs": {"model": ["12", 0], "scheduler": "simple", "steps": 20, "denoise": 1},
            "class_type": "BasicScheduler",
        },
        # Positive
        "6": {"inputs": {"text": prompt_text, "clip": ["10", 0]}, "class_type": "CLIPTextEncode"},
        # Negative
        "7": {
            "inputs": {
                "text": "blurry, low quality, distorted, ugly, bad anatomy, deformed, poorly drawn",
                "clip": ["10", 0],
            },
            "class_type": "CLIPTextEncode",
        },
        # Guider
        "27": {
            "inputs": {
                "model": ["12", 0],
                "cond1": ["6", 0],
                "cond2": ["6", 0],
                "negative": ["7", 0],
                "cfg1": 5.0,
                "cfg2": 2.0,
                "cfg_conds": 1.0,
                "cfg_cond2_negative": 1.0,
                "style": "regular",
            },
            "class_type": "DualCFGGuider",
        },
        # Latent
        "11": {"inputs": {"width": WIDTH, "height": HEIGHT, "batch_size": 1}, "class_type": "EmptySD3LatentImage"},
        # Sampler Advanced
        "28": {
            "inputs": {
                "noise": ["21", 0],
                "guider": ["27", 0],
                "sampler": ["20", 0],
                "sigmas": ["23", 0],
                "latent_image": ["11", 0],
            },
            "class_type": "SamplerCustomAdvanced",
        },
        # Decode
        "8": {"inputs": {"samples": ["28", 0], "vae": ["13", 0]}, "class_type": "VAEDecode"},
        # Save
        "9": {"inputs": {"images": ["8", 0], "filename_prefix": filename}, "class_type": "SaveImage"},
    }


# ======================
# ComfyUI 통신
# ======================
def send_prompt_and_wait(prompt_data):
    resp = requests.post(f"{COMFY_URL}/prompt", json={"prompt": prompt_data})
    if resp.status_code != 200:
        print("[!] 요청 실패:", resp.text)
        return False

    prompt_id = resp.json().get("prompt_id")
    print(f"[▶] 프롬프트 실행 중 (ID={prompt_id})")

    while True:
        time.sleep(2)
        status = requests.get(f"{COMFY_URL}/history/{prompt_id}").json()
        if status.get("status", {}).get("completed"):
            print(f"[✓] 이미지 생성 완료 ({datetime.now().strftime('%H:%M:%S')})")
            return True


# ======================
# 뉴스 기반 이미지 생성
# ======================
def generate_from_latest():
    """out/latest.json 파일을 읽고 무한 이미지 생성"""
    try:
        with open(LATEST_JSON_PATH, "r", encoding="utf-8") as f:
            news = json.load(f)
    except Exception as e:
        print("[!] latest.json 읽기 오류:", e)
        return

    title = news.get("title", "")
    summary = clean_text(news.get("summary", ""))

    base_prompt = (
        f"{title}. {summary}. "
        "Cinematic surreal hyperrealism, photorealistic but dreamlike, fantastical lighting, "
        "dramatic composition, 16:9 aspect."
    )

    variation = random_variation()
    full_prompt = f"{base_prompt} {variation}"

    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Prompt ▶ {full_prompt}")
    prompt_data = build_omnigen2_prompt(full_prompt)
    send_prompt_and_wait(prompt_data)


# ======================
# 메인 루프
# ======================
if __name__ == "__main__":
    print("=== 🌐 실시간 뉴스 기반 Omnigen2 무한 이미지 생성 ===")
    print("ComfyUI 서버와 연결 중... (http://127.0.0.1:8188)")
    print("매 60초마다 새로운 이미지가 생성됩니다.\n")

    while True:
        try:
            generate_from_latest()
        except Exception as e:
            print("[!] 오류 발생:", e)
        print("⏳ 다음 생성까지 60초 대기...\n")
        time.sleep(60)
