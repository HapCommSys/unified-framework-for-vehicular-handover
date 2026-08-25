import sys
import torch
import torch.nn as nn
import torch.nn.functional as F
from scipy.optimize import linear_sum_assignment
import torch.optim as optim
import random
from collections import deque
import numpy as np
from itertools import permutations
# from rich.traceback import install
# install(show_locals=True)
# from torch.utils.tensorboard import SummaryWriter
import os

torch.set_printoptions(threshold=float('inf'), linewidth=400)
np.set_printoptions(threshold=float('inf'), linewidth=400)
# writer = SummaryWriter(f'../logs/ICQL/')

MAX_EPISODE = 10000000
WEIGHT = 0.5
PENALTY = 1
# MAX_PENALTY = 100
NUM_STATIONS = 10       # base stations
MAX_CARS = 6         # max active cars you ever see
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
huge_neg = torch.tensor(-1e9, device=device)
MAX_PERMS_PER_N = 5040     # cap per n; you can keep 5040

# def precompute_perms_by_n(num_stations=NUM_STATIONS,
#                           max_cars=MAX_CARS,
#                           device=device):
#     """
#     Precompute permutations of base-station IDs 0..num_stations-1
#     for each possible number of active cars n = 0..max_cars.

#     Returns:
#         perms_by_n: dict mapping n -> tensor [K_n, n],
#         where K_n <= max_perms_per_n.
#     """
#     perms_by_n = {}
#     bs_ids = list(range(num_stations))

#     for n in range(1,max_cars + 1):
#         # if n == 0:
#         #     # no active cars: special trivial case
#         #     perms_by_n[0] = torch.empty((1, 0), dtype=torch.long, device=device)
#         #     continue

#         # all permutations of length n
#         perms_iter = permutations(bs_ids, n)
#         perms_list = []
#         for i, p in enumerate(perms_iter):
#             perms_list.append(p)

#         if len(perms_list) == 0:
#             perms_tensor = torch.empty((0, n), dtype=torch.long, device=device)
#         else:
#             perms_tensor = torch.tensor(perms_list,
#                                         dtype=torch.long,
#                                         device=device)  # [K_n, n]

#         print(f"Precomputed n={n}: {perms_tensor.shape[0]} permutations")
#         perms_by_n[n] = perms_tensor

#     return perms_by_n

# # global lookup: n -> [K_n, n] tensor **already on GPU**
# PERMS_BY_N = precompute_perms_by_n()

# def sample_actions_from_precomputed(valid_indices,
#                                     perms_by_n=PERMS_BY_N,
#                                     max_samples=MAX_PERMS_PER_N,
#                                     device=device):
#     """
#     valid_indices: LongTensor of active car slot indices for this state, e.g. [2,3,5]
#     Returns:
#         actions_bs: [K, NUM_STATIONS] LongTensor on `device`:
#           - positions in valid_indices assigned unique BS IDs per row
#           - other positions = -1
#         where K = min(max_samples, K_n) and K_n = perms_by_n[num_valid].shape[0].
#     """
#     total_size = NUM_STATIONS
#     num_valid = valid_indices.numel()

#     if num_valid == 0:
#         # no cars: one dummy action of all -1
#         return torch.full((1, total_size), -1, dtype=torch.long, device=device)

#     perms_n = perms_by_n[num_valid]   # [K_n, num_valid]
#     K_n = perms_n.size(0)

#     if K_n == 0:
#         # shouldn't happen, but be safe
#         return torch.full((1, total_size), -1, dtype=torch.long, device=device)

#     K = min(max_samples, K_n)

#     if K == K_n:
#         # use all precomputed permutations for this n
#         row_perms = perms_n                           # [K_n, num_valid]
#     else:
#         # sample K rows from the precomputed table
#         idxs = torch.randint(0, K_n, (K,), device=device)
#         row_perms = perms_n[idxs]                     # [K, num_valid]

#     actions = torch.full((row_perms.size(0), total_size),
#                          -1, dtype=torch.long, device=device)    # [K,10]
#     actions[:, valid_indices] = row_perms                        # fill active cars
#     return actions

# def validate_transition_or_die(state_t, action_t, reward_t, state_tp1,
#                               meta=None,
#                               enforce_imsi_mapping_when_count_same=True):
#     """
#     state_t/state_tp1: (10,17)  其中 state[...,0] 为 IMSI(0=无车)
#     action_t: (10,)            0=无车, 否则 2..11 目标基站
#     reward_t: (10,3)           基站维度 reward (inactive 可为 0)

#     meta: dict, 用于打印定位信息，比如 {"exp":a,"S":S,"seed":i,"t":timestamp,"idx":j}
#     """

#     imsi_t = state_t[:, 0].astype(int)
#     imsi_tp1 = state_tp1[:, 0].astype(int)

#     active_t = imsi_t > 0
#     active_tp1 = imsi_tp1 > 0

#     # ---- 1) action 值域与 state_t 的 active 集合一致 ----
#     # inactive 必须为 0（你现在的数据定义就是 0）
#     if not np.all(action_t[~active_t] == 0):
#         _die("Inactive station has non-zero action",
#              meta, imsi_t, action_t, imsi_tp1, extra={
#                  "bad_idx": np.where((~active_t) & (action_t != 0))[0],
#                  "bad_action": action_t[(~active_t) & (action_t != 0)],
#              })

#     # active 必须在 2..11
#     a_active = action_t[active_t]
#     if not np.all((a_active >= 2) & (a_active <= 11)):
#         _die("Active station action out of [2,11]",
#              meta, imsi_t, action_t, imsi_tp1, extra={
#                  "a_active": a_active
#              })

#     # ---- 2) reward 至少要是有限数（不做 latency>0 这种硬断言）----
#     r_active = reward_t[active_t]
#     if r_active.size > 0 and (not np.isfinite(r_active).all()):
#         _die("Active reward contains NaN/Inf",
#              meta, imsi_t, action_t, imsi_tp1, extra={
#                  "r_active": r_active
#              })

#     # inactive reward 建议为 0；如果你确认可能出现非零，就把这段删掉
#     if not np.allclose(reward_t[~active_t], 0.0):
#         _die("Inactive reward is not all zero",
#              meta, imsi_t, action_t, imsi_tp1, extra={
#                  "bad_idx": np.where(~active_t)[0],
#                  "bad_reward_rows": reward_t[~active_t]
#              })

#     # ---- 3) IMSI 对齐校验（只在车数不变的相邻步上强制）----
#     if enforce_imsi_mapping_when_count_same and (active_t.sum() == active_tp1.sum()):
#         tgt_idx = (action_t[active_t] - 2).astype(int)  # 映射到 0..9
#         if not np.all((tgt_idx >= 0) & (tgt_idx < 10)):
#             _die("Target index out of [0,9]",
#                  meta, imsi_t, action_t, imsi_tp1, extra={
#                      "tgt_idx": tgt_idx
#                  })

#         imsi_should = imsi_t[active_t]
#         imsi_got = imsi_tp1[tgt_idx]

#         if not np.all(imsi_got == imsi_should):
#             mismatch_mask = (imsi_got != imsi_should)
#             _die("IMSI mapping mismatch: state_t IMSI not found at next_state target",
#                  meta, imsi_t, action_t, imsi_tp1, extra={
#                      "source_slots": np.where(active_t)[0][mismatch_mask],
#                      "imsi_should": imsi_should[mismatch_mask],
#                      "target_bs": action_t[active_t][mismatch_mask],
#                      "target_slots": tgt_idx[mismatch_mask],
#                      "imsi_got": imsi_got[mismatch_mask],
#                      "imsi_tp1_full": imsi_tp1
#                  })

# def _die(msg, meta, imsi_t, action_t, imsi_tp1, extra=None):
#     print("\n========== DATA CONSISTENCY ERROR ==========")
#     print("Reason:", msg)
#     if meta is not None:
#         print("Meta:", meta)
#     print("state_t IMSI:", imsi_t)
#     print("action_t    :", action_t.astype(int))
#     print("state_tp1 IMSI:", imsi_tp1)
#     if extra:
#         print("Extra:", extra)
#     print("===========================================\n")
#     sys.exit(1)

# # Replay Buffer
# class ReplayBuffer:
#     def __init__(self, ):
#         self.buffer = deque()

#     def add(self, state, action, reward, next_state, done):
#         self.buffer.append((state, action, reward, next_state, done))

#     def sample(self, batch_size):
#         batch = random.sample(self.buffer, batch_size)
#         states, actions, rewards, next_states, done = zip(*batch)
#         states = np.array(states)
#         actions = np.array(actions)
#         rewards = np.array(rewards)
#         next_states = np.array(next_states)
#         done = np.array(done)
#         return (torch.tensor(states, dtype=torch.float32, device=device),
#                 torch.tensor(actions, dtype=torch.long, device=device),
#                 # torch.tensor(rewards, dtype=torch.float32, device=device).unsqueeze(-1),
#                 torch.tensor(rewards, dtype=torch.float32, device=device),      # (1+30, )
#                 torch.tensor(next_states, dtype=torch.float32, device=device),
#                 torch.tensor(done, dtype=torch.float32, device=device))

#     def __len__(self):
#         return len(self.buffer)

#     def __getitem__(self, item):
#         states, actions, rewards, next_states, done = self.buffer[item]
#         return states, actions, rewards, next_states, done


class ParallelMLP(nn.Module):
    """
    实现并行且独立的MLP提取。
    这就好比同时运行 N 个不同的 MLP，但通过矩阵运算一次性完成。
    核心原理：使用 Conv1d 的 groups 参数实现通道隔离。
    """

    def __init__(self, num_branches, input_per_branch, hidden_size, output_size):
        super(ParallelMLP, self).__init__()
        self.num_branches = num_branches

        # 1. 定义网络层
        # 输入通道总数 = 分支数 * 每个分支的特征数
        # groups=num_branches 保证了第 i 组输入只与第 i 组权重运算
        self.conv1 = nn.Conv1d(
            in_channels=num_branches * input_per_branch,
            out_channels=num_branches * hidden_size,
            kernel_size=1,
            groups=num_branches  # 关键参数：实现不共享权重
        )

        self.conv2 = nn.Conv1d(
            in_channels=num_branches * hidden_size,
            out_channels=num_branches * output_size,
            kernel_size=1,
            groups=num_branches  # 关键参数
        )

    def forward(self, x):
        # x shape: (Batch, Num_Branches, Input_Per_Branch)
        b, n, c = x.shape

        # 变换形状以适应 Conv1d: (Batch, N*C, 1)
        # 我们把所有特征拼成一条长向量，让 Conv1d 认为有 N*C 个通道
        x = x.reshape(b, n * c, 1)

        # 执行前向传播 (并行计算)
        x = F.relu(self.conv1(x))
        x = F.relu(self.conv2(x))

        # 恢复形状: (Batch, N*Output, 1) -> (Batch, N, Output)
        x = x.view(b, n, -1)
        return x


class MLP_for_Aggregation(nn.Module):
    def __init__(self, input_size=320, hidden_size=256, output_size=128):
        super(MLP_for_Aggregation, self).__init__()
        self.fc1 = nn.Linear(input_size, hidden_size)
        self.fc2 = nn.Linear(hidden_size, output_size)

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        return x


class Feature_Extraction_and_Aggregation(nn.Module):
    def __init__(self, input_size=(10, 17), hidden_for_extraction=32, hidden_for_aggregation=256,
                 output_for_extraction=32, output_for_aggregation=128):
        super(Feature_Extraction_and_Aggregation, self).__init__()

        self.num_points = input_size[0]  # 10
        self.feat_dim = input_size[1] - 1  # 17 - 1 = 16

        # --- 核心改进 ---
        # 使用 ParallelMLP 替代 ModuleList
        # 这保证了10个点拥有独立的权重，但计算是并行的
        self.extraction = ParallelMLP(
            num_branches=self.num_points,
            input_per_branch=self.feat_dim,
            hidden_size=hidden_for_extraction,
            output_size=output_for_extraction
        )
        self.aggregation = MLP_for_Aggregation(
            input_size=output_for_extraction * self.num_points,
            hidden_size=hidden_for_aggregation,
            output_size=output_for_aggregation
        )

    def forward(self, x):
        # x shape: (Batch, 10, 17)

        # 1. 拆分 Mask 和 特征
        mask, features = x[:, :, 0:1], x[:, :, 1:]

        # 2. 并行特征提取 (不共享权重，无循环)
        # 输入: (Batch, 10, 16) -> 输出: (Batch, 10, 32)
        extracted_features = self.extraction(features)

        # 3. 应用 Mask
        # 利用广播机制: (B, 10, 32) * (B, 10, 1)
        # extracted_features = extracted_features * mask
        # extracted_features = torch.where(mask > 0, extracted_features, 0.0)
        extracted_features = extracted_features * (mask > 0).to(dtype=extracted_features.dtype)

        # 4. 聚合
        batch_size = x.size(0)
        concat_features = extracted_features.view(batch_size, -1)  # 展平
        global_feature = self.aggregation(concat_features)

        return mask, extracted_features, global_feature


class DQN(nn.Module):
    def __init__(self, state_dim=(10, 17), action_dim=(10, 10), extraction_size=(32, 32), aggregation_size=(256, 128), hidden_size=64):
        super(DQN, self).__init__()
        assert state_dim[0] == action_dim[0], "Error: Number of agents in state and action dims must match!"
        self.extraction = Feature_Extraction_and_Aggregation(input_size=state_dim,
                                                             hidden_for_extraction=extraction_size[0],
                                                             hidden_for_aggregation=aggregation_size[0],
                                                             output_for_extraction=extraction_size[1],
                                                             output_for_aggregation=aggregation_size[1])
        self.conv1 = nn.Conv1d(in_channels=state_dim[0] * (extraction_size[1] + aggregation_size[1]),
                               out_channels=state_dim[0] * hidden_size, kernel_size=1, groups=state_dim[0])
        self.conv2 = nn.Conv1d(in_channels=action_dim[0] * hidden_size,
                               out_channels=action_dim[0] * action_dim[1], kernel_size=1, groups=state_dim[0])
        self.register_buffer('huge_neg', torch.tensor(-1e9))
        self.action_dim = action_dim

    def forward(self, state):
        mask, extracted_features, global_feature = self.extraction(state)

        # 准备输入数据
        local_feature = extracted_features
        global_feature = global_feature.unsqueeze(1).expand(-1, self.action_dim[0], -1)
        x = torch.cat([local_feature, global_feature], dim=-1)
        # x shape: (Batch, 10, 160)
        b, n, c = x.shape
        # 变形以适应 Conv1d
        # (Batch, 10, 160) -> (Batch, 1600, 1)
        x = x.reshape(b, n * c, 1)
        x = F.relu(self.conv1(x))
        # 输出 logits
        logits = self.conv2(x)

        # 恢复形状: (Batch, 100, 1) -> (Batch, 10, 10)
        logits = logits.view(b, n, -1)

        # Mask
        logits = torch.where(mask > 0, logits, self.huge_neg)
        return logits


# class Model:
#     def __init__(self, state_dim=(10, 17), action_dim=(10, 10), extraction_size=(32, 32), aggregation_size=(256, 128), hidden_size=64,
#                         lr = 3e-4, alpha = 1.0, initial_penalty = 10, max_update=30000):
#         self.agent = DQN(state_dim, action_dim, extraction_size, aggregation_size, hidden_size).to(device)
#         self.agent_target = DQN(state_dim, action_dim, extraction_size, aggregation_size, hidden_size).to(device)
#         self.agent_target.load_state_dict(self.agent.state_dict())
#         self.agent_optimizer = torch.optim.Adam(self.agent.parameters(), lr=lr)

#         self.replay_buffer = ReplayBuffer()
#         self.gamma = 0.99
#         self.tau = 0.005
#         self.alpha = alpha
#         self.penalty = initial_penalty

#         self.max_update = max_update        # Cosine annealing
#         self.agent_scheduler = optim.lr_scheduler.CosineAnnealingLR(self.agent_optimizer, T_max=max_update, eta_min=1e-5)

#     def update(self, batch_size=64, global_step=0):
#         if len(self.replay_buffer) < batch_size:
#             return

#         states, actions, rewards, next_states, done = self.replay_buffer.sample(batch_size)
#         if rewards.dim() == 1:
#             print(f'{rewards}')
#             sys.exit()

#         masks = states[:, :, 0]
#         next_masks = next_states[:, :, 0]
#         masks = (masks != 0).float()
#         next_masks = (next_masks != 0).float()
#         num_ho, latency, reli = rewards[:, :, 0], rewards[:, :, 1], rewards[:, :, 2]
#         latency = (latency / 20).clamp(max=1)
#         failrate = ((1 - reli) / 0.30).clamp(max=1)
#         rewards = -(num_ho + self.penalty * (WEIGHT * latency + (1 - WEIGHT) * failrate))
#         denom = masks.sum(dim=0).clamp(min=1)
#         print(f'At Episode = {global_step}\nnum_ho = {(num_ho*masks).sum(dim=0)/denom}\n'
#               f'latency = {(latency*masks).sum(dim=0)/denom}\n'
#               f'failrate = {(failrate*masks).sum(dim=0)/denom}\n'
#               f'rewards = {(rewards*masks).sum(dim=0)/denom}.')

#         q_current = self.agent(states)  # [masks[i].nonzero(as_tuple=True)]
#         # if (actions[(masks == 1)] < 2).any():
#         #     print("Warning: Found valid station ID < 2, logic error possible!")
#         # actions = (actions - 2).clamp(min=0).long()
#         # q_values = q_current.gather(dim=-1, index=actions.unsqueeze(-1)).squeeze(-1)
#         active = masks == 1
#         inactive = ~active

#         # 1) 严格校验
#         a_active = actions[active]
#         assert (a_active >= 2).all().item()
#         assert (a_active <= 11).all().item()

#         a_inactive = actions[inactive]
#         assert (a_inactive < 2).all().item()  # 这句建议加上，保证数据一致性

#         # 2) 转成 0~9 的索引；inactive 位置先填 0 防止负 index
#         actions_idx = actions.clone()
#         actions_idx[active] = actions_idx[active] - 2
#         actions_idx[inactive] = 0  # dummy safe index

#         actions_idx = actions_idx.long()

#         # 3) gather
#         q_values = q_current.gather(dim=-1, index=actions_idx.unsqueeze(-1)).squeeze(-1)

#         # 4) 可选：把 inactive 的 q_values 置 0（更干净）
#         q_values = torch.where(active, q_values, torch.zeros_like(q_values))

#         with torch.no_grad():
#             next_q_values = self.agent_target(next_states)
#         q_target = torch.zeros_like(q_values)
#         cql_loss_list = []
#         next_q_values = next_q_values.cpu().numpy()
#         next_masks = next_masks.cpu().numpy()

#         for i in range(batch_size):
#             valid_idx = np.where(next_masks[i] == 1)[0]
#             if len(valid_idx) == 0:
#                 continue
#             sub_matrix = next_q_values[i, valid_idx, :]
#             row, col = linear_sum_assignment(-sub_matrix)
#             q_target[i, valid_idx] = torch.from_numpy(sub_matrix[row, col]).to(device)

#             idx = masks[i].nonzero().squeeze(-1)        # num_valid
#             actions_bs = sample_actions_from_precomputed(valid_indices=idx, perms_by_n=PERMS_BY_N,
#                                                          max_samples=MAX_PERMS_PER_N, device=device)    # [K, 10]
#             K = actions_bs.size(0)
#             # q_tmp = self.agent(states[i].unsqueeze(0).expand(K, -1, -1))    # [K, 10, 10]
#             q_tmp = q_current[i].unsqueeze(0).expand(K, -1, -1)[:, idx, :]    # [K, num_valid, 10]
#             # state_expanded = states[i].unsqueeze(0).expand(K, -1, -1)
#             # q_tmp = self.agent(state_expanded)[:, idx, :]

#             valid_sampled_cols = actions_bs[:, idx]                           # [K, num_valid]
#             q_sample = q_tmp.gather(dim=-1, index=valid_sampled_cols.unsqueeze(-1)).squeeze(-1)
#             q_sample = q_sample.sum(dim=1)
#             q_data = q_values[i, idx].sum()
#             combined_scores = torch.cat([q_data.view(1), q_sample])
#             if torch.isnan(q_sample).any() or torch.isnan(q_data).any():
#                 print(f'Warning: q_sample is {torch.isnan(q_sample).any()}, q_sample is {torch.isnan(q_data).any()}')
#                 continue
#             cql_loss = torch.logsumexp(combined_scores, dim=0) - q_data
#             cql_loss = cql_loss / idx.size(0)
#             cql_loss_list.append(cql_loss)

#         # ===== Bellman target 已就绪 =====
#         q_target = rewards + self.gamma * q_target * (1 - done).view(-1, 1)

#         # ===== 1. 有符号 Bellman 残差 =====
#         residual = q_values - q_target

#         # ===== 2. Q(s,a) 均值（你已经加了，这是对的）=====
#         q_data_mean = (q_values * masks).sum() / masks.sum().clamp(min=1)
#         # writer.add_scalar('Q/q_data_mean', q_data_mean.detach().item(), global_step)

#         # ===== 3. Q_target 均值（新增）=====
#         q_target_mean = (q_target * masks).sum() / masks.sum().clamp(min=1)
#         # writer.add_scalar('Q/q_target_mean', q_target_mean.detach().item(), global_step)

#         # ===== 4. Bellman 残差均值（新增，最关键）=====
#         res_mean = (residual * masks).sum() / masks.sum().clamp(min=1)
#         # writer.add_scalar('Bellman/res_mean', res_mean.detach().item(), global_step)

#         # ===== 5. Bellman 残差绝对值均值（可选但强烈推荐）=====
#         res_abs_mean = (residual.abs() * masks).sum() / masks.sum().clamp(min=1)
#         # writer.add_scalar('Bellman/res_abs_mean', res_abs_mean.detach().item(), global_step)

#         # ===== 原有 TD error =====
#         td_error = torch.where(masks == 1, residual ** 2, 0).sum() / masks.sum().clamp(min=1)
#         if len(cql_loss_list) == 0:
#             cql_loss_global = torch.tensor(0.0, device=device)
#         else:
#             cql_loss_global = torch.stack(cql_loss_list).mean()
#         total_loss = td_error + self.alpha * cql_loss_global
#         # writer.add_scalar('Loss/td_error', td_error.item(), global_step)
#         # writer.add_scalar('Loss/cql_loss', cql_loss_global.item(), global_step)
#         # writer.add_scalar('Loss/total_loss', total_loss.item(), global_step)
#         # print(f'TD Error = {td_error}, CQL Loss = {cql_loss_global}, Total Loss = {total_loss}\n')

#         self.agent_optimizer.zero_grad()
#         total_loss.backward()
#         self.agent_optimizer.step()
#         self.agent_scheduler.step()

#         for t_param, param in zip(self.agent_target.parameters(), self.agent.parameters()):
#             t_param.data.copy_(self.tau * param.data + (1 - self.tau) * t_param.data)

# if __name__ == "__main__":
#     strategy = ["ThresholdSeamless/", "DynamicTttSeamless/", "GreedySeamlessHO/"]
#     seed = 50
#     trainer = Model(state_dim=(10, 17), action_dim=(10, 10), lr = 3e-4, alpha = 1.0, initial_penalty = PENALTY, max_update=MAX_EPISODE//4)
#     single, vehnumchange, num_done = 0, 0, 0
#     for a in [2, 3, 4]:
#         # dataset_path = f"./Dataset/exp=0.{a}/"
#         dataset_path = f'/path/to/Dataset/exp=0.{a}/'
#         for S in [0, 1, 2]:
#             for i in range(1, seed + 1):
#                 state = np.genfromtxt(dataset_path + strategy[S] + f"Seed={i}/State.txt", skip_header=1, delimiter=',')
#                 ts_state = state[:, 0]
#                 state = state[:, 1:].reshape((len(state), 10, 17))
#                 action = np.genfromtxt(dataset_path + strategy[S] + f"Seed={i}/Action.txt", skip_header=1, delimiter=',')
#                 ts_action = action[:, 0]
#                 action = action[:, 1:]
#                 reward = np.genfromtxt(dataset_path + strategy[S] + f"Seed={i}/Reward_.txt", skip_header=1, delimiter=',')
#                 ts_reward = reward[:, 0]
#                 reward = reward[:, 1:].reshape((len(reward), 10, 3))

#                 pending = None  # 缓存上一条“准备加入”的 transition: (s, a, r, s')

#                 for j in range(len(state) - 1):
#                     meta = {
#                         "exp": a,
#                         "S": S,
#                         "seed": i,
#                         "idx": j,
#                         "t_state": float(ts_state[j]),
#                         "t_action": float(ts_action[j]),
#                         "t_reward": float(ts_reward[j]),
#                     }
#                     validate_transition_or_die(
#                         state[j], action[j], reward[j], state[j + 1],
#                         meta=meta,
#                         enforce_imsi_mapping_when_count_same=True
#                     )

#                     # 如果这一跳车数变化：认为轨迹在 state[j] 处断开
#                     if len(state[j][:, 0].nonzero()[0]) != len(state[j + 1][:, 0].nonzero()[0]):
#                         vehnumchange += 1

#                         # 把 pending 的那条作为片段末尾（done=True）写入
#                         if pending is not None:
#                             s_p, a_p, r_p, ns_p = pending
#                             trainer.replay_buffer.add(state=s_p, action=a_p, reward=r_p, next_state=ns_p, done=True)
#                             num_done += 1
#                             pending = None
#                         continue

#                     # 正常连续：先把上一条 pending 写入（done=False）
#                     if pending is not None:
#                         s_p, a_p, r_p, ns_p = pending
#                         trainer.replay_buffer.add(state=s_p, action=a_p, reward=r_p, next_state=ns_p, done=False)
#                     ############################################################
#                     # 更新 pending 为当前这条合法 transition
#                     pending = (state[j], action[j], reward[j], state[j + 1])
#                     ############################################################

#                 # 轨迹结束：pending 作为最后一条（done=True）
#                 if pending is not None:
#                     s_p, a_p, r_p, ns_p = pending
#                     trainer.replay_buffer.add(state=s_p, action=a_p, reward=r_p, next_state=ns_p, done=True)
#                     num_done += 1

#     print(f'single-vehicle: {single}, vehicle number changes: {vehnumchange}, number of dones: {num_done}')
#     print(f"Length of Replay Buffer: {trainer.replay_buffer.__len__()}")

#     for episode in range(MAX_EPISODE):
#         trainer.update(batch_size=256, global_step=episode)
#         if episode % 50000 == 0 and episode > 0:
#             os.makedirs(f'./model/', exist_ok=True)
#             torch.save({
#                 'episode': episode,
#                 'agent_state_dict': trainer.agent.state_dict(),
#                 'agent_target_state_dict': trainer.agent_target.state_dict(),
#                 'agent_optimizer_state_dict': trainer.agent_optimizer.state_dict(),
#                 'agent_scheduler_state_dict': trainer.agent_scheduler.state_dict(),
#             }, f'../model/DQN_{episode}.pth')
