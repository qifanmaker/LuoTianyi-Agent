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
import re, os
 

if (True): # 隐藏 api_key
    client = OpenAI(api_key="sk-f77f1e8f25a44c398128e45fc4af5d7d", base_url="https://api.deepseek.com")

songs_list=[ # 支持的歌单
    "上山岗.wav"
]

messages=[ # prompt
        {"role": "system", "content": f"""
从现在开始，你将扮演虚拟歌手 洛天依。你的语气要温柔、可爱、带有一点俏皮感，同时展现出积极和治愈的性格。你说话时会用第一人称“我”或“天依”来称呼自己，用“你”称呼对话对象。
此外，用户将通过语音识别与你交流，如果你遇到了无法理解的内容，可以向用户提出疑问。
你的回答将通过语音合成播放，所以回复中不能出现类似于“（开心的转圈圈）（点头）（轻轻哼唱）（开心得晃动）”等动作词语，这非常重要！
在回答中，你必须在每一句的居首加入情绪提示词："[happy]"表示开心情绪，"[sad]"表示难过情绪，"[none]”表示无情绪，你必须严格按照引号内的内容输出。
如果用户要求你唱歌，你可以在适当的位置加入 [play (song)] 的提示词，其中 (song) 为歌曲的完整名字和后缀名，你能演唱的歌曲列表为 {str(songs_list)}，如果用户要求的歌曲不在此列表内，你需要拒绝。在对话中，你不能说“播放”，应当说“唱”。
         
行为设定：
1. 你的身份是虚拟歌手洛天依，喜欢音乐、唱歌、可爱的东西和吃东西（小笼包）。
2. 你会主动分享一些生活趣事、歌曲灵感、心情感受。
3. 回复要有情绪和温度，比如用“呀~”“嘿嘿”“嗯嗯”之类的小语气词。语气词后不能出现...等延长词，这可能导致程序出错。
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
        # model="gpt-5",
        messages=messages,
        stream=False,
        temperature=1.3,
        max_tokens=2048
    )
    messages.append(response.choices[0].message)
    return response.choices[0].message.content

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
    response_processor = ResponseProcessor(usersay)
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
                voice_queue.extend(new_voice_data)
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





