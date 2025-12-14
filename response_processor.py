import threading
import queue
from typing import List, Tuple, Optional
import requests
import os
import re
import tianyi_voice

class ResponseProcessor:
    def __init__(self, llm_callback, voice_save_dir="voices", song_save_dir="songs"):
        self.llm_callback = llm_callback  # LLM回调函数（usersay函数）
        self.voice_save_dir = voice_save_dir
        self.song_save_dir = song_save_dir
        self.processing_queue = queue.Queue()  # 待处理的用户输入队列
        self.voice_result_queue = queue.Queue()  # 处理完成的语音文件队列
        self.processing = False
        self.processor_thread = None

    def start_processing(self):
        """启动处理线程"""
        if not self.processing:
            self.processing = True
            self.processor_thread = threading.Thread(target=self._process_loop)
            self.processor_thread.daemon = True
            self.processor_thread.start()

    def stop_processing(self):
        """停止处理线程"""
        self.processing = False
        if self.processor_thread:
            self.processor_thread.join()

    def add_user_input(self, user_input: str):
        """添加用户输入到处理队列"""
        self.processing_queue.put(user_input)

    def get_voice_files_nonblocking(self) -> Optional[dict]:
        """非阻塞地获取处理完成的语音文件列表和文本内容"""
        try:
            return self.voice_result_queue.get_nowait()
        except queue.Empty:
            return None

    def _process_loop(self):
        """处理循环"""
        while self.processing:
            try:
                # 获取用户输入
                user_input = self.processing_queue.get(timeout=0.1)
                
                try:
                    # 获取LLM回复
                    print("Asking LLM for reply...")
                    response = self.llm_callback(user_input)
                    print("LLM replied:", response)

                    # 生成语音文件
                    print("Getting voices...")
                    wav_files = self._generate_voice_files(response)
                    
                    # 提取文本内容
                    text_content = ""
                    if isinstance(response, dict):
                        text_content = response.get('content', '')
                    elif isinstance(response, (tuple, list)) and len(response) == 2:
                        # 兼容 (emotion, content) 格式
                        if not (response[0] and isinstance(response[0], str) and response[0].endswith(('.wav', '.mp3'))):
                            text_content = response[1] if len(response) > 1 else ''
                    else:
                        # 尝试解析字符串
                        import json
                        try:
                            resp_obj = json.loads(response)
                            if isinstance(resp_obj, dict):
                                text_content = resp_obj.get('content', '')
                        except:
                            text_content = str(response)
                    
                    # 将结果放入输出队列，现在包含文本内容
                    result = {
                        'files': wav_files,
                        'text': text_content
                    }
                    self.voice_result_queue.put(result)

                except Exception as e:
                    print(f"Error processing response: {e}")
                    continue

            except queue.Empty:
                continue

    def _generate_voice_files(self, response) -> List[Tuple[str, str]]:
        """生成语音文件，支持 LLM JSON 格式返回
        response: 可以是 str（老格式），也可以是 dict（新格式），或 emotion/content 字段
        Returns:
            List[Tuple[str, str]]: 每个元素是(文件路径, 情绪标签)的元组
        """
        import json
        voice_data = []
        os.makedirs(self.voice_save_dir, exist_ok=True)

        # 1. 新格式：dict、tuple 或 json字符串
        if isinstance(response, dict):
            # 新增：支持新版 action 字段
            emotion = response.get('emotion', 'none')
            content = response.get('content', '')
            action = response.get('action', None)
            
            # 如果有action参数，先处理content的语音，再添加歌曲
            if action and isinstance(action, dict) and action.get('type') == 'play_song':
                song_file = action.get('song')
                if song_file:
                    # 先处理content的语音（如果有内容）
                    if content and content.strip():
                        # 生成content的语音文件
                        voice_url = tianyi_voice.GetVoice(content.strip())
                        r = requests.get(f'http://localhost:9872/file={voice_url}')
                        r.raise_for_status()
                        filename = os.path.join(self.voice_save_dir, f"000_{len(voice_data):02d}_{emotion}.wav")
                        with open(filename, "wb") as f:
                            f.write(r.content)
                        voice_data.append((filename, emotion))
                        print(f"Saved content voice: {filename} with mood: {emotion}")
                    
                    # 然后添加歌曲文件
                    filename = os.path.join(self.song_save_dir, song_file.strip('()'))
                    voice_data.append((filename, emotion))
                    return voice_data
        elif isinstance(response, (tuple, list)) and len(response) == 2:
            # 兼容 (emotion, content)
            # 也兼容 (play_song, emotion)
            if response[0] and isinstance(response[0], str) and response[0].endswith(('.wav', '.mp3')):
                # 认为是 (play_song, emotion)
                filename = os.path.join(self.song_save_dir, response[0].strip('()'))
                voice_data.append((filename, response[1] if len(response) > 1 else 'none'))
                return voice_data
            else:
                emotion, content = response
        else:
            # 兼容字符串格式，尝试解析json
            try:
                resp_obj = json.loads(response)
                if isinstance(resp_obj, dict):
                    emotion = resp_obj.get('emotion', 'none')
                    content = resp_obj.get('content', '')
                    action = resp_obj.get('action', None)
                    if action and isinstance(action, dict) and action.get('type') == 'play_song':
                        song_file = action.get('song')
                        if song_file:
                            # 先处理content的语音（如果有内容）
                            if content and content.strip():
                                # 生成content的语音文件
                                voice_url = tianyi_voice.GetVoice(content.strip())
                                r = requests.get(f'http://localhost:9872/file={voice_url}')
                                r.raise_for_status()
                                filename = os.path.join(self.voice_save_dir, f"000_{len(voice_data):02d}_{emotion}.wav")
                                with open(filename, "wb") as f:
                                    f.write(r.content)
                                voice_data.append((filename, emotion))
                                print(f"Saved content voice: {filename} with mood: {emotion}")
                            
                            # 然后添加歌曲文件
                            filename = os.path.join(self.song_save_dir, song_file.strip('()'))
                            voice_data.append((filename, emotion))
                            return voice_data
                else:
                    emotion = 'none'
                    content = response
            except Exception:
                # 老格式，按原有正则分句
                pattern = r'\[(happy|sad|shy|angry)\](.*?)(?=\[(?:happy|sad|shy|angry)\]|$)'
                sentences = re.findall(pattern, response, flags=re.DOTALL)
                for i, (mood, content) in enumerate(sentences, 1):
                    # 检查是否整个句子都是歌曲播放指令
                    if content.strip() == content and re.match(r'^\s*\[play\s+([^\]]+)\]\s*$', content):
                        song_file = re.match(r'^\s*\[play\s+([^\]]+)\]\s*$', content).group(1)
                        filename = os.path.join(self.song_save_dir, song_file.strip('()'))
                        voice_data.append((filename, mood))
                        continue
                    # 对于包含歌曲播放指令的句子，需要分开处理
                    parts = re.split(r'(\[play\s+[^\]]+\])', content)
                    for part in parts:
                        if part.strip():
                            if re.match(r'^\[play\s+([^\]]+)\]$', part.strip()):
                                song_file = re.match(r'^\[play\s+([^\]]+)\]$', part.strip()).group(1)
                                filename = os.path.join(self.song_save_dir, song_file.strip('()'))
                                voice_data.append((filename, mood))
                            else:
                                voice_url = tianyi_voice.GetVoice(part.strip())
                                r = requests.get(f'http://localhost:9872/file={voice_url}')
                                r.raise_for_status()
                                filename = os.path.join(self.voice_save_dir, f"{i:03d}_{len(voice_data):02d}_{mood}.wav")
                                with open(filename, "wb") as f:
                                    f.write(r.content)
                                voice_data.append((filename, mood))
                                print(f"Saved: {filename} with mood: {mood}")
                return voice_data

        # 2. 新格式单条（只处理一条 content/emotion）
        # 检查是否为歌曲播放指令
        if content.strip() == content and re.match(r'^\s*\[play\s+([^\]]+)\]\s*$', content):
            song_file = re.match(r'^\s*\[play\s+([^\]]+)\]\s*$', content).group(1)
            filename = os.path.join(self.song_save_dir, song_file.strip('()'))
            voice_data.append((filename, emotion))
        else:
            # 可能包含多个 [play ...] 指令，分割处理
            parts = re.split(r'(\[play\s+[^\]]+\])', content)
            for part in parts:
                if part.strip():
                    if re.match(r'^\[play\s+([^\]]+)\]$', part.strip()):
                        song_file = re.match(r'^\[play\s+([^\]]+)\]$', part.strip()).group(1)
                        filename = os.path.join(self.song_save_dir, song_file.strip('()'))
                        voice_data.append((filename, emotion))
                    else:
                        voice_url = tianyi_voice.GetVoice(part.strip())
                        r = requests.get(f'http://localhost:9872/file={voice_url}')
                        r.raise_for_status()
                        filename = os.path.join(self.voice_save_dir, f"000_{len(voice_data):02d}_{emotion}.wav")
                        with open(filename, "wb") as f:
                            f.write(r.content)
                        voice_data.append((filename, emotion))
                        print(f"Saved: {filename} with mood: {emotion}")
        return voice_data
