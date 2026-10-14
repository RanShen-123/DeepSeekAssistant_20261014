"""读取配置并原子保存，所有路径均相对于项目目录。"""
from pathlib import Path
import os
import tempfile
import yaml

PROJECT_DIR = Path(__file__).resolve().parent.parent


def validate_region(region: object) -> dict:
    if not isinstance(region, dict):
        raise ValueError("请先设置题目区域。")
    keys = ("x", "y", "width", "height")
    if any(type(region.get(k)) is not int for k in keys):
        raise ValueError("题目区域配置格式错误，请重新框选。")
    if region["width"] < 10 or region["height"] < 10:
        raise ValueError("题目区域太小，请重新框选。")
    return {k: region[k] for k in keys}


class ConfigStore:
    def __init__(self, path: Path = PROJECT_DIR / "config.yaml") -> None:
        self.path = Path(path)

    def load(self) -> dict:
        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        except (OSError, yaml.YAMLError) as exc:
            raise ValueError("无法读取 config.yaml，请检查文件权限和 YAML 格式。") from exc
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("config.yaml 顶层必须是键值配置。")
        return {"api_key": "", "base_url": "https://api.deepseek.com",
                "model": "deepseek-flash", "screen_region": None, "timeout": 90,
                **data}

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             suffix=".tmp", delete=False) as file:
                name = file.name
                yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False)
                file.flush()
                os.fsync(file.fileno())
            os.replace(name, self.path)
        finally:
            if name and os.path.exists(name):
                os.unlink(name)

    def set_region(self, region: dict) -> None:
        data = self.load()
        data["screen_region"] = validate_region(region)
        self.save(data)
