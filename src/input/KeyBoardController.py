'''
KeyBoardController
Simulate user keyboard input to control character in the game 
'''
# Standard Import
import threading
import time
import ctypes
from ctypes import wintypes

# Library import
import pyautogui
from pynput import keyboard

# Local import
from src.utils.logger import logger
from src.utils.common import is_mac

if is_mac():
    import Quartz
else:
    import pygetwindow as gw

    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008
    MAPVK_VK_TO_VSC = 0

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", wintypes.WPARAM),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", wintypes.WPARAM),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT),
                    ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("union",)
        _fields_ = [("type", wintypes.DWORD), ("union", INPUTUNION)]

    USER32 = ctypes.WinDLL("user32", use_last_error=True)
    USER32.SendInput.argtypes = (
        wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    USER32.SendInput.restype = wintypes.UINT
    USER32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
    USER32.MapVirtualKeyW.restype = wintypes.UINT
    USER32.VkKeyScanW.argtypes = (wintypes.WCHAR,)
    USER32.VkKeyScanW.restype = ctypes.c_short

    SPECIAL_VIRTUAL_KEYS = {
        "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
        "shift": 0x10, "ctrl": 0x11, "control": 0x11, "alt": 0x12,
        "esc": 0x1B, "escape": 0x1B, "space": 0x20,
        "pageup": 0x21, "pagedown": 0x22, "end": 0x23, "home": 0x24,
        "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
        "insert": 0x2D, "delete": 0x2E, "del": 0x2E,
    }
    SPECIAL_VIRTUAL_KEYS.update({f"f{i}": 0x6F + i for i in range(1, 13)})
    EXTENDED_KEYS = {
        "pageup", "pagedown", "end", "home", "left", "up", "right",
        "down", "insert", "delete", "del"
    }

pyautogui.PAUSE = 0  # remove delay

def send_scan_code(key, is_key_up=False):
    """Send a Windows keyboard event using hardware scan-code semantics."""
    key_name = str(key).lower()
    if key_name in SPECIAL_VIRTUAL_KEYS:
        virtual_key = SPECIAL_VIRTUAL_KEYS[key_name]
    elif len(key_name) == 1:
        virtual_key = USER32.VkKeyScanW(key_name) & 0xFF
    else:
        raise ValueError(f"Unsupported key for SendInput: {key}")

    scan_code = USER32.MapVirtualKeyW(virtual_key, MAPVK_VK_TO_VSC)
    flags = KEYEVENTF_SCANCODE
    if key_name in EXTENDED_KEYS:
        flags |= KEYEVENTF_EXTENDEDKEY
    if is_key_up:
        flags |= KEYEVENTF_KEYUP

    event = INPUT(type=1, ki=KEYBDINPUT(
        wVk=0, wScan=scan_code, dwFlags=flags, time=0, dwExtraInfo=0))
    sent = USER32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
    if sent != 1:
        error_code = ctypes.get_last_error()
        raise OSError(error_code, f"SendInput failed for key: {key}")

def key_down(key):
    '''
    Press key down
    '''
    try:
        if is_mac():
            pyautogui.keyDown(key)
        else:
            send_scan_code(key, is_key_up=False)
    except pyautogui.FailSafeException:
        logger.warning("[key_down] pyautogui failsafe triggered during key_down.")
        recover_mouse()
    except Exception as e:
        logger.error(f"[key_down] {e}")

def key_up(key):
    '''
    Release key
    '''
    try:
        if is_mac():
            pyautogui.keyUp(key)
        else:
            send_scan_code(key, is_key_up=True)
    except pyautogui.FailSafeException:
        logger.warning("[key_up] pyautogui failsafe triggered during key_up.")
        recover_mouse()
    except Exception as e:
        logger.error(f"[key_up] {e}")

def recover_mouse():
    '''
    Move mouse back to center to avoid pyautogui failsafe
    '''
    pyautogui.FAILSAFE = False # Temp disasble failsafe to avoid nested exception

    screen_w, screen_h = pyautogui.size()
    pyautogui.moveTo(screen_w // 2, screen_h // 2)
    time.sleep(0.2) # Give it a moment to "cool down"

    pyautogui.FAILSAFE = True # Recover failsafe

def press_key(key, duration=0.05):
    '''
    Simulates a key press for a specified duration
    '''
    if key:
        key_down(key)
        time.sleep(duration)
        key_up(key)

class KeyBoardController():
    '''
    KeyBoardController
    '''
    def __init__(self, cfg):
        self.cfg = cfg
        self.cmd_action = "none"
        self.cmd_up_down = "none"
        self.cmd_left_right = "none"
        self.cmd_up_down_last = ""
        self.cmd_left_right_last = ""
        self.window_title = cfg["game_window"]["title"]
        self.fps = 0 # Frame per seconds
        # Timer
        self.t_last_up = 0.0
        self.t_last_down = 0.0
        self.t_last_toggle = 0.0
        self.t_last_screenshot = 0.0
        self.t_last_jump_down = 0.0
        self.t_last_run = time.time()
        self.t_last_diagnostic = 0.0
        self.t_last_skill = 0.0 # Last time character perform action(attack, cast spell, ...)
        self.t_last_buff_cast = [0] * len(self.cfg["buff_skill"]["keys"]) # Last time cast buff skill
        # Flags
        self.is_enable = True
        self.is_need_force_heal = False
        self.is_terminated = False
        self.active_window_title = ""
        self.window_check_error = ""
        self.last_keyboard_state = None
        # Parameters
        self.debounce_interval = self.cfg["system"]["key_debounce_interval"]
        self.fps_limit = self.cfg["system"]["fps_limit_keyboard_controller"]

        # use 'ctrl', 'alt' for mac, because it's hard to get around
        # macOS's security settings
        if is_mac():
            self.toggle_key = keyboard.Key.ctrl
            self.screenshot_key = keyboard.Key.alt
            self.terminate_key = keyboard.Key.esc
        else:
            self.toggle_key = keyboard.Key.f1
            self.screenshot_key = keyboard.Key.f2
            self.terminate_key = keyboard.Key.f12

        # set up attack key
        self.attack_key = ""
        if cfg["bot"]["attack"] == "aoe_skill":
            self.attack_key = cfg["key"]["aoe_skill"]
        elif cfg["bot"]["attack"] == "directional":
            self.attack_key = cfg["key"]["directional_attack"]
        else:
            raise ValueError(f"Unexpected attack type: {cfg['bot']['attack']}")

        # Start keyboard control thread
        threading.Thread(target=self.run, daemon=True).start()

        backend = "PyAutoGUI" if is_mac() else "Windows SendInput scan codes"
        logger.info(f"[KeyBoardController] Init done; input_backend={backend}")

    def toggle_enable(self):
        '''
        toggle_enable
        '''
        self.is_enable = not self.is_enable
        logger.info(f"Player pressed F1, is_enable:{self.is_enable}")

        # Make sure all key are released
        self.release_all_key()

    def disable(self):
        '''
        disable keyboard controlller
        '''
        self.is_enable = False

    def enable(self):
        '''
        enable keyboard controlller
        '''
        self.is_enable = True

    def set_command(self, new_command):
        '''
        Set keyboard command
        '''
        command = tuple(new_command.split())
        previous = (self.cmd_left_right, self.cmd_up_down, self.cmd_action)
        if command != previous:
            logger.info(f"[CommandPipeline] requested={' '.join(command)}")
        self.cmd_left_right, self.cmd_up_down, self.cmd_action = command

    def is_game_window_active(self):
        '''
        Check if the game window is currently the active (foreground) window.

        Returns:
        - True
        - False
        '''
        if is_mac():
            active_window = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID
            )
            for window in active_window:
                window_name = window.get(Quartz.kCGWindowName, '')
                if window_name and self.window_title in window_name:
                    return True
            return False
        else:
            try:
                active_window = gw.getActiveWindow()
                if not active_window:
                    self.active_window_title = ""
                    return False
                self.active_window_title = active_window.title or ""
                self.window_check_error = ""
                return self.window_title in self.active_window_title
            except Exception as e:
                self.window_check_error = str(e)
                return False

    def log_keyboard_diagnostic(self, game_window_active):
        """Log why input is executed or skipped without flooding the console."""
        now = time.time()
        state = (self.is_enable, game_window_active, self.active_window_title,
                 self.cmd_left_right, self.cmd_up_down, self.cmd_action,
                 self.window_check_error)
        if state == self.last_keyboard_state and now - self.t_last_diagnostic < 2.0:
            return

        status = "executing" if self.is_enable and game_window_active else "skipped"
        reason = "ready"
        if not self.is_enable:
            reason = "controller disabled"
        elif not game_window_active:
            reason = "game window is not foreground"
        if self.window_check_error:
            reason += f"; window check error={self.window_check_error}"

        logger.info(
            f"[KeyboardDiagnostic] status={status}, reason={reason}, "
            f"active_window={self.active_window_title!r}, "
            f"expected_window_token={self.window_title!r}, "
            f"command={self.cmd_left_right} {self.cmd_up_down} {self.cmd_action}"
        )
        self.last_keyboard_state = state
        self.t_last_diagnostic = now

    def release_all_key(self):
        '''
        Release all key
        '''
        key_up("left")
        key_up("right")
        key_up("up")
        key_up("down")
        # Also release attack keys to stop any ongoing attacks
        key_up(self.attack_key)

    def limit_fps(self):
        '''
        Limit FPS
        '''
        # If the loop finished early, sleep to maintain target FPS
        target_duration = 1.0 / self.fps_limit  # seconds per frame
        frame_duration = time.time() - self.t_last_run
        if frame_duration < target_duration:
            time.sleep(target_duration - frame_duration)

        # Update FPS
        self.fps = round(1.0 / (time.time() - self.t_last_run))
        self.t_last_run = time.time()
        # logger.info(f"FPS = {self.fps}")

    def run(self):
        '''
        run
        '''
        while not self.is_terminated:
            # Check if game window is active
            game_window_active = self.is_game_window_active()
            self.log_keyboard_diagnostic(game_window_active)
            if not self.is_enable or not game_window_active:
                self.limit_fps()
                continue

            # Buff skill
            for i, buff_skill_key in enumerate(self.cfg["buff_skill"]["keys"]):
                cooldown = self.cfg["buff_skill"]["cooldown"][i]
                if time.time() - self.t_last_buff_cast[i] >= cooldown and \
                    time.time() - self.t_last_skill > self.cfg["buff_skill"]["action_cooldown"]:
                    press_key(buff_skill_key)
                    logger.info(f"[Buff] Press buff skill key: '{buff_skill_key}' (cooldown: {cooldown}s)")
                    # Reset timers
                    self.t_last_buff_cast[i] = time.time()
                    self.t_last_skill = time.time()
                    break

            # Force Heal
            if self.is_need_force_heal:
                self.cmd_action = "add_hp"

            ##########################
            ### Left-Right Command ###
            ##########################
            direction_changed = self.cmd_left_right in ("left", "right") and \
                self.cmd_left_right != self.cmd_left_right_last
            if self.cmd_left_right == "left":
                key_up("right")
                key_down("left")
            elif self.cmd_left_right == "right":
                key_up("left")
                key_down("right")
            elif self.cmd_left_right == "stop":
                key_up("left")
                key_up("right")
            elif self.cmd_left_right == "none":
                if self.cmd_left_right_last != "none":
                    key_up("left")
                    key_up("right")
            else:
                logger.error("[KeyBoardController] Unsupported left-right command: "
                             f"{self.cmd_left_right}")
            self.cmd_left_right_last = self.cmd_left_right

            #######################
            ### Up-Down Command ###
            #######################
            if self.cmd_up_down == "up":
                key_up("down")
                key_down("up")
            elif self.cmd_up_down == "down":
                key_up("up")
                key_down("down")
            elif self.cmd_up_down == "stop":
                key_up("up")
                key_up("down")
            elif self.cmd_up_down == "none":
                if self.cmd_up_down_last != "none":
                    key_up("up")
                    key_up("down")
            else:
                logger.error("[KeyBoardController] Unsupported up-down command: "
                             f"{self.cmd_up_down}")
            self.cmd_up_down_last = self.cmd_up_down

            ######################
            ### Action Command ###
            ######################
            if self.cmd_action == "jump":
                press_key(self.cfg["key"]["jump"])
                self.cmd_action = "none"
            elif self.cmd_action == "teleport":
                press_key(self.cfg["key"]["teleport"])
                self.cmd_action = "none"
            elif self.cmd_action == "attack":
                attack_direction = self.cmd_left_right
                turn_delay = 0.0
                if direction_changed and self.cfg["bot"]["attack"] == "directional":
                    turn_delay = self.cfg["directional_attack"].get(
                        "character_turn_delay", 0.1)
                    time.sleep(turn_delay)
                if self.cmd_left_right == attack_direction:
                    # Direction was held long enough to turn the character.
                    # Release it before attacking so the character does not
                    # walk through a close target during the attack animation.
                    if self.cfg["bot"]["attack"] == "directional":
                        key_up("left")
                        key_up("right")
                    press_key(self.attack_key)
                    self.t_last_skill = time.time()
                    logger.info(
                        f"[AttackInput] direction={attack_direction}, "
                        f"turned={direction_changed}, "
                        f"turn_delay={turn_delay:.3f}s, key={self.attack_key!r}")
                else:
                    logger.info(
                        f"[AttackInput] canceled because direction changed "
                        f"from {attack_direction} to {self.cmd_left_right}")
                if self.cfg["bot"]["attack"] == "directional":
                    self.cmd_left_right = "stop"
                    self.cmd_left_right_last = "stop"
                self.cmd_action = "none"
            elif self.cmd_action == "add_hp":
                press_key(self.cfg["key"]["add_hp"])
                self.cmd_action = "none"  # Reset command
            elif self.cmd_action == "add_mp":
                press_key(self.cfg["key"]["add_mp"])
                self.cmd_action = "none"  # Reset command
            elif self.cmd_action == "goal":
                pass
            elif self.cmd_action == "none":
                pass
            else:
                logger.error("[KeyBoardController] Unsupported action command: "
                             f"{self.cmd_action}")

            self.limit_fps()

        self.release_all_key() # Prevent key keep press down after termination

        logger.info("[KeyBoardController] terminated")
