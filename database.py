# plugins_human/eh_preview/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.plugin import PROJECT_ROOT

from .models import Base

# 定义插件专属的数据库文件路径
# 我们把它放在 data 目录下，和其他插件数据放在一起，但用插件名做区分
PLUGIN_DATA_DIR = PROJECT_ROOT / "data" / "eh_preview"
PLUGIN_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = PLUGIN_DATA_DIR / "cache.db"

# 创建只属于这个插件的数据库引擎和会话工厂
engine = create_engine(f"sqlite:///{DB_PATH.resolve()}")
SessionFactory = sessionmaker(bind=engine)


def init_database() -> None:
    """初始化插件的数据库和表."""
    Base.metadata.create_all(engine)
