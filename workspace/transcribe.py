import speech_recognition as sr
from pydub import AudioSegment
import os

# Convert ogg to wav
ogg_path = r'C:\Users\00\.nanobot\media\AwACAgUAAxkBAAIC.ogg'
wav_path = r'C:\Users\00\.nanobot\media\temp.wav'

audio = AudioSegment.from_ogg(ogg_path)
audio.export(wav_path, format='wav')

# Recognize
r = sr.Recognizer()
with sr.AudioFile(wav_path) as source:
    audio_data = r.record(source)
    try:
        text = r.recognize_google(audio_data, language='zh-CN')
        print('语音内容:', text)
    except Exception as e:
        print('识别失败:', e)
