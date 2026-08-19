from xapp_control import *
from ICQL import *
device = torch.device('cpu')

# ckpt = f'DQN_5'
# ckpt = f'ICQL_HO_Cosine_40'
ckpt = f'ICQL_HO_Cosine_Lite_20'

state_dim, action_dim = (10, 17), (10, 10)
agent = DQN(state_dim=state_dim, action_dim=action_dim).to(device)
checkpoint = f'./model/'+ckpt+f'000.pth'
checkpoint = torch.load(checkpoint, map_location=device)
agent.load_state_dict(checkpoint['agent_target_state_dict'])
agent.eval()
print(f'Loaded agent from {ckpt}.')



@torch.no_grad()
def select_action(agent, state_np):
    state = torch.tensor(state_np, dtype=torch.float32,device=device).unsqueeze(0)
    mask = (state[:, :, 0] > 0).squeeze(0).numpy() # [10, ]
    action = np.zeros_like(mask, dtype=int)
    if np.all(mask == 0):
        return action, mask

    logits = agent(state).numpy()   # [1, 10, 10]
    valid_idx = np.where(mask)[0]
    sub_matrix = logits[0, valid_idx, :]
    row, col = linear_sum_assignment(-sub_matrix)
    action[valid_idx] = col + 2
    # print(f'State:\n{state}\nlogits:\n{logits}\nsub_matrix:\n{sub_matrix}')

    return action, mask


if __name__ == '__main__':
    example_state = np.genfromtxt(f'./State.txt', skip_header=1, delimiter=',')[432, 1:].reshape(state_dim)
    action, mask = select_action(agent=agent, state_np=example_state)

    print('Active RSU (rows with True): ', mask)
    print('Selected RSU (2..11) per row: ', action)
    if np.array_equal(action, action * mask):
        print('Pass')
    else:
        print('Error')
    