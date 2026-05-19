# 重序 (ReOrder)

**重序** 是一款现代化的批量文件重命名工具，支持多媒体元数据提取、多种命名规则和灵活的主题定制。

## 主要功能

- **批量重命名** — 支持插入、删除、替换、正则表达式、序号、大小写转换等多种规则
- **多媒体元数据** — 自动提取图片 EXIF、音频 ID3 标签、视频元数据用于命名
- **命名风格转换** — 一键转换驼峰、蛇形、短横线命名，支持中文转拼音
- **拖拽导入** — 支持拖拽文件/文件夹到窗口快速加载
- **实时预览** — 重命名前可预览结果，避免出错
- **撤销操作** — 支持撤销最近的重命名操作
- **模板系统** — 保存、导入、导出命名规则模板，方便复用
- **重复检测** — 扫描并标记重名文件
- **CSV 导入** — 支持通过 CSV 文件批量映射文件名
- **主题定制** — 内置多种配色主题，支持明暗模式跟随系统，可自定义颜色
- **会话恢复** — 关闭软件后自动恢复上次的工作状态

## 系统要求

- Windows 10 或更高版本
- 无需安装 Python 环境（已打包为独立 exe）

## 快速开始

### 使用打包版本

从 [Releases](../../releases) 页面下载 `ReOrder.exe`，直接运行即可。

### 从源码运行

```bash
# 安装依赖
pip install customtkinter pillow mutagen hachoir pypinyin tkinterdnd2

# 运行
python ReOrder.py
```

### 自行打包

```bash
pip install pyinstaller
build.bat
```

## 项目结构

```
ReOrder/
├── ReOrder.py          # 主程序入口
├── ReOrder.spec        # PyInstaller 打包配置
├── build.bat           # 构建脚本
├── tests/              # 单元测试
└── README.md
```

## 技术栈

- **GUI**: customtkinter + tkinter
- **图片元数据**: Pillow (PIL)
- **音频元数据**: mutagen
- **视频元数据**: hachoir
- **拼音转换**: pypinyin
- **拖拽支持**: tkinterdnd2
- **打包**: PyInstaller

## 许可

MIT License
