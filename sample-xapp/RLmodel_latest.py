import os
from pathlib import Path

import numpy as np
import torch
from scipy.optimize import linear_sum_assignment

from ICQL import DQN

device = torch.device('cpu')

base_dir = Path(__file__).resolve().parent
default_model_path = base_dir / 'model' / 'ICQL_HO_Cosine_Lite_20000.pth'
model_path = Path(os.environ.get('XAPP_MODEL_PATH', str(default_model_path))).expanduser()
if not model_path.is_absolute():
    model_path = base_dir / model_path

ckpt = model_path.stem

state_dim, action_dim = (10, 17), (10, 10)
agent = DQN(state_dim=state_dim, action_dim=action_dim).to(device)
if not model_path.is_file():
    raise FileNotFoundError(f'xApp checkpoint not found: {model_path}')

checkpoint = torch.load(str(model_path), map_location=device)
if 'agent_target_state_dict' not in checkpoint:
    raise KeyError(f"Checkpoint {model_path} has no 'agent_target_state_dict' entry")
agent.load_state_dict(checkpoint['agent_target_state_dict'])
agent.eval()
print(f'Loaded xApp checkpoint from {model_path}.')



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
    # A synthetic state is sufficient for a checkpoint-loading smoke test and
    # avoids bundling experiment data with the deployment code.
    example_state = np.zeros(state_dim, dtype=np.float32)
    example_state[0, 0] = 1
    action, mask = select_action(agent=agent, state_np=example_state)

    print('Active RSU (rows with True): ', mask)
    print('Selected RSU (2..11) per row: ', action)
    if np.array_equal(action, action * mask):
        print('Pass')
    else:
        print('Error')
