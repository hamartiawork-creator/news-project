import json
import requests
import time
import re
import os

def clean_text(text):
    """HTML 태그 제거"""
    return re.sub(r"<[^>]*>", "", text)

def generate_image():
    # 1) 최신 뉴스 불러오기
    try:
        with open("out/latest.json", "r", encoding="utf-8") as f:
            news = json.load(f)
    except Exception as e:
        print("뉴스 파일 읽기 실패:", e)
        return

    title = news.get("title", "")
    summary = news.get("summary", "")
    clean_summary = clean_text(summary)

    prompt_text = f"{title}. {clean_summary}. Realistic photo, documentary style, high detail, fantastical realism, metaphysical surreal photography"
    print(">> 프롬프트:", prompt_text)

    # 2) ComfyUI용 JSON 프롬프트
    prompt_data = {
        "3": {
            "inputs": {
                "seed": int(time.time()),  # 매번 다른 이미지 나오게 시드 시간으로
                "steps": 20,
                "cfg": 8.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0]
            },
            "class_type": "KSampler"
        },
        "4": {
            "inputs": {"ckpt_name": "v1-5-pruned-emaonly-fp16.safetensors"},
            "class_type": "CheckpointLoaderSimple"
        },
        "5": {
            "inputs": {"width": 512, "height": 512, "batch_size": 1},
            "class_type": "EmptyLatentImage"
        },
        "6": {
            "inputs": {"text": prompt_text, "clip": ["4", 1]},
            "class_type": "CLIPTextEncode"
        },
        "7": {
            "inputs": {
                "text": "blurry, distorted, low quality, cartoon, anime, text, watermark",
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "8": {
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            "class_type": "VAEDecode"
        },
        "9": {
            "inputs": {"filename_prefix": "NewsImage", "images": ["8", 0]},
            "class_type": "SaveImage"
        }
    }

    # 3) ComfyUI API 호출
    try:
        resp = requests.post("http://127.0.0.1:8188/prompt", json={"prompt": prompt_data})
        if resp.status_code == 200:
            print("이미지 생성 완료:", resp.json())
        else:
            print("에러:", resp.text)
    except Exception as e:
        print("ComfyUI API 호출 실패:", e)


if __name__ == "__main__":
    while True:
        generate_image()
        print("다음 업데이트까지 대기 중...\n")
        time.sleep(60)