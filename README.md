# LuoTianyi-Agent

[](https://www.google.com/search?q=https://github.com/qifanmaker/LuoTianyi-Agent/blob/main/LICENSE)
[](https://github.com/qifanmaker/LuoTianyi-Agent)

## 🌟 项目简介

这是一个基于大型语言模型（LLM）驱动的洛天依（Luo Tianyi）虚拟智能体项目。它集成了先进的语音合成技术 **GPT-SoVITS** 和动态角色显示技术 **Live2D**，旨在创建一个可以进行实时语音对话、拥有洛天依独特声线和生动形象的交互式 AI 伴侣。

您可以与她进行自然语言交流，听她以洛天依的声音回答问题，并在 Live2D 窗口中看到她生动的表情和动作。

## ✨ 核心功能

  * **智能对话 (LLM):** 使用大型语言模型作为核心，实现自然流畅、富有逻辑的对话能力。
  * **洛天依专属声线 (GPT-SoVITS):** 集成 GPT-SoVITS 语音合成，将文本响应转化为逼真的洛天依声线语音输出。
  * **动态形象 (Live2D):** 通过 Live2D 技术驱动洛天依模型，实现嘴型同步、表情变化和身体动作，增强交互的沉浸感。
  * **语音交互:** 支持语音输入（通过 `voice_listener.py`）和语音播放（通过 `audio_player.py`）。
  * **文本模式:** 提供纯文本交互模式（通过 `main_text.py`）用于快速测试和部署。

## 🛠️ 环境与依赖

本项目主要使用 **Python** 语言开发。

### 1\. 克隆项目

```bash
git clone https://github.com/qifanmaker/LuoTianyi-Agent.git
cd LuoTianyi-Agent
```

### 2\. Python 环境

本项目依赖多个 Python 库，请确保您的环境中安装了所需的依赖。

  * **（待补充）** 由于项目未提供 `requirements.txt`，请根据代码中的 `import` 语句手动安装必要的库，例如：
      * `openai` 或其他 LLM 相关的库
      * `pyaudio` 或其他语音输入/输出库
      * `numpy`, `scipy` 等科学计算库

### 3\. 模型配置

您需要准备并配置以下模型或资源：

  * **LLM API Key:** 配置您选择的大型语言模型（如 GPT-3.5/4 或其他开源模型）的 API 密钥和调用接口。
  * **GPT-SoVITS 模型:** 将洛天依声线的模型文件（如 `.pth`, `.pt` 文件）放置在指定位置。并启用 TTS 推理 WebUI，开启 http://localhost:9872/ 的 api 接口。

## 🚀 使用方法

### 1\. 语音交互模式 (Live2D + 语音)

这是项目的完整体验模式。

```bash
# 确保所有模型和API配置已完成
python main.py
```

运行后，程序将启动 Live2D 窗口、语音监听器和 LLM 交互模块。对着麦克风说话即可与洛天依进行实时对话。

### 2\. 纯文本交互模式

如果不需要 Live2D 或语音输入/输出，可以使用纯文本模式进行 LLM 逻辑的测试。

```bash
python main_text.py
```

## 📂 项目结构概览

| 文件/文件夹 | 说明 |
| :--- | :--- |
| `main.py` | 项目主入口，负责集成语音、Live2D 和 LLM。 |
| `main_text.py` | 纯文本模式的交互入口，用于快速测试 LLM 逻辑。 |
| `voice_listener.py` | 语音输入模块，负责麦克风监听和语音识别。 |
| `audio_player.py` | 音频播放模块，负责播放合成的洛天依语音。 |
| `tianyi_voice.py` | 洛天依声线相关的语音合成逻辑封装。 |
| `response_processor.py` | 响应处理模块，可能负责将 LLM 文本转化为 Live2D 动作和语音指令。 |
| `Resources/hiyori_pro_zh` | Live2D 模型资源存放目录。 |
| `songs` | 可能用于存放歌唱或背景音乐资源。 |
| `voice.wav`, `sample_voice.pkf` | 语音样本和配置，用于 GPT-SoVITS 模型。 |

## 📜 许可证

本项目采用 **MIT License** 开放源代码。详情请参阅 `LICENSE` 文件。

```
MIT License

Copyright (c) 2025 LuoTianyi-Agent Contributors

...
```

## 💖 致谢

感谢所有对本项目做出贡献的人，以及以下开源项目和技术：

  * 大型语言模型 (LLM) 提供方
  * GPT-SoVITS 语音合成项目
  * Live2D 官方及相关 SDK
  * 洛天依的创造者和所有喜爱她的粉丝
