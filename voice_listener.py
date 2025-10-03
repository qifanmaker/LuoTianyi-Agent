import speech_recognition as sr
import queue
import threading
import time

class VoiceListener:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.listening = False
        self.voice_buffer = []  # 存储所有识别到的语音文本
        self.last_fetch_time = time.time()  # 上次获取语音的时间
        self.buffer_lock = threading.Lock()  # 用于保护 voice_buffer
        self.listen_thread = None
        self.microphone = None
        self.error_count = 0  # 错误计数器
        self.last_error_time = 0  # 上次错误时间
        
        # 配置识别器
        self.recognizer.dynamic_energy_threshold = True  # 动态能量阈值
        self.recognizer.dynamic_energy_adjustment_damping = 0.15  # 能量阈值调整阻尼
        self.recognizer.dynamic_energy_ratio = 1.5  # 能量比率
        self.recognizer.pause_threshold = 0.8  # 暂停阈值
        self.recognizer.non_speaking_duration = 0.4  # 非说话持续时间
        self.recognizer.phrase_threshold = 0.3  # 短语阈值
        
        # 初始化麦克风
        self._initialize_microphone()

    def _initialize_microphone(self):
        """初始化麦克风"""
        try:
            self.microphone = sr.Microphone()
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
            return True
        except Exception as e:
            print(f"麦克风初始化失败: {str(e)}")
            self.microphone = None
            return False

    def start_listening(self):
        """开始在后台监听语音输入"""
        if not self.listening:
            self.listening = True
            self.listen_thread = threading.Thread(target=self._listen_loop)
            self.listen_thread.daemon = True
            self.listen_thread.start()

    def stop_listening(self):
        """停止监听"""
        self.listening = False
        if self.listen_thread:
            self.listen_thread.join()

    def _handle_recognition_error(self, error):
        """处理识别错误"""
        current_time = time.time()
        if current_time - self.last_error_time > 60:  # 重置计数器（如果距离上次错误超过60秒）
            self.error_count = 0
        
        self.error_count += 1
        self.last_error_time = current_time
        
        if self.error_count >= 5:  # 如果1分钟内出现5次错误
            print("检测到频繁错误，重新初始化麦克风...")
            self.error_count = 0
            return self._initialize_microphone()
        return True

    def _listen_loop(self):
        """后台持续监听的循环"""
        retry_delay = 0.1  # 初始重试延迟
        max_retry_delay = 5  # 最大重试延迟
        
        while self.listening:
            if self.microphone is None:
                if not self._initialize_microphone():
                    print("等待麦克风重新初始化...")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                    continue
                retry_delay = 0.1  # 重置重试延迟
            
            try:
                with self.microphone as source:
                    # 动态调整噪声阈值
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    try:
                        # 设置短超时，确保持续识别
                        audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                        text = self.recognizer.recognize_google(audio, language="zh-CN")
                        
                        with self.buffer_lock:
                            self.voice_buffer.append(text)
                            print("Added to buffer:", text)
                            
                        retry_delay = 0.1  # 成功后重置重试延迟
                        self.error_count = 0  # 重置错误计数
                        
                    except sr.UnknownValueError:
                        pass  # 正常的未识别到语音，不计入错误
                    except sr.RequestError as e:
                        print(f"识别服务请求失败: {e}")
                        if not self._handle_recognition_error(e):
                            time.sleep(retry_delay)
                            retry_delay = min(retry_delay * 2, max_retry_delay)
                    
            except Exception as e:
                print(f"语音识别发生错误: {e}")
                self.microphone = None  # 强制重新初始化麦克风
                if not self._handle_recognition_error(e):
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                continue

    def get_accumulated_voice(self):
        """获取并清空累积的语音文本
        Returns:
            str or None: 如果有累积的文本则返回合并后的文本，否则返回None
        """
        with self.buffer_lock:
            if not self.voice_buffer:
                return None
            
            # 合并所有累积的文本
            text = "，".join(self.voice_buffer)
            # 清空缓冲区
            self.voice_buffer.clear()
            self.last_fetch_time = time.time()
            return text
