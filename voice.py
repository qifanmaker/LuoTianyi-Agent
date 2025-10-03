import speech_recognition as sr

# 创建识别器
recognizer = sr.Recognizer()

def get_voice():
    # 从麦克风录音
    with sr.Microphone() as source:
        audio = recognizer.listen(source)

    # print("Calling Google STT...")
    # 使用 Google 语音识别
    try:
        text = recognizer.recognize_google(audio, language="zh-CN")  # 中文
        print("result: ", text)
        return text
    except sr.UnknownValueError:
        get_voice()
    except sr.RequestError:
        print("Cannot connect to Google STT")
        return "Error"
