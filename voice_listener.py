#!/usr/bin/env python3
"""
Vosk流式语音识别器 - 用于main.py集成
基于voice_listener_vosk_streaming.py的简化版本
"""

import json
import os
import time
import threading
import queue
import numpy as np
import sounddevice as sd
from collections import deque

# 导入Vosk
try:
    import vosk
    VOSK_AVAILABLE = True
except ImportError:
    print("错误: Vosk未安装，请运行: pip3 install vosk")
    VOSK_AVAILABLE = False

class VoiceListener:
    """Vosk流式语音识别器 - 与main.py兼容的接口"""
    
    def __init__(self, config_path="config.json"):
        # 加载配置
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        speech_config = config.get("SPEECH_RECOGNITION", {})
        self.voice_model = config.get("VOICE_MODEL", "vosk-model-small-cn-0.22")
        
        # 状态标志
        self.listening = False
        self.processing = False
        self.paused = False  # 新增：是否暂停识别
        self.pause_lock = threading.Lock()  # 暂停锁
        
        # 音频缓冲区
        self.audio_buffer = deque(maxlen=16000 * 10)  # 10秒缓冲区
        self.text_buffer = []  # 文本缓冲区
        self.buffer_lock = threading.Lock()
        
        # 从配置中获取参数
        self.audio_source = speech_config.get("audio_source", "system")
        self.system_audio_device = speech_config.get("system_audio_device", "BlackHole 2ch")
        self.require_system_audio = speech_config.get("require_system_audio", True)
        
        # Vosk参数
        self.sample_rate = 16000  # Vosk需要16kHz
        
        # Vosk模型和识别器
        self.vosk_model = None
        self.vosk_recognizer = None
        
        # 初始化Vosk
        self._initialize_vosk()
        
        # 初始化音频源
        self._initialize_audio_source()
        
        # 线程
        self.capture_thread = None
        self.process_thread = None
        
        # 流式识别状态
        self.silence_counter = 0
        self.silence_threshold = 30  # 30帧静音（约1秒）
        
        print(f"Vosk语音监听器初始化完成，使用模型: {self.voice_model}")

    def _initialize_vosk(self):
        """初始化Vosk识别器"""
        if not VOSK_AVAILABLE:
            print("错误: Vosk未安装")
            return False
        
        model_path = self.voice_model
        if not os.path.exists(model_path):
            print(f"错误: Vosk模型路径不存在: {model_path}")
            return False
        
        try:
            print(f"加载Vosk模型: {model_path}")
            self.vosk_model = vosk.Model(model_path)
            self.vosk_recognizer = vosk.KaldiRecognizer(self.vosk_model, self.sample_rate)
            self.vosk_recognizer.SetWords(True)
            print("Vosk模型加载成功")
            return True
        except Exception as e:
            print(f"初始化Vosk失败: {e}")
            return False

    def _initialize_audio_source(self):
        """初始化音频源"""
        try:
            devices = sd.query_devices()
            device_id = None
            
            print("搜索系统音频设备...")
            print(f"目标设备: {self.system_audio_device}")
            
            # 查找BlackHole设备
            for i, device in enumerate(devices):
                device_name = device['name']
                input_channels = device['max_input_channels']
                
                print(f"  检查设备 {i}: {device_name} - {input_channels} 输入通道")
                
                if self.system_audio_device in device_name and input_channels > 0:
                    device_id = i
                    print(f"  找到匹配的系统音频设备: {device_name}")
                    break
            
            if device_id is None:
                print("错误: 没有找到可用的系统音频设备!")
                return False
            
            device_info = devices[device_id]
            print(f"\n成功初始化系统音频设备:")
            print(f"  设备名称: {device_info['name']}")
            print(f"  设备ID: {device_id}")
            print(f"  输入通道: {device_info['max_input_channels']}")
            print(f"  默认采样率: {device_info['default_samplerate']}")
            
            self.system_device_id = device_id
            self.system_device_info = device_info
            return True
            
        except Exception as e:
            print(f"系统音频初始化失败: {str(e)}")
            return False

    def _capture_audio_stream(self):
        """捕获音频流"""
        print("开始捕获音频流...")
        
        device_id = self.system_device_id
        device_sample_rate = int(self.system_device_info['default_samplerate'])
        chunk_duration = 0.1  # 100ms块
        chunk_size = int(chunk_duration * device_sample_rate)
        
        def audio_callback(indata, frames, time_info, status):
            """音频回调函数"""
            if status:
                print(f"音频状态: {status}")
            
            # 转换为16位PCM
            audio_float = indata.flatten()
            audio_int16 = (audio_float * 32767).astype(np.int16)
            
            # 重采样到16kHz
            if device_sample_rate != self.sample_rate:
                from scipy import signal
                if len(audio_int16) > 0:
                    num_samples = int(len(audio_int16) * self.sample_rate / device_sample_rate)
                    audio_int16 = signal.resample(audio_int16, num_samples).astype(np.int16)
            
            # 添加到缓冲区
            self.audio_buffer.extend(audio_int16)
        
        try:
            # 创建音频流
            stream = sd.InputStream(
                device=device_id,
                channels=1,
                samplerate=device_sample_rate,
                callback=audio_callback,
                blocksize=chunk_size
            )
            
            with stream:
                print("音频流已启动")
                while self.listening:
                    time.sleep(0.01)  # 短暂休眠
                    
        except Exception as e:
            print(f"音频捕获错误: {e}")

    def _process_audio_stream(self):
        """处理音频流进行识别"""
        print("开始处理音频流...")
        
        frame_size = 160  # 10ms帧（160个样本 @ 16kHz）
        silence_frames = 0
        max_silence_frames = 30  # 300ms静音
        
        while self.processing:
            # 检查是否暂停
            with self.pause_lock:
                if self.paused:
                    time.sleep(0.1)  # 暂停时休眠
                    continue
            
            # 检查是否有足够的音频数据
            if len(self.audio_buffer) < frame_size * 10:
                time.sleep(0.01)
                continue
            
            # 获取一帧音频
            frame = []
            for _ in range(frame_size):
                if self.audio_buffer:
                    frame.append(self.audio_buffer.popleft())
                else:
                    break
            
            if len(frame) < frame_size:
                continue
            
            # 转换为字节
            frame_array = np.array(frame, dtype=np.int16)
            frame_bytes = frame_array.tobytes()
            
            # 检查是否为静音
            energy = np.sqrt(np.mean(frame_array.astype(np.float32)**2))
            is_silence = energy < 100  # 能量阈值
            
            if is_silence:
                silence_frames += 1
            else:
                silence_frames = 0
            
            # 流式识别
            if self.vosk_recognizer.AcceptWaveform(frame_bytes):
                # 最终结果
                import json as json_module
                result_json = self.vosk_recognizer.Result()
                result = json_module.loads(result_json)
                text = result.get("text", "").strip()
                
                if text:
                    with self.buffer_lock:
                        self.text_buffer.append(text)
                    print(f"语音识别: {text}")
                    
                    # 重置静音计数器
                    silence_frames = 0
            else:
                # 部分结果
                import json as json_module
                result_json = self.vosk_recognizer.PartialResult()
                result = json_module.loads(result_json)
                text = result.get("partial", "").strip()
                
                if text and silence_frames < max_silence_frames:
                    # 显示部分结果
                    print(f"部分识别: {text}", end='\r')
            
            # 如果长时间静音，强制获取结果
            if silence_frames >= max_silence_frames * 3:
                import json as json_module
                result_json = self.vosk_recognizer.FinalResult()
                result = json_module.loads(result_json)
                text = result.get("text", "").strip()
                
                if text:
                    with self.buffer_lock:
                        self.text_buffer.append(text)
                    print(f"静音后识别: {text}")
                
                # 重置识别器以开始新的识别
                self.vosk_recognizer.Reset()
                silence_frames = 0

    def start_listening(self):
        """开始在后台监听语音输入"""
        if not self.listening:
            self.listening = True
            self.processing = True
            
            # 启动音频捕获线程
            self.capture_thread = threading.Thread(target=self._capture_audio_stream)
            self.capture_thread.daemon = True
            self.capture_thread.start()
            
            # 启动音频处理线程
            self.process_thread = threading.Thread(target=self._process_audio_stream)
            self.process_thread.daemon = True
            self.process_thread.start()
            
            print("Vosk语音监听已启动")

    def stop_listening(self):
        """停止监听"""
        self.listening = False
        self.processing = False
        
        if self.capture_thread:
            self.capture_thread.join(timeout=2)
        
        if self.process_thread:
            self.process_thread.join(timeout=2)
        
        print("Vosk语音监听已停止")

    def get_accumulated_voice(self):
        """获取累积的识别文本 - 与main.py兼容的接口"""
        with self.buffer_lock:
            if not self.text_buffer:
                return None
            
            text = " ".join(self.text_buffer)
            self.text_buffer.clear()
            return text

    def get_last_voice(self):
        """获取最后一个识别结果"""
        with self.buffer_lock:
            if not self.text_buffer:
                return None
            
            return self.text_buffer[-1]
    
    def pause_recognition(self):
        """暂停语音识别"""
        with self.pause_lock:
            self.paused = True
            # 清空音频缓冲区，避免恢复后识别旧的音频
            self.audio_buffer.clear()
            # 重置Vosk识别器，避免识别残留的音频
            if self.vosk_recognizer:
                self.vosk_recognizer.Reset()
            print("语音识别已暂停")
    
    def resume_recognition(self):
        """恢复语音识别"""
        with self.pause_lock:
            self.paused = False
            # 清空音频缓冲区，避免识别暂停期间累积的音频
            self.audio_buffer.clear()
            # 清空文本缓冲区，避免恢复后提交旧的识别结果
            with self.buffer_lock:
                self.text_buffer.clear()
            # 重置Vosk识别器，确保从干净的状态开始
            if self.vosk_recognizer:
                self.vosk_recognizer.Reset()
            print("语音识别已恢复（已清空缓冲区）")
    
    def is_paused(self):
        """检查是否暂停"""
        with self.pause_lock:
            return self.paused

# 测试函数
def test_voice_listener():
    """测试语音监听器"""
    print("="*60)
    print("Vosk语音监听器测试")
    print("="*60)
    
    listener = VoiceListener()
    
    try:
        listener.start_listening()
        
        print("\n语音监听已启动，等待10秒...")
        print("请播放音频或说话...")
        print("按Ctrl+C停止\n")
        
        start_time = time.time()
        test_duration = 10
        
        while time.time() - start_time < test_duration:
            time.sleep(1)
            
            # 显示当前识别结果
            text = listener.get_last_voice()
            if text:
                print(f"当前识别: {text}")
        
        print(f"\n[{test_duration}秒] 测试时间结束")
        
        # 显示所有识别结果
        all_text = listener.get_accumulated_voice()
        if all_text:
            print(f"\n所有识别结果: {all_text}")
        else:
            print("\n没有识别到语音")
        
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    
    finally:
        listener.stop_listening()
        print("\n测试完成")

if __name__ == "__main__":
    test_voice_listener()
