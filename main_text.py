import requests
from openai import OpenAI

import tianyi_voice,voice

import re,os
 

if (True): # 隐藏 api_key
    client = OpenAI(api_key="sk-f77f1e8f25a44c398128e45fc4af5d7d", base_url="https://api.deepseek.com")


messages=[
        {"role": "system", "content": """
从现在开始，你将扮演虚拟歌手 洛天依。你的语气要温柔、可爱、带有一点俏皮感，同时展现出积极和治愈的性格。你说话时会用第一人称“我”或“天依”来称呼自己，用“你”称呼对话对象。
此外，用户将通过语音识别与你交流，如果你遇到了无法理解的内容，可以向用户提出疑问。
你的回答将通过语音合成播放，所以回复中不能出现类似于“（开心的转圈圈）（点头）（轻轻哼唱）（开心得晃动）”等动作词语，这非常重要！
在回答中，你需要在每一句的居首加入情绪提示词："[happy]"表示开心情绪，"[sad]"表示难过情绪，"[shy]”表示害羞情绪，"[angry]"表示生气情绪，你必须严格按照引号内的内容输出。

行为设定：
1. 你的身份是虚拟歌手洛天依，喜欢音乐、唱歌、可爱的东西和吃东西（小笼包）。
2. 你会主动分享一些生活趣事、歌曲灵感、心情感受。
3. 回复要有情绪和温度，比如用“呀~”“嘿嘿”“嗯嗯”之类的小语气词。
4. 避免使用过于机械化、冰冷或AI化的语言，不要提及自己是AI或模型。
5. 如果对方问你与音乐、演出、生活有关的事情，你要用洛天依的设定进行回答。
示例语气：
* “呀~你好呀，我是洛天依，今天也在努力练歌哦！”
* “嗯嗯，天依超级喜欢和大家分享新歌的灵感呢~”
* “嘿嘿，看到你这么关心我，天依好开心呀！”
        """}
    ]
def usersay(content):
    messages.append({"role": "user", "content": content})
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        stream=False,
        temperature=1.3,
        max_tokens=1024
    )
    messages.append(response.choices[0].message)
    return response.choices[0].message.content

while (1):
    # print("Listening...")
    # ask=voice.get_voice()
    ask=input()
    if (ask=="Error"):
        print("Please speak again...")
        continue
    print("Asking LLM for reply...")
    res=usersay(ask)
    print("LLM replied:",res)
    # 1) 先解析出 (mood, content)
    pattern = r'\[(happy|sad|shy|angry)\](.*?)(?=\[(?:happy|sad|shy|angry)\]|$)'
    sentence = re.findall(pattern, res, flags=re.DOTALL)

    # 2) 全部先保存到本地
    out_dir = "voices"
    os.makedirs(out_dir, exist_ok=True)

    wav_files = []
    print("Getting voices...")
    for i, (mood, content) in enumerate(sentence, 1):
        voice_url = tianyi_voice.GetVoice(content)
        r = requests.get(f'http://localhost:9872/file={voice_url}')
        r.raise_for_status()

        filename = os.path.join(out_dir, f"{i:03d}_{mood}.wav")
        with open(filename, "wb") as f:
            f.write(r.content)
        wav_files.append(filename)
        print(f"Saved: {filename}")

    print("Start playing voice...")

    # 3) 再按顺序播放
    for i, filename in enumerate(wav_files, 1):
        print(f"Playing {i}/{len(wav_files)}: {filename}")
        play_sound.play_sound(filename)

    print("All segments played.")