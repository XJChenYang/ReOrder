# -*- coding: utf-8 -*-
import os
import re
import datetime
import json
import threading
import queue
import logging
import traceback
import sys
import customtkinter as ctk

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser

# ================= 动态导入多媒体解析库（带安全降级保护） =================
try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import mutagen
    from mutagen.easyid3 import EasyID3
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

try:
    from hachoir.parser import createParser
    from hachoir.metadata import extractMetadata
    HACHOIR_AVAILABLE = True
except ImportError:
    HACHOIR_AVAILABLE = False


# 设置全局主题和外观 (默认跟随系统)
ctk.set_appearance_mode("System")  
ctk.set_default_color_theme("blue")  

class ModernRenamerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # 软件版本号 v3.0 (全面升级版)
        self.version = "v3.0"
        self.title(f"重序 - {self.version}")
        self.geometry("1340x950")
        self.minsize(1240, 880)

        # 核心数据
        self.source_items = [] 
        self.current_base_dir = "" 
        self.files_data = [] 
        self.undo_stack = []  
        self.rule_templates = {}  

        # 多线程 & 异步操作控制流
        self.scan_queue = queue.Queue()
        self.execute_queue = queue.Queue()
        self.is_scanning = False
        self.is_executing = False
        self.scan_cancel_flag = False

        # 默认主题预设 (静谧海洋)
        self.active_theme = {
            "name": "海洋",
            "light_primary": "#3B82F6", "dark_primary": "#1D4ED8",
            "light_hover": "#2563EB", "dark_hover": "#1E40AF"
        }

        self.configure(fg_color=("#F4F6F8", "#141517"))

        # 初始化日志系统
        self._setup_logging()

        # 初始化本地存储路径
        self.recovery_path = os.path.join(os.path.expanduser("~"), ".reorder_recovery.json")
        self.templates_path = os.path.join(os.path.expanduser("~"), ".reorder_templates.json")

        self.load_local_templates()
        self.setup_ui()
        self.create_context_menu()
        self.apply_theme_colors()

        # ⚡ 载入历史会话
        self.load_session()

        self.last_known_mode = self.safe_get_appearance_mode()
        self.monitor_system_theme()
        self.after(100, self._setup_drag_drop)  # 延迟初始化拖拽，确保窗口句柄就绪

    def _setup_logging(self):
        """配置日志系统：文件记录详细日志，控制台仅输出警告以上级别"""
        log_path = os.path.join(os.path.expanduser("~"), ".reorder.log")
        self.logger = logging.getLogger("ReOrder")
        self.logger.setLevel(logging.DEBUG)
        # 避免重复添加 handler
        if not self.logger.handlers:
            fh = logging.FileHandler(log_path, encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            ))
            self.logger.addHandler(fh)
        self.logger.info(f"ReOrder v{self.version} 启动")

    def safe_get_appearance_mode(self):
        """获取系统真实外观模式（即使是跟随系统也能正确解析）"""
        try:
            mode = ctk.get_appearance_mode()
            if mode in ["Light", "Dark"]:
                return mode
            # 当模式为 System 时，尝试从系统 API 检测
            if sys.platform == "win32":
                try:
                    import winreg
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
                    value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                    winreg.CloseKey(key)
                    return "Light" if value == 1 else "Dark"
                except Exception:
                    pass
            # macOS / Linux 回退检测
            try:
                from tkinter import Tk
                root = Tk()
                root.withdraw()
                bg = root.cget("background")
                root.destroy()
                # 浅色背景通常较亮
                r = int(bg[1:3], 16) if bg.startswith("#") else 200
                return "Light" if r > 127 else "Dark"
            except Exception:
                pass
        except Exception:
            self.logger.debug("Failed to get appearance mode, defaulting to Light")
        return "Light"

    def monitor_system_theme(self):
        if self.theme_selector.get() == "跟随系统":
            current_mode = self.safe_get_appearance_mode()
            if current_mode != self.last_known_mode:
                self.last_known_mode = current_mode
                self.update_idletasks()
                self.update_tree_style(current_mode)
                self.update_idletasks()
        self.after(1000, self.monitor_system_theme)

    def get_tint_color(self, hex_color, mode="light"):
        hex_color = hex_color.lstrip('#')
        if len(hex_color) != 6:
            hex_color = "3B82F6"
        try:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            if mode == "light":
                bg_r = int(r * 0.05 + 255 * 0.95)
                bg_g = int(g * 0.05 + 255 * 0.95)
                bg_b = int(b * 0.05 + 255 * 0.95)
            else:
                bg_r = int(r * 0.04 + 18 * 0.96)
                bg_g = int(g * 0.04 + 18 * 0.96)
                bg_b = int(b * 0.04 + 18 * 0.96)
            return f"#{bg_r:02x}{bg_g:02x}{bg_b:02x}"
        except Exception:
            return "#F4F6F8" if mode == "light" else "#141517"

    def get_panel_tint(self, hex_color, mode="light"):
        hex_color = hex_color.lstrip('#')
        if len(hex_color) != 6:
            hex_color = "3B82F6"
        try:
            r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
            if mode == "light":
                return "#FFFFFF"
            else:
                bg_r = int(r * 0.06 + 28 * 0.94)
                bg_g = int(g * 0.06 + 28 * 0.94)
                bg_b = int(b * 0.06 + 28 * 0.94)
                return f"#{bg_r:02x}{bg_g:02x}{bg_b:02x}"
        except Exception:
            return "#FFFFFF" if mode == "light" else "#1E1E24"

    # ================= ⚡ 防抖动输入拦截引擎 (Debounce) =================
    def schedule_update_preview(self, event=None):
        """防抖更新预览：防止用户打字过快时导致 UI 频繁重绘引发卡顿"""
        if hasattr(self, '_debounce_after_id') and self._debounce_after_id:
            self.after_cancel(self._debounce_after_id)
        self._debounce_after_id = self.after(250, self.update_preview)

    def schedule_load_files(self, event=None):
        """防抖加载文件：防止高级筛选框中快速输入字母时频繁拉起扫描线程"""
        if hasattr(self, '_load_after_id') and self._load_after_id:
            self.after_cancel(self._load_after_id)
        self._load_after_id = self.after(500, self._execute_scheduled_load)

    def _execute_scheduled_load(self):
        self.load_files()
        self.save_session()

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=0, minsize=480)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_left_panel_container()
        self._build_folder_selector()
        self._build_filter_panel()
        self._build_template_bar()
        self._build_theme_section()
        self._build_rename_tabs()
        self._build_right_panel()


    def _build_left_panel_container(self):
        # ================= 左侧面板 (操作区) =================
        self.left_canvas_container = ctk.CTkFrame(self, corner_radius=12, fg_color="transparent")
        self.left_canvas_container.grid(row=0, column=0, padx=(15, 5), pady=15, sticky="nsew")
        
        self.left_canvas_container.grid_rowconfigure(0, weight=1)
        self.left_canvas_container.grid_columnconfigure(0, weight=1)

        self.left_panel = ctk.CTkScrollableFrame(self.left_canvas_container, corner_radius=12, fg_color=("#FFFFFF", "#12141A"), border_color=("#CBD5E1", "#334155"), border_width=2)
        self.left_panel.grid(row=0, column=0, sticky="nsew")






    def _build_folder_selector(self):
        # 文件夹选择
        self.folder_frame = ctk.CTkFrame(self.left_panel, fg_color=("#F8FAFC", "#14161C"), corner_radius=10)
        self.folder_frame.pack(fill="x", padx=8, pady=(5, 5))
        
        ctk.CTkLabel(self.folder_frame, text="📁 工作目录", font=ctk.CTkFont(family="Microsoft YaHei", size=15, weight="bold")).pack(anchor="w")
        
        self.btn_browse = ctk.CTkButton(
            self.folder_frame, text="📁 浏览文件夹", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=13, weight="bold"),
            command=self.browse_folder
        )
        self.btn_browse.pack(fill="x", pady=(5, 5))

        self.lbl_path = ctk.CTkLabel(self.folder_frame, text="未选择文件夹 (点击上方浏览按钮导入)", font=ctk.CTkFont(family="Microsoft YaHei", size=12), text_color=("#5A6478", "#B0B8C8"), wraplength=440, justify="left")
        self.lbl_path.pack(anchor="w")

        self.switch_recursive = ctk.CTkSwitch(
            self.folder_frame, text="🔄 包含子文件夹", font=ctk.CTkFont(family="Microsoft YaHei", size=12),
            command=self._execute_scheduled_load
        )
        self.switch_recursive.pack(anchor="w", pady=(8, 0))


    def _build_filter_panel(self):
        # ================= 高级筛选引擎 =================
        self.filter_container = ctk.CTkFrame(self.left_panel, fg_color=("#F7FAFC", "#1A1B20"), border_width=2, border_color=("#CBD5E1", "#3E3E48"), corner_radius=8)
        self.filter_container.pack(fill="x", padx=8, pady=8)
        
        self.filter_header = ctk.CTkButton(
            self.filter_container, text="🔍 高级筛选过滤条件 (点击展开/收起)", font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold"),
            fg_color="transparent", hover=False, text_color=("gray10", "gray90"), anchor="w", height=32,
            command=self.toggle_filter_panel
        )
        self.filter_header.pack(fill="x", padx=5, pady=2)
        
        self.filter_body = ctk.CTkFrame(self.filter_container, fg_color=("#F8FAFC", "#14161C"), corner_radius=8)
        self.filter_body.pack(fill="x", padx=10, pady=(0, 10))
        self.filter_panel_visible = True

        # 1. 后缀/类型
        ctk.CTkLabel(self.filter_body, text="文件类型 (后缀名, 逗号分隔, 如 .jpg,.png):", font=("Microsoft YaHei", 11)).pack(anchor="w", pady=(2, 0))
        self.entry_filter_ext = ctk.CTkEntry(self.filter_body, placeholder_text="例如: .jpg, .png", font=("Microsoft YaHei", 11), height=32)
        self.entry_filter_ext.pack(fill="x", pady=(2, 6))
        self.entry_filter_ext.bind("<KeyRelease>", self.schedule_load_files)

        # 2. 大小过滤
        size_frame = ctk.CTkFrame(self.filter_body, fg_color="transparent")
        size_frame.pack(fill="x", pady=(2, 6))
        ctk.CTkLabel(size_frame, text="大小限制:", font=("Microsoft YaHei", 11)).pack(side="left")
        
        self.combo_size_op = ctk.CTkOptionMenu(size_frame, values=["不限", "大于", "小于"], width=75, font=("Microsoft YaHei", 11), height=26)
        self.combo_size_op.pack(side="left", padx=5)
        
        self.entry_size_val = ctk.CTkEntry(size_frame, placeholder_text="100", width=65, font=("Microsoft YaHei", 11), height=26)
        self.entry_size_val.pack(side="left")
        self.entry_size_val.bind("<KeyRelease>", self.schedule_load_files)
        
        self.combo_size_unit = ctk.CTkOptionMenu(size_frame, values=["KB", "MB"], width=65, font=("Microsoft YaHei", 11), height=26)
        self.combo_size_unit.pack(side="left", padx=5)
        
        self.combo_size_op.configure(command=lambda e: self._execute_scheduled_load())
        self.combo_size_unit.configure(command=lambda e: self._execute_scheduled_load())

        # 3. 修改时间
        date_frame = ctk.CTkFrame(self.filter_body, fg_color="transparent")
        date_frame.pack(fill="x", pady=(2, 6))
        ctk.CTkLabel(date_frame, text="修改时间:", font=("Microsoft YaHei", 11)).pack(side="left")
        self.combo_date_filter = ctk.CTkOptionMenu(
            date_frame, values=["不限", "最近 1 天", "最近 1 周", "最近 1 月", "最近 1 年"], 
            command=lambda e: self._execute_scheduled_load(), font=("Microsoft YaHei", 11), height=26
        )
        self.combo_date_filter.pack(side="left", padx=5, fill="x", expand=True)

        # 4. 名称匹配
        name_match_frame = ctk.CTkFrame(self.filter_body, fg_color="transparent")
        name_match_frame.pack(fill="x", pady=(2, 6))
        ctk.CTkLabel(name_match_frame, text="名称规则:", font=("Microsoft YaHei", 11)).pack(side="left")
        self.combo_name_match_mode = ctk.CTkOptionMenu(
            name_match_frame, values=["不限", "包含", "开头是", "结尾是"], 
            command=lambda e: self._execute_scheduled_load(), font=("Microsoft YaHei", 11), width=90, height=26
        )
        self.combo_name_match_mode.pack(side="left", padx=5)
        self.entry_name_match_val = ctk.CTkEntry(name_match_frame, placeholder_text="文本", font=("Microsoft YaHei", 11), height=26)
        self.entry_name_match_val.pack(side="left", fill="x", expand=True)
        self.entry_name_match_val.bind("<KeyRelease>", self.schedule_load_files)

        # 5. 正则筛选
        regex_filter_frame = ctk.CTkFrame(self.filter_body, fg_color="transparent")
        regex_filter_frame.pack(fill="x", pady=(2, 2))
        ctk.CTkLabel(regex_filter_frame, text="正则筛选:", font=("Microsoft YaHei", 11)).pack(side="left")
        self.entry_regex_filter = ctk.CTkEntry(regex_filter_frame, placeholder_text="输入正则表达式筛选原名", font=("Microsoft YaHei", 11), height=26)
        self.entry_regex_filter.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_regex_filter.bind("<KeyRelease>", self.schedule_load_files)






    def _build_template_bar(self):
        ctk.CTkFrame(self.left_panel, height=3, fg_color=("#CBD5E1", "#334155")).pack(fill="x", padx=5, pady=5)

        # ================= 规则模板管理栏 =================
        self.template_bar = ctk.CTkFrame(self.left_panel, fg_color=("#F8FAFC", "#14161C"), corner_radius=10)
        self.template_bar.pack(fill="x", padx=8, pady=5)
        ctk.CTkLabel(self.template_bar, text="📋 规则模板方案", font=ctk.CTkFont(family="Microsoft YaHei", size=14, weight="bold")).pack(anchor="w")

        combo_row = ctk.CTkFrame(self.template_bar, fg_color="transparent")
        combo_row.pack(fill="x", pady=2)
        
        self.combo_templates = ctk.CTkOptionMenu(
            combo_row, values=["无 / 默认"], command=self.on_template_selected,
            font=ctk.CTkFont(family="Microsoft YaHei", size=12)
        )
        self.combo_templates.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_save_tpl = ctk.CTkButton(
            combo_row, text="💾 保存当前", width=70, font=ctk.CTkFont(family="Microsoft YaHei", size=11, weight="bold"),
            command=self.save_current_template_dialog
        )
        self.btn_save_tpl.pack(side="right")

        btn_row = ctk.CTkFrame(self.template_bar, fg_color="transparent")
        btn_row.pack(fill="x", pady=(2, 5))
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)
        btn_row.grid_columnconfigure(2, weight=1)

        self.btn_import_tpl = ctk.CTkButton(
            btn_row, text="📥 导入", width=70, height=28, font=ctk.CTkFont(family="Microsoft YaHei", size=11),
            fg_color="transparent", border_width=1, text_color=("gray10", "gray90"), command=self.import_templates
        )
        self.btn_import_tpl.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self.btn_export_tpl = ctk.CTkButton(
            btn_row, text="📤 导出", width=70, height=28, font=ctk.CTkFont(family="Microsoft YaHei", size=11),
            fg_color="transparent", border_width=1, text_color=("gray10", "gray90"), command=self.export_templates
        )
        self.btn_export_tpl.grid(row=0, column=1, padx=(2, 4), sticky="ew")

        self.btn_delete_tpl = ctk.CTkButton(
            btn_row, text="❌ 删除", width=70, height=28, font=ctk.CTkFont(family="Microsoft YaHei", size=11),
            fg_color=("#FEE2E2", "#450A0A"), hover_color=("#FCA5A5", "#7F1D1D"), text_color=("#991B1B", "#FCA5A5"),
            command=self.delete_current_template
        )
        self.btn_delete_tpl.grid(row=0, column=2, padx=(2, 0), sticky="ew")

        # 分割线
        ctk.CTkFrame(self.left_panel, height=3, fg_color=("#CBD5E1", "#334155")).pack(fill="x", padx=5, pady=5)

        # 重命名规则区域标题
        ctk.CTkLabel(self.left_panel, text="⚙ 重命名规则配置", font=ctk.CTkFont(family="Microsoft YaHei", size=14, weight="bold"), wraplength=460).pack(anchor="w", padx=8, pady=(8, 4))
        ctk.CTkFrame(self.left_panel, height=2, fg_color=("#CBD5E1", "#334155")).pack(fill="x", padx=8, pady=(0, 4))

        left_bottom_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        left_bottom_frame.pack(fill="x", padx=5, pady=(0, 10), side="bottom")

        self.btn_clear = ctk.CTkButton(left_bottom_frame, text="🧹 清除所有规则", font=ctk.CTkFont(family="Microsoft YaHei", size=12), fg_color="transparent", border_width=1, text_color=("gray10", "gray90"), command=self.clear_rules)
        self.btn_clear.pack(fill="x", pady=(0, 5))

        self.btn_help = ctk.CTkButton(left_bottom_frame, text="❓ 使用帮助与说明", font=ctk.CTkFont(family="Microsoft YaHei", size=12), fg_color="transparent", border_width=1, text_color=("gray10", "gray90"), command=self.open_help_dialog)
        self.btn_help.pack(fill="x")




    def _build_theme_section(self):
        self.theme_section = ctk.CTkFrame(self.left_panel, fg_color=("#F8FAFC", "#14161C"), corner_radius=10)
        self.theme_section.pack(fill="x", padx=5, pady=(5, 5), side="bottom")
        
        ctk.CTkLabel(self.theme_section, text="🎨 个性化配色方案", font=ctk.CTkFont(family="Microsoft YaHei", size=13, weight="bold")).pack(anchor="w")
        
        colors_row = ctk.CTkFrame(self.theme_section, fg_color="transparent")
        colors_row.pack(fill="x", pady=5)
        
        theme_presets = [
            {"name": "海洋", "color": "#2563EB", "tip": "活力海洋"},
            {"name": "翡翠", "color": "#059669", "tip": "清透翡翠"},
            {"name": "紫韵", "color": "#7C3AED", "tip": "梦幻紫韵"},
            {"name": "橙焰", "color": "#EA580C", "tip": "热烈橙焰"},
            {"name": "玫红", "color": "#DB2777", "tip": "浪漫玫红"},
            {"name": "青空", "color": "#0891B2", "tip": "明朗青空"},
        ]
        
        for t in theme_presets:
            btn = ctk.CTkButton(
                colors_row, text="", width=28, height=32, corner_radius=14, 
                fg_color=t["color"], hover_color=t["color"], 
                command=lambda name=t["name"]: self.set_theme_color(name)
            )
            btn.pack(side="left", padx=5)
            
        self.btn_custom_color = ctk.CTkButton(
            colors_row, text="🎨", width=32, height=32, corner_radius=16, 
            font=("Microsoft YaHei", 12), fg_color=("#E2E8F0", "#2D2D35"),
            hover_color=("#CBD5E1", "#475569"), text_color=("#1E293B", "#F1F5F9"), command=self.pick_custom_color
        )
        self.btn_custom_color.pack(side="left", padx=10)






    def _build_rename_tabs(self):
        # 核心重命名规则标签页 (第1排)
        self.tabview = ctk.CTkTabview(self.left_panel, corner_radius=10, width=440)
        self.tabview.pack(fill="x", padx=8, pady=(8, 0))
        self.tabview.add("替换")
        self.tabview.add("插入")
        self.tabview.add("命名")
        self.tabview.add("附加")
        self.tabview.add("编号")

        # 高级功能标签页 (第2排)
        self.tabview_adv = ctk.CTkTabview(self.left_panel, corner_radius=10, width=440)
        self.tabview_adv.pack(fill="both", expand=True, padx=8, pady=(4, 5))
        self.tabview_adv.add("元数据")
        self.tabview_adv.add("格式")
        self.tabview_adv.add("查重")
        self.tabview_adv.add("归类")

        # --- Tab 1: 替换 ---
        tab_replace = self.tabview.tab("替换")
        ctk.CTkLabel(tab_replace, text="查找内容:", font=ctk.CTkFont(family="Microsoft YaHei", size=12)).pack(anchor="w", pady=(5,0))
        self.entry_find = ctk.CTkEntry(tab_replace, font=ctk.CTkFont(family="Microsoft YaHei", size=12))
        self.entry_find.pack(fill="x", pady=(0, 10))
        self.entry_find.bind("<KeyRelease>", self.schedule_update_preview)
        
        ctk.CTkLabel(tab_replace, text="替换为 (留空则为删除):", font=ctk.CTkFont(family="Microsoft YaHei", size=12)).pack(anchor="w")
        self.entry_replace = ctk.CTkEntry(tab_replace, font=ctk.CTkFont(family="Microsoft YaHei", size=12))
        self.entry_replace.pack(fill="x", pady=(0, 10))
        self.entry_replace.bind("<KeyRelease>", self.schedule_update_preview)
        
        self.switch_regex = ctk.CTkSwitch(tab_replace, text="⚡ 使用正则表达式匹配 (高级)", font=ctk.CTkFont(family="Microsoft YaHei", size=11), command=self.update_preview)
        self.switch_regex.pack(anchor="w", pady=(5, 4))
        
        self.switch_ignore_case = ctk.CTkSwitch(tab_replace, text="🔤 忽略英文大小写", font=ctk.CTkFont(family="Microsoft YaHei", size=11), command=self.update_preview)
        self.switch_ignore_case.pack(anchor="w", pady=(2, 0))

        # --- Tab 2: 插入 ---
        tab_insert = self.tabview.tab("插入")
        ctk.CTkLabel(tab_insert, text="要插入的文本内容:", font=ctk.CTkFont(family="Microsoft YaHei", size=12)).pack(anchor="w", pady=(5,0))
        self.entry_insert_text = ctk.CTkEntry(tab_insert, font=ctk.CTkFont(family="Microsoft YaHei", size=12))
        self.entry_insert_text.pack(fill="x", pady=(0, 10))
        self.entry_insert_text.bind("<KeyRelease>", self.schedule_update_preview)
        
        insert_pos_frame = ctk.CTkFrame(tab_insert, fg_color="transparent")
        insert_pos_frame.pack(fill="x", pady=5)
        
        self.combo_insert_dir = ctk.CTkOptionMenu(insert_pos_frame, values=["从开头", "从末尾"], command=lambda e: self.update_preview(), width=90)
        self.combo_insert_dir.pack(side="left", padx=(0, 10))
        
        ctk.CTkLabel(insert_pos_frame, text="第", font=ctk.CTkFont(family="Microsoft YaHei", size=12)).pack(side="left")
        self.entry_insert_pos = ctk.CTkEntry(insert_pos_frame, width=50, font=("Microsoft YaHei", 12))
        self.entry_insert_pos.insert(0, "0")
        self.entry_insert_pos.pack(side="left", padx=5)
        self.entry_insert_pos.bind("<KeyRelease>", self.schedule_update_preview)
        ctk.CTkLabel(insert_pos_frame, text="个字符处", font=ctk.CTkFont(family="Microsoft YaHei", size=12)).pack(side="left")
        
        ctk.CTkLabel(tab_insert, text="💡 提示: 填 0 代表紧贴头尾插入", font=ctk.CTkFont(family="Microsoft YaHei", size=11), text_color=("#5A6478", "#B0B8C8")).pack(anchor="w", pady=(15,0))

        # --- Tab 3: 命名 ---
        tab_new_name = self.tabview.tab("命名")
        self.switch_overwrite = ctk.CTkSwitch(tab_new_name, text="启用全新命名 (忽略原名)", font=ctk.CTkFont(family="Microsoft YaHei", size=12), command=self.update_preview)
        self.switch_overwrite.pack(anchor="w", pady=(5, 15))
        
        ctk.CTkLabel(tab_new_name, text="新文件名模版:", font=ctk.CTkFont(family="Microsoft YaHei", size=12)).pack(anchor="w")
        self.entry_overwrite = ctk.CTkEntry(tab_new_name, placeholder_text="例: 最终设计图", font=ctk.CTkFont(family="Microsoft YaHei", size=12))
        self.entry_overwrite.pack(fill="x", pady=(0, 10))
        self.entry_overwrite.bind("<KeyRelease>", self.schedule_update_preview)
        
        ctk.CTkLabel(tab_new_name, text="💡 提示: 强烈建议配合右侧【编号】一同使用，防止重名导致覆盖失败！", font=ctk.CTkFont(family="Microsoft YaHei", size=11), text_color=("#5A6478", "#B0B8C8"), wraplength=440, justify="left").pack(anchor="w", pady=5)

        # CSV 导入映射
        ctk.CTkFrame(tab_new_name, height=2, fg_color=("#CBD5E1", "#334155")).pack(fill="x", pady=8)
        ctk.CTkLabel(tab_new_name, text="📋 CSV映射导入", font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(tab_new_name, text="CSV格式: 原名,新名 (可批量映射重命名)", font=ctk.CTkFont(family="Microsoft YaHei", size=11), text_color=("#5A6478", "#B0B8C8")).pack(anchor="w", pady=(0, 3))
        self.btn_csv_import = ctk.CTkButton(
            tab_new_name, text="📥 导入CSV映射文件", font=ctk.CTkFont(family="Microsoft YaHei", size=12),
            height=32, command=self.import_csv_mapping
        )
        self.btn_csv_import.pack(fill="x", pady=(2, 0))

        # --- Tab 4: 元数据 ---
        tab_metadata = self.tabview_adv.tab("元数据")
        self.switch_metadata = ctk.CTkSwitch(tab_metadata, text="启用多媒体元数据重命名", font=ctk.CTkFont(family="Microsoft YaHei", size=12), command=self.update_preview)
        self.switch_metadata.pack(anchor="w", pady=(5, 10))

        ctk.CTkLabel(tab_metadata, text="格式占位符规则 (自定义模版):", font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold")).pack(anchor="w", pady=(2, 0))
        self.entry_meta_template = ctk.CTkEntry(tab_metadata, placeholder_text="例: {拍摄时间}_{相机型号}", font=ctk.CTkFont(family="Microsoft YaHei", size=12))
        self.entry_meta_template.insert(0, "{原名}_{拍摄时间}")
        self.entry_meta_template.pack(fill="x", pady=(2, 10))
        self.entry_meta_template.bind("<KeyRelease>", self.schedule_update_preview)

        dep_box = ctk.CTkFrame(tab_metadata, fg_color=("#EDF2F7", "#24252B"), corner_radius=8)
        dep_box.pack(fill="both", expand=True, pady=5)
        
        def get_status_str(available):
            return "🟢 已就绪" if available else "❌ 未就绪 (不生效)"
        
        ctk.CTkLabel(dep_box, text="系统底层多媒体依赖检测:", font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold")).pack(anchor="w", padx=10, pady=(8, 2))
        ctk.CTkLabel(dep_box, text=f"• 图片 (PIL/Pillow): {get_status_str(PIL_AVAILABLE)}", font=("Microsoft YaHei", 11)).pack(anchor="w", padx=15, pady=1)
        ctk.CTkLabel(dep_box, text=f"• 音乐 (mutagen): {get_status_str(MUTAGEN_AVAILABLE)}", font=("Microsoft YaHei", 11)).pack(anchor="w", padx=15, pady=1)
        ctk.CTkLabel(dep_box, text=f"• 视频 (hachoir): {get_status_str(HACHOIR_AVAILABLE)}", font=("Microsoft YaHei", 11)).pack(anchor="w", padx=15, pady=1)

        copy_lbl = ctk.CTkLabel(tab_metadata, text="常用支持占位符:\n"
                                                      "图片: {原名} {拍摄时间} {相机型号} {GPS纬度} {GPS经度}\n"
                                                      "音乐: {原名} {歌手} {专辑} {曲目号} {歌名}\n"
                                                      "视频: {原名} {分辨率} {宽度} {高度} {时长} {视频编码}", 
                                text_color=("#5A6478", "#B0B8C8"), font=ctk.CTkFont(family="Microsoft YaHei", size=11), justify="left", wraplength=440)
        copy_lbl.pack(anchor="w", pady=(10, 5))

        # --- Tab 5: 附加 ---
        tab_add = self.tabview.tab("附加")
        ctk.CTkLabel(tab_add, text="添加前缀:", font=ctk.CTkFont(family="Microsoft YaHei", size=12)).pack(anchor="w", pady=(5,0))
        self.entry_prefix = ctk.CTkEntry(tab_add, font=ctk.CTkFont(family="Microsoft YaHei", size=12))
        self.entry_prefix.pack(fill="x", pady=(0, 10))
        self.entry_prefix.bind("<KeyRelease>", self.schedule_update_preview)

        ctk.CTkLabel(tab_add, text="添加后缀:", font=ctk.CTkFont(family="Microsoft YaHei", size=12)).pack(anchor="w")
        self.entry_suffix = ctk.CTkEntry(tab_add, font=ctk.CTkFont(family="Microsoft YaHei", size=12))
        self.entry_suffix.pack(fill="x", pady=(0, 10))
        self.entry_suffix.bind("<KeyRelease>", self.schedule_update_preview)
        
        self.switch_date = ctk.CTkSwitch(tab_add, text="📅 自动附加文件修改日期", font=ctk.CTkFont(family="Microsoft YaHei", size=12), command=self.update_preview)
        self.switch_date.pack(anchor="w", pady=(5, 5))
        
        self.date_format_var = ctk.StringVar(value="_YYYYMMDD")
        self.date_options = ctk.CTkOptionMenu(tab_add, values=["_YYYYMMDD", "_YYYY-MM-DD", "_YYYYMMDD_HHMMSS"], variable=self.date_format_var, command=lambda e: self.update_preview())
        self.date_options.pack(fill="x", pady=(0, 5))

        # --- Tab 6: 编号 ---
        tab_num = self.tabview.tab("编号")
        
        self.switch_num = ctk.CTkSwitch(tab_num, text="启用自动编号", font=ctk.CTkFont(family="Microsoft YaHei", size=12), command=self.update_preview)
        self.switch_num.pack(anchor="w", pady=(5, 5))

        self.combo_num_pos = ctk.CTkOptionMenu(tab_num, values=["文件名开头", "文件名末尾"], command=lambda e: self.update_preview())
        self.combo_num_pos.pack(fill="x", pady=(2, 5))

        num_sep_frame = ctk.CTkFrame(tab_num, fg_color="transparent")
        num_sep_frame.pack(fill="x", pady=2)
        ctk.CTkLabel(num_sep_frame, text="连接符:", font=ctk.CTkFont(family="Microsoft YaHei", size=11)).pack(side="left")
        self.entry_num_sep = ctk.CTkEntry(num_sep_frame, width=120, font=("Microsoft YaHei", 11))
        self.entry_num_sep.insert(0, "_")
        self.entry_num_sep.pack(side="right", fill="x", expand=True, padx=(10, 0))
        self.entry_num_sep.bind("<KeyRelease>", self.schedule_update_preview)

        grid_frame = ctk.CTkFrame(tab_num, fg_color="transparent")
        grid_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(grid_frame, text="起始数:", font=ctk.CTkFont(family="Microsoft YaHei", size=11)).grid(row=0, column=0, sticky="w", pady=2)
        self.entry_num_start = ctk.CTkEntry(grid_frame, width=90, font=("Microsoft YaHei", 11))
        self.entry_num_start.insert(0, "1")
        self.entry_num_start.grid(row=0, column=1, sticky="w", padx=(5, 10), pady=2)
        self.entry_num_start.bind("<KeyRelease>", self.schedule_update_preview)

        ctk.CTkLabel(grid_frame, text="步长:", font=ctk.CTkFont(family="Microsoft YaHei", size=11)).grid(row=0, column=2, sticky="w", pady=2)
        self.entry_num_step = ctk.CTkEntry(grid_frame, width=90, font=("Microsoft YaHei", 11))
        self.entry_num_step.insert(0, "1")
        self.entry_num_step.grid(row=0, column=3, sticky="w", padx=(5, 0), pady=2)
        self.entry_num_step.bind("<KeyRelease>", self.schedule_update_preview)

        ctk.CTkLabel(grid_frame, text="补零位数:", font=ctk.CTkFont(family="Microsoft YaHei", size=11)).grid(row=1, column=0, sticky="w", pady=2)
        self.entry_num_pad = ctk.CTkEntry(grid_frame, width=90, font=("Microsoft YaHei", 11))
        self.entry_num_pad.insert(0, "2")
        self.entry_num_pad.grid(row=1, column=1, sticky="w", padx=(5, 10), pady=2)
        self.entry_num_pad.bind("<KeyRelease>", self.schedule_update_preview)

        sep = ctk.CTkLabel(tab_num, text="━" * 28, text_color=("#5A6478", "#B0B8C8"))
        sep.pack(fill="x", pady=5)

        self.switch_remove_nums = ctk.CTkSwitch(tab_num, text="🧹 清理/删除文件名原有数字", font=ctk.CTkFont(family="Microsoft YaHei", size=11), command=self.update_preview)
        self.switch_remove_nums.pack(anchor="w", pady=(2, 5))
        
        self.combo_remove_pos = ctk.CTkOptionMenu(tab_num, values=["清除开头所有数字", "清除末尾所有数字", "清除名字里所有数字"], command=lambda e: self.update_preview())
        self.combo_remove_pos.pack(fill="x", pady=2)

        # --- Tab 7: 格式 ---
        tab_ext = self.tabview_adv.tab("格式")
        
        # --- 主文件名大小写 (双列网格布局) ---
        ctk.CTkLabel(tab_ext, text="【主文件名大小写】", font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold")).pack(anchor="w", pady=(5, 5))
        self.name_case_var = ctk.StringVar(value="keep")
        name_grid = ctk.CTkFrame(tab_ext, fg_color="transparent")
        name_grid.pack(fill="x", pady=(0, 5))
        name_grid.grid_columnconfigure(0, weight=1)
        name_grid.grid_columnconfigure(1, weight=1)
        name_opts = [
            ("保持原样", "keep"), ("全部小写", "lower"),
            ("全部大写", "upper"), ("Title 首字母大写", "title"),
            ("camelCase 驼峰", "camel"), ("snake_case 蛇形", "snake"),
            ("kebab-case 短横线", "kebab"),
        ]
        self._all_radio_widgets = []
        for idx, (label, val) in enumerate(name_opts):
            row, col = idx // 2, idx % 2
            rb = ctk.CTkRadioButton(name_grid, text=label, font=ctk.CTkFont(family="Microsoft YaHei", size=12), variable=self.name_case_var, value=val, command=self.update_preview)
            rb.grid(row=row, column=col, sticky="w", pady=3, padx=(0, 5))
            self._all_radio_widgets.append(rb)

        # --- 中文拼音转换 ---
        try:
            import pypinyin
            self._pypinyin_available = True
        except ImportError:
            self._pypinyin_available = False

        py_label = "【中文拼音转换】" + (" (pypinyin 未安装)" if not self._pypinyin_available else "")
        ctk.CTkLabel(tab_ext, text=py_label, font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold")).pack(anchor="w", pady=(12, 5))
        self.pinyin_var = ctk.StringVar(value="keep")
        py_grid = ctk.CTkFrame(tab_ext, fg_color="transparent")
        py_grid.pack(fill="x", pady=(0, 5))
        py_grid.grid_columnconfigure(0, weight=1)
        py_grid.grid_columnconfigure(1, weight=1)
        py_opts = [
            ("保持原样", "keep"), ("全拼 (无声调)", "pinyin"),
            ("全拼 (带声调)", "pinyin_tone"), ("首字母缩写", "pinyin_initials"),
        ]
        for idx, (label, val) in enumerate(py_opts):
            rb = ctk.CTkRadioButton(py_grid, text=label, font=ctk.CTkFont(family="Microsoft YaHei", size=12), variable=self.pinyin_var, value=val, command=self.update_preview)
            rb.grid(row=idx//2, column=idx%2, sticky="w", pady=3, padx=(0, 5))
            self._all_radio_widgets.append(rb)

        # --- 后缀名大小写 ---
        ctk.CTkLabel(tab_ext, text="【后缀名大小写】", font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold")).pack(anchor="w", pady=(12, 5))
        self.ext_var = ctk.StringVar(value="keep")
        ext_grid = ctk.CTkFrame(tab_ext, fg_color="transparent")
        ext_grid.pack(fill="x", pady=(0, 5))
        ext_grid.grid_columnconfigure(0, weight=1)
        ext_grid.grid_columnconfigure(1, weight=1)
        ext_grid.grid_columnconfigure(2, weight=1)
        ext_opts = [
            ("保持原样", "keep"), ("全部小写 .jpg", "lower"), ("全部大写 .JPG", "upper"),
        ]
        for idx, (label, val) in enumerate(ext_opts):
            rb = ctk.CTkRadioButton(ext_grid, text=label, font=ctk.CTkFont(family="Microsoft YaHei", size=12), variable=self.ext_var, value=val, command=self.update_preview)
            rb.grid(row=0, column=idx, sticky="w", pady=3, padx=(0, 5))
            self._all_radio_widgets.append(rb)

        # --- Tab 8: 查重 ---
        tab_dup = self.tabview_adv.tab("查重")
        ctk.CTkLabel(tab_dup, text="🔍 重复文件检测", font=ctk.CTkFont(family="Microsoft YaHei", size=14, weight="bold")).pack(anchor="w", pady=(5, 10))

        ctk.CTkLabel(tab_dup, text="检测模式:", font=ctk.CTkFont(family="Microsoft YaHei", size=12)).pack(anchor="w")
        self.dup_mode_var = ctk.StringVar(value="name")
        self.radio_dup_name = ctk.CTkRadioButton(tab_dup, text="同名检测 (快速)", font=ctk.CTkFont(family="Microsoft YaHei", size=12), variable=self.dup_mode_var, value="name")
        self.radio_dup_name.pack(anchor="w", pady=2)
        self._all_radio_widgets.append(self.radio_dup_name)
        self.radio_dup_hash = ctk.CTkRadioButton(tab_dup, text="MD5哈希检测 (精确)", font=ctk.CTkFont(family="Microsoft YaHei", size=12), variable=self.dup_mode_var, value="hash")
        self.radio_dup_hash.pack(anchor="w", pady=2)
        self._all_radio_widgets.append(self.radio_dup_hash)

        self.btn_scan_dup = ctk.CTkButton(tab_dup, text="🔎 开始扫描重复文件", font=ctk.CTkFont(family="Microsoft YaHei", size=13, weight="bold"), height=34, command=self.scan_duplicates)
        self.btn_scan_dup.pack(fill="x", pady=(12, 8))

        self.lbl_dup_result = ctk.CTkLabel(tab_dup, text="", font=ctk.CTkFont(family="Microsoft YaHei", size=11), text_color=("#5A6478", "#B0B8C8"), wraplength=440, justify="left")
        self.lbl_dup_result.pack(anchor="w", pady=(0, 8))

        self.btn_mark_dups = ctk.CTkButton(tab_dup, text="☐ 批量取消勾选重复项 (保留每组第一个)", font=ctk.CTkFont(family="Microsoft YaHei", size=11), fg_color=("#FEE2E2", "#450A0A"), text_color=("#991B1B", "#FCA5A5"), hover_color=("#FCA5A5", "#7F1D1D"), command=self.mark_duplicates_for_removal)
        self.btn_mark_dups.pack(fill="x", pady=(2, 0))

        # --- Tab 9: 归类 ---
        tab_classify = self.tabview_adv.tab("归类")
        ctk.CTkLabel(tab_classify, text="📂 智能文件夹归类", font=ctk.CTkFont(family="Microsoft YaHei", size=14, weight="bold")).pack(anchor="w", pady=(5, 10))

        ctk.CTkLabel(tab_classify, text="归类规则:", font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold")).pack(anchor="w")
        self.classify_rule_var = ctk.StringVar(value="ext")
        rules = [
            ("按扩展名分类 (jpg/ mp4/ 等)", "ext"),
            ("按修改日期分类 (YYYY/MM/)", "date"),
            ("按首字母分类 (A/ B/ C/)", "first_letter"),
            ("按正则捕获组分类", "regex"),
        ]
        classify_grid = ctk.CTkFrame(tab_classify, fg_color="transparent")
        classify_grid.pack(fill="x", pady=(0, 5))
        classify_grid.grid_columnconfigure(0, weight=1)
        classify_grid.grid_columnconfigure(1, weight=1)
        for idx, (label, val) in enumerate(rules):
            rb = ctk.CTkRadioButton(classify_grid, text=label, font=ctk.CTkFont(family="Microsoft YaHei", size=11), variable=self.classify_rule_var, value=val)
            rb.grid(row=idx//2, column=idx%2, sticky="w", pady=2, padx=(0, 5))
            self._all_radio_widgets.append(rb)

        ctk.CTkLabel(tab_classify, text="正则表达式 (regex模式下):", font=ctk.CTkFont(family="Microsoft YaHei", size=11)).pack(anchor="w", pady=(8, 0))
        self.entry_classify_regex = ctk.CTkEntry(tab_classify, placeholder_text=r"例: (.+?)_(\d+) 按前缀和数字分组", font=("Microsoft YaHei", 11), height=28)
        self.entry_classify_regex.pack(fill="x", pady=2)

        self.btn_execute_classify = ctk.CTkButton(tab_classify, text="🚀 执行归类移动", font=ctk.CTkFont(family="Microsoft YaHei", size=13, weight="bold"), height=34, command=self.execute_classify)
        self.btn_execute_classify.pack(fill="x", pady=(12, 8))

        ctk.CTkLabel(tab_classify, text="⚠ 归类操作会实际移动文件到子文件夹，\n请先在右侧预览中核对无误后再执行。", font=ctk.CTkFont(family="Microsoft YaHei", size=11), text_color=("#5A6478", "#B0B8C8"), wraplength=440, justify="left").pack(anchor="w")

    def _build_right_panel(self):
        # ================= 右侧面板 (预览区) =================
        self.right_panel = ctk.CTkFrame(self, corner_radius=12, fg_color=("#FFFFFF", "#1E1E24"), border_color=("#E2E8F0", "#2D2D35"), border_width=2)
        self.right_panel.grid(row=0, column=1, padx=(5, 15), pady=15, sticky="nsew")
        self.right_panel.grid_rowconfigure(3, weight=1)
        self.right_panel.grid_columnconfigure(0, weight=1)

        # 1. 顶部栏
        top_right_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        top_right_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=10)

        self.lbl_summary = ctk.CTkLabel(top_right_frame, text="重序 | 共找到 0 个文件 | 已选中 0 个 | 将修改 0 个", font=ctk.CTkFont(family="Microsoft YaHei", size=13, weight="bold"))
        self.lbl_summary.pack(side="left")

        self.theme_selector = ctk.CTkSegmentedButton(
            top_right_frame, values=["浅色", "深色", "跟随系统"],
            command=self.change_theme, font=ctk.CTkFont(family="Microsoft YaHei", size=11)
        )
        self.theme_selector.set("跟随系统")
        self.theme_selector.pack(side="right")

        # 2. 快捷工具栏
        selection_toolbar = ctk.CTkFrame(self.right_panel, fg_color="transparent", height=32)
        selection_toolbar.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 5))

        self.btn_select_all = ctk.CTkButton(
            selection_toolbar, text="\u2611 一键全选", width=90, height=32,
            font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold"),
            command=lambda: self.set_all_selection(True)
        )
        self.btn_select_all.pack(side="left", padx=(0, 10))

        self.btn_deselect_all = ctk.CTkButton(
            selection_toolbar, text="☐ 一键清除", width=90, height=32,
            fg_color=("#A0AEC0", "#5A6578"), hover_color=("#718096", "#4A5568"),
            font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold"),
            command=lambda: self.set_all_selection(False)
        )
        self.btn_deselect_all.pack(side="left", padx=(0, 10))

        self.lbl_scan_status = ctk.CTkLabel(selection_toolbar, text="", text_color="#10B981", font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold"))
        self.lbl_scan_status.pack(side="left", padx=15)

        self.lbl_click_tips = ctk.CTkLabel(selection_toolbar, text="双击文件名可复制文字 | 列头可排序 | UI仅预览前5000个", text_color=("#5A6478", "#B0B8C8"), font=ctk.CTkFont(family="Microsoft YaHei", size=11))
        self.lbl_click_tips.pack(side="right")

        # 2.5 快速搜索过滤栏
        search_frame = ctk.CTkFrame(self.right_panel, fg_color=("#F1F5F9", "#1A1D24"), height=36, corner_radius=8)
        search_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 0))
        self.entry_search = ctk.CTkEntry(search_frame, placeholder_text="🔍 实时搜索过滤文件名...", font=("Microsoft YaHei", 12), height=32, border_width=0, fg_color="transparent")
        self.entry_search.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.entry_search.bind("<KeyRelease>", self._on_search_keyrelease)
        self.btn_search_clear = ctk.CTkButton(search_frame, text="✕", width=32, height=32, font=("Microsoft YaHei", 14), fg_color="transparent", border_width=0, text_color=("#94A3B8", "#64748B"), hover_color=("#E2E8F0", "#334155"), command=self._clear_search)
        self.btn_search_clear.pack(side="right")

        # 3. 文件列表树形图
        tree_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        tree_frame.grid(row=3, column=0, sticky="nsew", padx=15, pady=(5, 15))

        columns = ("check", "icon", "old", "new")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("check", text="状态", command=lambda: self._sort_treeview("check"))
        self.tree.heading("icon", text="", command=lambda: self._sort_treeview("icon"))
        self.tree.heading("old", text="📄 原文件名 / 相对路径", command=lambda: self._sort_treeview("old"))
        self.tree.heading("new", text="✨ 新文件名 (预览)", command=lambda: self._sort_treeview("new"))

        self.tree.column("check", width=50, minwidth=50, stretch=False, anchor="center")
        self.tree.column("icon", width=40, minwidth=40, stretch=False, anchor="center")
        self.tree.column("old", width=360, minwidth=220)
        self.tree.column("new", width=360, minwidth=220)

        self.scrollbar = ctk.CTkScrollbar(tree_frame, orientation="vertical", command=self.tree.yview, width=8, corner_radius=4, fg_color="transparent")
        self.tree.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y", padx=(5, 0))
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<Double-1>", lambda e: self.open_partial_copy_dialog())
        self.tree.bind("<Configure>", lambda e: self.update_scrollbar_visibility())

        # 4. 底部操作区 (冲突处理选项)
        bottom_frame = ctk.CTkFrame(self.right_panel, fg_color=("#F8FAFC", "#14161C"), height=48, corner_radius=10)
        bottom_frame.grid(row=4, column=0, sticky="ew", padx=15, pady=(0, 15))

        self.btn_undo = ctk.CTkButton(
            bottom_frame, text="↩ 撤销上次重命名",
            font=ctk.CTkFont(family="Microsoft YaHei", size=13, weight="bold"),
            fg_color=("#F59E0B", "#D97706"), hover_color=("#D97706", "#B45309"),
            state="disabled", command=self.undo_rename
        )
        self.btn_undo.pack(side="left")

        conflict_frame = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        conflict_frame.pack(side="left", padx=25)

        ctk.CTkLabel(conflict_frame, text="⚠️ 命名冲突处理:", font=("Microsoft YaHei", 12)).pack(side="left", padx=(0, 5))
        self.combo_conflict_policy = ctk.CTkOptionMenu(
            conflict_frame, values=["自动编号 (推荐)", "跳过当前", "强行覆盖", "弹窗询问"],
            width=135, font=("Microsoft YaHei", 12, "bold")
        )
        self.combo_conflict_policy.pack(side="left")

        self.btn_execute = ctk.CTkButton(
            bottom_frame, text="🚀 立即重命名",
            font=ctk.CTkFont(family="Microsoft YaHei", size=15, weight="bold"),
            height=42, command=self.execute_rename
        )
        self.btn_execute.pack(side="right")

    def toggle_filter_panel(self):

        """折叠/展开高级筛选控制区"""
        if self.filter_panel_visible:
            self.filter_body.pack_forget()
            self.filter_panel_visible = False
        else:
            self.filter_body.pack(fill="x", padx=10, pady=(0, 10))
            self.filter_panel_visible = True

    # ================= 规则模板管理引擎 =================
    def load_local_templates(self):
        if os.path.exists(self.templates_path):
            try:
                with open(self.templates_path, "r", encoding="utf-8") as f:
                    self.rule_templates = json.load(f)
            except Exception as e:
                self.logger.error(f"Failed to load templates: {e}")
                self.rule_templates = {}
        else:
            self.rule_templates = {}
            self.save_local_templates_to_disk()

    def save_local_templates_to_disk(self):
        try:
            with open(self.templates_path, "w", encoding="utf-8") as f:
                json.dump(self.rule_templates, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.logger.error(f"Failed to save templates: {e}")

    def update_templates_combobox_list(self):
        keys = ["无 / 默认"] + list(self.rule_templates.keys())
        self.combo_templates.configure(values=keys)

    def extract_current_rules_as_dict(self):
        return {
            "recursive": self.switch_recursive.get(),
            "find": self.entry_find.get(),
            "replace": self.entry_replace.get(),
            "regex": self.switch_regex.get(),
            "ignore_case": self.switch_ignore_case.get(),
            "insert_text": self.entry_insert_text.get(),
            "insert_pos": self.entry_insert_pos.get(),
            "insert_dir": self.combo_insert_dir.get(),
            "prefix": self.entry_prefix.get(),
            "suffix": self.entry_suffix.get(),
            "use_date": self.switch_date.get(),
            "date_format": self.date_format_var.get(),
            "overwrite": self.switch_overwrite.get(),
            "overwrite_template": self.entry_overwrite.get(),
            "num": self.switch_num.get(),
            "num_pos": self.combo_num_pos.get(),
            "num_sep": self.entry_num_sep.get(),
            "num_start": self.entry_num_start.get(),
            "num_pad": self.entry_num_pad.get(),
            "num_step": self.entry_num_step.get(),
            "remove_nums": self.switch_remove_nums.get(),
            "remove_pos": self.combo_remove_pos.get(),
            "name_case": self.name_case_var.get(),
            "ext_mode": self.ext_var.get(),
            "pinyin_mode": self.pinyin_var.get(),
            "use_metadata": self.switch_metadata.get(),
            "meta_template": self.entry_meta_template.get(),
            "conflict_policy": self.combo_conflict_policy.get()
        }

    def apply_rules_dict_to_gui(self, rules):
        for entry in [self.entry_find, self.entry_replace, self.entry_insert_text, 
                      self.entry_prefix, self.entry_suffix, self.entry_overwrite, 
                      self.entry_num_sep, self.entry_num_start, self.entry_num_pad, 
                      self.entry_num_step, self.entry_meta_template]:
            entry.delete(0, 'end')

        self.entry_find.insert(0, rules.get("find", ""))
        self.entry_replace.insert(0, rules.get("replace", ""))
        self.entry_insert_text.insert(0, rules.get("insert_text", ""))
        self.entry_insert_pos.delete(0, 'end')
        self.entry_insert_pos.insert(0, rules.get("insert_pos", "0"))
        self.combo_insert_dir.set(rules.get("insert_dir", "从开头"))
        
        self.entry_prefix.insert(0, rules.get("prefix", ""))
        self.entry_suffix.insert(0, rules.get("suffix", ""))
        self.date_format_var.set(rules.get("date_format", "_YYYYMMDD"))
        self.entry_overwrite.insert(0, rules.get("overwrite_template", ""))
        
        self.combo_num_pos.set(rules.get("num_pos", "文件名开头"))
        self.entry_num_sep.insert(0, rules.get("num_sep", "_"))
        self.entry_num_start.insert(0, rules.get("num_start", "1"))
        self.entry_num_pad.insert(0, rules.get("num_pad", "2"))
        self.entry_num_step.insert(0, rules.get("num_step", "1"))
        self.combo_remove_pos.set(rules.get("remove_pos", "清除开头所有数字"))
        self.entry_meta_template.insert(0, rules.get("meta_template", "{原名}_{拍摄时间}"))
        self.combo_conflict_policy.set(rules.get("conflict_policy", "自动编号 (推荐)"))

        self.name_case_var.set(rules.get("name_case", "keep"))
        self.ext_var.set(rules.get("ext_mode", "keep"))
        self.pinyin_var.set(rules.get("pinyin_mode", "keep"))

        def set_switch(switch_widget, value):
            if value: switch_widget.select()
            else: switch_widget.deselect()

        set_switch(self.switch_recursive, rules.get("recursive", False))
        set_switch(self.switch_regex, rules.get("regex", False))
        set_switch(self.switch_ignore_case, rules.get("ignore_case", False))
        set_switch(self.switch_overwrite, rules.get("overwrite", False))
        set_switch(self.switch_date, rules.get("use_date", False))
        set_switch(self.switch_num, rules.get("num", False))
        set_switch(self.switch_remove_nums, rules.get("remove_nums", False))
        set_switch(self.switch_metadata, rules.get("use_metadata", False))

        self.update_preview()

    def on_template_selected(self, choice):
        if choice == "无 / 默认":
            self.clear_rules()
            self.show_toast("已重置为默认空白规则")
        elif choice in self.rule_templates:
            self.apply_rules_dict_to_gui(self.rule_templates[choice])
            self.show_toast(f"已成功应用模板: {choice}")

    def save_current_template_dialog(self):
        dialog = ctk.CTkInputDialog(text="请给当前的配置组合起一个好听的名字:", title="保存为规则方案模板")
        self.update_idletasks()
        name = dialog.get_input()
        if name:
            name = name.strip()
            if not name: return
            self.rule_templates[name] = self.extract_current_rules_as_dict()
            self.save_local_templates_to_disk()
            self.update_templates_combobox_list()
            self.combo_templates.set(name)
            self.show_toast(f"模板 '{name}' 已保存！")

    def delete_current_template(self):
        current = self.combo_templates.get()
        if current == "无 / 默认":
            messagebox.showwarning("提示", "默认空模板无法被删除。")
            return
        if messagebox.askyesno("确认删除", f"您确定要永久删除规则方案模板 '{current}' 吗？"):
            if current in self.rule_templates:
                del self.rule_templates[current]
                self.save_local_templates_to_disk()
                self.update_templates_combobox_list()
                self.combo_templates.set("无 / 默认")
                self.clear_rules()
                self.show_toast("模板删除成功，已恢复空配置")

    def export_templates(self):
        if not self.rule_templates:
            messagebox.showinfo("提示", "当前无任何自定义模板可导出。")
            return

        current_selected = self.combo_templates.get()
        export_choice_window = ctk.CTkToplevel(self)
        export_choice_window.title("导出模板方案范围")
        export_choice_window.geometry("380x200")
        export_choice_window.resizable(False, False)
        export_choice_window.transient(self)
        export_choice_window.grab_set()

        export_choice_window.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 190
        y = self.winfo_y() + (self.winfo_height() // 2) - 100
        export_choice_window.geometry(f"+{x}+{y}")

        ctk.CTkLabel(export_choice_window, text="⚙️ 请选择您需要导出的模板范围:", font=("Microsoft YaHei", 13, "bold")).pack(pady=(15, 10))

        export_mode = ctk.StringVar(value="current" if current_selected != "无 / 默认" else "all")

        radio_current = ctk.CTkRadioButton(
            export_choice_window, 
            text=f"仅导出当前选中的模板: {current_selected}" if current_selected != "无 / 默认" else "仅导出当前选中的模板 (不可选，请先选中)", 
            variable=export_mode, value="current", 
            state="normal" if current_selected != "无 / 默认" else "disabled"
        )
        radio_current.pack(anchor="w", padx=30, pady=5)

        radio_all = ctk.CTkRadioButton(export_choice_window, text="全部导出 (合并您当前所有本地自定义方案)", variable=export_mode, value="all")
        radio_all.pack(anchor="w", padx=30, pady=5)

        def do_export():
            mode = export_mode.get()
            export_data = {}
            if mode == "current":
                export_data = {current_selected: self.rule_templates[current_selected]}
                filename_suggest = f"重序命名模板_{current_selected}.json"
            else:
                export_data = self.rule_templates
                filename_suggest = "重序命名全部规则模板导出.json"

            export_choice_window.destroy()

            path = filedialog.asksaveasfilename(
                title="选择导出模板的保存路径",
                filetypes=[("JSON Files", "*.json")],
                defaultextension=".json",
                initialfile=filename_suggest
            )
            if path:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(export_data, f, ensure_ascii=False, indent=4)
                    messagebox.showinfo("成功", f"🎉 已成功导出模板方案至:\n{path}")
                except Exception as e:
                    messagebox.showerror("导出失败", f"导出过程中发生错误:\n{str(e)}")

        btn_confirm = ctk.CTkButton(export_choice_window, text="确定导出", width=120, height=32, font=("Microsoft YaHei", 12, "bold"), command=do_export)
        btn_confirm.pack(pady=(15, 10))

    def import_templates(self):
        path = filedialog.askopenfilename(
            title="选择要导入的规则模板 JSON 文件",
            filetypes=[("JSON Files", "*.json")]
        )
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    imported = json.load(f)
                if not isinstance(imported, dict):
                    raise ValueError("模板文件格式非合法的规则集合字典")
                
                for k, v in imported.items():
                    if isinstance(v, dict):
                        self.rule_templates[k] = v
                
                self.save_local_templates_to_disk()
                self.update_templates_combobox_list()
                messagebox.showinfo("导入成功", f"🎉 成功导入并合并了 {len(imported)} 个规则模板方案！")
            except Exception as e:
                messagebox.showerror("导入失败", f"无法解析所选文件，可能不是有效的模板格式:\n{str(e)}")

    # ================= 深度提取元数据核心功能函数 =================
    def extract_file_metadata(self, filepath, ext):
        meta_dict = {}
        ext = ext.lower()

        if PIL_AVAILABLE and ext in ['.jpg', '.jpeg', '.png', '.tiff', '.webp']:
            try:
                with Image.open(filepath) as img:
                    exif_data = img._getexif()
                    if exif_data:
                        for tag, val in exif_data.items():
                            decoded = TAGS.get(tag, tag)
                            if decoded == 'DateTimeOriginal':
                                formatted_time = val.replace(':', '').replace(' ', '_')
                                meta_dict['拍摄时间'] = formatted_time[:15]  
                            elif decoded == 'Model':
                                meta_dict['相机型号'] = str(val).strip().replace(' ', '_')
                        
                        if 34853 in exif_data: 
                            gps_info = {}
                            for g_tag in exif_data[34853]:
                                g_decoded = GPSTAGS.get(g_tag, g_tag)
                                gps_info[g_decoded] = exif_data[34853][g_tag]
                            
                            if 'GPSLatitude' in gps_info and 'GPSLongitude' in gps_info:
                                def convert_to_degrees(value):
                                    try:
                                        d = float(value[0])
                                        m = float(value[1])
                                        s = float(value[2])
                                        return f"{d:.0f}°{m:.0f}′{s:.1f}″"
                                    except Exception:
                                        return str(value)
                                meta_dict['GPS纬度'] = convert_to_degrees(gps_info['GPSLatitude']) + str(gps_info.get('GPSLatitudeRef', ''))
                                meta_dict['GPS经度'] = convert_to_degrees(gps_info['GPSLongitude']) + str(gps_info.get('GPSLongitudeRef', ''))
            except Exception:
                self.logger.debug(f"Non-critical image metadata extraction skipped", exc_info=True)

        elif MUTAGEN_AVAILABLE and ext in ['.mp3', '.flac', '.wav', '.ogg', '.m4a']:
            try:
                audio = mutagen.File(filepath)
                if audio:
                    if ext == '.mp3':
                        try:
                            audio_easy = EasyID3(filepath)
                            meta_dict['歌手'] = audio_easy.get('artist', [''])[0]
                            meta_dict['专辑'] = audio_easy.get('album', [''])[0]
                            meta_dict['曲目号'] = audio_easy.get('tracknumber', [''])[0].split('/')[0] 
                            meta_dict['歌名'] = audio_easy.get('title', [''])[0]
                        except Exception:
                            pass
                    else:
                        meta_dict['歌手'] = audio.get('artist', audio.get('ARTIST', ['']))[0]
                        meta_dict['专辑'] = audio.get('album', audio.get('ALBUM', ['']))[0]
                        meta_dict['曲目号'] = audio.get('tracknumber', audio.get('TRACKNUMBER', ['']))[0].split('/')[0]
                        meta_dict['歌名'] = audio.get('title', audio.get('TITLE', ['']))[0]
            except Exception:
                self.logger.debug(f"Non-critical image metadata extraction skipped", exc_info=True)

        elif HACHOIR_AVAILABLE and ext in ['.mp4', '.mov', '.avi', '.mkv', '.wmv']:
            try:
                parser = createParser(filepath)
                if parser:
                    with parser:
                        metadata = extractMetadata(parser)
                        if metadata:
                            if metadata.has('width') and metadata.has('height'):
                                w = metadata.get('width')
                                h = metadata.get('height')
                                meta_dict['宽度'] = str(w)
                                meta_dict['高度'] = str(h)
                                meta_dict['分辨率'] = f"{w}x{h}"
                            
                            if metadata.has('duration'):
                                duration_sec = metadata.get('duration').seconds
                                t_str = str(datetime.timedelta(seconds=int(duration_sec)))
                                meta_dict['时长'] = t_str.replace(':', '_') 

                            if metadata.has('video_codec'):
                                meta_dict['视频编码'] = str(metadata.get('video_codec')).split(' ')[0].replace('/', '_')
            except Exception:
                self.logger.debug(f"Non-critical image metadata extraction skipped", exc_info=True)

        sanitized = {}
        for k, v in meta_dict.items():
            val = str(v).strip().replace('\\', '').replace('/', '').replace(':', '').replace('*', '').replace('?', '').replace('"', '').replace('<', '').replace('>', '').replace('|', '') 
            if val and val != "None":
                sanitized[k] = val
        return sanitized

    def save_session(self):
        try:
            state = {
                "recursive": self.switch_recursive.get(),
                "filter_ext": self.entry_filter_ext.get(),
                "size_op": self.combo_size_op.get(),
                "size_val": self.entry_size_val.get(),
                "size_unit": self.combo_size_unit.get(),
                "date_filter": self.combo_date_filter.get(),
                "name_match_mode": self.combo_name_match_mode.get(),
                "name_match_val": self.entry_name_match_val.get(),
                "regex_filter": self.entry_regex_filter.get(),
                "find": self.entry_find.get(),
                "replace": self.entry_replace.get(),
                "regex": self.switch_regex.get(),
                "ignore_case": self.switch_ignore_case.get(),
                "insert_text": self.entry_insert_text.get(),
                "insert_pos": self.entry_insert_pos.get(),
                "insert_dir": self.combo_insert_dir.get(),
                "prefix": self.entry_prefix.get(),
                "suffix": self.entry_suffix.get(),
                "use_date": self.switch_date.get(),
                "date_format": self.date_format_var.get(),
                "overwrite": self.switch_overwrite.get(),
                "overwrite_template": self.entry_overwrite.get(),
                "num": self.switch_num.get(),
                "num_pos": self.combo_num_pos.get(),
                "num_sep": self.entry_num_sep.get(),
                "num_start": self.entry_num_start.get(),
                "num_pad": self.entry_num_pad.get(),
                "num_step": self.entry_num_step.get(),
                "remove_nums": self.switch_remove_nums.get(),
                "remove_pos": self.combo_remove_pos.get(),
                "name_case": self.name_case_var.get(),
                "ext_mode": self.ext_var.get(),
                "pinyin_mode": self.pinyin_var.get(),
                "theme": self.theme_selector.get(),
                "active_theme_name": self.active_theme.get("name", "海洋"),
                "active_theme_color": self.active_theme.get("light_primary", ""),
                "undo_stack": self.undo_stack,
                "use_metadata": self.switch_metadata.get(),
                "meta_template": self.entry_meta_template.get(),
                "combo_selected_template": self.combo_templates.get(),
                "conflict_policy": self.combo_conflict_policy.get()
            }
            with open(self.recovery_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.logger.error(f"Failed to save session: {e}")

    def load_session(self):
        self.update_templates_combobox_list()

        if not os.path.exists(self.recovery_path):
            return
        try:
            with open(self.recovery_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            
            self.source_items = []
            self.current_base_dir = ""
            
            if state.get("recursive"): self.switch_recursive.select()
            else: self.switch_recursive.deselect()
            
            self.entry_filter_ext.insert(0, state.get("filter_ext", ""))
            self.combo_size_op.set(state.get("size_op", "不限"))
            self.entry_size_val.insert(0, state.get("size_val", ""))
            self.combo_size_unit.set(state.get("size_unit", "KB"))
            self.combo_date_filter.set(state.get("date_filter", "不限"))
            self.combo_name_match_mode.set(state.get("name_match_mode", "不限"))
            self.entry_name_match_val.insert(0, state.get("name_match_val", ""))
            self.entry_regex_filter.insert(0, state.get("regex_filter", ""))

            self.entry_find.insert(0, state.get("find", ""))
            self.entry_replace.insert(0, state.get("replace", ""))
            if state.get("regex"): self.switch_regex.select()
            if state.get("ignore_case"): self.switch_ignore_case.select()
            
            self.entry_insert_text.insert(0, state.get("insert_text", ""))
            self.entry_insert_pos.delete(0, 'end')
            self.entry_insert_pos.insert(0, state.get("insert_pos", "0"))
            self.combo_insert_dir.set(state.get("insert_dir", "从开头"))
            
            if state.get("use_metadata"): self.switch_metadata.select()
            self.entry_meta_template.delete(0, 'end')
            self.entry_meta_template.insert(0, state.get("meta_template", "{原名}_{拍摄时间}"))

            self.entry_prefix.insert(0, state.get("prefix", ""))
            self.entry_suffix.insert(0, state.get("suffix", ""))
            if state.get("use_date"): self.switch_date.select()
            self.date_format_var.set(state.get("date_format", "_YYYYMMDD"))
            
            if state.get("overwrite"): self.switch_overwrite.select()
            self.entry_overwrite.insert(0, state.get("overwrite_template", ""))
            
            if state.get("num"): self.switch_num.select()
            self.combo_num_pos.set(state.get("num_pos", "文件名开头"))
            self.entry_num_sep.delete(0, 'end')
            self.entry_num_sep.insert(0, state.get("num_sep", "_"))
            
            self.entry_num_start.delete(0, 'end')
            self.entry_num_start.insert(0, state.get("num_start", "1"))
            self.entry_num_pad.delete(0, 'end')
            self.entry_num_pad.insert(0, state.get("num_pad", "2"))
            self.entry_num_step.delete(0, 'end')
            self.entry_num_step.insert(0, state.get("num_step", "1"))
            
            if state.get("remove_nums"): self.switch_remove_nums.select()
            self.combo_remove_pos.set(state.get("remove_pos", "清除开头所有数字"))
            
            self.name_case_var.set(state.get("name_case", "keep"))
            self.ext_var.set(state.get("ext_mode", "keep"))
            self.pinyin_var.set(state.get("pinyin_mode", "keep"))
            self.combo_conflict_policy.set(state.get("conflict_policy", "自动编号 (推荐)"))
            
            self.undo_stack = state.get("undo_stack", [])
            self.update_undo_button_state()
            
            theme_selector_val = state.get("theme", "跟随系统")
            self.theme_selector.set(theme_selector_val)
            self.change_theme(theme_selector_val)
            theme_name = state.get("active_theme_name", "海洋")
            theme_color = state.get("active_theme_color", "")
            if theme_name == "自定义" and theme_color:
                self.set_theme_color("自定义", theme_color)
            else:
                self.set_theme_color(theme_name)

            tpl_choice = state.get("combo_selected_template", "无 / 默认")
            if tpl_choice in self.combo_templates.cget("values"):
                self.combo_templates.set(tpl_choice)

            self.update_preview()
            
        except Exception as e:
            self.logger.error(f"Failed to load session: {e}")

    def update_scrollbar_visibility(self):
        self.update_idletasks()
        try:
            y_span = self.tree.yview()
            if y_span[0] == 0.0 and y_span[1] == 1.0:
                self.scrollbar.pack_forget()
            else:
                self.scrollbar.pack_forget()
                self.tree.pack_forget()
                self.scrollbar.pack(side="right", fill="y", padx=(5, 0))
                self.tree.pack(side="left", fill="both", expand=True)
        except Exception:
            pass

    # ================= 快速搜索过滤与排序 =================
    def _on_search_keyrelease(self, event=None):
        """实时搜索过滤 TreeView 中的条目"""
        query = self.entry_search.get().strip().lower()
        for item in self.tree.get_children():
            values = self.tree.item(item, "values")
            if len(values) >= 4:
                filename = values[2].lower()  # old column is now index 2 (check, icon, old, new)
                if query and query not in filename:
                    self.tree.detach(item)
                else:
                    self.tree.reattach(item, "", "end")

    def _clear_search(self):
        """清除搜索框并恢复所有条目"""
        self.entry_search.delete(0, "end")
        for item in self.tree.get_children():
            self.tree.reattach(item, "", "end")

    def _sort_treeview(self, col):
        """按指定列排序 TreeView 条目"""
        col_idx = {"check": 0, "icon": 1, "old": 2, "new": 3}.get(col, 2)
        reverse = getattr(self, "_sort_reverse", False)
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]
        try:
            items.sort(key=lambda x: x[0].lower(), reverse=reverse)
        except Exception:
            items.sort(key=lambda x: x[0], reverse=reverse)
        for idx, (_, item) in enumerate(items):
            self.tree.move(item, "", idx)
        self._sort_reverse = not reverse

    @staticmethod
    @staticmethod
    def _get_file_icon(ext, is_dir=False):
        """根据文件后缀名或类型返回 Unicode 图标"""
        if is_dir:
            return "📁"
        ext = ext.lower()
        if ext in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".ico", ".svg"):
            return "🖼️"
        elif ext in (".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".wma"):
            return "🎵"
        elif ext in (".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm"):
            return "🎬"
        elif ext in (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"):
            return "📦"
        elif ext in (".pdf"):
            return "📕"
        elif ext in (".doc", ".docx"):
            return "📝"
        elif ext in (".xls", ".xlsx", ".csv"):
            return "📊"
        elif ext in (".ppt", ".pptx"):
            return "📽️"
        elif ext in (".py", ".js", ".html", ".css", ".cpp", ".java", ".go", ".rs"):
            return "💻"
        elif ext in (".txt", ".md", ".log"):
            return "📄"
        elif ext in (".exe", ".dll", ".so", ".dylib"):
            return "⚙️"
        return "📎"

    def create_context_menu(self):
        self.context_menu = tk.Menu(self, tearoff=0, relief="flat", borderwidth=0)
        self.context_menu.add_command(label="📋 复制完整文件名", command=self.copy_filename)
        self.context_menu.add_command(label="🔍 复制部分文件名...", command=self.open_partial_copy_dialog)
        
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.tree.bind("<Button-2>", self.show_context_menu)

    def show_context_menu(self, event):
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self.tree.selection_set(row_id)
            self.context_menu.post(event.x_root, event.y_root)

    def on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            row_id = self.tree.identify_row(event.y)
            if column == "#1" and row_id:
                index = self.tree.index(row_id)
                self.files_data[index]['checked'] = not self.files_data[index]['checked']
                self.update_preview()

    def set_all_selection(self, select_all=True):
        if not self.files_data: return
        for file in self.files_data: file['checked'] = select_all
        self.update_preview()

    def copy_filename(self):
        selected_item = self.tree.selection()
        if selected_item:
            values = self.tree.item(selected_item[0], "values")
            if values:
                filename = os.path.basename(values[2])
                self.clipboard_clear()
                self.clipboard_append(filename)
                self.show_toast(f"已复制: {filename[:25]}...")

    def open_partial_copy_dialog(self):
        selected_item = self.tree.selection()
        if not selected_item: return
        values = self.tree.item(selected_item[0], "values")
        if not values: return
        
        filename = os.path.basename(values[2])

        dialog = ctk.CTkToplevel(self)
        dialog.title("选中并复制任意部分文字")
        dialog.geometry("520x190")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 260
        y = self.winfo_y() + (self.winfo_height() // 2) - 95
        dialog.geometry(f"+{x}+{y}")

        lbl = ctk.CTkLabel(dialog, text="💡 请用鼠标左键拖动选择需要的部分，然后按 Ctrl + C 复制：", font=ctk.CTkFont(family="Microsoft YaHei", size=13), wraplength=480, justify="left")
        lbl.pack(padx=20, pady=(20, 10), anchor="w")

        entry = ctk.CTkEntry(dialog, width=480, font=("Microsoft YaHei", 13, "bold"))
        entry.insert(0, filename)
        entry.pack(padx=20, pady=5)
        entry.focus()
        entry.select_range(0, 'end')

        btn_close = ctk.CTkButton(dialog, text="完成", width=100, font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold"), command=dialog.destroy)
        btn_close.pack(pady=(15, 10))

    # ================= 🔥 升级：全面重写的超详细帮助文档 =================
    def open_help_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("重序 v3.0 - 使用说明书")
        dialog.geometry("860x800")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 430
        y = self.winfo_y() + (self.winfo_height() // 2) - 390
        dialog.geometry(f"+{x}+{y}")

        title_lbl = ctk.CTkLabel(dialog, text="重序 (ReOrder) v3.0 全景指南", font=ctk.CTkFont(family="Microsoft YaHei", size=20, weight="bold"), text_color=self.active_theme["light_primary"])
        title_lbl.pack(pady=(15, 5))

        author_lbl = ctk.CTkLabel(dialog, text="作者：鱼鱼鱼鱼吃", font=ctk.CTkFont(family="Microsoft YaHei", size=12), text_color=("#5A6478", "#B0B8C8"))
        author_lbl.pack(pady=(0, 10))

        help_box = ctk.CTkTextbox(dialog, width=800, height=620, font=("Microsoft YaHei", 12), corner_radius=8)
        help_box.pack(padx=30, pady=(0, 15))

        help_text = (
            "欢迎使用【重序 (ReOrder) v3.0】— 全面升级的专业级海量文件整理工具！\n"
            "\n"
            "🌟 【基础操作与文件导入】\n"
            "• 浏览导入：点击「浏览文件夹」选择目录，可开启递归扫描子文件夹\n"
            "• 拖拽导入：将文件/文件夹从资源管理器直接拖入窗口（Windows）\n"
            "• 实时搜索：右侧预览列表上方搜索框，输入关键字实时过滤\n"
            "• 点击列标题可按状态/类型/原名/新名排序\n"
            "• 双击文件名可弹出复制窗口，精准提取部分文字\n"
            "\n"
            "🔍 【高级筛选引擎】\n"
            "• 文件类型：按后缀名过滤（.jpg, .mp4，逗号分隔）\n"
            "• 大小限制：按 KB/MB 限制文件体积范围\n"
            "• 修改时间：筛选最近 1天/1周/1月/1年 的文件\n"
            "• 名称规则：包含/开头是/结尾是\n"
            "• 正则筛选：使用正则表达式精准匹配文件名\n"
            "\n"
            "🛠️ 【核心重命名规则（支持自由叠加）】\n"
            "执行顺序：清理数字→元数据/命名/替换→插入→附加→编号→格式/拼音\n"
            "• 替换：普通文本或正则替换，支持 $1 $2 捕获组引用\n"
            "• 插入：在文件名精准位置（从头/尾计算字符）插入文本\n"
            "• 命名：完全重写文件名，支持 CSV 映射批量导入\n"
            "• 元数据：从图片/音乐/视频提取 EXIF/ID3/编码信息自动命名\n"
            "• 附加：添加前缀、后缀，或自动附加文件修改日期\n"
            "• 编号：自动序号，自定义起始数、步长、补零位数、连接符\n"
            "• 清理数字：清除文件名开头/末尾/全部的数字\n"
            "• 格式：camelCase / snake_case / kebab-case\n"
            "• 拼音：中文转拼音（全拼无声调 / 全拼带声调 / 首字母缩写）\n"
            "\n"
            "🎵 【多媒体元数据智能重命名】\n"
            "使用花括号 {} 占位符组合模板（如 {拍摄时间}_{相机型号}）\n"
            "• 图片：{原名} {拍摄时间} {相机型号} {GPS纬度} {GPS经度}\n"
            "• 音乐：{原名} {歌手} {专辑} {曲目号} {歌名}\n"
            "• 视频：{原名} {分辨率} {宽度} {高度} {时长} {视频编码}\n"
            "\n"
            "🆕 【v3.0 新增功能】\n"
            "• 拖拽导入：资源管理器直接拖入文件/文件夹\n"
            "• 实时搜索过滤：预览列表上方搜索框即时筛选\n"
            "• 文件类型图标：15种图标自动标识（🖼图片 🎵音乐 🎬视频 📦压缩包等）\n"
            "• 列排序：点击列标题按状态/类型/原名/新名排序\n"
            "• 重复文件检测：同名检测 + MD5 哈希内容检测，自动标记重复项\n"
            "• 智能归类：按扩展名/日期/首字母/正则分组自动创建子文件夹并移动文件\n"
            "• 6 套活力配色：海洋蓝/翡翠绿/梦幻紫/热烈橙/浪漫玫红/明朗青空\n"
            "• 日志记录：操作日志写入 ~/.reorder.log 方便排查\n"
            "\n"
            "⚡ 【安全与性能保障】\n"
            "• 命名冲突：自动编号 / 跳过 / 覆盖 / 弹窗询问 四种策略\n"
            "• 多线程异步：扫描和执行在后台线程运行，界面流畅不卡死\n"
            "• 多步撤销：最多回滚 15 步历史操作\n"
            "• 会话恢复：重新打开自动恢复上次规则配置和撤销栈\n"
            "• 预览保护：预览上限 5000 条，实际执行覆盖全部文件\n"
            "\n"
            "📋 【规则模板管理】\n"
            "• 保存当前：将所有规则保存为模板，下拉菜单一键切换复用\n"
            "• 导入/导出：分享模板为 .json 文件，团队协作更高效\n"
            "\n"
            "— 作者：鱼鱼鱼鱼吃 —\n"
        )

        help_box.insert("0.0", help_text)
        help_box.configure(state="disabled")

        btn_close = ctk.CTkButton(dialog, text="我知道了", width=140, height=38, corner_radius=10, font=ctk.CTkFont(family="Microsoft YaHei", size=13, weight="bold"), command=dialog.destroy)
        btn_close.pack(pady=(0, 15))


    def show_toast(self, message):
        toast = ctk.CTkLabel(self.right_panel, text=message, fg_color=self.active_theme["light_primary"], text_color="white", corner_radius=8, padx=10, pady=5)
        toast.place(relx=0.5, rely=0.08, anchor="center")
        self.after(1500, toast.destroy)

    def change_theme(self, value):
        # 冻结更新以避免闪烁
        self.update_idletasks()
        try:
            if value == "深色":
                ctk.set_appearance_mode("Dark")
                target_mode = "Dark"
            elif value == "浅色":
                ctk.set_appearance_mode("Light")
                target_mode = "Light"
            else:
                ctk.set_appearance_mode("System")
                target_mode = self.safe_get_appearance_mode()

            # 同步更新所有控件颜色，消除闪烁
            self.update_idletasks()
            self.update_tree_style(target_mode)
            self.update_idletasks()
        finally:
            pass

        self.save_session()

    def adjust_color_brightness(self, hex_color, factor):
        hex_color = hex_color.lstrip('#')
        if len(hex_color) != 6:
            return "#3B82F6" 
        try:
            r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
            r = min(255, max(0, int(r * factor)))
            g = min(255, max(0, int(g * factor)))
            b = min(255, max(0, int(b * factor)))
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return "#3B82F6"

    def set_theme_color(self, theme_name, custom_color=None):
        if theme_name == "自定义" and custom_color:
            light_p = custom_color
            dark_p = self.adjust_color_brightness(custom_color, 0.75)
            light_h = self.adjust_color_brightness(custom_color, 1.15)
            dark_h = self.adjust_color_brightness(custom_color, 0.65)
            light_accent = self.adjust_color_brightness(custom_color, 0.85)
            dark_accent = self.adjust_color_brightness(custom_color, 0.55)
            self.active_theme = {
                "name": "自定义",
                "light_primary": light_p, "dark_primary": dark_p,
                "light_hover": light_h, "dark_hover": dark_h,
                "light_accent": light_accent, "dark_accent": dark_accent,
                "light_surface": self.get_tint_color(custom_color, "light"),
                "dark_surface": self.get_tint_color(custom_color, "dark"),
                "light_border": self.adjust_color_brightness(custom_color, 0.6),
                "dark_border": self.adjust_color_brightness(custom_color, 0.4),
            }
        else:
            # 全新活力配色预设 (v3.0)
            presets = {
                "海洋": {
                    "light_primary": "#2563EB", "dark_primary": "#3B82F6",
                    "light_hover": "#1D4ED8", "dark_hover": "#60A5FA",
                    "light_accent": "#93C5FD", "dark_accent": "#1E3A5F",
                    "light_surface": "#EFF6FF", "dark_surface": "#0F172A",
                    "light_border": "#BFDBFE", "dark_border": "#1E40AF",
                },
                "翡翠": {
                    "light_primary": "#059669", "dark_primary": "#10B981",
                    "light_hover": "#047857", "dark_hover": "#34D399",
                    "light_accent": "#A7F3D0", "dark_accent": "#064E3B",
                    "light_surface": "#ECFDF5", "dark_surface": "#0A1C14",
                    "light_border": "#6EE7B7", "dark_border": "#065F46",
                },
                "紫韵": {
                    "light_primary": "#7C3AED", "dark_primary": "#8B5CF6",
                    "light_hover": "#6D28D9", "dark_hover": "#A78BFA",
                    "light_accent": "#DDD6FE", "dark_accent": "#3B1F6E",
                    "light_surface": "#F5F3FF", "dark_surface": "#120C24",
                    "light_border": "#C4B5FD", "dark_border": "#5B21B6",
                },
                "橙焰": {
                    "light_primary": "#EA580C", "dark_primary": "#F97316",
                    "light_hover": "#C2410C", "dark_hover": "#FB923C",
                    "light_accent": "#FED7AA", "dark_accent": "#5C1D04",
                    "light_surface": "#FFF7ED", "dark_surface": "#1C1006",
                    "light_border": "#FDBA74", "dark_border": "#9A3412",
                },
                "玫红": {
                    "light_primary": "#DB2777", "dark_primary": "#EC4899",
                    "light_hover": "#BE185D", "dark_hover": "#F472B6",
                    "light_accent": "#FCE7F3", "dark_accent": "#4C1D2F",
                    "light_surface": "#FFF1F2", "dark_surface": "#1A0D12",
                    "light_border": "#F9A8D4", "dark_border": "#9D174D",
                },
                "青空": {
                    "light_primary": "#0891B2", "dark_primary": "#06B6D4",
                    "light_hover": "#0E7490", "dark_hover": "#22D3EE",
                    "light_accent": "#CFFAFE", "dark_accent": "#0A3A42",
                    "light_surface": "#F0FDFA", "dark_surface": "#0B1C20",
                    "light_border": "#67E8F9", "dark_border": "#155E75",
                },
            }
            self.active_theme = presets.get(theme_name, presets["海洋"])

        self.apply_theme_colors()
        self.save_session()

    def pick_custom_color(self):
        color = colorchooser.askcolor(title="选择您专属的主题颜色")
        if color and color[1]:
            self.set_theme_color("自定义", color[1])

    def apply_theme_colors(self):
        theme = self.active_theme
        lp = theme.get("light_primary", "#2563EB")
        dp = theme.get("dark_primary", "#3B82F6")
        lh = theme.get("light_hover", "#1D4ED8")
        dh = theme.get("dark_hover", "#60A5FA")
        la = theme.get("light_accent", "#93C5FD")
        da = theme.get("dark_accent", "#1E3A5F")
        ls = theme.get("light_surface", "#EFF6FF")
        ds = theme.get("dark_surface", "#0F172A")
        lb = theme.get("light_border", "#BFDBFE")
        db = theme.get("dark_border", "#1E40AF")

        # 主窗口背景
        self.configure(fg_color=(ls, ds))

        # 面板容器
        try:
            self.left_canvas_container.configure(fg_color=(ls, ds))
            self.left_panel.configure(fg_color=("#FFFFFF", "#12141A"))
            self.left_panel.configure(border_color=(lb, db))
            self.right_panel.configure(fg_color=("#FFFFFF", "#12141A"))
            self.right_panel.configure(border_color=(lb, db))
        except Exception: pass

        # 过滤面板
        try:
            self.filter_container.configure(fg_color=(la, da), border_color=(lb, db))
            self.filter_header.configure(text_color=(lp, dp))
        except Exception: pass

        # 核心按钮
        try:
            self.btn_browse.configure(fg_color=(lp, dp), hover_color=(lh, dh))
            self.btn_select_all.configure(fg_color=(lp, dp), hover_color=(lh, dh))
            self.btn_execute.configure(fg_color=(lp, dp), hover_color=(lh, dh))
            self.btn_scan_dup.configure(fg_color=(lp, dp), hover_color=(lh, dh))
            self.btn_execute_classify.configure(fg_color=(lp, dp), hover_color=(lh, dh))
        except Exception: pass

        # 选项菜单 (combo boxes)
        try:
            for combo in [self.combo_size_op, self.combo_size_unit, self.combo_date_filter,
                          self.combo_name_match_mode, self.combo_conflict_policy,
                          self.combo_num_pos, self.combo_remove_pos, self.combo_insert_dir,
                          self.combo_templates]:
                combo.configure(button_color=(lp, dp), button_hover_color=(lh, dh))
            self.combo_insert_dir.configure(button_color=(lp, dp), button_hover_color=(lh, dh))
        except Exception: pass

        # 标签页
        try:
            for tv in [self.tabview, self.tabview_adv]:
                tv.configure(
                    segmented_button_selected_color=(lp, dp),
                    segmented_button_selected_hover_color=(lh, dh),
                    segmented_button_unselected_color=(la, da),
                    segmented_button_unselected_hover_color=(self.adjust_color_brightness(la, 1.1), self.adjust_color_brightness(da, 1.2))
                )
            self.theme_selector.configure(selected_color=(lp, dp))
            self.theme_selector.configure(unselected_color=(la, da))
        except Exception: pass

        # 各类开关
        try:
            for sw in [self.switch_recursive, self.switch_regex, self.switch_ignore_case,
                       self.switch_overwrite, self.switch_date, self.switch_num,
                       self.switch_remove_nums, self.switch_metadata]:
                sw.configure(progress_color=(lp, dp))
        except Exception: pass

        # 单选按钮 (radio buttons) - 统一列表
        try:
            if hasattr(self, '_all_radio_widgets'):
                for rb in self._all_radio_widgets:
                    rb.configure(fg_color=(lp, dp))
        except Exception: pass

        # 滚动条
        try:
            self.scrollbar.configure(fg_color=(la, da), thumb_color=(lp, dp), thumb_hover_color=(lh, dh))
        except Exception: pass

        # 进度条
        try:
            self.progress_bar.configure(progress_color=(lp, dp))
        except Exception: pass

        # 模板按钮
        try:
            self.btn_save_tpl.configure(fg_color=(lp, dp), hover_color=(lh, dh))
        except Exception: pass

        # 底部附加操作按钮
        try:
            self.date_options.configure(button_color=(lp, dp), button_hover_color=(lh, dh))
        except Exception: pass

        # 搜索过滤栏
        try:
            self.entry_search.configure(border_color=(lb, db))
        except Exception: pass

        # toast 通知颜色 (动态，不在此处静态设置；保留旧引用)

        self.update_tree_style(self.safe_get_appearance_mode())

    def update_tree_style(self, mode):
        if mode == "System" or mode not in ["Light", "Dark"]:
            mode = self.safe_get_appearance_mode()
            
        style = ttk.Style()
        style.theme_use("default")
        
        theme = self.active_theme
        lp = theme.get("light_primary", "#3B82F6")
        dp = theme.get("dark_primary", "#1D4ED8")
        sel_bg = lp if mode == "Light" else dp
        sel_fg = "#FFFFFF" if mode == "Dark" else "#1A365D"
        
        bg_even = self.get_panel_tint(lp, "light") if mode == "Light" else self.get_panel_tint(dp, "dark")
        
        if mode == "Dark":
            bg_odd = self.adjust_color_brightness(bg_even, 1.15)       
            fg_color = "#E2E8F0"     
            head_bg = "#2C2D32"      
            head_fg = "#A0AEC0"      
        else: 
            bg_odd = "#F7FAFC"       
            fg_color = "#2D3748"     
            head_bg = "#EDF2F7"      
            head_fg = "#4A5568"      

        style.configure("Treeview", 
                        background=bg_even, 
                        foreground=fg_color, 
                        fieldbackground=bg_even,
                        rowheight=36,
                        borderwidth=0, 
                        font=("Microsoft YaHei", 11))
                            
        style.map('Treeview', 
                  background=[('selected', sel_bg)],
                  foreground=[('selected', sel_fg)])
                      
        style.configure("Treeview.Heading", 
                        background=head_bg, 
                        foreground=head_fg, 
                        relief="flat", 
                        font=("Microsoft YaHei", 11, "bold"))
            
        self.tree.tag_configure('even', background=bg_even, foreground=fg_color)
        self.tree.tag_configure('odd', background=bg_odd, foreground=fg_color)
        
        if hasattr(self, 'context_menu'):
            self.context_menu.configure(bg=bg_even, fg=fg_color)

    # ================= 命名风格与拼音转换工具 =================
    @staticmethod
    def _to_camel_case(text):
        """转换为驼峰命名: hello_world -> helloWorld"""
        words = re.split(r'[_\-\s]+', text)
        return words[0].lower() + ''.join(w.capitalize() for w in words[1:])

    @staticmethod
    def _to_snake_case(text):
        """转换为蛇形命名: HelloWorld -> hello_world"""
        s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', text)
        return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower().replace('-', '_').replace(' ', '_')

    @staticmethod
    def _to_kebab_case(text):
        """转换为短横线命名: HelloWorld -> hello-world"""
        s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1-\2', text)
        return re.sub(r'([a-z0-9])([A-Z])', r'\1-\2', s1).lower().replace('_', '-').replace(' ', '-')

    def _convert_to_pinyin(self, text, mode):
        """将中文文本转换为拼音"""
        try:
            from pypinyin import pinyin, Style
            if mode == "pinyin":
                result = pinyin(text, style=Style.NORMAL)
                return ''.join(item[0] for item in result)
            elif mode == "pinyin_tone":
                result = pinyin(text, style=Style.TONE3)
                return ''.join(item[0] for item in result)
            elif mode == "pinyin_initials":
                result = pinyin(text, style=Style.FIRST_LETTER)
                return ''.join(item[0] for item in result)
        except Exception as e:
            self.logger.debug(f"Pinyin conversion failed: {e}")
        return text

    # ================= CSV 映射导入 =================
    def import_csv_mapping(self):
        """从CSV文件导入文件名映射表进行批量重命名"""
        filepath = filedialog.askopenfilename(
            title="选择CSV映射文件",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")]
        )
        if not filepath:
            return
        try:
            import csv
            mapping = {}
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for row in reader:
                    if len(row) >= 2 and row[0].strip() and row[1].strip():
                        mapping[row[0].strip()] = row[1].strip()

            if not mapping:
                messagebox.showwarning("提示", "CSV文件中未找到有效的映射数据 (至少需要两列：原名, 新名)")
                return

            # 应用到预览
            matched = 0
            for d in self.files_data:
                if d['old'] in mapping:
                    name_part, ext_part = os.path.splitext(d['old'])
                    new_name = os.path.splitext(mapping[d['old']])[0] + ext_part
                    d['new'] = new_name
                    matched += 1

            self.update_preview()
            self.logger.info(f"CSV imported: {len(mapping)} entries, {matched} files matched")
            messagebox.showinfo("CSV导入完成", f"成功导入 {len(mapping)} 条映射规则，匹配到 {matched} 个文件。\n请检查预览结果后执行重命名。")
        except Exception as e:
            self.logger.error(f"CSV import failed: {e}")
            messagebox.showerror("导入失败", f"读取CSV文件出错:\n{e}")

    def browse_folder(self):
        folder = filedialog.askdirectory(title="选择工作文件夹")
        if folder:
            self.source_items = [folder]
            self.lbl_path.configure(text=folder)
            self.load_files()
            self.save_session()

    # ================= 拖拽导入支持 =================
    def _setup_drag_drop(self):
        """初始化拖拽导入：用 tkinterdnd2 加载 Tcl 扩展并注册窗口"""
        try:
            import tkinterdnd2, os as _os
            # 关键：把 tkdnd 的 Tcl 扩展目录加入 Tcl 搜索路径
            _tkdnd_dir = _os.path.join(_os.path.dirname(tkinterdnd2.__file__), 'tkdnd')
            self.tk.call('lappend', 'auto_path', _tkdnd_dir)
            self.tk.call('package', 'require', 'tkdnd')
            self.tk.call('tkdnd::drop_target', 'register', self._w, 'DND_Files')
            self.bind('<<Drop>>', self._on_dnd_drop)
            self.logger.info("Drag & drop ready")
        except Exception as e:
            self.logger.warning(f"DnD not available: {e}")

    def _on_dnd_drop(self, event):
        """拖拽事件：解析 Tcl 列表格式的文件路径"""
        try:
            data = event.data
            # Tcl 列表格式: {C:/path/file1} {C:/path/file2}
            paths = [p.strip() for p in str(data).replace('{','').split('}') if p.strip()]
            paths = [p for p in paths if os.path.exists(p)]
            if paths:
                self.after(0, lambda: self._on_drop_files(paths))
        except Exception:
            pass

    def _on_drop_files(self, paths):
        """处理拖入的文件/文件夹"""
        if not paths:
            return
        first_dir = None
        for p in paths:
            if os.path.isdir(p):
                first_dir = p
                break
        if first_dir:
            self.source_items = [first_dir]
            self.lbl_path.configure(text=first_dir)
            self.logger.info(f"DnD set work dir: {first_dir}")
        else:
            first_file = paths[0]
            parent_dir = os.path.dirname(first_file)
            self.source_items = [parent_dir]
            self.lbl_path.configure(text=parent_dir)
            self.logger.info(f"DnD set work dir from file: {parent_dir}")
        self.load_files()
        self.save_session()

    # ================= ⚡ 多线程异步无卡顿扫描 =================
    def load_files(self):
        if not self.source_items:
            return

        # 终止可能存在的上一次未完成的扫描任务，防止资源竞争
        self.scan_cancel_flag = True
        self.is_scanning = True
        self.lbl_scan_status.configure(text="⏳ 正在分析目录结构...")

        threading.Thread(target=self._async_scan_worker, daemon=True).start()
        self.after(50, self._poll_scan_queue)

    def _async_scan_worker(self):
        self.scan_cancel_flag = False
        valid_paths = [p for p in self.source_items if os.path.exists(p)]
        if not valid_paths: 
            self.scan_queue.put(('error', "路径不存在"))
            return

        if len(valid_paths) == 1:
            base_dir = valid_paths[0] if os.path.isdir(valid_paths[0]) else os.path.dirname(valid_paths[0])
        else:
            try:
                base = os.path.commonpath(valid_paths)
                base_dir = base if os.path.isdir(base) else os.path.dirname(base)
            except ValueError:
                base_dir = ""

        filter_ext_val = self.entry_filter_ext.get().strip().lower()
        target_exts = [x.strip() for x in filter_ext_val.split(',') if x.strip()] if filter_ext_val else []
        for i, ext in enumerate(target_exts):
            if not ext.startswith("."): target_exts[i] = "." + ext

        size_op = self.combo_size_op.get()
        size_limit_bytes = 0
        if size_op != "不限":
            try:
                size_num = float(self.entry_size_val.get().strip() or 0)
                size_limit_bytes = size_num * (1024 if self.combo_size_unit.get() == "KB" else 1024 * 1024)
            except ValueError:
                size_op = "不限"

        date_filter = self.combo_date_filter.get()
        time_threshold = None
        if date_filter != "不限":
            now = datetime.datetime.now()
            deltas = {"最近 1 天": datetime.timedelta(days=1), "最近 1 周": datetime.timedelta(weeks=1),
                      "最近 1 月": datetime.timedelta(days=30), "最近 1 年": datetime.timedelta(days=365)}
            time_threshold = now - deltas.get(date_filter, datetime.timedelta(0))

        name_match_mode = self.combo_name_match_mode.get()
        name_match_val = self.entry_name_match_val.get().strip().lower()

        regex_filter_val = self.entry_regex_filter.get().strip()
        regex_pattern = None
        if regex_filter_val:
            try: regex_pattern = re.compile(regex_filter_val)
            except re.error: pass


        recursive = self.switch_recursive.get()
        scanned_files = []
        added_paths = set()

        def scan_file_action(root, f):
            if self.scan_cancel_flag: return False
            full_path = os.path.join(root, f)
            if full_path in added_paths: return True

            f_lower = f.lower()
            # 扩展名过滤仅对文件生效，文件夹不受此限制
            if not os.path.isdir(full_path) and target_exts and not any(f_lower.endswith(ext) for ext in target_exts):
                return True

            try:
                stat_info = os.stat(full_path)
                if size_op != "不限":
                    file_size = stat_info.st_size
                    if size_op == "大于" and file_size <= size_limit_bytes: return True
                    if size_op == "小于" and file_size >= size_limit_bytes: return True
                
                if time_threshold is not None:
                    if datetime.datetime.fromtimestamp(stat_info.st_mtime) < time_threshold: return True
                
                if name_match_mode != "不限" and name_match_val:
                    name_part_lower = f.lower()
                    if name_match_mode == "包含" and name_match_val not in name_part_lower: return True
                    if name_match_mode == "开头是" and not name_part_lower.startswith(name_match_val): return True
                    if name_match_mode == "结尾是" and not name_part_lower.endswith(name_match_val): return True
                
                if regex_pattern and not regex_pattern.search(f_name_only):
                    return True

            except Exception:
                return True

            added_paths.add(full_path)
            rel_path = os.path.relpath(full_path, base_dir) if base_dir else full_path
            is_dir = os.path.isdir(full_path)
            scanned_files.append({
                'dir': root,
                'old_rel': rel_path,
                'old': f,
                'new': f,
                'checked': True,
                'is_dir': is_dir,
            })
            
            if len(scanned_files) % 1000 == 0:
                self.scan_queue.put(('progress', len(scanned_files)))
            return True

        for item in valid_paths:
            if self.scan_cancel_flag: break
            if os.path.isdir(item):
                if recursive:
                    for root, dirs, files in os.walk(item):
                        if self.scan_cancel_flag: break
                        for f in files:
                            scan_file_action(root, f)
                        for d in dirs:
                            scan_file_action(root, d)
                else:
                    try:
                        for f in os.listdir(item):
                            if self.scan_cancel_flag: break
                            fp = os.path.join(item, f)
                            if os.path.isfile(fp) or os.path.isdir(fp):
                                scan_file_action(item, f)
                    except Exception: pass
            elif os.path.isfile(item):
                scan_file_action(os.path.dirname(item), os.path.basename(item))

        if not self.scan_cancel_flag:
            self.scan_queue.put(('done', (scanned_files, base_dir)))

    def _poll_scan_queue(self):
        try:
            while True:
                msg_type, data = self.scan_queue.get_nowait()
                if msg_type == 'progress':
                    self.lbl_scan_status.configure(text=f"⏳ 后台异步载入中 (已扫描 {data} 个项目)...")
                elif msg_type == 'error':
                    self.is_scanning = False
                    self.lbl_scan_status.configure(text="")
                    messagebox.showerror("错误", f"分析失败: {data}")
                elif msg_type == 'done':
                    self.is_scanning = False
                    self.lbl_scan_status.configure(text="🟢 扫描分析完成")
                    self.after(1000, lambda: self.lbl_scan_status.configure(text=""))
                    
                    self.files_data = data[0]
                    self.current_base_dir = data[1]
                    self.files_data.sort(key=lambda x: x['old_rel'])
                    
                    self.update_preview()
                self.scan_queue.task_done()
        except queue.Empty:
            if self.is_scanning:
                self.after(50, self._poll_scan_queue)

    def clear_rules(self):
        self.entry_find.delete(0, 'end')
        self.entry_replace.delete(0, 'end')
        self.switch_regex.deselect()
        self.switch_ignore_case.deselect()
        
        self.entry_insert_text.delete(0, 'end')
        self.entry_insert_pos.delete(0, 'end')
        self.entry_insert_pos.insert(0, "0")
        self.combo_insert_dir.set("从开头")

        self.switch_metadata.deselect()
        self.entry_meta_template.delete(0, 'end')
        self.entry_meta_template.insert(0, "{原名}_{拍摄时间}")
        
        self.entry_prefix.delete(0, 'end')
        self.entry_suffix.delete(0, 'end')
        self.switch_date.deselect()
        self.date_format_var.set("_YYYYMMDD")
        self.entry_overwrite.delete(0, 'end')
        self.switch_overwrite.deselect()
        self.switch_num.deselect()
        self.combo_num_pos.set("文件名开头")
        self.entry_num_sep.delete(0, 'end')
        self.entry_num_sep.insert(0, "_")
        self.entry_num_start.delete(0, 'end')
        self.entry_num_start.insert(0, "1")
        self.entry_num_pad.delete(0, 'end')
        self.entry_num_pad.insert(0, "2")
        self.entry_num_step.delete(0, 'end')
        self.entry_num_step.insert(0, "1")
        self.switch_remove_nums.deselect()
        self.combo_remove_pos.set("清除开头所有数字")
        self.ext_var.set("keep")
        self.name_case_var.set("keep")
        self.pinyin_var.set("keep")
        self.update_preview()
        self.save_session()

    # ================= 极速 Chunk 分片 UI 预览防假死 =================
    def update_preview(self):
        if hasattr(self, '_preview_after_id') and self._preview_after_id:
            self.after_cancel(self._preview_after_id)
            self._preview_after_id = None

        for item in self.tree.get_children():
            self.tree.delete(item)

        if not self.files_data:
            self.lbl_summary.configure(text="重序 | 共找到 0 个文件 | 已选中 0 个 | 将修改 0 个")
            return

        self.preview_args = {
            "find_str": self.entry_find.get(),
            "replace_str": self.entry_replace.get(),
            "use_regex": self.switch_regex.get(),
            "use_ignore_case": self.switch_ignore_case.get(),
            "insert_text": self.entry_insert_text.get(),
            "insert_pos": int(self.entry_insert_pos.get() or 0),
            "insert_dir": self.combo_insert_dir.get(),
            "use_metadata": self.switch_metadata.get(),
            "meta_template": self.entry_meta_template.get(),
            "prefix": self.entry_prefix.get(),
            "suffix": self.entry_suffix.get(),
            "use_date": self.switch_date.get(),
            "date_fmt": self.date_format_var.get(),
            "use_overwrite": self.switch_overwrite.get(),
            "overwrite_template": self.entry_overwrite.get(),
            "use_num": self.switch_num.get(),
            "num_pos": self.combo_num_pos.get(),
            "num_sep": self.entry_num_sep.get(),
            "num_start": int(self.entry_num_start.get() or 1),
            "num_pad": int(self.entry_num_pad.get() or 1),
            "num_step": int(self.entry_num_step.get() or 1),
            "use_remove_nums": self.switch_remove_nums.get(),
            "remove_pos": self.combo_remove_pos.get(),
            "name_case": self.name_case_var.get(),
            "ext_mode": self.ext_var.get(),
            "pinyin_mode": self.pinyin_var.get()
        }

        self.total_count = len(self.files_data)
        self.preview_limit = min(self.total_count, 5000)
        
        self._changed_count = 0
        self._checked_count = 0
        
        self._render_preview_chunk(0)

    def _render_preview_chunk(self, start_idx):
        chunk_size = 150
        end_idx = min(start_idx + chunk_size, self.preview_limit)
        args = self.preview_args

        current_num = args["num_start"] + start_idx * args["num_step"]

        for idx in range(start_idx, end_idx):
            data = self.files_data[idx]
            old_name = data['old']
            name_part, ext_part = os.path.splitext(old_name)
            is_checked = data['checked']

            if is_checked:
                self._checked_count += 1
                
                if args["use_remove_nums"]:
                    if args["remove_pos"] == "清除开头所有数字":
                        name_part = re.sub(r"^\d+[\s._-]*", "", name_part)
                    elif args["remove_pos"] == "清除末尾所有数字":
                        name_part = re.sub(r"[\s._-]*\d+$", "", name_part)
                    elif args["remove_pos"] == "清除名字里所有数字":
                        name_part = re.sub(r"\d+", "", name_part)

                if args["use_metadata"] and args["meta_template"]:
                    abs_filepath = os.path.join(data['dir'], old_name)
                    extracted_meta = self.extract_file_metadata(abs_filepath, ext_part)
                    temp_name = args["meta_template"].replace("{原名}", name_part)
                    all_supported_tags = [
                        "拍摄时间", "相机型号", "GPS纬度", "GPS经度", "歌手", 
                        "专辑", "曲目号", "歌名", "宽度", "高度", "分辨率", "时长", "视频编码"
                    ]
                    for tag in all_supported_tags:
                        placeholder = "{" + tag + "}"
                        if placeholder in temp_name:
                            temp_name = temp_name.replace(placeholder, extracted_meta.get(tag, ""))
                    name_part = temp_name.strip('_').replace('__', '_')
                    if not name_part: name_part = "未命名的多媒体"

                if args["use_overwrite"]:
                    name_part = args["overwrite_template"] if args["overwrite_template"] else "未命名"
                elif not (args["use_metadata"] and args["meta_template"]):
                    if args["find_str"]:
                        flags = re.IGNORECASE if args["use_ignore_case"] else 0
                        if args["use_regex"]:
                            # 支持 $1, $2 捕获组引用 (转换为 Python 的 \1, \2)
                            replace_with_groups = re.sub(r'\$(\d+)', r'\\\1', args["replace_str"])
                            try: name_part = re.sub(args["find_str"], replace_with_groups, name_part, flags=flags)
                            except re.error: pass
                        else:
                            try: name_part = re.sub(re.escape(args["find_str"]), args["replace_str"], name_part, flags=flags)
                            except re.error: pass

                if args["insert_text"]:
                    pos = args["insert_pos"]
                    if args["insert_dir"] == "从开头":
                        name_part = name_part[:pos] + args["insert_text"] + name_part[pos:]
                    else:
                        if pos == 0: name_part = name_part + args["insert_text"]
                        else: name_part = name_part[:-pos] + args["insert_text"] + name_part[-pos:]

                name_part = f"{args['prefix']}{name_part}{args['suffix']}"

                if args["use_date"]:
                    try:
                        filepath = os.path.join(data['dir'], old_name)
                        mtime = os.path.getmtime(filepath)
                        dt = datetime.datetime.fromtimestamp(mtime)
                        fmt_map = {"_YYYYMMDD": "_%Y%m%d", "_YYYY-MM-DD": "_%Y-%m-%d", "_YYYYMMDD_HHMMSS": "_%Y%m%d_%H%M%S"}
                        name_part = f"{name_part}{dt.strftime(fmt_map.get(args['date_fmt'], '_%Y%m%d'))}"
                    except Exception: pass

                if args["use_num"]:
                    num_str = str(current_num).zfill(args["num_pad"])
                    if args["num_pos"] == "文件名开头":
                        name_part = f"{num_str}{args['num_sep']}{name_part}"
                    else:
                        name_part = f"{name_part}{args['num_sep']}{num_str}"
                    current_num += args["num_step"]

                if args["name_case"] == "lower": name_part = name_part.lower()
                elif args["name_case"] == "upper": name_part = name_part.upper()
                elif args["name_case"] == "title": name_part = name_part.title()
                elif args["name_case"] == "camel": name_part = self._to_camel_case(name_part)
                elif args["name_case"] == "snake": name_part = self._to_snake_case(name_part)
                elif args["name_case"] == "kebab": name_part = self._to_kebab_case(name_part)

                # --- 拼音转换 ---
                pinyin_mode = args.get("pinyin_mode", "keep")
                if pinyin_mode != "keep" and self._pypinyin_available:
                    name_part = self._convert_to_pinyin(name_part, pinyin_mode)

                if args["ext_mode"] == "lower": ext_part = ext_part.lower()
                elif args["ext_mode"] == "upper": ext_part = ext_part.upper()

                new_name = name_part + ext_part
            else:
                new_name = old_name

            data['new'] = new_name
            row_tag = 'odd' if idx % 2 != 0 else 'even'
            check_box_symbol = "☑" if is_checked else "☐"
            file_icon = self._get_file_icon(ext_part, data.get('is_dir', False))

            rel_dir = os.path.dirname(data['old_rel'])
            new_rel = os.path.join(rel_dir, new_name) if rel_dir else new_name
            new_rel = new_rel.replace('\\', '/')

            if new_name != old_name:
                self._changed_count += 1
                self.tree.insert("", "end", values=(check_box_symbol, file_icon, data['old_rel'], f"🟢 {new_rel}"), tags=(row_tag,))
            else:
                self.tree.insert("", "end", values=(check_box_symbol, file_icon, data['old_rel'], new_rel), tags=(row_tag,))

        self.lbl_summary.configure(text=f"重序 | 共 {self.total_count} 个项目 | 已选 {self._checked_count} | 将改 {self._changed_count}")
        self.update_scrollbar_visibility()

        if end_idx < self.preview_limit:
            self._preview_after_id = self.after(15, lambda: self._render_preview_chunk(end_idx))
        else:
            self._preview_after_id = None
            self.save_session()

    # ================= ⚡ 多线程执行与冲突避让系统 =================
    def execute_rename(self):
        if not self.files_data:
            messagebox.showwarning("提示", "未载入任何文件！")
            return
            
        to_change = [d for d in self.files_data if d['checked'] and d['old'] != d['new']]
        if not to_change:
            messagebox.showinfo("提示", "未勾选任何将被修改的文件，无需执行。")
            return
            
        if not messagebox.askyesno("确认", f"即将对过滤选中的 {len(to_change)} 个文件进行重命名。\n\n确定执行吗？"):
            return

        self.is_executing = True
        self.execute_queue = queue.Queue()

        self.progress_win = ctk.CTkToplevel(self)
        self.progress_win.title("执行重命名")
        self.progress_win.geometry("480x180")
        self.progress_win.resizable(False, False)
        self.progress_win.transient(self)
        self.progress_win.grab_set()

        self.progress_win.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 240
        y = self.winfo_y() + (self.winfo_height() // 2) - 90
        self.progress_win.geometry(f"+{x}+{y}")

        self.lbl_progress_status = ctk.CTkLabel(self.progress_win, text="正在安全筹备重命名执行队列...", font=("Microsoft YaHei", 12))
        self.lbl_progress_status.pack(pady=(20, 10))

        self.progress_bar = ctk.CTkProgressBar(self.progress_win, width=400)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=10)

        threading.Thread(target=self._async_execute_worker, args=(to_change,), daemon=True).start()
        self.after(50, self._poll_execute_queue)

    def _async_execute_worker(self, to_change):
        policy = self.combo_conflict_policy.get()
        success = 0
        current_undo_log = []
        errors = []
        apply_to_all_choice = None 

        total = len(to_change)

        for idx, d in enumerate(to_change):
            old_path = os.path.join(d['dir'], d['old'])
            new_path_target = os.path.join(d['dir'], d['new'])
            
            if os.path.exists(new_path_target) and d['old'].lower() != d['new'].lower():
                current_policy = policy
                
                if apply_to_all_choice:
                    current_policy = apply_to_all_choice
                
                if current_policy == "弹窗询问":
                    response_q = queue.Queue()
                    self.execute_queue.put(('ask_conflict', (d['old'], d['new'], response_q)))
                    user_action, apply_all = response_q.get() 
                    
                    if apply_all:
                        apply_to_all_choice = user_action
                    current_policy = user_action

                if current_policy in ["自动编号 (推荐)", "自动编号"]:
                    base, ext = os.path.splitext(d['new'])
                    counter = 1
                    while True:
                        candidate_name = f"{base} ({counter}){ext}"
                        candidate_path = os.path.join(d['dir'], candidate_name)
                        if not os.path.exists(candidate_path):
                            new_path_target = candidate_path
                            d['new'] = candidate_name 
                            break
                        counter += 1
                
                elif current_policy == "强行覆盖":
                    try: os.remove(new_path_target)
                    except Exception as e:
                        errors.append(f"强行覆写失败: {d['old']} -> 被目标锁定 ({str(e)})")
                        continue

                elif current_policy == "跳过当前":
                    errors.append(f"跳过冲突: {d['old']} -> 目标文件 {d['new']} 已存在")
                    continue

            try:
                os.rename(old_path, new_path_target)
                success += 1
                current_undo_log.append({'old': old_path, 'new': new_path_target})
            except Exception as e:
                errors.append(f"重命名失败: {d['old']} ({str(e)})")

            if idx % 10 == 0 or idx == total - 1:
                self.execute_queue.put(('progress', (idx + 1, total)))

        self.execute_queue.put(('done', (success, current_undo_log, errors)))

    def _poll_execute_queue(self):
        try:
            while True:
                msg_type, data = self.execute_queue.get_nowait()
                if msg_type == 'progress':
                    curr, total = data
                    ratio = curr / total
                    self.progress_bar.set(ratio)
                    self.lbl_progress_status.configure(text=f"🚀 正在后台物理改名 ({curr} / {total})...")
                
                elif msg_type == 'ask_conflict':
                    old_name, conflicted_name, resp_q = data
                    self._show_conflict_modal(old_name, conflicted_name, resp_q)
                
                elif msg_type == 'done':
                    self.is_executing = False
                    self.progress_win.destroy()
                    
                    success, undo_log, errors = data
                    if success > 0:
                        self.undo_stack.append(undo_log)
                        if len(self.undo_stack) > 15:
                            self.undo_stack.pop(0)
                        self.update_undo_button_state()
                    
                    self.load_files()
                    
                    if errors:
                        err_str = "\n".join(errors[:8]) + ("\n...(更多错误已被折叠)" if len(errors) > 8 else "")
                        messagebox.showwarning("执行部分完成", f"✅ 成功重命名: {success} 个文件\n❌ 遇到异常跳过: {len(errors)} 个\n\n冲突异常日志摘要:\n{err_str}")
                    else:
                        messagebox.showinfo("完成", f"🎉 物理重命名执行大功告成！已成功处理 {success} 个文件！")
                self.execute_queue.task_done()
        except queue.Empty:
            if self.is_executing:
                self.after(50, self._poll_execute_queue)

    def _show_conflict_modal(self, old_name, conflicted_name, resp_q):
        ask_win = ctk.CTkToplevel(self)
        ask_win.title("⚠️ 文件名同名冲突拦截")
        ask_win.geometry("520x260")
        ask_win.resizable(False, False)
        ask_win.transient(self)
        ask_win.grab_set()

        ask_win.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 260
        y = self.winfo_y() + (self.winfo_height() // 2) - 130
        ask_win.geometry(f"+{x}+{y}")

        msg_text = (
            f"重命名目标已存在！请选择您的动作：\n\n"
            f"• 原始源文件: {old_name}\n"
            f"• 冲突目标名: {conflicted_name}"
        )
        lbl = ctk.CTkLabel(ask_win, text=msg_text, font=("Microsoft YaHei", 12), justify="left", wraplength=460)
        lbl.pack(padx=20, pady=(20, 15), anchor="w")

        apply_all_var = tk.BooleanVar(value=False)
        chk = ctk.CTkCheckBox(ask_win, text="将此选择应用于后续所有同名冲突 (不再弹窗询问)", variable=apply_all_var, font=("Microsoft YaHei", 11))
        chk.pack(padx=20, pady=(0, 15), anchor="w")

        btn_row = ctk.CTkFrame(ask_win, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=10)

        def submit(action):
            resp_q.put((action, apply_all_var.get()))
            ask_win.destroy()

        btn_auto = ctk.CTkButton(btn_row, text="自动重编号", width=110, font=("Microsoft YaHei", 12, "bold"), command=lambda: submit("自动编号"))
        btn_auto.pack(side="left", padx=5)

        btn_skip = ctk.CTkButton(btn_row, text="跳过该文件", width=110, fg_color=("#CBD5E1", "#475569"), text_color=("#1E293B", "#F1F5F9"), hover_color=("#94A3B8", "#334155"), font=("Microsoft YaHei", 12), command=lambda: submit("跳过当前"))
        btn_skip.pack(side="left", padx=5)

        btn_ovr = ctk.CTkButton(btn_row, text="强行覆盖", width=110, fg_color=("#FEE2E2", "#450A0A"), text_color=("#991B1B", "#FCA5A5"), hover_color=("#FCA5A5", "#7F1D1D"), font=("Microsoft YaHei", 12), command=lambda: submit("强行覆盖"))
        btn_ovr.pack(side="left", padx=5)

    def update_undo_button_state(self):
        if self.undo_stack:
            self.btn_undo.configure(
                state="normal", 
                text=f"↩ 撤销上次重命名 (历史 {len(self.undo_stack)} 步)"
            )
        else:
            self.btn_undo.configure(
                state="disabled", 
                text="↩ 撤销上次重命名"
            )

    # ================= 重复文件检测 =================
    def scan_duplicates(self):
        """扫描重复文件并在右侧预览中标记"""
        if not self.files_data:
            messagebox.showwarning("提示", "请先载入文件！")
            return

        mode = self.dup_mode_var.get()
        self.lbl_dup_result.configure(text="⏳ 正在扫描重复文件...")
        self.update_idletasks()

        if mode == "name":
            # 同名检测
            name_map = {}
            for d in self.files_data:
                name_lower = d['old'].lower()
                name_map.setdefault(name_lower, []).append(d)
            dups = {k: v for k, v in name_map.items() if len(v) > 1}
        else:
            # 哈希检测
            import hashlib
            hash_map = {}
            total = len(self.files_data)
            for idx, d in enumerate(self.files_data):
                try:
                    filepath = os.path.join(d['dir'], d['old'])
                    with open(filepath, 'rb') as f:
                        file_hash = hashlib.md5(f.read()).hexdigest()
                    hash_map.setdefault(file_hash, []).append(d)
                except Exception:
                    pass
                if idx % 50 == 0:
                    self.lbl_dup_result.configure(text=f"⏳ 正在计算哈希 ({idx+1}/{total})...")
                    self.update_idletasks()
            dups = {k: v for k, v in hash_map.items() if len(v) > 1}

        dup_count = sum(len(v) - 1 for v in dups.values())
        group_count = len(dups)

        if dup_count == 0:
            self.lbl_dup_result.configure(text="✅ 未发现重复文件！")
            messagebox.showinfo("查重完成", "恭喜，未发现任何重复文件！")
            return

        result_text = f"发现 {group_count} 组重复，共 {dup_count} 个多余文件"
        self.lbl_dup_result.configure(text=result_text)

        # 将重复组信息暂存
        self._dup_groups = dups
        self.logger.info(f"Duplicate scan: {result_text}")

        # 高亮显示重复文件(将重复组的第一个保留勾选，其余取消勾选以标记)
        for group_files in dups.values():
            for i, d in enumerate(group_files):
                if i == 0:
                    d['checked'] = True  # 保留第一个
                else:
                    d['checked'] = False  # 标记重复

        self.update_preview()
        messagebox.showinfo("查重完成", f"{result_text}\n\n已在预览列表中标记重复项（☑=保留，☐=建议删除的重复项）")

    def mark_duplicates_for_removal(self):
        """批量取消勾选所有重复项(仅保留每组的第一个)"""
        if not hasattr(self, '_dup_groups') or not self._dup_groups:
            messagebox.showinfo("提示", "请先执行重复文件扫描！")
            return

        for group_files in self._dup_groups.values():
            for i, d in enumerate(group_files):
                d['checked'] = (i == 0)

        self.update_preview()
        messagebox.showinfo("完成", "已批量标记重复项，请检查预览后执行右下方「立即重命名」或手动操作。")

    # ================= 智能文件夹归类 =================
    def execute_classify(self):
        """根据归类规则将文件移动到子文件夹"""
        if not self.files_data:
            messagebox.showwarning("提示", "请先载入文件！")
            return
        if not self.current_base_dir:
            messagebox.showwarning("提示", "未检测到有效的工作目录！")
            return

        rule = self.classify_rule_var.get()
        regex_pattern = self.entry_classify_regex.get().strip()
        base_dir = self.current_base_dir

        if not messagebox.askyesno("确认归类", f"即将根据规则「{rule}」在 {base_dir} 下创建子文件夹并移动文件。\n\n确定执行吗？"):
            return

        success = 0
        errors = []
        undo_log = []

        for d in self.files_data:
            if not d['checked']:
                continue
            try:
                # 确定目标子文件夹名
                if rule == "ext":
                    ext = os.path.splitext(d['old'])[1].lstrip('.').lower()
                    subfolder = ext if ext else "no_ext"
                elif rule == "date":
                    filepath = os.path.join(d['dir'], d['old'])
                    mtime = os.path.getmtime(filepath)
                    dt = datetime.datetime.fromtimestamp(mtime)
                    subfolder = os.path.join(str(dt.year), f"{dt.month:02d}")
                elif rule == "first_letter":
                    first = d['old'][0].upper() if d['old'] else '_'
                    subfolder = first if first.isalnum() else '_'
                elif rule == "regex":
                    if regex_pattern:
                        m = re.match(regex_pattern, os.path.splitext(d['old'])[0])
                        if m:
                            subfolder = os.path.join(*m.groups()) if m.groups() else "matched"
                        else:
                            subfolder = "unmatched"
                    else:
                        subfolder = "no_regex"
                else:
                    subfolder = "classified"

                # 创建目标文件夹
                dest_dir = os.path.join(base_dir, subfolder)
                if not os.path.exists(dest_dir):
                    os.makedirs(dest_dir, exist_ok=True)

                old_path = os.path.join(d['dir'], d['old'])
                new_path = os.path.join(dest_dir, d['old'])

                # 处理目标文件冲突
                if os.path.exists(new_path):
                    base, ext = os.path.splitext(d['old'])
                    counter = 1
                    while os.path.exists(os.path.join(dest_dir, f"{base} ({counter}){ext}")):
                        counter += 1
                    new_path = os.path.join(dest_dir, f"{base} ({counter}){ext}")

                os.rename(old_path, new_path)
                undo_log.append({'old': old_path, 'new': new_path})
                success += 1
            except Exception as e:
                errors.append(f"{d['old']}: {e}")

        if undo_log:
            self.undo_stack.append(undo_log)
            if len(self.undo_stack) > 15:
                self.undo_stack.pop(0)
            self.update_undo_button_state()

        self.load_files()

        if errors:
            messagebox.showwarning("归类完成（部分失败）", f"✅ 成功归类 {success} 个文件\n❌ 失败 {len(errors)} 个\n\n错误摘要:\n" + "\n".join(errors[:5]))
        else:
            messagebox.showinfo("归类完成", f"🎉 成功将 {success} 个文件按规则归类到子文件夹！")

    def undo_rename(self):
        if not self.undo_stack:
            return

        last_log = self.undo_stack[-1]
        if not messagebox.askyesno("撤销确认", f"即将回滚上一次的 {len(last_log)} 个重命名操作。\n\n是否继续？"):
            return
            
        log_to_undo = self.undo_stack.pop() 
        success = 0
        for log in log_to_undo:
            try:
                if os.path.exists(log['new']):
                    os.rename(log['new'], log['old'])
                    success += 1
            except Exception as e:
                self.logger.error(f"Failed to restore file: {e}")
                
        self.load_files()
        self.update_undo_button_state()
        self.save_session()  
        messagebox.showinfo("撤销完成", f"↩ 成功恢复 {success} 个文件原来的名字！")


if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass

    app = ModernRenamerApp()
    app.mainloop()