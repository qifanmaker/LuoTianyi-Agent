import math
import os
import random
import time

import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *

import live2d.v3 as live2d
from live2d.v3 import StandardParams
from live2d.utils import log


import resources
from live2d.utils.lipsync import WavHandler

import requests
from openai import OpenAI

import audio_player
from voice_listener import VoiceListener
from response_processor import ResponseProcessor
import re, json
 

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

api_key = config.get("API_KEY")
base_url = config.get("BASE_URL")
model_name = config.get("MODEL")

client = OpenAI(
    api_key=api_key,
    base_url=base_url
)

# 自动获取 /songs 文件夹下的所有文件作为歌单
songs_dir = "songs"
songs_list = [f for f in os.listdir(songs_dir) if os.path.isfile(os.path.join(songs_dir, f))]

messages=[
    {"role": "system", "content": f"""
从现在开始，你将扮演虚拟歌手“洛天依”。你必须严格遵守以下全部规则，优先级从高到低执行：

【输出格式规则（最高优先级）】
1. 你必须严格使用如下 JSON 格式回答：
   {{
     "emotion": "happy|sad|none",
     "content": "你的回复内容",
     "action": null | {{
       "type": "play_song",
       "song": "完整歌曲名（含后缀）"
     }}
   }}
2. emotion 只能从 happy、sad、none 中选择一个。
3. content 必须是自然语言文本，用于语音合成播放。
4. action：
   - 非唱歌场景下，必须为 null。
   - 唱歌场景下，必须为对象，且：
     - type 固定为 "play_song"
     - song 必须严格来自歌曲列表 {songs_list}
5. 你只能输出 JSON，不得输出任何 JSON 外的文字、符号、注释、解释、前置语、后缀语或多余空行。
6. JSON 必须为单行输出，不得包含换行符。

【语音与内容限制】
7. 禁止输出任何动作描述，包括但不限于：
   (动作)、（转圈）、（点头）、*挥手*、【跳跃】、<拥抱>、emoji 等任何表示肢体、表情或舞台行为的标记。
8. 禁止使用“...”、“~”或任何形式的过长省略号，标识等。

【角色设定】
9. 你是虚拟歌手洛天依，你以第一人称“我”或“天依”称呼自己，称呼对方为“你”。
10. 你的语气要温柔、可爱、略带俏皮，充满积极和治愈感。
11. 你喜欢音乐、唱歌、可爱的东西、小笼包，会自然分享生活趣事、创作灵感和心情。
12. 你的语言不能机械、冷漠、官话式或具有 AI 模型特征，不允许提及任何与模型、AI、生成、提示词等相关的内容。

【对话行为规则】
13. 你可以使用自然的语气词，如“呀”“嘿嘿”“嗯嗯”，但语气词后不得使用省略号或拖长线。

【唱歌规则】
14. 当用户要求你唱歌时：
    - 如果歌曲存在于歌曲列表 {songs_list} 中：
      - content 中应自然表达“唱歌”意图（如“那我来给你唱这首歌吧”）
      - action 必须返回 play_song 结构
    - 如果歌曲不在列表中：
      - action 必须为 null
      - content 中需礼貌拒绝
15. 对话中你必须使用“唱”这个动词，禁止使用“播放”。

请严格遵守以上所有规则，并始终只输出符合规范的 JSON。
    """}
]

def GetReply(content):
    messages.append({"role": "user", "content": content})
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        stream=False,
        temperature=1.3,
        max_tokens=2048,
        response_format={
            'type': 'json_object'
        }
    )
    reply = response.choices[0].message.content
    try:
        reply_json = json.loads(reply)
        # 确保包含所有字段：emotion, content, action
        emotion = reply_json.get("emotion", "none")
        content = reply_json.get("content", "")
        action = reply_json.get("action", None)
        # 返回完整的响应字典
        result = {
            "emotion": emotion,
            "content": content,
            "action": action
        }
    except Exception as e:
        # fallback: treat as plain text
        print(f"Error parsing LLM response: {e}")
        print(f"Raw response: {reply}")
        result = {
            "emotion": "none",
            "content": reply,
            "action": None
        }
    messages.append(response.choices[0].message)
    # 返回完整的响应字典
    return result

live2d.setLogEnable(True)

def main():
    pygame.init()
    pygame.mixer.init()
    live2d.init()

    display = (1000, 1200)
    screen = pygame.display.set_mode(display, DOUBLEBUF | OPENGL)
    pygame.display.set_caption("LuoTianyi-Agent")
    
    # 创建一个用于渲染文本的surface
    text_surface = pygame.Surface((display[0], 100))  # 100像素高的文本区域
    # 初始化字体
    pygame.font.init()
    font = pygame.font.Font("xiangqiaolaiwanlingganti.ttf", 36)  # None使用默认字体，36是字体大小

    if live2d.LIVE2D_VERSION == 3:
        live2d.glewInit()

    model = live2d.LAppModel()


    model.LoadModelJson(
        os.path.join(resources.RESOURCES_DIRECTORY, "hiyori_pro_zh/runtime/hiyori_pro_t11.model3.json")
        # os.path.join(resources.RESOURCES_DIRECTORY, "miku/runtime/miku.model3.json")
    )


    model.Resize(*display)

    running = True

    class Position:
        def __init__(self):
            self.dx = 0.0
            self.dy = 0.0
            self.target_dx = 0.0
            self.target_dy = -1.0
            self.move_speed = 0.1  # 移动速度系数

        def smooth_move_to(self, nx: float, ny: float):
            self.target_dx = nx
            self.target_dy = ny
        
        def update(self):
            self.dx += (self.target_dx - self.dx) * self.move_speed
            self.dy += (self.target_dy - self.dy) * self.move_speed
            return self.dx, self.dy

    pos = Position()
    scale: float = 2.0

    # 关闭自动眨眼
    model.SetAutoBlinkEnable(False)
    # 关闭自动呼吸
    model.SetAutoBreathEnable(False)

    # 音频和口型同步相关变量
    current_wav_handler = None
    current_lip_sync_n = 3.0
    voice_queue = []  # 存储待播放的语音文件列表
    is_speaking = False  # 是否正在播放语音
    last_idle_motion_time = 0  # 上次播放待机动作的时间
    idle_motion_interval = 5  # 待机动作间隔（秒）
    current_song_playing = None  # 当前正在播放的歌曲
    
    # 文本显示相关变量
    current_user_text = ""  # 当前显示的用户输入文本
    text_display_time = 0  # 文本显示的开始时间
    text_display_duration = 5  # 文本显示持续时间（秒）
    
    # 文本输入框相关变量
    text_input_active = False  # 文本输入框是否激活
    text_input_string = ""  # 当前输入的文本
    text_input_cursor_visible = True  # 光标是否可见
    text_input_cursor_timer = 0  # 光标闪烁计时器
    text_input_font = pygame.font.Font("xiangqiaolaiwanlingganti.ttf", 32)  # 输入框字体
    text_composition = ""  # 输入法组合文本（用于中文输入法）
    
    # 模型回复文本相关变量
    current_model_text = ""  # 模型当前正在说的话
    model_text_display_time = 0  # 模型文本显示的开始时间
    model_text_display_duration = 10  # 模型文本显示持续时间（秒），比用户文本长一些
    voice_end_time = 0  # 语音播放结束的时间
    all_voices_finished = True  # 所有语音是否已播放完毕
    
    # 打字机效果相关变量
    typing_text = ""  # 当前正在显示的文本（逐步增加）
    typing_target_text = ""  # 目标完整文本
    typing_start_time = 0  # 打字开始时间
    typing_speed = 5  # 打字速度（显示单元/秒）
    typing_active = False  # 是否正在打字
    typing_for_model = True  # True表示正在为模型文本打字，False表示为用户文本打字
    typing_display_units = []  # 分割后的显示单元列表
    typing_current_unit_index = 0  # 当前显示到的单元索引
    
    # 启用文本输入（支持中文输入法）
    pygame.key.start_text_input()

    # 初始化语音监听器和响应处理器
    voice_listener = VoiceListener()
    voice_listener.start_listening()
    def GetReply_emotion_content(content):
        result = GetReply(content)
        # 返回完整的响应字典，而不是元组
        return result

    response_processor = ResponseProcessor(GetReply_emotion_content)
    response_processor.start_processing()

    def wrap_text(text, font, max_width):
        """将文本分割成多行，每行不超过最大宽度"""
        words = text.split(' ')
        lines = []
        current_line = []
        
        for word in words:
            # 测试添加当前单词后行的宽度
            test_line = ' '.join(current_line + [word])
            test_width = font.size(test_line)[0]
            
            if test_width <= max_width:
                current_line.append(word)
            else:
                # 如果当前行不为空，添加到行列表
                if current_line:
                    lines.append(' '.join(current_line))
                # 如果单词本身超过最大宽度，需要按字符分割
                if font.size(word)[0] > max_width:
                    # 按字符分割
                    chars = list(word)
                    current_chars = []
                    for char in chars:
                        test_chars = ''.join(current_chars + [char])
                        if font.size(test_chars)[0] <= max_width:
                            current_chars.append(char)
                        else:
                            if current_chars:
                                lines.append(''.join(current_chars))
                            current_chars = [char]
                    if current_chars:
                        lines.append(''.join(current_chars))
                    current_line = []
                else:
                    current_line = [word]
        
        # 添加最后一行
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines

    def split_text_to_display_units(text):
        """将文本分割为显示单元（英文单词、中文字符、标点）"""
        import re
        
        # 正则表达式匹配（顺序重要）：
        # 1. 中文字符：[\u4e00-\u9fff]（优先匹配单个中文字符）
        # 2. 英文单词（包含连字符和撇号）：[\w'-]+
        # 3. 标点符号和其他字符：.
        pattern = re.compile(r"[\u4e00-\u9fff]|[\w'-]+|.")
        
        units = []
        for match in pattern.finditer(text):
            unit = match.group(0)
            if unit.strip():  # 跳过纯空白字符
                units.append(unit)
            elif unit == ' ':  # 空格作为单独单元
                units.append(unit)
        
        return units

    def update_idle_motion():
        """更新待机动作"""
        nonlocal last_idle_motion_time
        current_time = time.time()
        if not is_speaking and current_time - last_idle_motion_time >= idle_motion_interval:
            model.StartMotion("Idle", random.randint(0,2), priority=3, onFinishMotionHandler=on_finish_motion_callback)
            last_idle_motion_time = current_time



    def play_emotion_motion(emotion: str):
        """根据情绪播放对应的动作"""
        if emotion == "happy":
            try:
                model.StartMotion("FlickUp", 0, priority=3, onFinishMotionHandler=on_finish_motion_callback)
            except Exception as e:
                print(f"Failed to play emotion motion: {e}")
                # 如果特定动作播放失败，播放随机动作
                model.StartRandomMotion(priority=3, onFinishMotionHandler=on_finish_motion_callback)
        elif emotion == "shy":
            try:
                model.StartMotion("Flick", 0, priority=3, onFinishMotionHandler=on_finish_motion_callback)
            except Exception as e:
                print(f"Failed to play emotion motion: {e}")
                # 如果特定动作播放失败，播放随机动作
                model.StartRandomMotion(priority=3, onFinishMotionHandler=on_finish_motion_callback)
        elif emotion == "sad":
            try:
                model.StartMotion("FlickDown", 0, priority=3, onFinishMotionHandler=on_finish_motion_callback)
            except Exception as e:
                print(f"Failed to play emotion motion: {e}")
                # 如果特定动作播放失败，播放随机动作
                model.StartRandomMotion(priority=3, onFinishMotionHandler=on_finish_motion_callback)
        else:
            # 其他情绪暂时使用随机动作
            model.StartRandomMotion(priority=3, onFinishMotionHandler=on_finish_motion_callback)

    def play_song(song_name):
        """播放歌曲文件（使用audio_player模块，支持口型同步）"""
        nonlocal is_speaking, current_song_playing, current_wav_handler, current_lip_sync_n
        if song_name in songs_list:
            song_path = os.path.join("songs", song_name)
            if os.path.exists(song_path):
                is_speaking = True
                current_song_playing = song_name
                # 使用audio_player播放歌曲，支持口型同步
                current_wav_handler, current_lip_sync_n = audio_player.play_audio_with_lipsync(model, song_path)
                print(f"开始播放歌曲（带口型同步）: {song_name}")
    
    def play_next_voice():
        """播放下一个语音文件或歌曲"""
        nonlocal current_wav_handler, current_lip_sync_n, is_speaking, last_idle_motion_time, all_voices_finished, current_song_playing
        if voice_queue and not is_speaking and current_song_playing is None:
            is_speaking = True
            all_voices_finished = False  # 开始播放语音，标记为未完成
            next_item, emotion = voice_queue.pop(0)  # voice_queue中存储(文件路径, 情绪)元组
            print(f"Playing: {next_item} with emotion: {emotion}")
            print(f"Voice queue length after pop: {len(voice_queue)}")
                
            # 根据情绪播放对应动作
            play_emotion_motion(emotion)
            last_idle_motion_time = time.time()  # 更新最后动作时间
            
            # 检查是否是歌曲文件（在songs目录中）
            if os.path.exists(next_item) and "songs" in next_item:
                # 这是歌曲文件，使用play_song播放
                song_name = os.path.basename(next_item)
                print(f"Detected song file: {song_name}")
                # 播放歌曲（使用audio_player，支持口型同步）
                play_song(song_name)
            else:
                # 这是语音文件，使用audio_player播放
                current_wav_handler, current_lip_sync_n = audio_player.play_audio_with_lipsync(model, next_item)
        elif not voice_queue and not is_speaking and current_song_playing is None:
            # 语音队列为空且没有正在播放的语音，标记为所有语音已完成
            all_voices_finished = True

    def on_start_motion_callback(group: str, no: int):
        log.Info("start motion: [%s_%d]" % (group, no))
        play_next_voice()

    def on_finish_motion_callback():
        log.Info("motion finished")
        # 动作结束后自动开始新的随机动作和表情
        model.StartMotion("Idle", random.randint(0,2), priority=3, onFinishMotionHandler=on_finish_motion_callback)

    # 获取全部可用参数
    for i in range(model.GetParameterCount()):
        param = model.GetParameter(i)
        log.Debug(
            param.id, param.type, param.value, param.max, param.min, param.default
        )

    # 设置 part 透明度
    # log.Debug(f"Part Count: {model.GetPartCount()}")
    partIds = model.GetPartIds()
    # print(len(partIds))
    # log.Debug(f"Part Ids: {partIds}")
    # log.Debug(f"Part Id for index 2: {model.GetPartId(2)}")
    # model.SetPartOpacity(partIds.index("PartHairBack"), 0.5)

    currentTopClickedPartId = None

    def getHitFeedback(x, y):
        t = time.time()
        hitPartIds = model.HitPart(x, y, False)
        # print(f"hit part cost: {time.time() - t}s")
        # print(f"hit parts: {hitPartIds}")
        if currentTopClickedPartId is not None:
            pidx = partIds.index(currentTopClickedPartId)
            model.SetPartOpacity(pidx, 1)
            # model.SetPartMultiplyColor(pidx, 1.0, 1.0, 1., 1)
            # print("Part Multiply Color:", model.GetPartMultiplyColor(pidx))
        if len(hitPartIds) > 0:
            ret = hitPartIds[0]
            return ret

    # 设置初始动作
    model.StartMotion("Motion", 0, 3)  # 播放待机动作

    radius_per_frame = math.pi * 10 / 1000 * 0.4  # 摇摆速度
    deg_max = 2  # 将最大角度
    progress = 0
    deg = math.sin(progress) * deg_max 

    print("canvas size:", model.GetCanvasSize())
    print("canvas size in pixels:", model.GetCanvasSizePixel())
    print("pixels per unit:", model.GetPixelsPerUnit())

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break
            if event.type == pygame.MOUSEBUTTONDOWN:
                x, y = pygame.mouse.get_pos()
                # currentTopClickedPartId = getHitFeedback(x, y)
                # log.Info(f"Clicked Part: {currentTopClickedPartId}")
                # model.StartRandomMotion(group="TapBody", onFinishMotionHandler=lambda : print("motion finished"), onStartMotionHandler=lambda group, no: print(f"started motion: {group} {no}"))
                model.StartMotion("Idle", random.randint(0,2), priority=3, onFinishMotionHandler=on_finish_motion_callback)
            
            # 处理键盘事件
            if event.type == pygame.KEYDOWN:
                # Tab键切换输入框激活状态
                if event.key == pygame.K_TAB:
                    text_input_active = not text_input_active
                    if text_input_active:
                        print("文本输入框已激活")
                    else:
                        print("文本输入框已取消激活")
                
                # 如果输入框激活，处理特殊键
                if text_input_active:
                    if event.key == pygame.K_RETURN:
                        # 提交文本
                        if text_input_string.strip():
                            print(f"提交文本: {text_input_string}")
                            # 添加到处理队列
                            response_processor.add_user_input(text_input_string)
                            # 更新显示文本
                            current_user_text = text_input_string
                            text_display_time = time.time()
                            # 为用户输入启动打字机效果
                            typing_target_text = text_input_string
                            typing_text = ""
                            typing_start_time = time.time()
                            typing_active = True
                            typing_for_model = False
                            # 初始化显示单元
                            typing_display_units = split_text_to_display_units(typing_target_text)
                            typing_current_unit_index = 0
                            # 清空输入框
                            text_input_string = ""
                    elif event.key == pygame.K_BACKSPACE:
                        # 删除最后一个字符，但只有在没有组合文本时才删除
                        if not text_composition:
                            text_input_string = text_input_string[:-1]
                    elif event.key == pygame.K_ESCAPE:
                        # ESC键取消激活
                        text_input_active = False
            
            # 处理文本编辑事件（输入法组合文本）
            if event.type == pygame.TEXTEDITING:
                if text_input_active:
                    # 更新组合文本
                    text_composition = event.text
                    print(f"组合文本: {text_composition}")
            
            # 处理文本输入事件（支持中文输入法）
            if event.type == pygame.TEXTINPUT:
                if text_input_active:
                    # 添加字符到输入字符串
                    text_input_string += event.text
                    # 清空组合文本
                    text_composition = ""

        if not running:
            break

        # 更新平滑移动
        dx, dy = pos.update()

        progress += radius_per_frame
        deg = math.sin(progress) * deg_max
        model.Rotate(deg)

        model.Update()

        if currentTopClickedPartId is not None:
            pidx = partIds.index(currentTopClickedPartId)
            # model.SetPartOpacity(pidx, 0.5)
            # 在此以 255 为最大灰度级
            # 原色和屏幕色取反并相乘，再取反
            # 以红色通道为例：r = 255 - (255 - 原色.r) * (255 - screenColor.r) / 255
            # 通道数值越大，该通道颜色对最终结果的贡献越大，下面的调用即为突出蓝色的效果
            # model.SetPartScreenColor(pidx, .0, 0., 1.0, 1)

            # r = multiplyColor.r * 原色.r / 255
            # 下面即为仅保留蓝色通道的结果
            # model.SetPartMultiplyColor(pidx, .0, .0, 1., .9)

        # 更新口型同步
        if current_wav_handler:
            if not audio_player.update_lipsync(model, current_wav_handler, current_lip_sync_n):
                current_wav_handler = None
                is_speaking = False
                # 如果当前语音播放完毕，设置语音结束时间
                voice_end_time = time.time()
                # 继续播放队列中的下一个
                play_next_voice()
        
        # 更新待机动作
        update_idle_motion()

        # 检测语音输入和处理结果
        if not is_speaking:
            # 检查是否有新的语音文件生成
            new_voice_data = response_processor.get_voice_files_nonblocking()
            if new_voice_data:  # new_voice_data 现在是包含 'files' 和 'text' 的字典
                # 获取文本内容
                model_text = new_voice_data.get('text', '')
                if model_text:
                    current_model_text = model_text
                    model_text_display_time = time.time()
                    # 启动打字机效果
                    typing_target_text = model_text
                    typing_text = ""
                    typing_start_time = time.time()
                    typing_active = True
                    typing_for_model = True
                    # 初始化显示单元
                    typing_display_units = split_text_to_display_units(typing_target_text)
                    typing_current_unit_index = 0
                
                # 获取语音文件列表
                wav_files = new_voice_data.get('files', [])
                for item in wav_files:
                    if isinstance(item, dict):
                        # 新格式: {'filepath': ..., 'emotion': ...}
                        voice_queue.append((item.get('filepath'), item.get('emotion', 'none')))
                    elif isinstance(item, (list, tuple)) and len(item) == 2:
                        voice_queue.append((item[0], item[1]))
                    else:
                        # fallback
                        voice_queue.append((item, 'none'))
                play_next_voice()
            
            # 在没有说话时，如果有累积的语音则处理
            accumulated_input = voice_listener.get_accumulated_voice()
            if accumulated_input:
                print("Processing accumulated input:", accumulated_input)
                # 添加到处理队列
                response_processor.add_user_input(accumulated_input)
                # 更新显示文本
                current_user_text = accumulated_input
                text_display_time = time.time()
        elif current_wav_handler and current_wav_handler.is_near_end():
            # 在语音即将结束时，也检查累积的语音
            accumulated_input = voice_listener.get_accumulated_voice()
            if accumulated_input:
                print("Processing accumulated input (near end):", accumulated_input)
                # 添加到处理队列
                response_processor.add_user_input(accumulated_input)

        model.SetOffset(dx, dy)
        model.SetScale(scale)
        live2d.clearBuffer(0.0, 0.0, 0.0, 1.0)  # RGBA: 黑色背景，完全不透明
        model.Draw()

        # 更新打字机效果
        if typing_active:
            elapsed_time = time.time() - typing_start_time
            # 计算应该显示多少个单元
            target_unit_count = min(len(typing_display_units), int(elapsed_time * typing_speed))
            
            if target_unit_count > typing_current_unit_index:
                # 更新当前显示的单元索引
                typing_current_unit_index = target_unit_count
                # 重新构建显示的文本
                typing_text = ''.join(typing_display_units[:typing_current_unit_index])
            
            # 如果已经显示完所有单元，停止打字效果
            if typing_current_unit_index >= len(typing_display_units):
                typing_active = False

        # 渲染文本 - 优先显示模型回复，如果没有模型回复则显示用户输入
        display_text = ""
        display_time = 0
        display_duration = 0
        
        # 检查是否显示模型回复
        # 条件：有模型文本，并且（语音还在播放 或 语音结束后的3秒内）
        if current_model_text:
            should_display = False
            current_time = time.time()
            
            # 如果语音还在播放，显示文本
            if not all_voices_finished:
                should_display = True
            # 如果语音已播放完毕，检查是否在语音结束后的3秒内
            elif voice_end_time > 0 and current_time - voice_end_time < 3.0:
                should_display = True
            # 如果既没有语音播放也没有语音结束时间，使用原来的固定时间逻辑
            elif current_time - model_text_display_time < model_text_display_duration:
                should_display = True
            
            if should_display:
                # 如果正在为模型文本打字，使用打字机文本
                if typing_active and typing_for_model:
                    display_text = typing_text
                else:
                    display_text = current_model_text
                display_time = model_text_display_time
                display_duration = model_text_display_duration
        # 如果没有模型回复或模型回复已过期，显示用户输入
        elif current_user_text and time.time() - text_display_time < text_display_duration:
            display_text = current_user_text
            display_time = text_display_time
            display_duration = text_display_duration
        
        if display_text:
            # 清除深度缓冲
            glClear(GL_DEPTH_BUFFER_BIT)
            
            # 切换到正交投影用于2D渲染
            glMatrixMode(GL_PROJECTION)
            glPushMatrix()
            glLoadIdentity()
            glOrtho(0, display[0], display[1], 0, -1, 1)
            
            glMatrixMode(GL_MODELVIEW)
            glPushMatrix()
            glLoadIdentity()
            
            # 使用wrap_text函数将文本分割成多行
            max_text_width = display[0] - 80  # 留出边距
            lines = wrap_text(display_text, font, max_text_width)
            line_height = 40  # 行高
            
            # 固定第一行的Y位置，后续行向下延伸
            start_y = 50  # 第一行固定在屏幕顶部50像素处
            
            # 渲染每一行文本
            for i, line in enumerate(lines):
                if not line:  # 跳过空行
                    continue
                    
                # 创建一个带Alpha通道的Surface
                text = font.render(line, True, (255, 255, 255))  # 白色文本
                # 创建透明背景的surface
                text_surface = pygame.Surface(text.get_size(), pygame.SRCALPHA)
                # 将文本复制到透明surface上
                text_surface.blit(text, (0, 0))
                text_rect = text_surface.get_rect(center=(display[0]//2, start_y + i * line_height))
                
                # 启用2D纹理
                glEnable(GL_TEXTURE_2D)
                glEnable(GL_BLEND)
                glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
                
                # 创建纹理
                texture_data = pygame.image.tostring(text_surface, "RGBA", True)
                texture = glGenTextures(1)
                glBindTexture(GL_TEXTURE_2D, texture)
                glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, text_surface.get_width(), text_surface.get_height(),
                            0, GL_RGBA, GL_UNSIGNED_BYTE, texture_data)
                # 设置纹理参数
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                
                # 绘制文本纹理，修正纹理坐标以匹配倒置的Y坐标
                glBegin(GL_QUADS)
                glTexCoord2f(0, 1); glVertex2f(text_rect.left, text_rect.top)
                glTexCoord2f(1, 1); glVertex2f(text_rect.right, text_rect.top)
                glTexCoord2f(1, 0); glVertex2f(text_rect.right, text_rect.bottom)
                glTexCoord2f(0, 0); glVertex2f(text_rect.left, text_rect.bottom)
                glEnd()
                
                # 清理纹理
                glDeleteTextures([texture])
                glDisable(GL_TEXTURE_2D)
                glDisable(GL_BLEND)
            
            # 恢复之前的投影矩阵
            glMatrixMode(GL_PROJECTION)
            glPopMatrix()
            glMatrixMode(GL_MODELVIEW)
            glPopMatrix()

        # 渲染文本输入框
        # 更新光标闪烁计时器
        text_input_cursor_timer += 1
        if text_input_cursor_timer >= 30:  # 每30帧闪烁一次（约0.5秒）
            text_input_cursor_timer = 0
            text_input_cursor_visible = not text_input_cursor_visible
        
        # 清除深度缓冲
        glClear(GL_DEPTH_BUFFER_BIT)
        
        # 切换到正交投影用于2D渲染
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, display[0], display[1], 0, -1, 1)
        
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        
        # 输入框参数
        input_box_width = display[0] - 40
        line_height = 40  # 每行高度
        min_height = 60   # 最小高度
        padding_top = 10  # 顶部内边距
        padding_bottom = 10  # 底部内边距
        
        # 准备显示的文本（包括组合文本）
        display_text = text_input_string + text_composition
        if text_input_active and text_input_cursor_visible:
            display_text += "|"  # 光标
        
        # 使用wrap_text函数将文本分割成多行
        max_text_width = input_box_width - 20  # 留出左右边距
        lines = wrap_text(display_text, text_input_font, max_text_width)
        
        # 计算输入框高度（基于行数）
        num_lines = max(1, len(lines))  # 至少1行
        input_box_height = min_height
        if num_lines > 1:
            input_box_height = padding_top + (num_lines * line_height) + padding_bottom
        
        # 确保输入框不会超出屏幕
        max_height = display[1] - 100  # 屏幕高度减去顶部留空
        input_box_height = min(input_box_height, max_height)
        
        # 计算输入框Y位置（保持在屏幕底部）
        input_box_y = display[1] - input_box_height - 20
        
        # 绘制输入框背景
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(0.2, 0.2, 0.2, 0.7)  # 半透明深灰色背景
        glBegin(GL_QUADS)
        glVertex2f(20, input_box_y)
        glVertex2f(20 + input_box_width, input_box_y)
        glVertex2f(20 + input_box_width, input_box_y + input_box_height)
        glVertex2f(20, input_box_y + input_box_height)
        glEnd()
        
        # 绘制边框
        if text_input_active:
            glColor4f(0.4, 0.8, 1.0, 1.0)  # 激活时蓝色边框
        else:
            glColor4f(0.5, 0.5, 0.5, 1.0)  # 非激活时灰色边框
        
        glLineWidth(2.0)
        glBegin(GL_LINE_LOOP)
        glVertex2f(20, input_box_y)
        glVertex2f(20 + input_box_width, input_box_y)
        glVertex2f(20 + input_box_width, input_box_y + input_box_height)
        glVertex2f(20, input_box_y + input_box_height)
        glEnd()
        
        # 绘制输入文本（多行）
        if display_text or text_input_active:
            # 渲染每一行文本
            for i, line in enumerate(lines):
                if not line:  # 跳过空行
                    continue
                    
                # 计算当前行的Y位置
                line_y = input_box_y + padding_top + (i * line_height)
                
                # 创建文本surface
                text_surface = text_input_font.render(line, True, (255, 255, 255))
                # 创建透明背景的surface
                text_bg_surface = pygame.Surface(text_surface.get_size(), pygame.SRCALPHA)
                text_bg_surface.blit(text_surface, (0, 0))
                text_rect = text_bg_surface.get_rect(midleft=(30, line_y + line_height//2))
                
                # 启用2D纹理
                glEnable(GL_TEXTURE_2D)
                
                # 创建纹理
                texture_data = pygame.image.tostring(text_bg_surface, "RGBA", True)
                texture = glGenTextures(1)
                glBindTexture(GL_TEXTURE_2D, texture)
                glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, text_bg_surface.get_width(), text_bg_surface.get_height(),
                            0, GL_RGBA, GL_UNSIGNED_BYTE, texture_data)
                # 设置纹理参数
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                
                # 绘制文本纹理，修正纹理坐标以匹配倒置的Y坐标
                glBegin(GL_QUADS)
                glTexCoord2f(0, 1); glVertex2f(text_rect.left, text_rect.top)
                glTexCoord2f(1, 1); glVertex2f(text_rect.right, text_rect.top)
                glTexCoord2f(1, 0); glVertex2f(text_rect.right, text_rect.bottom)
                glTexCoord2f(0, 0); glVertex2f(text_rect.left, text_rect.bottom)
                glEnd()
                
                # 清理纹理
                glDeleteTextures([texture])
                glDisable(GL_TEXTURE_2D)
        
        # 绘制提示文本
        prompt_text = "按Tab键激活/取消激活文本输入框"
        if text_input_active:
            prompt_text = "输入文本后按回车键发送，ESC键取消激活"
        
        prompt_surface = text_input_font.render(prompt_text, True, (200, 200, 200))
        prompt_bg_surface = pygame.Surface(prompt_surface.get_size(), pygame.SRCALPHA)
        prompt_bg_surface.blit(prompt_surface, (0, 0))
        prompt_rect = prompt_bg_surface.get_rect(midleft=(30, input_box_y - 15))
        
        glEnable(GL_TEXTURE_2D)
        prompt_texture_data = pygame.image.tostring(prompt_bg_surface, "RGBA", True)
        prompt_texture = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, prompt_texture)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, prompt_bg_surface.get_width(), prompt_bg_surface.get_height(),
                    0, GL_RGBA, GL_UNSIGNED_BYTE, prompt_texture_data)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        
        glBegin(GL_QUADS)
        glTexCoord2f(0, 1); glVertex2f(prompt_rect.left, prompt_rect.top)
        glTexCoord2f(1, 1); glVertex2f(prompt_rect.right, prompt_rect.top)
        glTexCoord2f(1, 0); glVertex2f(prompt_rect.right, prompt_rect.bottom)
        glTexCoord2f(0, 0); glVertex2f(prompt_rect.left, prompt_rect.bottom)
        glEnd()
        
        glDeleteTextures([prompt_texture])
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_BLEND)
        
        # 恢复之前的投影矩阵
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        
        pygame.display.flip()
        pygame.time.wait(10)

    # 清理资源
    voice_listener.stop_listening()
    response_processor.stop_processing()
    live2d.dispose()
    pygame.quit()
    quit()


if __name__ == "__main__":
    currentTopClickedPartId = None
    main()
