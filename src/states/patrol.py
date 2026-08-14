import time

# Local import
from src.states.base_state import State

class PatrolState(State):
    def __init__(self, name, bot):
        super().__init__(name, bot)
        self.bot = bot
        self.is_patrol_to_left = True # Patrol direction flag
        self.patrol_turn_point_cnt = 0 # Patrol tuning back counter
        self.t_last_direction_change = time.time()

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

        x, y = self.bot.loc_player
        h, w = self.bot.img_frame.shape[:2]
        loc_player_ratio = float(x)/float(w)
        left_ratio, right_ratio = self.bot.cfg["patrol"]["range"]

        # Do not use an uninitialised/failed nametag coordinate as a boundary.
        # Without a valid screen location the timed direction change below is
        # still sufficient to patrol both ways.
        if not self.bot.has_valid_player_screen_location:
            self.patrol_turn_point_cnt = 0
        elif self.is_patrol_to_left and loc_player_ratio < left_ratio:
            self.patrol_turn_point_cnt += 1
        elif (not self.is_patrol_to_left) and loc_player_ratio > right_ratio:
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
