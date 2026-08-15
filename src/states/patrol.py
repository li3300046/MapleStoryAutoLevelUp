import time

# Local import
from src.states.base_state import State
from src.utils.logger import logger

class PatrolState(State):
    def __init__(self, name, bot):
        super().__init__(name, bot)
        self.bot = bot
        self.is_patrol_to_left = True # Patrol direction flag
        self.patrol_turn_point_cnt = 0 # Patrol tuning back counter
        self.t_last_direction_change = time.time()
        self.origin_minimap_x = None

    def on_enter(self):
        # A new patrol run establishes a new origin after the first reliable
        # player coordinate is detected on the minimap.
        self.origin_minimap_x = None
        self.patrol_turn_point_cnt = 0
        self.t_last_direction_change = time.time()

    def on_exit(self):
        pass

    def check_transitions(self):
        return None

    def get_start_x_boundary(self):
        """Return current/left/right minimap X values when they are reliable."""
        patrol_cfg = self.bot.cfg["patrol"]
        if not patrol_cfg.get("use_start_x_range", False):
            return None

        # Both flags describe the current frame. Do not establish an origin or
        # turn on stale minimap data when the minimap/player dot is unavailable.
        if not self.bot.diag_minimap_found or \
                not self.bot.diag_minimap_player_found:
            return None

        current_x = self.bot.loc_player_minimap[0]
        if self.origin_minimap_x is None:
            self.origin_minimap_x = current_x
            logger.info(
                "[PatrolState] Set startup minimap X origin to "
                f"{self.origin_minimap_x}")

        configured_range = patrol_cfg.get("start_x_range", [30, 30])
        if isinstance(configured_range, (int, float)):
            left_range = right_range = max(0, configured_range)
        elif len(configured_range) >= 2:
            left_range = max(0, configured_range[0])
            right_range = max(0, configured_range[1])
        else:
            return None

        return (
            current_x,
            self.origin_minimap_x - left_range,
            self.origin_minimap_x + right_range,
        )

    def on_frame(self):
        # Patrol mode uses one-frame vertical/action commands. Reset them so a
        # previous jump-down or attack is not held indefinitely.
        self.bot.cmd_move_y = "none"
        self.bot.cmd_action = "none"

        x, _ = self.bot.loc_player
        _, w = self.bot.img_frame.shape[:2]
        loc_player_ratio = float(x)/float(w)
        left_ratio, right_ratio = self.bot.cfg["patrol"]["range"]

        start_x_boundary = self.get_start_x_boundary()
        if start_x_boundary is not None:
            current_x, left_x, right_x = start_x_boundary
            if self.is_patrol_to_left and current_x <= left_x:
                self.patrol_turn_point_cnt += 1
            elif (not self.is_patrol_to_left) and current_x >= right_x:
                self.patrol_turn_point_cnt += 1
            else:
                self.patrol_turn_point_cnt = 0
        # Fall back to the original screen-relative boundary until a reliable
        # minimap coordinate is available, or when startup range is disabled.
        elif not self.bot.has_valid_player_screen_location:
            self.patrol_turn_point_cnt = 0
        elif self.is_patrol_to_left and loc_player_ratio <= left_ratio:
            self.patrol_turn_point_cnt += 1
        elif (not self.is_patrol_to_left) and loc_player_ratio >= right_ratio:
            self.patrol_turn_point_cnt += 1
        else:
            self.patrol_turn_point_cnt = 0

        if self.patrol_turn_point_cnt > self.bot.cfg["patrol"]["turn_point_thres"]:
            self.is_patrol_to_left = not self.is_patrol_to_left
            self.patrol_turn_point_cnt = 0
            self.t_last_direction_change = time.time()
        elif time.time() - self.t_last_direction_change > \
                self.bot.cfg["patrol"].get("direction_change_interval", 8.0):
            self.is_patrol_to_left = not self.is_patrol_to_left
            self.t_last_direction_change = time.time()

        # Update cmd_move_x
        if self.is_patrol_to_left:
            self.bot.cmd_move_x = "left"
        else:
            self.bot.cmd_move_x = "right"

        # Monster distance/direction is relative to the player. If the player
        # nametag is hidden by the overlapping pet, prefer the pet center over
        # the fixed camera estimate. Neither fallback is considered precise
        # enough for boundary/stuck checks.
        if not self.bot.has_valid_player_screen_location:
            pet_location = self.bot.get_player_location_by_pet()
            if pet_location is not None:
                self.bot.loc_player = pet_location
                self.bot.diag_player_screen_source = "pet_estimate"
            else:
                fallback_x, fallback_y = self.bot.cfg["patrol"].get(
                    "fallback_player_position_ratio", [0.505, 0.55])
                playable_height = min(
                    self.bot.img_frame.shape[0],
                    self.bot.cfg["ui_coords"]["ui_y_start"])
                self.bot.loc_player = (
                    int(self.bot.img_frame.shape[1] * fallback_x),
                    int(playable_height * fallback_y))
                self.bot.diag_player_screen_source = "patrol_estimate"

        self.bot.update_cmd_by_mob_detection()

        # Optional blind periodic attack. Keep disabled when attacks consume
        # items/resources; confirmed monster detection still attacks normally.
        if self.bot.cfg["patrol"].get("attack_without_target", False) and \
            time.time() - self.bot.t_last_attack > \
            self.bot.cfg["patrol"]["patrol_attack_interval"]:
            self.bot.cmd_action = "attack"
            self.bot.t_last_attack = time.time()

        # If stuck, immediately reverse and jump away from the obstacle.
        if self.bot.has_valid_player_screen_location and \
                self.bot.is_player_stuck():
            self.is_patrol_to_left = not self.is_patrol_to_left
            self.t_last_direction_change = time.time()
            self.bot.cmd_move_x = "left" if self.is_patrol_to_left else "right"
            self.bot.cmd_move_y = "none"
            self.bot.cmd_action = "jump"

        # send command to keyboard controller
        self.bot.kb.set_command(self.bot.cmd_move_x + ' ' + \
                                self.bot.cmd_move_y + ' ' + \
                                self.bot.cmd_action)
