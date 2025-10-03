import live2d.v3 as live2d
import pygame
from pygame.locals import *
from OpenGL.GL import *
import os
import sys
import traceback

def debug_gl_info():
    try:
        print("\nOpenGL 信息:")
        print(f"Vendor: {glGetString(GL_VENDOR).decode()}")
        print(f"Renderer: {glGetString(GL_RENDERER).decode()}")
        print(f"Version: {glGetString(GL_VERSION).decode()}")
        return True
    except Exception as e:
        print(f"获取 OpenGL 信息失败: {e}")
        return False

print("启动调试...")
print(f"Python 版本: {sys.version}")
print(f"工作目录: {os.getcwd()}")

# 初始化 Pygame
print("\nStep 1: 初始化 Pygame...")
pygame.init()

# 设置 OpenGL 属性
print("\nStep 2: 设置 OpenGL 属性...")
try:
    # 使用最基础的 OpenGL 版本来确保兼容性
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 2)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 0)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_COMPATIBILITY)
    pygame.display.gl_set_attribute(pygame.GL_DOUBLEBUFFER, 1)
    pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 24)
    pygame.display.gl_set_attribute(pygame.GL_ALPHA_SIZE, 8)  # 确保有 Alpha 通道
    print("OpenGL 属性设置成功")
except Exception as e:
    print(f"设置 OpenGL 属性失败: {e}")
    pygame.quit()
    exit(1)
if pygame.init()[1] != 0:
    print(f"警告：Pygame 初始化时有 {pygame.init()[1]} 个模块初始化失败")

# 创建窗口
print("\nStep 3: 创建窗口...")
try:
    display = pygame.display.set_mode((1200, 800), DOUBLEBUF | OPENGL)
    print("窗口创建成功")
except Exception as e:
    print(f"窗口创建失败: {e}")
    pygame.quit()
    exit(1)

# 初始化 Live2D
print("\nStep 4: 初始化 Live2D...")
try:
    live2d.init()
    print("Live2D 核心初始化成功")
    live2d.glInit()
    print("Live2D OpenGL 初始化成功")
except Exception as e:
    print(f"Live2D 初始化失败: {e}")
    pygame.quit()
    exit(1)
try:
    display = pygame.display.set_mode((1200, 800), DOUBLEBUF | OPENGL, vsync=1)
    if not display:
        raise Exception("无法创建显示窗口")
except Exception as e:
    print(f"显示初始化失败: {e}")
    live2d.dispose()
    pygame.quit()
    exit(1)

# 检查 OpenGL 状态
debug_gl_info()

# 创建 Live2D 模型实例
try:
    print("\nStep 5: 创建模型实例...")
    model = live2d.LAppModel()
    if not model:
        raise Exception("无法创建模型实例")
    print("模型实例创建成功")
except Exception as e:
    print(f"模型实例创建失败: {e}")
    print(f"错误堆栈: {traceback.format_exc()}")
    live2d.dispose()
    pygame.quit()
    exit(1)
print("\nStep 6: 检查模型文件...")
model_json_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../Resources/hiyori_pro_zh/runtime/hiyori_pro_t11.model3.json"))
model_dir = os.path.dirname(model_json_path)

# 检查模型文件和目录
if not os.path.exists(model_dir):
    print(f"错误: 模型目录不存在: {model_dir}")
    live2d.dispose()
    pygame.quit()
    exit(1)

if not os.path.exists(model_json_path):
    print(f"错误: 模型文件不存在: {model_json_path}")
    live2d.dispose()
    pygame.quit()
    exit(1)

print(f"模型目录存在: {model_dir}")
print(f"模型文件存在: {model_json_path}")

# 模型状态

live2d_scale: float = 0.9
model.SetScale(live2d_scale)

model.SetAutoBreathEnable(True)
model.SetAutoBlinkEnable(True)

# 最后加载live2d
print("\nStep 7: 加载模型...")
try:
    model.LoadModelJson(model_json_path)
    print(f"模型加载成功: {model_json_path}")
except Exception as e:
    print(f"加载模型失败: {e}")
    print(f"错误堆栈: {traceback.format_exc()}")
    live2d.dispose()
    pygame.quit()
    exit(1)

# 设置时钟来控制帧率
clock = pygame.time.Clock()
target_fps = 60

# 给系统一点时间初始化
pygame.time.wait(1000)

run: bool = True
error_count = 0  # 用于跟踪错误次数
max_errors = 10  # 最大允许的连续错误次数

while run:
    # 处理事件
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            run = False
            break
        
    # 限制帧率
    clock.tick(target_fps)
 
    try:
        # 1、清除缓冲区
        live2d.clearBuffer()
        
        # 2、更新live2d到缓冲区
        model.Update()
        
        # 3、渲染live2d到屏幕
        model.Draw()
        
        # 4、刷新显示
        pygame.display.flip()
        
        # 使用局部变量来跟踪第一帧
        if not 'frame_count' in locals():
            frame_count = 0
        frame_count += 1
        
        if frame_count == 1:
            print("\n渲染成功!")
            
    except Exception as e:
        error_count += 1
        print(f"\n渲染循环出错 ({error_count}/{max_errors}): {e}")
        if error_count >= max_errors:
            print("达到最大错误次数，退出程序")
            print(f"最后一个错误的堆栈: {traceback.format_exc()}")
            run = False
        else:
            # 尝试继续运行
            pygame.time.wait(100)  # 给系统一些恢复的时间
 
    #之后是其他的操作
    ...
 
#退出之后：
#1、结束live2d
live2d.dispose()
#2、结束pygame
pygame.quit()
#3、结束程序
exit()