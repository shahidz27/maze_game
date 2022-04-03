"""
Contains the class definition for Level, which handles collision,
player movement, victory checking, and path finding.
"""
import math
import random
from typing import Dict, List, Optional, Set, Tuple


def floor_coordinates(coord: Tuple[float, float]):
    """
    Convert a precise coordinate to one representing whole tile position.
    """
    return math.floor(coord[0]), math.floor(coord[1])


class Level:
    """
    A class representing a single maze level. Contains a wall map
    as a 2D array, with True representing the maze walls, and False
    representing occupy-able space. Also keeps track of the current player
    coordinates within the level and can calculate possible solutions.
    Monster start and wait can be set to None if you do not wish the level
    to have a monster. This class will not automatically move or spawn
    the monster by itself, however does provide the method required to do so.
    """
    def __init__(self, dimensions: Tuple[int, int],
                 wall_map: List[List[bool]], start_point: Tuple[int, int],
                 end_point: Tuple[int, int], exit_keys: List[Tuple[int, int]],
                 monster_start: Optional[Tuple[int, int]],
                 monster_wait: Optional[float]):
        """
        Create a level with a wall map, start and end points, and
        collectable keys required to exit the level.
        """
        self.dimensions = dimensions

        if (len(wall_map) != dimensions[1]
                or sum(1 for x in wall_map if len(x) != dimensions[0]) != 0):
            raise ValueError(
                f"Wall map must be {dimensions[0]}x{dimensions[1]} points"
            )
        self.wall_map = wall_map

        if not self.is_coord_in_bounds(start_point):
            raise ValueError("Out of bounds start point coordinates")
        if self[start_point]:
            raise ValueError("Start point cannot be inside wall")
        self.start_point = start_point
        # Start in centre of tile
        self.player_coords = (start_point[0] + 0.5, start_point[1] + 0.5)

        if not self.is_coord_in_bounds(end_point):
            raise ValueError("Out of bounds end point coordinates")
        if self[end_point]:
            raise ValueError("End point cannot be inside wall")
        self.end_point = end_point

        for key in exit_keys:
            if not self.is_coord_in_bounds(key):
                raise ValueError("Out of bounds key coordinates")
            if self[key]:
                raise ValueError("Key cannot be inside wall")
        self.original_exit_keys = exit_keys
        # Create a shallow copy of exit keys to be manipulated on collection
        self.exit_keys = [*exit_keys]

        self.monster_coords: Optional[Tuple[int, int]] = None
        if monster_start is not None:
            if not self.is_coord_in_bounds(monster_start):
                raise ValueError("Out of bounds monster start coordinates")
            if self[monster_start]:
                raise ValueError("Monster start cannot be inside wall")
            self.monster_start = monster_start
            self.monster_wait = monster_wait
        else:
            self.monster_start = None
            self.monster_wait = None

        self.player_flags: Set[Tuple[int, int]] = set()

        # Used to prevent monster from backtracking
        self._last_monster_position = (-1, -1)

        # Maps coordinates to a list of lists of coordinates represented
        # possible paths from a previous player position. Saves on unnecessary
        # repeated calculations.
        self._solution_cache: Dict[
            Tuple[int, int], List[List[Tuple[int, int]]]
        ] = {}

        self.won = False
        self.killed = False

    def __str__(self):
        """
        Returns a string representation of the maze. '██' is a wall,
        '  ' is empty space, 'PP' is the player, 'KK' are keys, 'SS' is the
        start point, and 'EE' is the end point.
        """
        string = ""
        for y, row in enumerate(self.wall_map):
            for x, point in enumerate(row):
                if floor_coordinates(self.player_coords) == (x, y):
                    string += "PP"
                elif self.monster_coords == (x, y):
                    string += "MM"
                elif (x, y) in self.exit_keys:
                    string += "KK"
                elif self.start_point == (x, y):
                    string += "SS"
                elif self.end_point == (x, y):
                    string += "EE"
                else:
                    string += "██" if point else "  "
            string += "\n"
        return string[:-1]

    def __getitem__(self, index: Tuple[float, float]):
        """
        Returns True if the specified tile is a wall.
        """
        if not self.is_coord_in_bounds(index):
            raise ValueError("Target coordinates out of bounds")
        grid_index = floor_coordinates(index)
        return self.wall_map[grid_index[1]][grid_index[0]]

    def __setitem__(self, index: Tuple[int, int], value: bool):
        """
        Change whether a particular tile is considered a wall.
        """
        if not self.is_coord_in_bounds(index):
            raise ValueError("Target coordinates out of bounds")
        self.wall_map[index[1]][index[0]] = value

    def move_player(self, vector: Tuple[float, float], relative: bool = True):
        """
        Moves the player either relative to their current position, or to an
        absolute location. Key collection and victory checking will be
        performed automatically. Silently fails if the player cannot move by
        the specified vector or to the specified position.
        """
        if self.won or self.killed:
            return
        if relative:
            target = (
                self.player_coords[0] + vector[0],
                self.player_coords[1] + vector[1]
            )
            # Try moving just in X or Y if primary target cannot be moved to
            alternate_targets = [
                (self.player_coords[0] + vector[0], self.player_coords[1]),
                (self.player_coords[0], self.player_coords[1] + vector[1])
            ]
        else:
            target = vector
            # There are no alternate movements if we aren't moving relatively
            alternate_targets = []
        if not self.is_coord_in_bounds(target) or self[target]:
            found_valid = False
            for alt_move in alternate_targets:
                if self.is_coord_in_bounds(alt_move) and not self[alt_move]:
                    target = alt_move
                    found_valid = True
            if not found_valid:
                return
        grid_coords = floor_coordinates(target)
        old_grid_coords = floor_coordinates(self.player_coords)
        relative_grid_pos = (
            grid_coords[0] - old_grid_coords[0],
            grid_coords[1] - old_grid_coords[1]
        )
        # Moved diagonally therefore skipping a square, make sure that's valid
        if relative_grid_pos[0] and relative_grid_pos[1]:
            diagonal_path_free = False
            if not self[old_grid_coords[0] + relative_grid_pos[0],
                        old_grid_coords[1]]:
                diagonal_path_free = True
            elif not self[old_grid_coords[0],
                          old_grid_coords[1] + relative_grid_pos[1]]:
                diagonal_path_free = True
            if not diagonal_path_free:
                return
        self.player_coords = target
        if grid_coords in self.exit_keys:
            self.exit_keys.remove(grid_coords)
        if grid_coords == self.monster_coords:
            self.killed = True
        elif grid_coords == self.end_point and len(self.exit_keys) == 0:
            self.won = True

    def move_monster(self):
        """
        Moves the monster one space in a random available direction, unless
        the player is in the unobstructed view of one of the cardinal
        directions, in which case move toward the player instead. If the
        monster and the player occupy the same grid square, self.killed will
        be set to True.
        """
        last_monster_position = self.monster_coords
        player_grid_position = floor_coordinates(self.player_coords)
        if self.monster_start is None:
            return
        if self.monster_coords is None:
            self.monster_coords = self.monster_start
        else:
            # 0 - Not in line of sight
            # 1 - Line of sight on Y axis
            # 2 - Line of sight on X axis
            line_of_sight = 0
            if player_grid_position[0] == self.monster_coords[0]:
                min_y_coord = min(
                    player_grid_position[1], self.monster_coords[1]
                )
                max_y_coord = max(
                    player_grid_position[1], self.monster_coords[1]
                )
                collided = False
                for y_coord in range(min_y_coord, max_y_coord + 1):
                    if self[player_grid_position[0], y_coord]:
                        collided = True
                        break
                if not collided:
                    line_of_sight = 1
            elif player_grid_position[1] == self.monster_coords[1]:
                min_x_coord = min(
                    player_grid_position[0], self.monster_coords[0]
                )
                max_x_coord = max(
                    player_grid_position[0], self.monster_coords[0]
                )
                collided = False
                for x_coord in range(min_x_coord, max_x_coord + 1):
                    if self[x_coord, player_grid_position[1]]:
                        collided = True
                        break
                if not collided:
                    line_of_sight = 2
            if line_of_sight == 1:
                if player_grid_position[1] > self.monster_coords[1]:
                    self.monster_coords = (
                        self.monster_coords[0], self.monster_coords[1] + 1
                    )
                else:
                    self.monster_coords = (
                        self.monster_coords[0], self.monster_coords[1] - 1
                    )
            elif line_of_sight == 2:
                if player_grid_position[0] > self.monster_coords[0]:
                    self.monster_coords = (
                        self.monster_coords[0] + 1, self.monster_coords[1]
                    )
                else:
                    self.monster_coords = (
                        self.monster_coords[0] - 1, self.monster_coords[1]
                    )
            else:
                # Randomise order of each cardinal direction, then move to
                # the first one available
                shuffled_vectors = [(0, 1), (0, -1), (1, 0), (-1, 0)]
                random.shuffle(shuffled_vectors)
                for vector in shuffled_vectors:
                    target = (
                        self.monster_coords[0] + vector[0],
                        self.monster_coords[1] + vector[1]
                    )
                    if (self.is_coord_in_bounds(target) and not self[target]
                            and self._last_monster_position != target):
                        self.monster_coords = target
                        break
        self._last_monster_position = last_monster_position
        if self.monster_coords in self.player_flags and random.random() < 0.25:
            self.player_flags.remove(self.monster_coords)
        if self.monster_coords == player_grid_position:
            self.killed = True

    def find_possible_paths(self):
        """
        Finds all possible paths to the current target(s) from the player's
        current position. The returned result is sorted by path length in
        ascending order (i.e. the shortest path is first). Potentially very
        computationally expensive.
        """
        targets = (
            [self.end_point] if len(self.exit_keys) == 0 else self.exit_keys
        )
        grid_coords = floor_coordinates(self.player_coords)
        if grid_coords in self._solution_cache:
            return [
                x for x in self._solution_cache[grid_coords]
                if x[-1] in targets
            ]
        result = sorted(
            self._path_search([grid_coords], targets), key=len
        )
        self._solution_cache[grid_coords] = result
        return result

    def reset(self):
        """
        Reset this level to its original state
        """
        # Shallow copy to prevent original key list being modified
        self.exit_keys = [*self.original_exit_keys]
        self.player_flags = set()
        self.player_coords = (
            self.start_point[0] + 0.5, self.start_point[1] + 0.5
        )
        self.monster_coords = None
        self.won = False
        self.killed = False

    def is_coord_in_bounds(self, coord: Tuple[float, float]):
        """
        Checks if a coordinate in within the boundaries of the maze.
        """
        return (
                0 <= coord[0] < self.dimensions[0]
                and 0 <= coord[1] < self.dimensions[1]
        )

    def _path_search(self, current_path: List[Tuple[int, int]],
                     targets: List[Tuple[int, int]]):
        """
        Recursively find all possible paths to a list of targets. Use the
        find_possible_paths method instead of this one for finding paths
        to the player's target(s).
        """
        found_paths: List[List[Tuple[int, int]]] = []
        for x_offset, y_offset in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            point = (
                current_path[-1][0] + x_offset,
                current_path[-1][1] + y_offset
            )
            if (not self.is_coord_in_bounds(point) or self[point]
                    or point in current_path):
                continue
            if point in targets:
                found_paths.append(current_path + [point])
            found_paths += self._path_search(
                current_path + [point], targets
            )
        return found_paths
