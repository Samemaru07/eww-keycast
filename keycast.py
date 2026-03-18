#!/usr/bin/env python3

import asyncio
import subprocess
import json
import evdev
from evdev import InputDevice, ecodes, KeyEvent

# --- 設定 ---
DISPLAY_DURATION = 2.0  # 表示時間（秒）
EWW_CMD = "/usr/bin/eww"

# 修飾キーのマッピング
MODIFIER_KEYS = {
    "KEY_LEFTCTRL": "󰘴",
    "KEY_RIGHTCTRL": "󰘴",
    "KEY_LEFTSHIFT": "󰘶",
    "KEY_RIGHTSHIFT": "󰘶",
    "KEY_LEFTALT": "󰘵",
    "KEY_RIGHTALT": "󰘵",
    "KEY_LEFTMETA": "󰣇",
    "KEY_RIGHTMETA": "󰣇",
}

# 特殊キーの表示名
SPECIAL_KEYS = {
    "KEY_SPACE": "󱁐",
    "KEY_ENTER": "󰌑",
    "KEY_TAB": "",
    "KEY_BACKSPACE": "⌫",
    "KEY_ESC": "󱊷",
    "KEY_DELETE": "󰆴",
    "KEY_INSERT": "Ins",
    "KEY_HOME": "Home",
    "KEY_END": "End",
    "KEY_PAGEUP": "PgUp",
    "KEY_PAGEDOWN": "PgDn",
    "KEY_UP": "↑",
    "KEY_DOWN": "↓",
    "KEY_LEFT": "←",
    "KEY_RIGHT": "→",
    "KEY_F1": "F1",
    "KEY_F2": "F2",
    "KEY_F3": "F3",
    "KEY_F4": "F4",
    "KEY_F5": "F5",
    "KEY_F6": "F6",
    "KEY_F7": "F7",
    "KEY_F8": "F8",
    "KEY_F9": "F9",
    "KEY_F10": "F10",
    "KEY_F11": "F11",
    "KEY_F12": "F12",
    "KEY_CAPSLOCK": "Caps",
    "KEY_SYSRQ": "PrtSc",
    "KEY_SCROLLLOCK": "ScrLk",
    "KEY_PAUSE": "Pause",
    "KEY_NUMLOCK": "NumLk",
    "KEY_GRAVE": "`",
    "KEY_MINUS": "-",
    "KEY_EQUAL": "=",
    "KEY_LEFTBRACE": "[",
    "KEY_RIGHTBRACE": "]",
    "KEY_BACKSLASH": "\\",
    "KEY_SEMICOLON": ";",
    "KEY_APOSTROPHE": "'",
    "KEY_COMMA": ",",
    "KEY_DOT": ".",
    "KEY_SLASH": "/",
}

# 現在押されている修飾キー
active_modifiers: set[str] = set()
hide_task: asyncio.Task | None = None


def get_focused_monitor() -> int:
    """フォーカス中のモニターのインデックスを返す"""
    try:
        result = subprocess.run(
            ["hyprctl", "monitors", "-j"], capture_output=True, text=True
        )
        monitors = json.loads(result.stdout)
        for i, m in enumerate(monitors):
            if m.get("focused"):
                return i
    except Exception:
        pass
    return 0


def keyname(key_str: str) -> str | None:
    if key_str in MODIFIER_KEYS:
        return None
    if key_str in SPECIAL_KEYS:
        return SPECIAL_KEYS[key_str]
    if key_str.startswith("KEY_"):
        rest = key_str[4:]
        if len(rest) == 1:
            if "Shift" in active_modifiers:
                return rest.upper()
            else:
                return rest.lower()
    return None


def build_display(key: str) -> str:
    """修飾キー+メインキーの表示文字列を組み立てる"""
    parts = []
    for mod in ["󰘴", "󰣇", "󰘵", "󰘶"]:
        if mod in active_modifiers:
            parts.append(mod)
    main = keyname(key)
    if main:
        parts.append(main)
    return "+".join(parts)


async def hide_after(delay: float):
    await asyncio.sleep(delay)
    subprocess.run([EWW_CMD, "update", "keycast-text="])


current_text = ""
MAX_LENGTH = 20
SPECIAL_VALUES = set(SPECIAL_KEYS.values())


last_key_was_special = False


async def show_key(text: str):
    global hide_task, current_text, last_key_was_special

    if hide_task and not hide_task.done():
        hide_task.cancel()
        separator = (
            " "
            if len(text) > 1 or text in SPECIAL_VALUES or last_key_was_special
            else ""
        )
        new_text = current_text + separator + text
        if len(new_text) > MAX_LENGTH:
            current_text = text
        else:
            current_text = new_text
    else:
        current_text = text

    last_key_was_special = len(text) > 1 or text in SPECIAL_VALUES
    monitor = get_focused_monitor()
    subprocess.run([EWW_CMD, "update", f"keycast-text={current_text}"])
    hide_task = asyncio.create_task(hide_after(DISPLAY_DURATION))


def find_keyboards() -> list[InputDevice]:
    """キーボードデバイスを自動検出"""
    devices = []
    for path in evdev.list_devices():
        try:
            dev = InputDevice(path)
            caps = dev.capabilities()
            if ecodes.EV_KEY in caps:
                keys = caps[ecodes.EV_KEY]
                # KEY_A(30) と KEY_SPACE(57) があればキーボードと判断
                if ecodes.KEY_A in keys and ecodes.KEY_SPACE in keys:
                    devices.append(dev)
        except Exception:
            pass
    return devices


async def watch_device(dev: InputDevice):
    async for event in dev.async_read_loop():
        if event.type != ecodes.EV_KEY:
            continue
        key_event = KeyEvent(event)
        key_str = evdev.ecodes.KEY.get(event.code, f"KEY_{event.code}")
        if isinstance(key_str, list):
            key_str = key_str[0]
        if isinstance(key_str, tuple):
            key_str = key_str[0]

        if key_event.keystate == KeyEvent.key_down:
            if key_str in MODIFIER_KEYS:
                active_modifiers.add(MODIFIER_KEYS[key_str])
            else:
                display = build_display(key_str)
                if display:
                    print(f"display: {display}")
                    await show_key(display)

        elif key_event.keystate == KeyEvent.key_up:
            if key_str in MODIFIER_KEYS:
                active_modifiers.discard(MODIFIER_KEYS[key_str])


async def main():
    keyboards = find_keyboards()
    if not keyboards:
        print("キーボードデバイスが見つかりませんでした")
        return

    monitor = get_focused_monitor()
    subprocess.run([EWW_CMD, "open", "keycast", "--screen", str(monitor)])

    print(f"監視中: {[dev.name for dev in keyboards]}")
    try:
        await asyncio.gather(*[watch_device(dev) for dev in keyboards])
    except asyncio.CancelledError:
        pass
    finally:
        subprocess.run([EWW_CMD, "close", "keycast"])


if __name__ == "__main__":
    asyncio.run(main())
