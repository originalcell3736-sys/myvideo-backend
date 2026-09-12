import asyncio
import concurrent.futures
import os
import urllib.parse
import edge_tts
from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    concatenate_videoclips,
)
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

VOICE_MAPPING = {
    "Arabic": "ar-SA-HamedNeural",
    "English": "en-US-ChristopherNeural",
    "Spanish": "es-ES-AlvaroNeural",
    "French": "fr-FR-HenriNeural",
    "German": "de-DE-KillianNeural",
    "Chinese": "zh-CN-YunxiNeural",
    "Hindi": "hi-IN-MadhurNeural",
    "Portuguese": "pt-BR-AntonioNeural",
    "Russian": "ru-RU-DmitryNeural",
    "Japanese": "ja-JP-KeitaNeural",
}

def generate_consistent_prompts(topic_script, theme_style):
    prompts = []
    theme_suffix = f", {theme_style} style, highly detailed, 8k resolution, cinematic lighting"
    for i in range(40):
        base_prompt = f"Scene {i+1} about {topic_script[:40]}"
        prompts.append(base_prompt + theme_suffix)
    return prompts

def fetch_single_image(prompt, index):
    safe_prompt = urllib.parse.quote(prompt.replace("\n", " ").strip())
    url = f"https://image.pollinations.ai/prompt/{safe_prompt}?seed={index}&width=1280&height=720&nologo=true"
    
    try:
        res = requests.get(url, timeout=20)
        if res.status_code == 200 and len(res.content) > 1000:
            path = f"img_{index}.jpg"
            with open(path, "wb") as f:
                f.write(res.content)
            return path
    except Exception as e:
        print(f"Error fetching image {index}: {e}")
    
    # مسار احتياطي لتجنب التعطل
    try:
        fallback_url = f"https://picsum.photos/1280/720?random={index}"
        res_fb = requests.get(fallback_url, timeout=10)
        if res_fb.status_code == 200:
            path = f"img_{index}.jpg"
            with open(path, "wb") as f:
                f.write(res_fb.content)
            return path
    except Exception:
        pass
        
    return None

def generate_images_parallel(prompts_list):
    images = [None] * len(prompts_list)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_idx = {
            executor.submit(fetch_single_image, prompt, i): i
            for i, prompt in enumerate(prompts_list)
        }
        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            images[idx] = future.result()
    return [img for img in images if img is not None]

async def generate_voice_async(text, voice_code):
    output_audio = "speech.mp3"
    communicate = edge_tts.Communicate(text, voice_code)
    await communicate.save(output_audio)
    return output_audio

def create_custom_caption(text, duration, font_color, bg_color, font_size, position_y):
    return TextClip(
        text,
        fontsize=int(font_size),
        color=font_color,
        bg_color=bg_color if bg_color != "None" else None,
        font="Arial-Bold",
        method="caption",
        size=(1100, None)
    ).set_duration(duration).set_position(("center", position_y))

@app.post("/generate-video/")
async def generate_video(
    script_text: str = Form(...),
    language: str = Form("Arabic"),
    theme_style: str = Form("Anime"),
    caption_color: str = Form("yellow"),
    caption_bg: str = Form("black"),
    caption_size: int = Form(36),
    caption_position: str = Form("bottom"),
    preset_music: str = Form("None"),
    custom_music: UploadFile = File(None)
):
    voice_code = VOICE_MAPPING.get(language, "ar-SA-HamedNeural")

    await generate_voice_async(script_text, voice_code)
    voice_clip = AudioFileClip("speech.mp3")

    prompts = generate_consistent_prompts(script_text, theme_style)
    image_paths = generate_images_parallel(prompts)
    if not image_paths:
        return {"error": "Failed to generate images"}

    fixed_img_duration = 3.0
    video_clips = []
    
    for img_path in image_paths:
        img_clip = ImageClip(img_path).set_duration(fixed_img_duration)
        img_clip = img_clip.crossfadein(0.3)
        txt_clip = create_custom_caption(
            script_text[:50], 
            fixed_img_duration, 
            caption_color, 
            caption_bg, 
            caption_size, 
            caption_position
        )
        composite = CompositeVideoClip([img_clip, txt_clip])
        video_clips.append(composite)

    final_video = concatenate_videoclips(video_clips, method="compose")

    bg_music_path = None
    if custom_music:
        bg_music_path = "temp_custom_music.mp3"
        with open(bg_music_path, "wb") as f:
            f.write(await custom_music.read())
    elif preset_music != "None" and os.path.exists(f"music/{preset_music}.mp3"):
        bg_music_path = f"music/{preset_music}.mp3"

    final_audio = voice_clip
    if bg_music_path and os.path.exists(bg_music_path):
        bg_music = AudioFileClip(bg_music_path).volumex(0.12).set_duration(final_video.duration)
        final_audio = CompositeAudioClip([voice_clip, bg_music])

    final_video = final_video.set_audio(final_audio)

    output_path = "output_video.mp4"
    final_video.write_videofile(
        output_path, fps=24, codec="libx264", audio_codec="aac"
    )

    return FileResponse(output_path, media_type="video/mp4", filename="generated_video.mp4")
def create_custom_caption(text, duration, font_color, bg_color, font_size, position_y):
    return TextClip(
        text,
        fontsize=int(font_size),
        color=font_color,
        bg_color=bg_color if bg_color != "None" else None,
        font="Arial-Bold",
        method="caption",
        size=(1100, None)
    ).set_duration(duration).set_position(("center", position_y))

@app.post("/generate-video/")
async def generate_video(
    script_text: str = Form(...),
    language: str = Form("Arabic"),
    theme_style: str = Form("Anime"),
    caption_color: str = Form("yellow"),
    caption_bg: str = Form("black"),
    caption_size: int = Form(36),
    caption_position: str = Form("bottom"),
    preset_music: str = Form("None"),
    custom_music: UploadFile = File(None)
):
    voice_code = VOICE_MAPPING.get(language, "ar-SA-HamedNeural")

    await generate_voice_async(script_text, voice_code)
    voice_clip = AudioFileClip("speech.mp3")

    prompts = generate_consistent_prompts(script_text, theme_style)
    image_paths = generate_images_parallel(prompts)
    if not image_paths:
        return {"error": "Failed to generate images"}

    fixed_img_duration = 3.0
    video_clips = []
    
    for img_path in image_paths:
        img_clip = ImageClip(img_path).set_duration(fixed_img_duration)
        img_clip = img_clip.crossfadein(0.3)
        txt_clip = create_custom_caption(
            script_text[:50], 
            fixed_img_duration, 
            caption_color, 
            caption_bg, 
            caption_size, 
            caption_position
        )
        composite = CompositeVideoClip([img_clip, txt_clip])
        video_clips.append(composite)

    final_video = concatenate_videoclips(video_clips, method="compose")

    bg_music_path = None
    if custom_music:
        bg_music_path = "temp_custom_music.mp3"
        with open(bg_music_path, "wb") as f:
            f.write(await custom_music.read())
    elif preset_music != "None" and os.path.exists(f"music/{preset_music}.mp3"):
        bg_music_path = f"music/{preset_music}.mp3"

    final_audio = voice_clip
    if bg_music_path and os.path.exists(bg_music_path):
        bg_music = AudioFileClip(bg_music_path).volumex(0.12).set_duration(final_video.duration)
        final_audio = CompositeAudioClip([voice_clip, bg_music])

    final_video = final_video.set_audio(final_audio)

    output_path = "output_video.mp4"
    final_video.write_videofile(
        output_path, fps=24, codec="libx264", audio_codec="aac"
    )

    return FileResponse(output_path, media_type="video/mp4", filename="generated_video.mp4")

