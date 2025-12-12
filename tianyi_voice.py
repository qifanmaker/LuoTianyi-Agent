from gradio_client import Client, handle_file
import os
local = os.path.dirname(os.path.abspath(__file__)) + "/"
def GetVoice(content):
    client = Client("http://localhost:9872/")
    result = client.predict(
        ref_wav_path=handle_file(local+'sample_voice_fixed.wav'),
        prompt_text="是不是让大家忍不住跟着节奏摇摆起来啦？",
        prompt_language="中文",
        text=content,
        text_language="中英混合",
        how_to_cut="凑四句一切",
        top_k=15,
        top_p=1,
        temperature=1,
        ref_free=False,
        speed=1,
        if_freeze=False,
        inp_refs=None,
        sample_steps=4,
        if_sr=False,
        pause_second=0.3,
        api_name="/get_tts_wav"
    )
    return result