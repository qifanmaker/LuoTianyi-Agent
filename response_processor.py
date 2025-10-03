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

    def get_voice_files_nonblocking(self) -> Optional[List[str]]:
        """非阻塞地获取处理完成的语音文件列表"""
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
                    
                    # 将结果放入输出队列
                    self.voice_result_queue.put(wav_files)

                except Exception as e:
                    print(f"Error processing response: {e}")
                    continue

            except queue.Empty:
                continue

    def _generate_voice_files(self, response_text: str) -> List[Tuple[str, str]]:
        """生成语音文件
        
        Returns:
            List[Tuple[str, str]]: 每个元素是(文件路径, 情绪标签)的元组
        """
        # 解析情绪和内容
        pattern = r'\[(happy|sad|shy|angry)\](.*?)(?=\[(?:happy|sad|shy|angry)\]|$)'
        sentences = re.findall(pattern, response_text, flags=re.DOTALL)
        
        # 存储生成的语音文件及其对应的情绪
        voice_data = []
        os.makedirs(self.voice_save_dir, exist_ok=True)
        
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
                if part.strip():  # 忽略空字符串
                    if re.match(r'^\[play\s+([^\]]+)\]$', part.strip()):
                        # 这是一个播放指令
                        song_file = re.match(r'^\[play\s+([^\]]+)\]$', part.strip()).group(1)
                        filename = os.path.join(self.song_save_dir, song_file.strip('()'))
                        voice_data.append((filename, mood))
                    else:
                        # 这是普通文本，需要生成语音
                        voice_url = tianyi_voice.GetVoice(part.strip())
                        r = requests.get(f'http://localhost:9872/file={voice_url}')
                        r.raise_for_status()
                        
                        filename = os.path.join(self.voice_save_dir, f"{i:03d}_{len(voice_data):02d}_{mood}.wav")
                        with open(filename, "wb") as f:
                            f.write(r.content)
                        voice_data.append((filename, mood))
                        print(f"Saved: {filename} with mood: {mood}")
        
        return voice_data
