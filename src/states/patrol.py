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
        self.t_last_patrol_diagnostic = 0.0
        self.last_minimap_x_ratio = None
        self.t_last_minimap_position = 0.0
        self.t_last_minimap_fallback_turn = time.time()

    def log_patrol_diagnostic(
            self, boundary_hit, control_x_ratio, boundary_source,
            reversal_reason="none", turn_elapsed=None):
        """Log the inputs that determine patrol direction and boundaries."""
        now = time.time()
        if reversal_reason == "none" and \
                now - self.t_last_patrol_diagnostic < 2.0:
            return

        frame_w = self.bot.img_frame.shape[1]
        screen_x = self.bot.loc_player[0]
        screen_x_ratio = screen_x / float(frame_w)
        minimap_x = self.bot.loc_player_minimap[0]
        minimap_w = self.bot.img_minimap.shape[1]
        minimap_x_ratio = (
            minimap_x / float(minimap_w) if minimap_w > 0 else -1.0)
        left_ratio, right_ratio = self.bot.cfg["patrol"]["range"]
        direction = "left" if self.is_patrol_to_left else "right"
        elapsed = (
            now - self.t_last_direction_change
            if turn_elapsed is None else turn_elapsed)

        logger.info(
            "[PatrolDiagnostic] "
            f"direction={direction}, reversal_reason={reversal_reason}, "
            f"boundary_hit={boundary_hit}, "
            f"boundary_counter={self.patrol_turn_point_cnt}/"
            f"{self.bot.cfg['patrol']['turn_point_thres']}, "
            f"screen_x={screen_x}, screen_x_ratio={screen_x_ratio:.3f}, "
            f"screen_valid={self.bot.has_valid_player_screen_location}, "
            f"screen_source={self.bot.diag_player_screen_source}, "
            f"configured_range=({left_ratio:.3f},{right_ratio:.3f}), "
            f"boundary_source={boundary_source}, "
            f"control_x_ratio="
            f"{control_x_ratio if control_x_ratio is not None else 'none'}, "
            f"minimap_found={self.bot.diag_minimap_player_found}, "
            f"minimap_x={minimap_x}, minimap_width={minimap_w}, "
            f"minimap_x_ratio={minimap_x_ratio:.3f}, "
            f"seconds_since_turn={elapsed:.2f}, "
            f"timer_limit="
            f"{self.bot.cfg['patrol'].get('direction_change_interval', 8.0):.2f}")
        self.t_last_patrol_diagnostic = now

    def on_enter(self):
        pass

    def on_exit(self):
        pass

    def check_transitions(self):
        return None

    def on_frame(self):
        # Patrol mode uses one-frame vertical/action commands. Reset them so a
        # previous jump-down or attack is not held indefinitely.
        self.bot.cmd_move_y = "none"
        self.bot.cmd_action = "none"

        now = time.time()
        left_ratio, right_ratio = self.bot.cfg["patrol"]["range"]

        # The camera follows the character, so screen X is not a stable map
        # coordinate. Use normalized minimap X for repeatable patrol bounds.
        boundary_source = "none"
        control_x_ratio = None
        if self.bot.diag_minimap_player_found:
            minimap_w = self.bot.img_minimap.shape[1]
            if minimap_w > 0:
                control_x_ratio = self.bot.loc_player_minimap[0] / \
                    float(minimap_w)
                self.last_minimap_x_ratio = control_x_ratio
                self.t_last_minimap_position = now
                boundary_source = "minimap"
        elif self.last_minimap_x_ratio is not None and \
                now - self.t_last_minimap_position <= \
                self.bot.cfg["patrol"].get(
                    "minimap_position_grace_seconds", 2.0):
            control_x_ratio = self.last_minimap_x_ratio
            boundary_source = "minimap_grace"

        boundary_hit = "none"
        if control_x_ratio is None:
            self.patrol_turn_point_cnt = 0
        elif self.is_patrol_to_left and control_x_ratio < left_ratio:
            boundary_hit = "left"
            self.patrol_turn_point_cnt += 1
        elif (not self.is_patrol_to_left) and control_x_ratio > right_ratio:
            boundary_hit = "right"
            self.patrol_turn_point_cnt += 1
        else:
            self.patrol_turn_point_cnt = 0

        reversal_reason = "none"
        turn_elapsed = now - self.t_last_direction_change
        if self.patrol_turn_point_cnt > self.bot.cfg["patrol"]["turn_point_thres"]:
            self.is_patrol_to_left = not self.is_patrol_to_left
            self.patrol_turn_point_cnt = 0
            self.t_last_direction_change = time.time()
            self.t_last_minimap_fallback_turn = now
            reversal_reason = "boundary_confirmed"
        elif control_x_ratio is None and \
                now - max(
                    self.t_last_minimap_position,
                    self.t_last_minimap_fallback_turn) > \
                self.bot.cfg["patrol"].get("direction_change_interval", 8.0):
            self.is_patrol_to_left = not self.is_patrol_to_left
            self.t_last_direction_change = time.time()
            self.t_last_minimap_fallback_turn = now
            reversal_reason = "minimap_lost_timer"

        self.log_patrol_diagnostic(
            boundary_hit, control_x_ratio, boundary_source,
            reversal_reason, turn_elapsed if reversal_reason != "none" else None)

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
            pet_location = None
            if not self.bot.is_current_player_position_out_of_range:
                pet_location = self.bot.get_player_location_by_pet()
            if self.bot.is_player_position_in_valid_range(pet_location):
                self.bot.loc_player = pet_location
                self.bot.diag_player_screen_source = "pet_estimate"
                self.bot.has_attack_valid_player_screen_location = True
                self.bot.loc_last_attack_valid_player = pet_location
                self.bot.t_last_attack_valid_player = time.time()
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

        # Brief nametag occlusion is common when the pet overlaps the player.
        # Reuse only a recently validated in-range position for attack aiming;
        # never promote the fixed patrol estimate or an out-of-range pet match.
        attack_grace = self.bot.cfg["patrol"].get(
            "attack_position_grace_seconds", 2.0)
        if not self.bot.has_attack_valid_player_screen_location and \
                not self.bot.is_current_player_position_out_of_range and \
                self.bot.loc_last_attack_valid_player is not None and \
                time.time() - self.bot.t_last_attack_valid_player <= \
                attack_grace:
            self.bot.loc_player = self.bot.loc_last_attack_valid_player
            self.bot.diag_player_screen_source = "attack_position_grace"
            self.bot.has_attack_valid_player_screen_location = True

        if self.bot.has_attack_valid_player_screen_location:
            self.bot.update_cmd_by_mob_detection()
        else:
            self.bot.monsters = []

        # Optional blind periodic attack. Keep disabled when attacks consume
        # items/resources; confirmed monster detection still attacks normally.
        if self.bot.has_attack_valid_player_screen_location and \
            self.bot.cfg["patrol"].get("attack_without_target", False) and \
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
