from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from smac.env.multiagentenv import MultiAgentEnv
from envs.starcraft.smac_maps import get_map_params
from envs.starcraft.DTW import dtw_d

import atexit
from operator import attrgetter
from copy import deepcopy
import numpy as np
import enum
import math
from absl import logging

from pysc2 import maps
from pysc2 import run_configs
from pysc2.lib import protocol

from s2clientprotocol import common_pb2 as sc_common
from s2clientprotocol import sc2api_pb2 as sc_pb
from s2clientprotocol import raw_pb2 as r_pb
from s2clientprotocol import debug_pb2 as d_pb

import time,os
import datetime
import random
import json



races = {
    "R": sc_common.Random,
    "P": sc_common.Protoss,
    "T": sc_common.Terran,
    "Z": sc_common.Zerg,
}

difficulties = {
    "1": sc_pb.VeryEasy,
    "2": sc_pb.Easy,
    "3": sc_pb.Medium,
    "4": sc_pb.MediumHard,
    "5": sc_pb.Hard,
    "6": sc_pb.Harder,
    "7": sc_pb.VeryHard,
    "8": sc_pb.CheatVision,
    "9": sc_pb.CheatMoney,
    "A": sc_pb.CheatInsane,
}

actions = {
    "move": 16,  # target: PointOrUnit
    "attack": 23,  # target: PointOrUnit
    "stop": 4,  # target: None
    "heal": 386,  # Unit
}


class Direction(enum.IntEnum):
    NORTH = 0
    SOUTH = 1
    EAST = 2
    WEST = 3
# state_file_C0 = open('results/6-30-2/state_file.txt','a')96*
# diff_game = open('results/6-30-2/diff_game.txt','a')

# f = open("results/6-30-2/demo.txt","a")
state_path = 'results/2m_vs_1z/C_move/state_file.txt'
p_cons_path = 'results/2m_vs_1z/C_move/p_cons.txt'
dist_agent_path = 'results/2m_vs_1z/C_move/dist_agent.txt'
shoot_range_path = 'results/2m_vs_1z/C_move/shoot_range.txt'
health_path = 'results/2m_vs_1z/C_move/health.txt'
dis_path = 'results/2m_vs_1z/C_move/dis.txt'
attack_path = 'results/2m_vs_1z/C_move/attack.txt'
activity_range_path = 'results/2m_vs_1z/C_move/activity_range.txt'
fre_path = 'results/2m_vs_1z/C_move/fre.txt'
constraint_path = 'results/2m_vs_1z/C_move/constraint.txt'
p_cons_path = 'results/2m_vs_1z/C_move/p_cons.txt'
#dis_json_path = 'results/2s3z/s3/dis_won.json'


# constraint_index = [0,0,0,0,0,0,0]
state_won_all = []
#state_game_all = []


def _compute_distance_behavior_states(y1, y2):
    """
    y1 is a list
    """
    # y is numpy
    y1_length = len(y1)
    y2_length = len(y2)

    coverage_score = abs(y1_length - y2_length)

    common_length = min(y1_length, y2_length)
    y1_common = y1[:common_length]
    y2_common = y2[:common_length]
    for i in range(common_length):
        y1_e = y1_common[i]
        y2_e = y2_common[i]
        if y1_e == y2_e:
            continue
        else:
            coverage_score += 1

    coverage_score /= float(max(y1_length, y2_length))

    score = float(format(coverage_score, '.4f'))
    return score

def compute_dtw_dis(y1, y2):
    s1 = []
    s1.append(y1)
    s1 = np.asarray(s1)
    s2 = []
    s2.append(y2)
    s2 = np.asarray(s2)
    dist = dtw_d(s1,s2,0)
    return dist

def process_state(my_list_line,n_enemies):
    my_list = []
    for i in range(0,len(my_list_line)):
        temp_list = []
        for j in range(0,n_enemies):
            temp_list.append([my_list_line[i][j][0],my_list_line[i][j][3]])
        my_list.append(temp_list)
        temp_list = []
    return my_list

def Diversity(state,n_enemies):
    distance_list = [1.0]
    for old_state in state_won_all:
        distance = _compute_distance_behavior_states(process_state(old_state,n_enemies),process_state(state,n_enemies))
        distance_list.append((distance))
    return min(distance_list)



def compute_frequency2(dis_json,battle_id):
    num_true = 0
    num_false = 0
    frequency = 0.0
    l = len(dis_json)

    key_list = []
    for key in dis_json.keys():
        key_list.append(key)

    if l <= 200:
        for key in dis_json.keys():
            if dis_json[key] >= 0.6:
                num_true += 1
            else:
                num_false += 1
            frequency = num_true / l
    else:
        for i in range(l-200,l):
            d = dis_json[key_list[i]]
            if d >= 0.6:
               num_true += 1
            else:
                num_false += 1 
            frequency = num_true / 200
    
    with open(fre_path,'a') as f:
        f.write(str(battle_id)+'_'+str(frequency)+'\n')
    return frequency


# 写入 JSON 文件
def write_json(data,path):
    json_data = json.dumps(data)
    with open(path, 'w') as f:
        f.write(json_data)
    
# 读取写入的数据并打印
def read_json(path):
    with open(path) as f:
        output_data = json.loads(f.read())
        return output_data
import os
#读取上一个约束添加的位置
def last_constraint():
    pos_list = []
    if os.path.getsize(constraint_path) == 0:
        return 0
    else:
        with open(constraint_path,'r') as f_con:
            lines = f_con.readlines()
            for line in lines:
                info = line.split('_')
                pos = int(info[0])
                pos_list.append(int(pos))
    return pos_list[-1]

#读取约束的历史执行结果
def history(game_now):
    count_list = [0,0,0,0,0,0,0,0]
    reward_list = [0,0,0,0,0,0,0,0]
    index_list = [] #存储加约束的位置
    cons_list = [] #存储加的约束
    with open(constraint_path,'r') as f_con:
        lines = f_con.readlines()
        for line in lines:
            info = line.split('_')
            pos = info[0]
            cons = info[1].strip()
            index_list.append(int(pos))
            cons_list.append(int(cons))
    fre_json = {}
    with open(fre_path,'r') as f_fre:
        lines = f_fre.readlines()
        for line in lines:
            info = line.split('_')
            game_id = info[0]
            fre = info[1].strip()
            fre_json[game_id] = float(fre)

    for i in range(len(cons_list)):
        c = cons_list[i]
        start = index_list[i]
        end = 0

        if i != len(cons_list) - 1:
            end = index_list[i+1]
        else:
            end = int(game_now)
            
        reward = 0
        for j in range(int(start),end):
            if str(j) in fre_json.keys():
                reward += fre_json[str(j)]
            else:
                reward += 0
    
        reward_list[c] += reward
    
    for i in range(0,8):
        count_list[i] = cons_list.count(i)
        if count_list[i] != 0:
            reward_list[i] = reward_list[i] / count_list[i]

    return reward_list


#读取血量之差
def read_health():
    health_json = {}
    game_id_num = {}
    with open(health_path,'r') as f:
        lines = f.readlines()
        for line in lines:
            info = line.split('_')
            game_id = info[0]
            agent_health = float(info[1])
            enemy_health = float(info[2])
            minus = float(info[3].strip())

            if game_id not in health_json.keys():
                game_id_num[game_id] = 1
                health_json[game_id] = minus
            else:
                game_id_num[game_id] += 1
                health_json[game_id] += minus

    for key in health_json.keys():
        health_json[key] = float(health_json[key])/float(game_id_num[key])
    return health_json

#读取窗口内血量之差(200)
def read_health_minus():
    health_json = read_health()
    health_minus_list = []
    l = len(health_json)
    
    for i in range(l-200,l-1):
        h = health_json[str(i)]
        health_minus_list.append(float(h))
    
    return health_minus_list

#读取窗口内shoot_range
def read_shoot_range(n_agents):
    shoot_range_json = {}
    
    game_id_num = {}
    with open(shoot_range_path,'r') as f:
        lines = f.readlines()
        for line in lines:
            info = line.split('_')
            game_id = info[0]

            shoot_range_sum = 0

            for i in range(n_agents):
                shoot_range_sum += int(info[i+1].strip())
            
            shoot_range_sum /= n_agents

            if game_id not in shoot_range_json.keys():
                game_id_num[game_id] = 1
                shoot_range_json[game_id] = shoot_range_sum / n_agents
            else:
                game_id_num[game_id] += 1
                shoot_range_json[game_id] += shoot_range_sum / n_agents

    for key in shoot_range_json.keys():
        shoot_range_json[key] = float(shoot_range_json[key]) / int(game_id_num[key])
    
    shoot_range_list = []
    l = len(shoot_range_json)

    for i in range(l-200,l-1):
        shoot_range_list.append(float(shoot_range_json[str(i)]))
    return shoot_range_list


#读取窗口内agent之间的距离
def read_dist_agent():
    dist_agent_json = {}
    game_id_num = {}
    
    with open(dist_agent_path,'r') as f:
        lines = f.readlines()
        for line in lines:
            info = line.split('_')
            game_id = info[0]
            dist_agent = float(info[1].strip())

            if game_id not in dist_agent_json.keys():
                game_id_num[game_id] = 1
                dist_agent_json[game_id] = dist_agent
            else:
                game_id_num[game_id] += 1
                dist_agent_json[game_id] += dist_agent
    
    for key in dist_agent_json.keys():
        dist_agent_json[key] = float(dist_agent_json[key])/int(game_id_num[key])
    
    dist_agent_list = []
    l = len(dist_agent_json)

    for i in range(l-200,l-1):
        dist_agent_list.append(float(dist_agent_json[str(i)]))
    return dist_agent_list

#读取agent活动范围
def read_check_bounds():
    activity_range_json = {}
    game_id_num = {}
    with open(activity_range_path,'r') as f:
        lines = f.readlines()
        for line in lines:
            info = line.split('_')
            game_id = info[0]
            check_bounds = info[1].strip()
            if game_id not in activity_range_json.keys():
                game_id_num[game_id] = 1
                if check_bounds == 'True':
                    activity_range_json[game_id] = 1
            else:
                game_id_num[game_id] += 1
                if check_bounds == 'True':
                    activity_range_json[game_id] += 1
    
    for key in activity_range_json.keys():
        activity_range_json[key] = float(activity_range_json[key])/int(game_id_num[key])
    
    activity_range_list = []
    l = len(activity_range_json)

    for i in range(l-200,l-1):
        activity_range_list.append(float(activity_range_json[str(i)]))

    return activity_range_list





def read_dis():
    dis_json = {}
    game_id_num = {}
    with open(dis_path,'r') as f:
        lines = f.readlines()
        for line in lines:
            info = line.split('_')
            game_id = info[0]
            dis = float(info[1].strip())

            if game_id not in dis_json.keys():
                game_id_num[game_id] = 1
                dis_json[game_id] = dis
            else:
                game_id_num[game_id] += 1
                dis_json[game_id] += dis

    for key in dis_json.keys():
        dis_json[key] /= int(game_id_num[key])
    return dis_json

def read_attack():
    health_max = 300.0
    shield_max = 150.0

    attack_json = {}
    game_id_num = {}
    #计算单次攻击值
    with open(attack_path,'r') as f:
        lines = f.readlines()
        for line in lines:
            array = line.split('_')
            game_id = int(array[0])
            enemy_health = float(array[3])
            enemy_shield = float(array[4])
            steps = int(array[5].strip())
            
            attack = (health_max - enemy_health) + (shield_max - enemy_shield)
            attack_average = attack / steps
            if game_id not in attack_json:
                game_id_num[game_id] = 1
                attack_json[game_id] = attack_average
            else:
                attack_json[game_id] += attack_average
                game_id_num[game_id] += 1
    return attack_json

def compute_frequency_health(health_json):
    num_true = 0
    num_false = 0
    frequency = 0.0
    l = len(health_json)

    key_list = []
    for key in health_json.keys():
        key_list.append(key)

    if l <= 200:
        for key in health_json.keys():
            if health_json[key] >= 50:
                num_true += 1
            else:
                num_false += 1
            frequency = num_true / l
    else:
        for i in range(l-200,l):
            h = health_json[key_list[i]]
            if h >= 50:
               num_true += 1
            else:
                num_false += 1 
            frequency = num_true / 200
    return frequency

def compute_frequency_attack(attack_json):
    num_true = 0
    num_false = 0
    frequency = 0.0
    l = len(attack_json)

    key_list = []
    for key in attack_json.keys():
        key_list.append(key)

    if l <= 200:
        for key in attack_json.keys():
            if attack_json[key] >= 6:
                num_true += 1
            else:
                num_false += 1
            frequency = num_true / l
    else:
        for i in range(l-200,l):
            h = attack_json[key_list[i]]
            if h >= 6:
               num_true += 1
            else:
                num_false += 1 
            frequency = num_true / 200
    return frequency

class StarCraft2Env(MultiAgentEnv):
    """The StarCraft II environment for decentralised multi-agent
    micromanagement scenarios.
    """
    def __init__(
        self,
        map_name="8m",
        step_mul=8,
        move_amount=2,
        difficulty="7",
        game_version=None,
        seed=None,
        continuing_episode=False,
        obs_all_health=True,
        obs_own_health=True,
        obs_last_action=False,
        obs_pathing_grid=False,
        obs_terrain_height=False,
        obs_instead_of_state=False,
        obs_timestep_number=False,
        state_last_action=True,
        state_timestep_number=False,
        reward_sparse=False,
        reward_only_positive=True,
        reward_death_value=10,
        reward_win=200,
        reward_defeat=0,
        reward_negative_scale=0.5,
        reward_scale=True,
        reward_scale_rate=20,
        replay_dir="",
        replay_prefix="",
        window_size_x=1920,
        window_size_y=1200,
        heuristic_ai=False,
        heuristic_rest=False,
        debug=False,
    ):
        """
        Create a StarCraftC2Env environment.

        Parameters
        ----------
        map_name : str, optional
            The name of the SC2 map to play (default is "8m"). The full list
            can be found by running bin/map_list.
        step_mul : int, optional
            How many game steps per agent step (default is 8). None
            indicates to use the default map step_mul.
        move_amount : float, optional
            How far away units are ordered to move per step (default is 2).
        difficulty : str, optional
            The difficulty of built-in computer AI bot (default is "7").
        game_version : str, optional
            StarCraft II game version (default is None). None indicates the
            latest version.
        seed : int, optional
            Random seed used during game initialisation. This allows to
        continuing_episode : bool, optional
            Whether to consider episodes continuing or finished after time
            limit is reached (default is False).
        obs_all_health : bool, optional
            Agents receive the health of all units (in the sight range) as part
            of observations (default is True).
        obs_own_health : bool, optional
            Agents receive their own health as a part of observations (default
            is False). This flag is ignored when obs_all_health == True.
        obs_last_action : bool, optional
            Agents receive the last actions of all units (in the sight range)
            as part of observations (default is False).
        obs_pathing_grid : bool, optional
            Whether observations include pathing values surrounding the agent
            (default is False).
        obs_terrain_height : bool, optional
            Whether observations include terrain height values surrounding the
            agent (default is False).
        obs_instead_of_state : bool, optional
            Use combination of all agents' observations as the global state
            (default is False).
        obs_timestep_number : bool, optional
            Whether observations include the current timestep of the episode
            (default is False).
        state_last_action : bool, optional
            Include the last actions of all agents as part of the global state
            (default is True).
        state_timestep_number : bool, optional
            Whether the state include the current timestep of the episode
            (default is False).
        reward_sparse : bool, optional
            Receive 1/-1 reward for winning/loosing an episode (default is
            False). Whe rest of reward parameters are ignored if True.
        reward_only_positive : bool, optional
            Reward is always positive (default is True).
        reward_death_value : float, optional
            The amount of reward received for killing an enemy unit (default
            is 10). This is also the negative penalty for having an allied unit
            killed if reward_only_positive == False.
        reward_win : float, optional
            The reward for winning in an episode (default is 200).
        reward_defeat : float, optional
            The reward for loosing in an episode (default is 0). This value
            should be nonpositive.
        reward_negative_scale : float, optional
            Scaling factor for negative rewards (default is 0.5). This
            parameter is ignored when reward_only_positive == True.
        reward_scale : bool, optional
            Whether or not to scale the reward (default is True).
        reward_scale_rate : float, optional
            Reward scale rate (default is 20). When reward_scale == True, the
            reward received by the agents is divided by (max_reward /
            reward_scale_rate), where max_reward is the maximum possible
            reward per episode without considering the shield regeneration
            of Protoss units.
        replay_dir : str, optional
            The directory to save replays (default is None). If None, the
            replay will be saved in Replays directory where StarCraft II is
            installed.
        replay_prefix : str, optional
            The prefix of the replay to be saved (default is None). If None,
            the name of the map will be used.
        window_size_x : int, optional
            The length of StarCraft II window size (default is 1920).
        window_size_y: int, optional
            The height of StarCraft II window size (default is 1200).
        heuristic_ai: bool, optional
            Whether or not to use a non-learning heuristic AI (default False).
        heuristic_rest: bool, optional
            At any moment, restrict the actions of the heuristic AI to be
            chosen from actions available to RL agents (default is False).
            Ignored if heuristic_ai == False.
        debug: bool, optional
            Log messages about observations, state, actions and rewards for
            debugging purposes (default is False).
        """
        # Map arguments
        self.map_name = map_name
        map_params = get_map_params(self.map_name)
        self.n_agents = map_params["n_agents"]
        print('n_agents:',self.n_agents)
        self.n_enemies = map_params["n_enemies"]
        print('n_enemies:',self.n_enemies)
        self.episode_limit = map_params["limit"]
        self._move_amount = move_amount
        self._step_mul = step_mul
        self.difficulty = difficulty

        # Observations and state
        self.obs_own_health = obs_own_health
        self.obs_all_health = obs_all_health
        self.obs_instead_of_state = obs_instead_of_state
        self.obs_last_action = obs_last_action
        self.obs_pathing_grid = obs_pathing_grid
        self.obs_terrain_height = obs_terrain_height
        self.obs_timestep_number = obs_timestep_number
        self.state_last_action = state_last_action
        self.state_timestep_number = state_timestep_number
        if self.obs_all_health:
            self.obs_own_health = True
        self.n_obs_pathing = 8
        self.n_obs_height = 9

        # Rewards args
        self.reward_sparse = reward_sparse
        self.reward_only_positive = reward_only_positive
        self.reward_negative_scale = reward_negative_scale
        self.reward_death_value = reward_death_value
        self.reward_win = reward_win
        self.reward_defeat = reward_defeat
        self.reward_scale = reward_scale
        self.reward_scale_rate = reward_scale_rate

        # Other
        self.game_version = game_version
        self.continuing_episode = continuing_episode
        self._seed = seed
        self.heuristic_ai = heuristic_ai
        self.heuristic_rest = heuristic_rest
        self.debug = debug
        self.window_size = (window_size_x, window_size_y)
        self.replay_dir = replay_dir
        self.replay_prefix = replay_prefix

        # Actions
        self.n_actions_no_attack = 6
        self.n_actions_move = 4
        self.n_actions = self.n_actions_no_attack + self.n_enemies

        # Map info
        self._agent_race = map_params["a_race"]
        self._bot_race = map_params["b_race"]
        self.shield_bits_ally = 1 if self._agent_race == "P" else 0
        self.shield_bits_enemy = 1 if self._bot_race == "P" else 0
        self.unit_type_bits = map_params["unit_type_bits"]
        self.map_type = map_params["map_type"]

        self.max_reward = (
            self.n_enemies * self.reward_death_value + self.reward_win
        )

        self.agents = {}
        self.enemies = {}
        self._episode_count = 0
        self._episode_steps = 0
        self._total_steps = 0
        self._obs = None
        self.battles_won = 0
        self.battles_game = 0
        self.timeouts = 0
        self.force_restarts = 0
        self.last_stats = None
        self.death_tracker_ally = np.zeros(self.n_agents)
        self.death_tracker_enemy = np.zeros(self.n_enemies)
        self.previous_ally_units = None
        self.previous_enemy_units = None
        self.last_action = np.zeros((self.n_agents, self.n_actions))
        self._min_unit_type = 0
        self.marine_id = self.marauder_id = self.medivac_id = 0
        self.hydralisk_id = self.zergling_id = self.baneling_id = 0
        self.stalker_id = self.colossus_id = self.zealot_id = 0
        self.max_distance_x = 0
        self.max_distance_y = 0
        self.map_x = 0
        self.map_y = 0
        self.terrain_height = None
        self.pathing_grid = None
        self._run_config = None
        self._sc2_proc = None
        self._controller = None

        #My data
        self.n_en_state = 0 #记录enemy的状态数�?
        self.en_state = []  #记录enemy的状�?
        self.en_this_battle = []
        self.flag = 0 #记录此时添加了什么约�?
        self.random_flag = [0,0]  #约束的掩�?
        self.health_constraint = 0
        self.state_all_list = [] #记录所有的状态序�?
        self.same_state = 0 #记录相同状态的数量
        self.diff_state = 0 #记录不同状态的数量
        self.constraint_now = 0
        self.dis_game_dict = {}
        

        # Try to avoid leaking SC2 processes on shutdown
        atexit.register(lambda: self.close())

        start_time = time.perf_counter()   # 程序开始时�?
        self.start_time = start_time
        

    def _launch(self):
        """Launch the StarCraft II game."""
        self._run_config = run_configs.get(version=self.game_version)
        _map = maps.get(self.map_name)
        print('map name:',self.map_name)
        # Setting up the interface
        interface_options = sc_pb.InterfaceOptions(raw=True, score=False)
        self._sc2_proc = self._run_config.start(window_size=self.window_size, want_rgb=False)
        self._controller = self._sc2_proc.controller

        # Request to create the game
        create = sc_pb.RequestCreateGame(
            local_map=sc_pb.LocalMap(
                map_path=_map.path,
                map_data=self._run_config.map_data(_map.path)),
            realtime=False,
            random_seed=self._seed)
        create.player_setup.add(type=sc_pb.Participant)
        create.player_setup.add(type=sc_pb.Computer, race=races[self._bot_race],
                                difficulty=difficulties[self.difficulty])
        self._controller.create_game(create)

        join = sc_pb.RequestJoinGame(race=races[self._agent_race],
                                     options=interface_options)
        self._controller.join_game(join)

        game_info = self._controller.game_info()
        map_info = game_info.start_raw
        map_play_area_min = map_info.playable_area.p0
        map_play_area_max = map_info.playable_area.p1
        self.max_distance_x = map_play_area_max.x - map_play_area_min.x
        self.max_distance_y = map_play_area_max.y - map_play_area_min.y
        self.map_x = map_info.map_size.x
        self.map_y = map_info.map_size.y

        if map_info.pathing_grid.bits_per_pixel == 1:
            vals = np.array(list(map_info.pathing_grid.data)).reshape(
                self.map_x, int(self.map_y / 8))
            self.pathing_grid = np.transpose(np.array([
                [(b >> i) & 1 for b in row for i in range(7, -1, -1)]
                for row in vals], dtype=np.bool))
        else:
            self.pathing_grid = np.invert(np.flip(np.transpose(np.array(
                list(map_info.pathing_grid.data), dtype=np.bool).reshape(
                    self.map_x, self.map_y)), axis=1))

        self.terrain_height = np.flip(
            np.transpose(np.array(list(map_info.terrain_height.data))
                .reshape(self.map_x, self.map_y)), 1) / 255
        
    def reset(self):
        """Reset the environment. Required after each full episode.
        Returns initial observations and states.
        """
        self._episode_steps = 0
        if self._episode_count == 0:
            # Launch StarCraft II
            self._launch()
        else:
            self._restart()

        # Information kept for counting the reward
        self.death_tracker_ally = np.zeros(self.n_agents)
        self.death_tracker_enemy = np.zeros(self.n_enemies)
        self.previous_ally_units = None
        self.previous_enemy_units = None
        self.win_counted = False
        self.defeat_counted = False

        self.last_action = np.zeros((self.n_agents, self.n_actions))

        if self.heuristic_ai:
            self.heuristic_targets = [None] * self.n_agents

        try:
            self._obs = self._controller.observe()
            self.init_units()
        except (protocol.ProtocolError, protocol.ConnectionError):
            self.full_restart()

        if self.debug:
            logging.debug("Started Episode {}"
                          .format(self._episode_count).center(60, "*"))
        
        return self.get_obs(), self.get_state()

    def _restart(self):
        """Restart the environment by killing all units on the map.
        There is a trigger in the SC2Map file, which restarts the
        episode when there are no units left.
        """
        try:
            self._kill_all_units()
            self._controller.step(2)
        except (protocol.ProtocolError, protocol.ConnectionError):
            self.full_restart()

    def full_restart(self):
        """Full restart. Closes the SC2 process and launches a new one. """
        self._sc2_proc.close()
        self._launch()
        self.force_restarts += 1
    

    def compute_preference(self):
        preference_list = [0,0,0,0,0,0,0,0]
        #读取窗口内的状态
        #状态1：血量之差
        health_minus_list = read_health_minus()
        h_avg = sum(health_minus_list)/len(health_minus_list)
        preference_list[0] = h_avg / 240

        #状态2：攻击距离
        shoot_range_list = read_shoot_range(self.n_agents)
        s_avg = sum(shoot_range_list) / len(shoot_range_list)

        preference_list[5] = s_avg/4 - 1
        preference_list[6] = -s_avg/4 + 2
        preference_list[7] = abs(s_avg - 6) /4


        #状态3：活动范围
        bounds_list = read_check_bounds()
        b_avg = sum(bounds_list) / len(bounds_list)
        preference_list[4] = b_avg
        
        #状态4：智能体之间的距离
        dist_agent_list = read_dist_agent()
        dist_avg = sum(dist_agent_list) / len(dist_agent_list)
        preference_list[1] = -dist_avg / 6 + 1
        preference_list[2] = dist_avg / 6

        return preference_list

    
    def compute_probability(self):
        p_cons = [0,0,0,0,0,0,0,0]
   
        #计算part1，喜好值转化为概率
        preference_list = self.compute_preference()
        p_list = []
        e_sum = 0
        for preference in preference_list:
            e_sum += math.exp(preference)

        for preference in preference_list:
            p_list.append(math.exp(preference)/e_sum)
        
        #计算part2
        reward_list = history(self.battles_game)
        max_reward = max(reward_list)
        

        for i in range(0,8):
            if max_reward > 0:
                p_cons[i] = p_list[i] + reward_list[i]/max_reward
            else:
                p_cons[i] = p_list[i]

        return p_cons
    def epsilon_greedy(self):
        p_cons = self.compute_probability()
        print('p_cons:',p_cons)
        with open(p_cons_path,'a',encoding='utf-8') as f:
            f.write(str(p_cons)+'\n')
        max_p = max(p_cons)
        p = p_cons.index(max_p)
        r = random.random()

        battle_id = int(self.battles_game)
        epsilon = -battle_id / 10000 + 1.1

        if epsilon <= 0.1:
            epsilon = 0.1

        if r > epsilon:
            return p
        else:
            return random.randint(0,len(p_cons)-1)
        
    def step(self, actions):
        """A single environment step. Returns reward, terminated, info."""
        actions_int = [int(a) for a in actions]

        self.last_action = np.eye(self.n_actions)[np.array(actions_int)]

        # Collect individual actions
        sc_actions = []
        if self.debug:
            logging.debug("Actions".center(60, "-"))

        for a_id, action in enumerate(actions_int):
            if not self.heuristic_ai:
                sc_action = self.get_agent_action(a_id, action)
            else:
                sc_action, action_num = self.get_agent_action_heuristic(
                    a_id, action)
                actions[a_id] = action_num
            if sc_action:
                sc_actions.append(sc_action)

        # Send action request
        req_actions = sc_pb.RequestAction(actions=sc_actions)
        try:
            self._controller.actions(req_actions)
            # Make step in SC2, i.e. apply actions
            self._controller.step(self._step_mul)
            # Observe here so that we know if the episode is over.
            self._obs = self._controller.observe()
        except (protocol.ProtocolError, protocol.ConnectionError):
            self.full_restart()
            return 0, True, {}

        self._total_steps += 1
        self._episode_steps += 1

        # Update units
        game_end_code = self.update_units()

        terminated = False
        reward = self.reward_battle()
        info = {"battle_won": False}
        
        if game_end_code is not None:
            # Battle is over
            terminated = True
            self.battles_game += 1
            
            if game_end_code == 1 and not self.win_counted:
                self.battles_won += 1
                self.win_counted = True
                info["battle_won"] = True
                if not self.reward_sparse:
                    reward += self.reward_win
                else:
                    reward = 1

            elif game_end_code == -1 and not self.defeat_counted:
                self.defeat_counted = True
                if not self.reward_sparse:
                    reward += self.reward_defeat
                else:
                    reward = -1
            
        elif self._episode_steps >= self.episode_limit:
            # Episode limit reached
            terminated = True
            
            if self.continuing_episode:
                info["episode_limit"] = True
            self.battles_game += 1
            self.timeouts += 1

        enemy_state,enemy_health,enemy_shield = self.get_enemy_state()
        #print(enemy_state)
        #enemy_temp_state = enemy_state[0].tolist()
        #shield = float(enemy_temp_state[3])
        enemy_state = enemy_state.tolist()
        self.en_this_battle.append(enemy_state)  #en_this_battle记录一局对战的状态序�?  
        agent_health = self.get_agent_state()
        minus = agent_health - enemy_health


            

        if terminated:
            # #存储当前状态序�?
            with open(state_path,'a',encoding='utf-8') as f_state:
                f_state.write(str(self.battles_game)+'_'+str(self.en_this_battle)+'\n')
            #存储血量差
            with open(health_path,'a',encoding='utf-8') as f:
                f.write(str(self.battles_game)+'_'+str(agent_health)+'_'+str(enemy_health)+'_'+str(minus)+'\n')
            with open(attack_path,'a',encoding='utf-8') as f_attack:
                f_attack.write(str(self.battles_game)+'_'+str(agent_health)+'_'+str(enemy_health)+'_'+str(enemy_shield)+'_'+str(self._episode_steps)+'\n')
            
            #存储攻击范围
            shoot_range_list = str(self.battles_game)+"_"
            for agent_id in range(self.n_agents):
                unit = self.get_unit_by_id(agent_id)
                shoot_range = self.unit_shoot_range(agent_id)
                shoot_range_list += str(shoot_range) + "_"
            with open(shoot_range_path,'a',encoding='utf-8') as f_shoot:
                f_shoot.write(shoot_range_list+'\n')
            
            if game_end_code == 1:
                #计算状态序列是否新
                dis = Diversity(self.en_this_battle,self.n_enemies)
                state_won_all.append(self.en_this_battle)

                with open(dis_path,'a') as f:
                    time_now = str(time.strftime('%m-%d-%H-%M',time.localtime(time.time())))
                    f.write(str(self.battles_game)+'_'+str(dis)+'_'+str(time_now)+'\n')

                dis_json = read_dis()
                fre_dis = compute_frequency2(dis_json,self.battles_game)
                
                #判断是否添加新约束
                # if len(dis_json) > 0:
                #     if fre_dis <= 0.2:
                #         last_constraint_game = last_constraint()
                #         if self.battles_game >= last_constraint_game + 200:
                #             c = self.epsilon_greedy()
                #             self.constraint_now = c
                #             with open(constraint_path,'a',encoding='utf-8') as f:
                #                 f.write(str(self.battles_game)+'_'+str(c)+'\n')
   
            self.en_this_battle = []


        #C1:
        if self.constraint_now == 4:
            if minus > 50:
                reward = 0.8 * reward      

        #存储agent之间的距离
        dist_list = []
        
        for agent_id in range(self.n_agents):
            unit = self.get_unit_by_id(agent_id)
            if unit.health > 0:
                target_items = self.enemies.items()
                for t_id, t_unit in target_items:
                    if t_unit.health > 0:
                        dist = self.distance(
                            unit.pos.x, unit.pos.y, t_unit.pos.x, t_unit.pos.y
                        )
                        shoot_range = self.unit_shoot_range(agent_id)
                        if self.constraint_now == 1:
                            if dist < 0.5 * shoot_range:
                                    reward = 0.8*reward
                        if self.constraint_now == 2:
                            if dist > shoot_range:
                                    reward = 0.8*reward

                        dist_list.append(dist)
        
        #存储agent的活动范围
        for agent_id in range(self.n_agents):
            unit = self.get_unit_by_id(agent_id)
            _range = self.activity_range(unit)
            with open(activity_range_path,'a',encoding='utf-8') as f_activity:
                f_activity.write(str(self.battles_game)+'_'+str(_range)+'\n')
        
        if len(dist_list) > 0:
            dist_average = sum(dist_list) / len(dist_list)
            with open(dist_agent_path,'a',encoding='utf-8') as f_dist_agent:
                f_dist_agent.write(str(self.battles_game)+'_'+str(dist_average)+'\n')
        
        #Old code
        if self.debug:
            logging.debug("Reward = {}".format(reward).center(60, '-'))

        if terminated:
            self._episode_count += 1

        if self.reward_scale:
            reward /= self.max_reward / self.reward_scale_rate

        
        return reward, terminated, info



    def get_agent_action(self, a_id, action):
        """Construct the action for agent a_id."""
        avail_actions = self.get_avail_agent_actions(a_id)
        assert avail_actions[action] == 1, \
                "Agent {} cannot perform action {}".format(a_id, action)

        unit = self.get_unit_by_id(a_id)
        tag = unit.tag
        x = unit.pos.x
        y = unit.pos.y

        if action == 0:
            # no-op (valid only when dead)
            assert unit.health == 0, "No-op only available for dead agents."
            if self.debug:
                logging.debug("Agent {}: Dead".format(a_id))
            return None
        elif action == 1:
            # stop
            cmd = r_pb.ActionRawUnitCommand(
                ability_id=actions["stop"],
                unit_tags=[tag],
                queue_command=False)
            if self.debug:
                logging.debug("Agent {}: Stop".format(a_id))

        elif action == 2:
            # move north
            cmd = r_pb.ActionRawUnitCommand(
                ability_id=actions["move"],
                target_world_space_pos=sc_common.Point2D(
                    x=x, y=y + self._move_amount),
                unit_tags=[tag],
                queue_command=False)
            if self.debug:
                logging.debug("Agent {}: Move North".format(a_id))

        elif action == 3:
            # move south
            cmd = r_pb.ActionRawUnitCommand(
                ability_id=actions["move"],
                target_world_space_pos=sc_common.Point2D(
                    x=x, y=y - self._move_amount),
                unit_tags=[tag],
                queue_command=False)
            if self.debug:
                logging.debug("Agent {}: Move South".format(a_id))

        elif action == 4:
            # move east
            cmd = r_pb.ActionRawUnitCommand(
                ability_id=actions["move"],
                target_world_space_pos=sc_common.Point2D(
                    x=x + self._move_amount, y=y),
                unit_tags=[tag],
                queue_command=False)
            if self.debug:
                logging.debug("Agent {}: Move East".format(a_id))

        elif action == 5:
            # move west
            cmd = r_pb.ActionRawUnitCommand(
                ability_id=actions["move"],
                target_world_space_pos=sc_common.Point2D(
                    x=x - self._move_amount, y=y),
                unit_tags=[tag],
                queue_command=False)
            if self.debug:
                logging.debug("Agent {}: Move West".format(a_id))
        else:
            # attack/heal units that are in range
            target_id = action - self.n_actions_no_attack
            if self.map_type == "MMM" and unit.unit_type == self.medivac_id:
                target_unit = self.agents[target_id]
                action_name = "heal"
            else:
                target_unit = self.enemies[target_id]
                action_name = "attack"

            action_id = actions[action_name]
            target_tag = target_unit.tag

            cmd = r_pb.ActionRawUnitCommand(
                ability_id=action_id,
                target_unit_tag=target_tag,
                unit_tags=[tag],
                queue_command=False)

            if self.debug:
                logging.debug("Agent {} {}s unit # {}".format(
                    a_id, action_name, target_id))

        sc_action = sc_pb.Action(action_raw=r_pb.ActionRaw(unit_command=cmd))
        return sc_action

    def get_agent_action_heuristic(self, a_id, action):
        unit = self.get_unit_by_id(a_id)
        tag = unit.tag

        target = self.heuristic_targets[a_id]
        if unit.unit_type == self.medivac_id:
            if (target is None or self.agents[target].health == 0 or
                self.agents[target].health == self.agents[target].health_max):
                min_dist = math.hypot(self.max_distance_x, self.max_distance_y)
                min_id = -1
                for al_id, al_unit in self.agents.items():
                    if al_unit.unit_type == self.medivac_id:
                        continue
                    if (al_unit.health != 0 and
                        al_unit.health != al_unit.health_max):
                        dist = self.distance(unit.pos.x, unit.pos.y,
                                             al_unit.pos.x, al_unit.pos.y)
                        if dist < min_dist:
                            min_dist = dist
                            min_id = al_id
                self.heuristic_targets[a_id] = min_id
                if min_id == -1:
                    self.heuristic_targets[a_id] = None
                    return None, 0
            action_id = actions['heal']
            target_tag = self.agents[self.heuristic_targets[a_id]].tag
        else:
            if target is None or self.enemies[target].health == 0:
                min_dist = math.hypot(self.max_distance_x, self.max_distance_y)
                min_id = -1
                for e_id, e_unit in self.enemies.items():
                    if (unit.unit_type == self.marauder_id and
                        e_unit.unit_type == self.medivac_id):
                        continue
                    if e_unit.health > 0:
                        dist = self.distance(unit.pos.x, unit.pos.y,
                                             e_unit.pos.x, e_unit.pos.y)
                        if dist < min_dist:
                            min_dist = dist
                            min_id = e_id
                self.heuristic_targets[a_id] = min_id
                if min_id == -1:
                    self.heuristic_targets[a_id] = None
                    return None, 0
            action_id = actions['attack']
            target_tag = self.enemies[self.heuristic_targets[a_id]].tag

        action_num = self.heuristic_targets[a_id] + self.n_actions_no_attack

        # Check if the action is available
        if (self.heuristic_rest and
            self.get_avail_agent_actions(a_id)[action_num] == 0):

            # Move towards the target rather than attacking/healing
            if unit.unit_type == self.medivac_id:
                target_unit = self.agents[self.heuristic_targets[a_id]]
            else:
                target_unit = self.enemies[self.heuristic_targets[a_id]]

            delta_x = target_unit.pos.x - unit.pos.x
            delta_y = target_unit.pos.y - unit.pos.y

            if abs(delta_x) > abs(delta_y): # east or west
                if delta_x > 0: # east
                    target_pos=sc_common.Point2D(
                        x=unit.pos.x + self._move_amount, y=unit.pos.y)
                    action_num = 4
                else: # west
                    target_pos=sc_common.Point2D(
                        x=unit.pos.x - self._move_amount, y=unit.pos.y)
                    action_num = 5
            else: # north or south
                if delta_y > 0: # north
                    target_pos=sc_common.Point2D(
                        x=unit.pos.x, y=unit.pos.y + self._move_amount)
                    action_num = 2
                else: # south
                    target_pos=sc_common.Point2D(
                        x=unit.pos.x, y=unit.pos.y - self._move_amount)
                    action_num = 3

            cmd = r_pb.ActionRawUnitCommand(
                ability_id = actions['move'],
                target_world_space_pos = target_pos,
                unit_tags = [tag],
                queue_command = False)
        else:
            # Attack/heal the target
            cmd = r_pb.ActionRawUnitCommand(
                ability_id = action_id,
                target_unit_tag = target_tag,
                unit_tags = [tag],
                queue_command = False)

        sc_action = sc_pb.Action(action_raw=r_pb.ActionRaw(unit_command=cmd))
        return sc_action, action_num

    def reward_battle(self):
        """Reward function when self.reward_spare==False.
        Returns accumulative(累计) hit/shield point damage dealt(造成命中/盾点伤害) to the enemy
        + reward_death_value per enemy unit killed, and, in case
        self.reward_only_positive == False, - (damage dealt to ally units
        + reward_death_value per ally unit killed) * self.reward_negative_scale
        """
        if self.reward_sparse:
            return 0

        reward = 0
        delta_deaths = 0
        delta_ally = 0
        delta_enemy = 0

        neg_scale = self.reward_negative_scale
        attack_value = 0
        # update deaths
        for al_id, al_unit in self.agents.items():
            if not self.death_tracker_ally[al_id]:
                # did not die so far
                prev_health = (
                    self.previous_ally_units[al_id].health
                    + self.previous_ally_units[al_id].shield
                )
                if al_unit.health == 0:
                    # just died
                    self.death_tracker_ally[al_id] = 1
                    if not self.reward_only_positive:
                        delta_deaths -= self.reward_death_value * neg_scale
                    delta_ally += prev_health * neg_scale
                else:
                    # still alive
                    delta_ally += neg_scale * (
                        prev_health - al_unit.health - al_unit.shield
                    )
        flag = False
        for e_id, e_unit in self.enemies.items():
            if not self.death_tracker_enemy[e_id]:
                prev_health = (
                    self.previous_enemy_units[e_id].health
                    + self.previous_enemy_units[e_id].shield
                )
                if e_unit.health == 0:
                    self.death_tracker_enemy[e_id] = 1
                    delta_deaths += self.reward_death_value
                    delta_enemy += prev_health
                    
                else:
                    delta_enemy += prev_health - e_unit.health - e_unit.shield
                    attack = (self.previous_enemy_units[e_id].health - e_unit.health) / self.previous_enemy_units[e_id].health
                    attack_value = self.previous_enemy_units[e_id].health - e_unit.health
                    if attack_value > 6:
                        flag = True
        
        if self.reward_only_positive:
            reward = abs(delta_enemy + delta_deaths)  # shield regeneration
        else:
            reward = delta_enemy + delta_deaths - delta_ally
        #C6
        if self.constraint_now == 3:
            if flag:
                reward = 0.8 * reward
        return reward

    def get_total_actions(self):
        """Returns the total number of actions an agent could ever take."""
        return self.n_actions

    @staticmethod
    def distance(x1, y1, x2, y2):
        """Distance between two points."""
        return math.hypot(x2 - x1, y2 - y1)

    def unit_shoot_range(self, agent_id):
        """Returns the shooting range for an agent."""
        #C7/C10
        if self.constraint_now == 5:
            return 3
        if self.constraint_now == 6:
            return 9
        if self.constraint_now == 7:
            return 6
        return 9

    def unit_sight_range(self, agent_id):
        """Returns the sight range for an agent."""
        return 9

    def unit_max_cooldown(self, unit):
        """Returns the maximal cooldown for a unit."""
        switcher = {
            self.marine_id: 15,
            self.marauder_id: 25,
            self.medivac_id: 200,  # max energy
            self.stalker_id: 35,
            self.zealot_id: 22,
            self.colossus_id: 24,
            self.hydralisk_id: 10,
            self.zergling_id: 11,
            self.baneling_id: 1
        }
        return switcher.get(unit.unit_type, 15)

    def save_replay(self):

        stats = self.get_stats()
        for key in stats.keys():
            logging.info(key+": %s" % stats[key])
        logging.info("enemy_state:")
        logging.info(self.n_en_state)

        """Save a replay."""
        prefix = self.replay_prefix or self.map_name
        replay_dir = self.replay_dir or ""
        logging.info("repaly dir:%s" % replay_dir)
        replay_path = self._run_config.save_replay(
            self._controller.save_replay(), replay_dir=replay_dir, prefix=prefix)
        logging.info("Replay saved at: %s" % replay_path)

    def unit_max_shield(self, unit):
        """Returns maximal shield for a given unit."""
        if unit.unit_type == 74 or unit.unit_type == self.stalker_id:
            return 80  # Protoss's Stalker
        if unit.unit_type == 73 or unit.unit_type == self.zealot_id:
            return 50  # Protoss's Zaelot
        if unit.unit_type == 4 or unit.unit_type == self.colossus_id:
            return 150  # Protoss's Colossus

    def can_move(self, unit, direction):
        """Whether a unit can move in a given direction."""
        m = self._move_amount / 2

        if direction == Direction.NORTH:
            x, y = int(unit.pos.x), int(unit.pos.y + m)
        elif direction == Direction.SOUTH:
            x, y = int(unit.pos.x), int(unit.pos.y - m)
        elif direction == Direction.EAST:
            x, y = int(unit.pos.x + m), int(unit.pos.y)
        else:
            x, y = int(unit.pos.x - m), int(unit.pos.y)

        if self.check_bounds(x, y) and self.pathing_grid[x, y]:
            return True

        return False

    def activity_range(self, unit):
        x, y = int(unit.pos.x), int(unit.pos.y)

        if 0 <= x < 0.5 *self.map_x and 0 <= y < 0.5*self.map_y:
            return True
        else:
            return False


    def get_surrounding_points(self, unit, include_self=False):
        """Returns the surrounding points of the unit in 8 directions."""
        x = int(unit.pos.x)
        y = int(unit.pos.y)

        ma = self._move_amount

        points = [
            (x, y + 2 * ma),
            (x, y - 2 * ma),
            (x + 2 * ma, y),
            (x - 2 * ma, y),
            (x + ma, y + ma),
            (x - ma, y - ma),
            (x + ma, y - ma),
            (x - ma, y + ma),
        ]

        if include_self:
            points.append((x, y))

        return points

    def check_bounds(self, x, y):
        """Whether a point is within the map bounds."""
        #C9
        if self.constraint_now == 0:
            return (0 <= x < 0.5*self.map_x and 0 <= y < 0.5*self.map_y)
        return (0 <= x < self.map_x and 0 <= y < self.map_y)

    def get_surrounding_pathing(self, unit):
        """Returns pathing values of the grid surrounding the given unit."""
        points = self.get_surrounding_points(unit, include_self=False)
        vals = [
            self.pathing_grid[x, y] if self.check_bounds(x, y) else 1
            for x, y in points
        ]
        return vals

    def get_surrounding_height(self, unit):
        """Returns height values of the grid surrounding the given unit."""
        points = self.get_surrounding_points(unit, include_self=True)
        vals = [
            self.terrain_height[x, y] if self.check_bounds(x, y) else 1
            for x, y in points
        ]
        return vals

    def get_obs_agent(self, agent_id):
        """Returns observation for agent_id. The observation is composed of:

           - agent movement features (where it can move to, height information and pathing grid)
           - enemy features (available_to_attack, health, relative_x, relative_y, shield, unit_type)
           - ally features (visible, distance, relative_x, relative_y, shield, unit_type)
           - agent unit features (health, shield, unit_type)

           All of this information is flattened and concatenated into a list,
           in the aforementioned order. To know the sizes of each of the
           features inside the final list of features, take a look at the
           functions ``get_obs_move_feats_size()``,
           ``get_obs_enemy_feats_size()``, ``get_obs_ally_feats_size()`` and
           ``get_obs_own_feats_size()``.

           The size of the observation vector may vary, depending on the
           environment configuration and type of units present in the map.
           For instance, non-Protoss units will not have shields, movement
           features may or may not include terrain height and pathing grid,
           unit_type is not included if there is only one type of unit in the
           map etc.).

           NOTE: Agents should have access only to their local observations
           during decentralised execution.
        """
        unit = self.get_unit_by_id(agent_id)

        move_feats_dim = self.get_obs_move_feats_size()
        enemy_feats_dim = self.get_obs_enemy_feats_size()
        ally_feats_dim = self.get_obs_ally_feats_size()
        own_feats_dim = self.get_obs_own_feats_size()

        move_feats = np.zeros(move_feats_dim, dtype=np.float32)
        enemy_feats = np.zeros(enemy_feats_dim, dtype=np.float32)
        ally_feats = np.zeros(ally_feats_dim, dtype=np.float32)
        own_feats = np.zeros(own_feats_dim, dtype=np.float32)

        if unit.health > 0:  # otherwise dead, return all zeros
            x = unit.pos.x
            y = unit.pos.y
            sight_range = self.unit_sight_range(agent_id)

            # Movement features
            avail_actions = self.get_avail_agent_actions(agent_id)
            for m in range(self.n_actions_move):
                move_feats[m] = avail_actions[m + 2]

            ind = self.n_actions_move

            if self.obs_pathing_grid:
                move_feats[
                    ind : ind + self.n_obs_pathing
                ] = self.get_surrounding_pathing(unit)
                ind += self.n_obs_pathing

            if self.obs_terrain_height:
                move_feats[ind:] = self.get_surrounding_height(unit)

            # Enemy features
            for e_id, e_unit in self.enemies.items():
                e_x = e_unit.pos.x
                e_y = e_unit.pos.y
                dist = self.distance(x, y, e_x, e_y)

                if (
                    dist < sight_range and e_unit.health > 0
                ):  # visible and alive
                    # Sight range > shoot range
                    enemy_feats[e_id, 0] = avail_actions[
                        self.n_actions_no_attack + e_id
                    ]  # available
                    enemy_feats[e_id, 1] = dist / sight_range  # distance
                    enemy_feats[e_id, 2] = (
                        e_x - x
                    ) / sight_range  # relative X
                    enemy_feats[e_id, 3] = (
                        e_y - y
                    ) / sight_range  # relative Y

                    ind = 4
                    if self.obs_all_health:
                        enemy_feats[e_id, ind] = (
                            e_unit.health / e_unit.health_max
                        )  # health
                        ind += 1
                        if self.shield_bits_enemy > 0:
                            max_shield = self.unit_max_shield(e_unit)
                            enemy_feats[e_id, ind] = (
                                e_unit.shield / max_shield
                            )  # shield
                            ind += 1

                    if self.unit_type_bits > 0:
                        type_id = self.get_unit_type_id(e_unit, False)
                        enemy_feats[e_id, ind + type_id] = 1  # unit type

            # Ally features
            al_ids = [
                al_id for al_id in range(self.n_agents) if al_id != agent_id
            ]
            for i, al_id in enumerate(al_ids):

                al_unit = self.get_unit_by_id(al_id)
                al_x = al_unit.pos.x
                al_y = al_unit.pos.y
                dist = self.distance(x, y, al_x, al_y)

                if (
                    dist < sight_range and al_unit.health > 0
                ):  # visible and alive
                    ally_feats[i, 0] = 1  # visible
                    ally_feats[i, 1] = dist / sight_range  # distance
                    ally_feats[i, 2] = (al_x - x) / sight_range  # relative X
                    ally_feats[i, 3] = (al_y - y) / sight_range  # relative Y

                    ind = 4
                    if self.obs_all_health:
                        ally_feats[i, ind] = (
                            al_unit.health / al_unit.health_max
                        )  # health
                        ind += 1
                        if self.shield_bits_ally > 0:
                            max_shield = self.unit_max_shield(al_unit)
                            ally_feats[i, ind] = (
                                al_unit.shield / max_shield
                            )  # shield
                            ind += 1

                    if self.unit_type_bits > 0:
                        type_id = self.get_unit_type_id(al_unit, True)
                        ally_feats[i, ind + type_id] = 1
                        ind += self.unit_type_bits

                    if self.obs_last_action:
                        ally_feats[i, ind:] = self.last_action[al_id]

            # Own features
            ind = 0
            if self.obs_own_health:
                own_feats[ind] = unit.health / unit.health_max
                ind += 1
                if self.shield_bits_ally > 0:
                    max_shield = self.unit_max_shield(unit)
                    own_feats[ind] = unit.shield / max_shield
                    ind += 1

            if self.unit_type_bits > 0:
                type_id = self.get_unit_type_id(unit, True)
                own_feats[ind + type_id] = 1

        agent_obs = np.concatenate(
            (
                move_feats.flatten(),
                enemy_feats.flatten(),
                ally_feats.flatten(),
                own_feats.flatten(),
            )
        )

        if self.obs_timestep_number:
            agent_obs = np.append(agent_obs,
                                  self._episode_steps / self.episode_limit)

        if self.debug:
            logging.debug("Obs Agent: {}".format(agent_id).center(60, "-"))
            logging.debug("Avail. actions {}".format(
                self.get_avail_agent_actions(agent_id)))
            logging.debug("Move feats {}".format(move_feats))
            logging.debug("Enemy feats {}".format(enemy_feats))
            logging.debug("Ally feats {}".format(ally_feats))
            logging.debug("Own feats {}".format(own_feats))

        return agent_obs

    def get_obs(self):
        """Returns all agent observations in a list.
        NOTE: Agents should have access only to their local observations
        during decentralised execution.
        """
        agents_obs = [self.get_obs_agent(i) for i in range(self.n_agents)]
        return agents_obs

    def get_state(self):
        """Returns the global state.
        NOTE: This functon should not be used during decentralised execution.
        """
        if self.obs_instead_of_state:
            obs_concat = np.concatenate(self.get_obs(), axis=0).astype(
                np.float32
            )
            return obs_concat

        nf_al = 4 + self.shield_bits_ally + self.unit_type_bits
        nf_en = 3 + self.shield_bits_enemy + self.unit_type_bits

        ally_state = np.zeros((self.n_agents, nf_al))
        enemy_state = np.zeros((self.n_enemies, nf_en))

        center_x = self.map_x / 2
        center_y = self.map_y / 2

        for al_id, al_unit in self.agents.items():
            if al_unit.health > 0:
                x = al_unit.pos.x
                y = al_unit.pos.y
                max_cd = self.unit_max_cooldown(al_unit)

                ally_state[al_id, 0] = (
                    al_unit.health / al_unit.health_max
                )  # health
                if (
                    self.map_type == "MMM"
                    and al_unit.unit_type == self.medivac_id
                ):
                    ally_state[al_id, 1] = al_unit.energy / max_cd  # energy
                else:
                    ally_state[al_id, 1] = (
                        al_unit.weapon_cooldown / max_cd
                    )  # cooldown
                ally_state[al_id, 2] = (
                    x - center_x
                ) / self.max_distance_x  # relative X
                ally_state[al_id, 3] = (
                    y - center_y
                ) / self.max_distance_y  # relative Y

                ind = 4
                if self.shield_bits_ally > 0:
                    max_shield = self.unit_max_shield(al_unit)
                    ally_state[al_id, ind] = (
                        al_unit.shield / max_shield
                    )  # shield
                    ind += 1

                if self.unit_type_bits > 0:
                    type_id = self.get_unit_type_id(al_unit, True)
                    ally_state[al_id, ind + type_id] = 1


        for e_id, e_unit in self.enemies.items():
            if e_unit.health > 0:
                x = e_unit.pos.x
                y = e_unit.pos.y


                enemy_state[e_id, 0] = (
                    e_unit.health / e_unit.health_max
                )  # health
                enemy_state[e_id, 1] = (
                    x - center_x
                ) / self.max_distance_x  # relative X
                enemy_state[e_id, 2] = (
                    y - center_y
                ) / self.max_distance_y  # relative Y

                ind = 3
                if self.shield_bits_enemy > 0:
                    max_shield = self.unit_max_shield(e_unit)
                    enemy_state[e_id, ind] = (
                        e_unit.shield / max_shield
                    )  # shield
                    ind += 1

                if self.unit_type_bits > 0:
                    type_id = self.get_unit_type_id(e_unit, False)
                    enemy_state[e_id, ind + type_id] = 1


        
        
        state = np.append(ally_state.flatten(), enemy_state.flatten())
        if self.state_last_action:
            state = np.append(state, self.last_action.flatten())
        if self.state_timestep_number:
            state = np.append(state,
                              self._episode_steps / self.episode_limit)

        state = state.astype(dtype=np.float32)

        if self.debug:
            logging.debug("STATE".center(60, "-"))
            logging.debug("Ally state {}".format(ally_state))
            logging.debug("Enemy state {}".format(enemy_state))
            if self.state_last_action:
                logging.debug("Last actions {}".format(self.last_action))

        return state

    def get_agent_state(self):
        """Returns the global state.
        NOTE: This functon should not be used during decentralised execution.
        """
        if self.obs_instead_of_state:
            obs_concat = np.concatenate(self.get_obs(), axis=0).astype(
                np.float32
            )
            return obs_concat

        nf_al = 4 + self.shield_bits_ally + self.unit_type_bits
        nf_en = 3 + self.shield_bits_enemy + self.unit_type_bits

        ally_state = np.zeros((self.n_agents, nf_al))

        center_x = self.map_x / 2
        center_y = self.map_y / 2

        health_sum = 0
        shield_sum = 0

        for al_id, al_unit in self.agents.items():
            if al_unit.health > 0:
                x = al_unit.pos.x
                y = al_unit.pos.y
                max_cd = self.unit_max_cooldown(al_unit)
                health_sum += al_unit.health

                ally_state[al_id, 0] = (
                    al_unit.health
                )  # health
                if (
                    self.map_type == "MMM"
                    and al_unit.unit_type == self.medivac_id
                ):
                    ally_state[al_id, 1] = al_unit.energy / max_cd  # energy
                else:
                    ally_state[al_id, 1] = (
                        al_unit.weapon_cooldown / max_cd
                    )  # cooldown
                ally_state[al_id, 2] = (
                    x - center_x
                ) / self.max_distance_x  # relative X
                ally_state[al_id, 3] = (
                    y - center_y
                ) / self.max_distance_y  # relative Y

                ind = 4
                if self.shield_bits_ally > 0:
                    max_shield = self.unit_max_shield(al_unit)
                    shield_sum += al_unit.shield
                    ally_state[al_id, ind] = (
                        al_unit.shield / max_shield
                    )  # shield
                    ind += 1

                if self.unit_type_bits > 0:
                    type_id = self.get_unit_type_id(al_unit, True)
                    ally_state[al_id, ind + type_id] = 1

    
        return health_sum
    def get_enemy_max(self):
        health_max_sum = 0
        for e_id, e_unit in self.enemies.items():
            health_max_sum += e_unit.health_max
        return health_max_sum

    def get_enemy_state(self):
        if self.obs_instead_of_state:
            obs_concat = np.concatenate(self.get_obs(), axis=0).astype(
                np.float32
            )
            return obs_concat

        nf_en = 3 + self.shield_bits_enemy + self.unit_type_bits
        enemy_state = np.zeros((self.n_enemies, nf_en))

        center_x = self.map_x / 2
        center_y = self.map_y / 2

        health_sum = 0
        shield_sum = 0

        
        for e_id, e_unit in self.enemies.items():
            if e_unit.health > 0:
                x = e_unit.pos.x
                y = e_unit.pos.y

                health_sum += e_unit.health
                shield_sum += e_unit.shield

                enemy_state[e_id, 0] = (
                    e_unit.health
                    # e_unit.health / e_unit.health_max
                )  # health
                enemy_state[e_id, 1] = (
                    x - center_x
                ) / self.max_distance_x  # relative X
                enemy_state[e_id, 2] = (
                    y - center_y
                ) / self.max_distance_y  # relative Y

                ind = 3
                if self.shield_bits_enemy > 0:
                    max_shield = self.unit_max_shield(e_unit)
                    enemy_state[e_id, ind] = (
                        e_unit.shield / max_shield
                    )  # shield
                    ind += 1

                if self.unit_type_bits > 0:
                    type_id = self.get_unit_type_id(e_unit, False)
                    enemy_state[e_id, ind + type_id] = 1

        return enemy_state,health_sum,shield_sum

    def get_obs_enemy_feats_size(self):
        """ Returns the dimensions of the matrix containing enemy features.
        Size is n_enemies x n_features.
        """
        nf_en = 4 + self.unit_type_bits

        if self.obs_all_health:
            nf_en += 1 + self.shield_bits_enemy

        return self.n_enemies, nf_en

    def get_obs_ally_feats_size(self):
        """Returns the dimensions of the matrix containing ally features.
        Size is n_allies x n_features.
        """
        nf_al = 4 + self.unit_type_bits

        if self.obs_all_health:
            nf_al += 1 + self.shield_bits_ally

        if self.obs_last_action:
            nf_al += self.n_actions

        return self.n_agents - 1, nf_al

    def get_obs_own_feats_size(self):
        """Returns the size of the vector containing the agents' own features.
        """
        own_feats = self.unit_type_bits
        if self.obs_own_health:
            own_feats += 1 + self.shield_bits_ally
        if self.obs_timestep_number:
            own_feats += 1

        return own_feats

    def get_obs_move_feats_size(self):
        """Returns the size of the vector containing the agents's movement-related features."""
        move_feats = self.n_actions_move
        if self.obs_pathing_grid:
            move_feats += self.n_obs_pathing
        if self.obs_terrain_height:
            move_feats += self.n_obs_height

        return move_feats

    def get_obs_size(self):
        """Returns the size of the observation."""
        own_feats = self.get_obs_own_feats_size()
        move_feats = self.get_obs_move_feats_size()

        n_enemies, n_enemy_feats = self.get_obs_enemy_feats_size()
        n_allies, n_ally_feats = self.get_obs_ally_feats_size()

        enemy_feats = n_enemies * n_enemy_feats
        ally_feats = n_allies * n_ally_feats

        return move_feats + enemy_feats + ally_feats + own_feats

    def get_state_size(self):
        """Returns the size of the global state."""
        if self.obs_instead_of_state:
            return self.get_obs_size() * self.n_agents

        nf_al = 4 + self.shield_bits_ally + self.unit_type_bits
        nf_en = 3 + self.shield_bits_enemy + self.unit_type_bits

        enemy_state = self.n_enemies * nf_en
        ally_state = self.n_agents * nf_al

        size = enemy_state + ally_state

        if self.state_last_action:
            size += self.n_agents * self.n_actions
        if self.state_timestep_number:
            size += 1

        return size

    def get_visibility_matrix(self):
        """Returns a boolean numpy array of dimensions 
        (n_agents, n_agents + n_enemies) indicating which units
        are visible to each agent.
        """
        arr = np.zeros(
            (self.n_agents, self.n_agents + self.n_enemies), 
            dtype=np.bool,
        )

        for agent_id in range(self.n_agents):
            current_agent = self.get_unit_by_id(agent_id)
            if current_agent.health > 0:  # it agent not dead
                x = current_agent.pos.x
                y = current_agent.pos.y
                sight_range = self.unit_sight_range(agent_id)

                # Enemies
                for e_id, e_unit in self.enemies.items():
                    e_x = e_unit.pos.x
                    e_y = e_unit.pos.y
                    dist = self.distance(x, y, e_x, e_y)

                    if (dist < sight_range and e_unit.health > 0):
                        # visible and alive
                        arr[agent_id, self.n_agents + e_id] = 1

                # The matrix for allies is filled symmetrically
                al_ids = [
                    al_id for al_id in range(self.n_agents) 
                    if al_id > agent_id
                ]
                for i, al_id in enumerate(al_ids):
                    al_unit = self.get_unit_by_id(al_id)
                    al_x = al_unit.pos.x
                    al_y = al_unit.pos.y
                    dist = self.distance(x, y, al_x, al_y)

                    if (dist < sight_range and al_unit.health > 0):  
                        # visible and alive
                        arr[agent_id, al_id] = arr[al_id, agent_id] = 1

        return arr

    def get_unit_type_id(self, unit, ally):
        """Returns the ID of unit type in the given scenario."""
        if ally:  # use new SC2 unit types
            type_id = unit.unit_type - self._min_unit_type
        else:  # use default SC2 unit types
            if self.map_type == "stalkers_and_zealots":
                # id(Stalker) = 74, id(Zealot) = 73
                type_id = unit.unit_type - 73
            elif self.map_type == "colossi_stalkers_zealots":
                # id(Stalker) = 74, id(Zealot) = 73, id(Colossus) = 4
                if unit.unit_type == 4:
                    type_id = 0
                elif unit.unit_type == 74:
                    type_id = 1
                else:
                    type_id = 2
            elif self.map_type == "bane":
                if unit.unit_type == 9:
                    type_id = 0
                else:
                    type_id = 1
            elif self.map_type == "MMM":
                if unit.unit_type == 51:
                    type_id = 0
                elif unit.unit_type == 48:
                    type_id = 1
                else:
                    type_id = 2
            # for communication
            elif self.map_type == "overload_roach":
                # roach
                type_id = 0
            elif self.map_type == "overload_bane":
                # baneling
                type_id = 0
            elif self.map_type == "bZ_hM":
                if unit.unit_type == 107:
                    # hydralisk
                    type_id = 0
                else:
                    # medivacs
                    type_id = 1

        return type_id

    def get_avail_agent_actions(self, agent_id):
        """Returns the available actions for agent_id."""
        unit = self.get_unit_by_id(agent_id)
        if unit.health > 0:
            # cannot choose no-op when alive
            avail_actions = [0] * self.n_actions

            # stop should be allowed
            avail_actions[1] = 1

            # see if we can move
            if self.can_move(unit, Direction.NORTH):
                avail_actions[2] = 1
            if self.can_move(unit, Direction.SOUTH):
                avail_actions[3] = 1
            if self.can_move(unit, Direction.EAST):
                avail_actions[4] = 1
            if self.can_move(unit, Direction.WEST):
                avail_actions[5] = 1

            # Can attack only alive units that are alive in the shooting range
            shoot_range = self.unit_shoot_range(agent_id)

            target_items = self.enemies.items()
            if self.map_type == "MMM" and unit.unit_type == self.medivac_id:
                # Medivacs cannot heal themselves or other flying units
                target_items = [
                    (t_id, t_unit)
                    for (t_id, t_unit) in self.agents.items()
                    if t_unit.unit_type != self.medivac_id
                ]

            for t_id, t_unit in target_items:
                if t_unit.health > 0:
                    dist = self.distance(
                        unit.pos.x, unit.pos.y, t_unit.pos.x, t_unit.pos.y
                    )
                    if dist <= shoot_range:
                        avail_actions[t_id + self.n_actions_no_attack] = 1

            return avail_actions

        else:
            # only no-op allowed
            return [1] + [0] * (self.n_actions - 1)

    def get_avail_actions(self):
        """Returns the available actions of all agents in a list."""
        avail_actions = []
        for agent_id in range(self.n_agents):
            avail_agent = self.get_avail_agent_actions(agent_id)
            avail_actions.append(avail_agent)
        return avail_actions

    def close(self):
        """Close StarCraft II."""
        if self._sc2_proc:
            self._sc2_proc.close()

    def seed(self):
        """Returns the random seed used by the environment."""
        return self._seed

    def render(self):
        """Not implemented."""
        pass

    def _kill_all_units(self):
        """Kill all units on the map."""
        units_alive = [
            unit.tag for unit in self.agents.values() if unit.health > 0
        ] + [unit.tag for unit in self.enemies.values() if unit.health > 0]
        debug_command = [
            d_pb.DebugCommand(kill_unit=d_pb.DebugKillUnit(tag=units_alive))
        ]
        self._controller.debug(debug_command)

    def init_units(self):
        """Initialise the units."""
        while True:
            # Sometimes not all units have yet been created by SC2
            self.agents = {}
            self.enemies = {}

            ally_units = [
                unit
                for unit in self._obs.observation.raw_data.units
                if unit.owner == 1
            ]
            ally_units_sorted = sorted(
                ally_units,
                key=attrgetter("unit_type", "pos.x", "pos.y"),
                reverse=False,
            )

            for i in range(len(ally_units_sorted)):
                self.agents[i] = ally_units_sorted[i]
                if self.debug:
                    logging.debug(
                        "Unit {} is {}, x = {}, y = {}".format(
                            len(self.agents),
                            self.agents[i].unit_type,
                            self.agents[i].pos.x,
                            self.agents[i].pos.y,
                        )
                    )

            for unit in self._obs.observation.raw_data.units:
                if unit.owner == 2:
                    self.enemies[len(self.enemies)] = unit
                    if self._episode_count == 0:
                        self.max_reward += unit.health_max + unit.shield_max

            if self._episode_count == 0:
                min_unit_type = min(
                    unit.unit_type for unit in self.agents.values()
                )
                self._init_ally_unit_types(min_unit_type)

            all_agents_created = (len(self.agents) == self.n_agents)
            all_enemies_created = (len(self.enemies) == self.n_enemies)

            if all_agents_created and all_enemies_created:  # all good
                return

            try:
                self._controller.step(1)
                self._obs = self._controller.observe()
            except (protocol.ProtocolError, protocol.ConnectionError):
                self.full_restart()
                self.reset()

    def update_units(self):
        """Update units after an environment step.
        This function assumes that self._obs is up-to-date.
        """
        n_ally_alive = 0
        n_enemy_alive = 0

        # Store previous state
        self.previous_ally_units = deepcopy(self.agents)
        self.previous_enemy_units = deepcopy(self.enemies)

        for al_id, al_unit in self.agents.items():
            updated = False
            for unit in self._obs.observation.raw_data.units:
                if al_unit.tag == unit.tag:
                    self.agents[al_id] = unit
                    updated = True
                    n_ally_alive += 1
                    break

            if not updated:  # dead
                al_unit.health = 0

        for e_id, e_unit in self.enemies.items():
            updated = False
            for unit in self._obs.observation.raw_data.units:
                if e_unit.tag == unit.tag:
                    self.enemies[e_id] = unit
                    updated = True
                    n_enemy_alive += 1
                    break

            if not updated:  # dead
                e_unit.health = 0

        if (n_ally_alive == 0 and n_enemy_alive > 0
                or self.only_medivac_left(ally=True)):
            return -1  # lost
        if (n_ally_alive > 0 and n_enemy_alive == 0
                or self.only_medivac_left(ally=False)):
            return 1  # won
        if n_ally_alive == 0 and n_enemy_alive == 0:
            return 0

        return None

    def _init_ally_unit_types(self, min_unit_type):
        """Initialise ally unit types. Should be called once from the
        init_units function.
        """
        self._min_unit_type = min_unit_type
        if self.map_type == "marines":
            self.marine_id = min_unit_type
        elif self.map_type == "stalkers_and_zealots":
            self.stalker_id = min_unit_type
            self.zealot_id = min_unit_type + 1
        elif self.map_type == "colossi_stalkers_zealots":
            self.colossus_id = min_unit_type
            self.stalker_id = min_unit_type + 1
            self.zealot_id = min_unit_type + 2
        elif self.map_type == "MMM":
            self.marauder_id = min_unit_type
            self.marine_id = min_unit_type + 1
            self.medivac_id = min_unit_type + 2
        elif self.map_type == "zealots":
            self.zealot_id = min_unit_type
        elif self.map_type == "hydralisks":
            self.hydralisk_id = min_unit_type
        elif self.map_type == "stalkers":
            self.stalker_id = min_unit_type
        elif self.map_type == "colossus":
            self.colossus_id = min_unit_type
        elif self.map_type == "bane":
            self.baneling_id = min_unit_type
            self.zergling_id = min_unit_type + 1

    def only_medivac_left(self, ally):
        """Check if only Medivac units are left."""
        if self.map_type != "MMM":
            return False

        if ally:
            units_alive = [
                a
                for a in self.agents.values()
                if (a.health > 0 and a.unit_type != self.medivac_id)
            ]
            if len(units_alive) == 0:
                return True
            return False
        else:
            units_alive = [
                a
                for a in self.enemies.values()
                if (a.health > 0 and a.unit_type != self.medivac_id)
            ]
            if len(units_alive) == 1 and units_alive[0].unit_type == 54:
                return True
            return False

    def get_unit_by_id(self, a_id):
        """Get unit by ID."""
        return self.agents[a_id]

    def get_stats(self):
        stats = {
            "battles_won": self.battles_won,
            "battles_game": self.battles_game,
            "battles_draw": self.timeouts,
            "win_rate": self.battles_won / self.battles_game,
            "timeouts": self.timeouts,
            "restarts": self.force_restarts,
        }
        return stats
