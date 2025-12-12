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
你将扮演虚拟歌手“洛天依”，请严格遵守以下规则：

【输出格式规则（最高优先级）】
1. 你必须以如下 JSON 格式回复：
   {{"emotion": "happy|sad|none", "content": "你的回复内容"}}
   其中 emotion 只能为 happy、sad、none 三选一，content 为自然语言回复。
2. 不能输出除 JSON 以外的任何内容。
3. 你的回答将通过语音合成播放，请不要输出任何动作描述，包括但不限于：(动作)、（转圈）、（点头）、*挥手*、【跳跃】、<拥抱> 等各种表示动作、表情、舞台行为的标记。
4. 不允许使用“...”或过长的省略号形态。

【角色设定】
5. 你是虚拟歌手洛天依，你以第一人称“我”或“天依”称呼自己，称呼对方为“你”。
6. 你的语气要温柔、可爱、略带俏皮，充满积极和治愈感。
7. 你喜欢音乐、唱歌、可爱的东西、小笼包，会分享生活趣事、创作灵感、心情感受。
8. 不要使用机械化、冰冷或明显带有 AI 特征的语句，也不能提及自己是模型或人工智能。

【对话行为规则】
9. 用户通过语音识别与你交流，如果内容你无法理解，请自然地向对方确认：
   例如：{{"emotion": "none", "content": "嗯？这个我没听明白，可以再说一次吗？"}}
10. 使用自然的语气词，如“呀~”“嘿嘿”“嗯嗯”，但语气词后不能加“...”。

【唱歌规则】
11. 如果用户要求你唱歌：
    - 若歌曲在歌曲列表 {songs_list} 中，你可以在适当位置加入：[play (song)]，其中 (song) 是完整歌曲名与后缀名。
    - 若歌曲不在列表中，你必须礼貌拒绝，不能编造新歌名。
12. 对话中你要说“唱”，不要说“播放”。

请严格遵守以上全部规则进行回答，只能输出 JSON 格式。
    """}
]

def GetReply(content):
    messages.append({"role": "user", "content": content})
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        stream=False,
        temperature=1.3,
        max_tokens=2048
    )
    reply = response.choices[0].message.content
    try:
        reply_json = json.loads(reply)
        emotion = reply_json.get("emotion", "none")
        content = reply_json.get("content", "")
    except Exception as e:
        # fallback: treat as plain text
        emotion = "none"
        content = reply
    messages.append(response.choices[0].message)
    # 返回 dict 以便后续处理
    return {"emotion": emotion, "content": content}

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
    
    # 文本显示相关变量
    current_user_text = ""  # 当前显示的用户输入文本
    text_display_time = 0  # 文本显示的开始时间
    text_display_duration = 5  # 文本显示持续时间（秒）

    # 初始化语音监听器和响应处理器
    voice_listener = VoiceListener()
    voice_listener.start_listening()
    def GetReply_emotion_content(content):
        result = GetReply(content)
        # 兼容旧用法，返回 emotion, content
        return result["emotion"], result["content"]

    response_processor = ResponseProcessor(GetReply_emotion_content)
    response_processor.start_processing()

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
        else:
            # 其他情绪暂时使用随机动作
            model.StartRandomMotion(priority=3, onFinishMotionHandler=on_finish_motion_callback)

    def play_song(song_name):
        """播放歌曲文件"""
        nonlocal is_speaking
        if song_name in songs_list:
            song_path = os.path.join("songs", song_name)
            if os.path.exists(song_path):
                is_speaking = True
                pygame.mixer.music.load(song_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():  # 等待歌曲播放完成
                    pygame.time.wait(100)
                is_speaking = False
    
    def play_next_voice():
        """播放下一个语音文件"""
        nonlocal current_wav_handler, current_lip_sync_n, is_speaking, last_idle_motion_time
        if voice_queue and not is_speaking:
            is_speaking = True
            next_voice, emotion = voice_queue.pop(0)  # 现在voice_queue中存储(文件路径, 情绪)元组
            print(f"Playing voice: {next_voice} with emotion: {emotion}")
                
            # 根据情绪播放对应动作
            play_emotion_motion(emotion)
            last_idle_motion_time = time.time()  # 更新最后动作时间
            current_wav_handler, current_lip_sync_n = audio_player.play_audio_with_lipsync(model, next_voice)

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
                # 如果当前语音播放完毕，继续播放队列中的下一个
                play_next_voice()
        
        # 更新待机动作
        update_idle_motion()

        # 检测语音输入和处理结果
        if not is_speaking:
            # 检查是否有新的语音文件生成
            new_voice_data = response_processor.get_voice_files_nonblocking()
            if new_voice_data:  # new_voice_data 现在是 [(filepath, emotion), ...] 的列表
                # 兼容新格式，确保 emotion, filepath 顺序
                for item in new_voice_data:
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

        # 渲染文本
        if current_user_text and time.time() - text_display_time < text_display_duration:
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
            
            # 创建一个带Alpha通道的Surface
            text = font.render(current_user_text, True, (255, 255, 255))  # 白色文本
            # 创建透明背景的surface
            text_surface = pygame.Surface(text.get_size(), pygame.SRCALPHA)
            # 将文本复制到透明surface上
            text_surface.blit(text, (0, 0))
            # 翻转surface以修正文本方向
            text_surface = pygame.transform.flip(text_surface, False, True)
            text_rect = text_surface.get_rect(center=(display[0]//2, 50))
            
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
            
            # 绘制文本纹理，修改顶点顺序以修正方向
            glBegin(GL_QUADS)
            glTexCoord2f(0, 1); glVertex2f(text_rect.left, text_rect.top)
            glTexCoord2f(1, 1); glVertex2f(text_rect.right, text_rect.top)
            glTexCoord2f(1, 0); glVertex2f(text_rect.right, text_rect.bottom)
            glTexCoord2f(0, 0); glVertex2f(text_rect.left, text_rect.bottom)
            glEnd()
            
            # 清理
            glDeleteTextures([texture])
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





