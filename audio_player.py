import pygame
from live2d.utils import log
from live2d.utils.lipsync import WavHandler
from live2d.v3 import StandardParams
import wave

class EnhancedWavHandler(WavHandler):
    def __init__(self):
        super().__init__()
        self.total_frames = 0
        self.current_frame = 0
        self.frame_step = 1024  # 默认帧步进大小

    def Start(self, wav_path):
        # 获取音频总帧数
        with wave.open(wav_path, 'rb') as wav_file:
            self.total_frames = wav_file.getnframes()
            # 根据采样率调整帧步进大小，确保进度计算准确
            self.frame_step = int(wav_file.getframerate() / 50)  # 假设50Hz更新率
        super().Start(wav_path)

    def Update(self):
        result = super().Update()
        if result:
            # 使用动态计算的帧步进大小
            self.current_frame += self.frame_step
        return result

    def is_near_end(self, threshold=0.9):
        """检查音频是否接近结束
        Args:
            threshold (float): 判断接近结束的阈值（0-1），默认0.9表示90%
        Returns:
            bool: 如果播放进度超过阈值则返回True
        """
        if self.total_frames == 0:
            return False
        return self.current_frame / self.total_frames >= threshold

def play_audio_with_lipsync(model, audio_path: str, lip_sync_n: float = 3.0):
    """
    播放指定的音频文件并同步口型动画
    
    Args:
        model: Live2D 模型实例
        audio_path (str): 音频文件的绝对路径
        lip_sync_n (float): 口型动画的放大系数，默认为3.0
        
    Returns:
        tuple: (WavHandler, float) - 返回音频处理器和口型系数，用于后续更新
    """
    # 初始化音频处理器
    wav_handler = EnhancedWavHandler()
    
    # 加载并播放音频
    pygame.mixer.music.load(audio_path)
    pygame.mixer.music.play()
    
    # 开始口型同步
    log.Info(f"Starting lipSync for {audio_path}")
    wav_handler.Start(audio_path)
    
    # 返回wav_handler以便外部更新口型
    return wav_handler, lip_sync_n

def update_lipsync(model, wav_handler, lip_sync_n: float = 3.0):
    """
    更新模型的口型动画
    
    Args:
        model: Live2D 模型实例
        wav_handler: WavHandler 实例
        lip_sync_n (float): 口型动画的放大系数
        
    Returns:
        bool: 如果音频还在播放返回True，否则返回False
    """
    if wav_handler.Update():
        # 利用 wav 响度更新嘴部张合
        model.SetParameterValue(
            StandardParams.ParamMouthOpenY, 
            wav_handler.GetRms() * lip_sync_n
        )
        return True
    return False
