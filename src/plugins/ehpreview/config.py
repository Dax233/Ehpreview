from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    E_COOKIE: str = ''
    image_dir: str = '.\\src\\data\\ehdownloader\\cache'
    src_dir: str = './src/data/ehdownloader'
    P_COOKIE: str = ''