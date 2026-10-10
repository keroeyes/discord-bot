"""Local request accounting; never store prompts, images or credentials."""
import json
import math
import os
from pathlib import Path
import sqlite3
import time
from datetime import datetime, timezone, timedelta


class ImageAccess:
    def __init__(self, cooldown=30, daily_limit=20, allowed_users=(), allowed_guilds=(),
                 allow_dm=True, state_path=':memory:', clock=time.time):
        if isinstance(cooldown, bool) or not isinstance(cooldown, (int, float)) or not math.isfinite(cooldown) or cooldown < 0:
            raise ValueError('Invalid image cooldown')
        if isinstance(daily_limit, bool) or not isinstance(daily_limit, int) or daily_limit < 0:
            raise ValueError('Invalid image daily limit')
        for ids in (allowed_users, allowed_guilds):
            if not isinstance(ids, (list, tuple, set, frozenset)) or any(type(i) is not int or i <= 0 for i in ids):
                raise ValueError('Invalid image allow list')
        if type(allow_dm) is not bool:
            raise ValueError('Invalid image DM setting')
        self.cooldown, self.daily_limit = cooldown, daily_limit
        self.allowed_users, self.allowed_guilds = set(allowed_users), set(allowed_guilds)
        self.allow_dm, self.clock = allow_dm, clock
        self.db = sqlite3.connect(state_path)
        self.db.execute('CREATE TABLE IF NOT EXISTS usage (user_id TEXT PRIMARY KEY, day TEXT NOT NULL, count INTEGER NOT NULL, next_at REAL NOT NULL)')

    def authorized(self, user_id, guild_id):
        # Configured dimensions are ANDed; owner has no exemption.
        return (not self.allowed_users or user_id in self.allowed_users) and (
            self.allow_dm if guild_id is None else not self.allowed_guilds or guild_id in self.allowed_guilds)

    def reserve(self, user_id):
        """Atomically count an accepted attempt; failures still consume budget."""
        now = self.clock()
        day = datetime.fromtimestamp(now, timezone(timedelta(hours=9))).date().isoformat()
        try:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT day, count, next_at FROM usage WHERE user_id=?', (str(user_id),)).fetchone()
            count = row[1] if row and row[0] == day else 0
            if row and now < row[2]:
                self.db.rollback()
                return 'cooldown', math.ceil(row[2] - now)
            if self.daily_limit and count >= self.daily_limit:
                self.db.rollback()
                return 'daily', 0
            self.db.execute('INSERT OR REPLACE INTO usage VALUES (?, ?, ?, ?)', (str(user_id), day, count + 1, now + self.cooldown))
            self.db.commit()
            return 'ok', 0
        except Exception:
            self.db.rollback()
            raise


def load_access():
    """Optional project JSON supports the Windows startup worker too."""
    path = Path(__file__).with_name('image_access_config.json')
    config = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    keys = {'cooldown', 'daily_limit', 'allowed_users', 'allowed_guilds', 'allow_dm'}
    if not isinstance(config, dict) or set(config) - keys:
        raise ValueError('Invalid image access configuration')
    for key, env in [('cooldown', 'IMAGE_USER_COOLDOWN_SECONDS'), ('daily_limit', 'IMAGE_DAILY_LIMIT')]:
        if env in os.environ:
            config[key] = int(os.environ[env])
    for key, env in [('allowed_users', 'IMAGE_ALLOWED_USER_IDS'), ('allowed_guilds', 'IMAGE_ALLOWED_GUILD_IDS')]:
        if env in os.environ:
            config[key] = [int(i.strip()) for i in os.environ[env].split(',') if i.strip()]
    if 'IMAGE_ALLOW_DM' in os.environ:
        value = os.environ['IMAGE_ALLOW_DM'].lower()
        if value not in ('true', 'false'):
            raise ValueError('Invalid image DM setting')
        config['allow_dm'] = value == 'true'
    state = Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'KeroroLocalImages'
    state.mkdir(parents=True, exist_ok=True)
    return ImageAccess(**config, state_path=str(state / 'image_usage.sqlite3'))
