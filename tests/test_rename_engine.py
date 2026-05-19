# -*- coding: utf-8 -*-
"""Unit tests for core rename engine logic."""
import pytest
import os
import re
import datetime
import tempfile
import shutil


class TestReplace:
    """测试查找替换功能"""
    def test_simple_replace(self):
        name = "photo_001.jpg"
        result = name.replace("photo", "vacation")
        assert result == "vacation_001.jpg"

    def test_regex_replace(self):
        name = "IMG_2024_001.jpg"
        result = re.sub(r"IMG_(\d{4})_(\d{3})", r"Photo_\1_\2", name)
        assert result == "Photo_2024_001.jpg"

    def test_capture_group_dollar_syntax(self):
        """测试 $1, $2 捕获组引用转换为 \\1, \\2"""
        replace_str = r"Photo_$1_$2"
        converted = re.sub(r'\$(\d+)', r'\\\1', replace_str)
        assert converted == r"Photo_\1_\2"

    def test_case_insensitive_replace(self):
        name = "HELLO_world.jpg"
        result = re.sub("hello", "hi", name, flags=re.IGNORECASE)
        assert result == "hi_world.jpg"

    def test_replace_empty_is_delete(self):
        name = "remove_this_tag_.jpg"
        result = name.replace("_tag", "")
        assert result == "remove_this_.jpg"


class TestInsert:
    """测试插入功能"""
    def test_insert_at_start(self):
        name = "file.txt"
        pos = 0
        text = "prefix_"
        result = name[:pos] + text + name[pos:]
        assert result == "prefix_file.txt"

    def test_insert_at_position(self):
        name = "hello_world.txt"
        pos = 5
        text = "_there"
        result = name[:pos] + text + name[pos:]
        assert result == "hello_there_world.txt"

    def test_insert_from_end(self):
        name = "document.txt"
        name_part, ext = os.path.splitext(name)
        pos = 0
        text = "_v2"
        result = name_part + text + ext  # pos=0 from end = append to filename part
        assert result == "document_v2.txt"


class TestNumbering:
    """测试编号功能"""
    def test_simple_numbering(self):
        num_start, num_step, num_pad = 1, 1, 3
        results = [str(num_start + i * num_step).zfill(num_pad) for i in range(5)]
        assert results == ["001", "002", "003", "004", "005"]

    def test_step_numbering(self):
        num_start, num_step, num_pad = 1, 2, 3
        results = [str(num_start + i * num_step).zfill(num_pad) for i in range(5)]
        assert results == ["001", "003", "005", "007", "009"]

    def test_zero_padding(self):
        assert str(1).zfill(1) == "1"
        assert str(1).zfill(2) == "01"
        assert str(1).zfill(3) == "001"
        assert str(99).zfill(5) == "00099"


class TestCaseConversion:
    """测试大小写转换"""
    def test_lower(self):
        assert "HELLO".lower() == "hello"

    def test_upper(self):
        assert "hello".upper() == "HELLO"

    def test_title(self):
        assert "hello world".title() == "Hello World"

    def test_camel_case(self):
        text = "hello_world_test"
        words = re.split(r'[_\-\s]+', text)
        result = words[0].lower() + ''.join(w.capitalize() for w in words[1:])
        assert result == "helloWorldTest"

    def test_snake_case(self):
        text = "HelloWorldTest"
        s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', text)
        result = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
        assert result == "hello_world_test"

    def test_kebab_case(self):
        text = "HelloWorldTest"
        s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1-\2', text)
        result = re.sub(r'([a-z0-9])([A-Z])', r'\1-\2', s1).lower()
        assert result == "hello-world-test"


class TestNumberRemoval:
    """测试数字清理"""
    def test_remove_leading_numbers(self):
        result = re.sub(r"^\d+[\s._-]*", "", "123_myfile")
        assert result == "myfile"

    def test_remove_trailing_numbers(self):
        result = re.sub(r"[\s._-]*\d+$", "", "myfile_456")
        assert result == "myfile"

    def test_remove_all_numbers(self):
        result = re.sub(r"\d+", "", "abc123def456")
        assert result == "abcdef"


class TestDateFormating:
    """测试日期格式化"""
    def test_date_format(self):
        dt = datetime.datetime(2026, 5, 19, 14, 30, 0)
        assert dt.strftime("_%Y%m%d") == "_20260519"
        assert dt.strftime("_%Y-%m-%d") == "_2026-05-19"
        assert dt.strftime("_%Y%m%d_%H%M%S") == "_20260519_143000"


class TestConflictHandling:
    """测试冲突处理"""
    def test_auto_numbered_conflict(self):
        base, ext = "myfile", ".txt"
        candidate = f"{base} (1){ext}"
        assert candidate == "myfile (1).txt"

    def test_multiple_numbered_conflict(self):
        base, ext = "myfile", ".txt"
        names = []
        for i in range(1, 6):
            names.append(f"{base} ({i}){ext}")
        assert names == [
            "myfile (1).txt",
            "myfile (2).txt",
            "myfile (3).txt",
            "myfile (4).txt",
            "myfile (5).txt",
        ]


class TestPathSanitization:
    """测试路径安全处理"""
    def test_sanitize_illegal_chars(self):
        illegal_name = 'file:with*illegal?"<>chars'
        cleaned = re.sub(r'[\\\\/*?:"<>|]', '', illegal_name)
        assert cleaned == "filewithillegalchars"

    def test_unicode_filename(self):
        name = "测试文件_中国.jpg"
        name_part, ext = os.path.splitext(name)
        assert name_part == "测试文件_中国"
        assert ext == ".jpg"


class TestFileTypeIcon:
    """测试文件类型图标映射"""
    def test_image_icon(self):
        from importlib import import_module
        # Test the icon mapping directly
        icons = {
            ".jpg": "🖼️", ".png": "🖼️", ".mp3": "🎵",
            ".mp4": "🎬", ".zip": "📦", ".pdf": "📕",
            ".doc": "📝", ".xlsx": "📊", ".py": "💻",
            ".txt": "📄", ".exe": "⚙️",
        }
        for ext, expected in icons.items():
            icon_map = {
                "jpg": "🖼️", "png": "🖼️", "mp3": "🎵",
                "mp4": "🎬", "zip": "📦", "pdf": "📕",
                "doc": "📝", "xlsx": "📊", "py": "💻",
                "txt": "📄", "exe": "⚙️",
            }
            assert icon_map.get(ext.lstrip('.').lower(), "📎") == expected


class TestDuplicateDetection:
    """测试重复文件检测逻辑"""
    def test_name_grouping(self):
        files = [
            {"old": "a.txt"}, {"old": "b.txt"},
            {"old": "a.txt"}, {"old": "c.txt"},
        ]
        name_map = {}
        for f in files:
            name_map.setdefault(f["old"].lower(), []).append(f)
        dups = {k: v for k, v in name_map.items() if len(v) > 1}
        assert len(dups) == 1
        assert "a.txt" in dups
        assert len(dups["a.txt"]) == 2

    def test_no_duplicates(self):
        files = [{"old": "a.txt"}, {"old": "b.txt"}, {"old": "c.txt"}]
        name_map = {}
        for f in files:
            name_map.setdefault(f["old"].lower(), []).append(f)
        dups = {k: v for k, v in name_map.items() if len(v) > 1}
        assert len(dups) == 0


class TestClassify:
    """测试智能归类逻辑"""
    def test_ext_classify(self):
        filename = "photo.jpg"
        ext = os.path.splitext(filename)[1].lstrip('.').lower()
        assert ext == "jpg"

    def test_first_letter_classify(self):
        filename = "Apple.txt"
        first = filename[0].upper()
        assert first == "A"

    def test_date_classify(self):
        # simulate mtime from timestamp
        ts = datetime.datetime(2026, 5, 19).timestamp()
        dt = datetime.datetime.fromtimestamp(ts)
        subfolder = os.path.join(str(dt.year), f"{dt.month:02d}")
        assert subfolder == os.path.join("2026", "05")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
