import pygame
import config_loader
import maze_levels
import netcode
import raycasting
import screen_drawing
import server

def maze_game(level_json_path="maze_levels.json", config_ini_path="config.ini", multiplayer_server=None, multiplayer_name=None):
    pygame.init()

    is_multi = multiplayer_server is not None
    is_coop = False

    cfg = config_loader.Config(config_ini_path)
    levels = maze_levels.load_level_json(level_json_path)
    if is_multi:
        # Handle multiplayer connection and setup
        try:
            sock = netcode.create_client_socket()
            assert multiplayer_server is not None
            addr = netcode.get_host_port(multiplayer_server)
            if multiplayer_name is None:
                multiplayer_name = "Unnamed"
            join_response = None
            retries = 0
            while join_response is None and retries < 10:
                join_response = netcode.join_server(
                    sock, addr, multiplayer_name
                )
                retries += 1
                time.sleep(0.5)
            if join_response is None:
                tkinter.messagebox.showerror(
                    "Connection Error", "Could not connect to server."
                )
                sys.exit(1)
        except Exception as e:
            print(e)
            tkinter.messagebox.showerror(
                "Connection Error", "Invalid server information provided."
            )
            sys.exit(1)
        player_key, current_level, is_coop = join_response
        if not is_coop:
            lvl = levels[current_level]
            lvl.randomise_player_coords()
            # Remove pickups and monsters from deathmatches
            lvl.original_exit_keys = frozenset()
            lvl.exit_keys = set()
            lvl.original_key_sensors = frozenset()
            lvl.key_sensors = set()
            lvl.original_guns = frozenset()
            lvl.guns = set()
            lvl.monster_start = None
            lvl.monster_wait = None
            lvl.end_point = (-1, -1)  # Make end inaccessible in deathmatches
            lvl.start_point = (-1, -1)  # Hide start point in deathmatches
    else:
        current_level = 0
        # Not needed in single player
        player_key = bytes()
        sock = socket.socket()
        addr = ("", 0)
    other_players: List[net_data.Player] = []
    time_since_server_ping = 0.0
    hits_remaining = 1  # This will be updated later
    last_killer_skin = 0  # This will be updated later
    kills = 0
    deaths = 0

    # Minimum window resolution is 500×500
    screen = pygame.display.set_mode((
        max(cfg.viewport_width, 500), max(cfg.viewport_height, 500)
    ))
    if not is_multi:
        pygame.display.set_caption("PyMaze - Level 1")
    elif is_coop:
        pygame.display.set_caption(f"PyMaze Co-op - Level {current_level + 1}")
    else:
        pygame.display.set_caption("PyMaze Deathmatch")
    pygame.display.set_icon(
        pygame.image.load(os.path.join("window_icons", "main.png")).convert()
    )

    # Resources must be imported here after pygame has been initialised.
    import resources

    clock = pygame.time.Clock()

    # X+Y facing directions, times, moves, etc. are specific to each level,
    # so are each stored in a list.
    facing_directions = [(0.0, 1.0)] * len(levels)
    # Camera planes are always perpendicular to facing directions
    camera_planes = [(-cfg.display_fov / 100, 0.0)] * len(levels)
    time_scores = [0.0] * len(levels)
    move_scores = [0.0] * len(levels)
    has_started_level = [False] * len(levels)
    if os.path.isfile("highscores.pickle"):
        with open("highscores.pickle", 'rb') as file:
            highscores: List[Tuple[float, float]] = pickle.load(file)
            if len(highscores) < len(levels):
                highscores += [(0.0, 0.0)] * (len(levels) - len(highscores))
    else:
        highscores = [(0.0, 0.0)] * len(levels)

    enable_mouse_control = False
    # Used to calculate how far mouse has travelled for mouse control.
    old_mouse_pos = (cfg.viewport_width // 2, cfg.viewport_height // 2)

    display_map = False
    display_compass = False
    display_stats = (not is_multi) or is_coop
    display_rays = False

    is_reset_prompt_shown = False

    monster_timeouts = [0.0] * len(levels)
    # How long since the monster was last spotted. Used to prevent the
    # "spotted" jumpscare sound playing repeatedly.
    monster_spotted = [cfg.monster_spot_timeout] * len(levels)
    monster_escape_time = [cfg.monster_time_to_escape] * len(levels)
    # -1 means that the monster has not currently caught the player.
    monster_escape_clicks = [-1] * len(levels)
    compass_times = [cfg.compass_time] * len(levels)
    compass_burned_out = [False] * len(levels)
    compass_charge_delays = [cfg.compass_charge_delay] * len(levels)
    key_sensor_times = [0.0] * len(levels)
    has_gun: List[bool] = [is_multi and not is_coop] * len(levels)
    wall_place_cooldown = [0.0] * len(levels)
    flicker_time_remaining = [0.0] * len(levels)
    pickup_flash_time_remaining = 0.0
    hurt_flash_time_remaining = 0.0
    time_to_breathing_finish = 0.0
    time_to_next_roam_sound = 0.0

    # [None | (grid_x, grid_y, time_of_placement)]
    player_walls: List[Optional[Tuple[int, int, float]]] = [None] * len(levels)

    # Used to draw level behind victory/reset screens without having to raycast
    # during every new frame.
    last_level_frame = [
        pygame.Surface((cfg.viewport_width, cfg.viewport_height))
        for _ in range(len(levels))
    ]

    # Used as both mouse and keyboard can be used to fire.
    def _fire_gun() -> None:
        nonlocal pickup_flash_time_remaining
        if (not display_map or cfg.enable_cheat_map) and not (
                levels[current_level].won
                or levels[current_level].killed):
            _, hit_sprites = raycasting.get_first_collision(
                levels[current_level],
                facing_directions[current_level],
                cfg.draw_maze_edge_as_wall, other_players
            )
            for sprite in hit_sprites:
                if sprite.type == raycasting.MONSTER:
                    # Monster was hit by gun
                    levels[current_level].monster_coords = None
                    break
            if is_multi:
                shot_response = netcode.fire_gun(
                    sock, addr, player_key,
                    levels[current_level].player_coords,
                    facing_directions[current_level]
                )
                if not is_coop and shot_response in (
                        server.SHOT_HIT_NO_KILL, server.SHOT_KILLED):
                    pickup_flash_time_remaining = 0.4
                if shot_response not in (server.SHOT_DENIED, None):
                    resources.gunshot_sound.play()
                if is_coop:
                    has_gun[current_level] = False
            else:
                has_gun[current_level] = False
                resources.gunshot_sound.play()

