dis_game_dict = {}
def get_dict():
    return dis_game_dict

def set_dict(key,value):
    dis_game_dict[key] = value

state_won_all = []
def set_state_won_all(state):
    state_won_all.append(state)

def get_state_won_all():
    return state_won_all


window_list = []
def set_window(w):
    window_list.append(w)

def get_window():
    return window_list

def remove_window():
    window_list.pop(0)

#计算窗口中出现的新状态的频率
def compute_frequency():
    num_true = 0
    num_false = 0
    for index in window_list:
        if index:
            num_true += 1
        else:
            num_false += 1
    #print('Window list:',self.window_list)
    #print('Frequency:',num_true/len(self.window_list))
    if num_true/len(window_list) <= 0.1:
        return False
    return True