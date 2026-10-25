"""Configuration lives in config/; migration never overwrites an existing file."""
from pathlib import Path
import os
import time

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = BASE_DIR / 'config'
IMAGES_DIR = BASE_DIR / 'src' / 'images'
SOUNDS_DIR = BASE_DIR / 'src' / 'sounds'
UI_DIR = BASE_DIR / 'src' / 'ui'
CONFIG_NAMES = ('.env', 'keywords.txt', 'models.yaml', 'shortcuts.yaml')


def sound_path(value, filename):
    if not value:
        return SOUNDS_DIR / filename
    normalized = value.replace('\\', '/')
    path = Path(normalized).expanduser()
    if path in (Path('sounds') / filename, Path('../sounds') / filename):
        return SOUNDS_DIR / filename
    if path.is_absolute() and path.parent == BASE_DIR / 'sounds':
        return SOUNDS_DIR / path.name
    return path if path.is_absolute() else BASE_DIR / path


def migrate_config(root=BASE_DIR):
    root = Path(root)
    folder = root / 'config'
    folder.mkdir(parents=True, exist_ok=True)
    for name in CONFIG_NAMES:
        old, new = root / name, folder / name
        if not old.is_file():
            continue
        if new.exists():
            archive = folder / 'legacy'
            archive.mkdir(exist_ok=True)
            new = archive / (name + '.' + str(time.time_ns()))
        os.replace(old, new)
    return folder


def initialize_config(root=BASE_DIR):
    folder = migrate_config(root)
    examples = {'.env': '.env.example', 'keywords.txt': 'keywords.example.txt',
                'models.yaml': 'models.example.yaml', 'shortcuts.yaml': 'shortcuts.example.yaml'}
    for name, example in examples.items():
        target, source = folder / name, folder / example
        if not target.exists() and source.exists():
            # Exclusive creation avoids overwriting configuration from another process.
            try:
                with target.open('xb') as out:
                    out.write(source.read_bytes())
            except FileExistsError:
                pass
    return folder


if __name__ == '__main__':
    initialize_config()
