import argparse
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
from torch.utils.tensorboard import SummaryWriter
from pathlib import Path

torch.set_printoptions(threshold=float('inf'), linewidth=400)
np.set_printoptions(threshold=float('inf'), linewidth=400)

script_stem = Path(__file__).resolve().stem


class NullSummaryWriter:
    def add_scalar(self, *args, **kwargs):
        pass

    def close(self):
        pass


writer = NullSummaryWriter()

MAX_EPISODE = 20000
WEIGHT = 0.5
PENALTY = 1
# MAX_PENALTY = 100
NUM_STATIONS = 10  # base stations
MAX_CARS = 6  # max active cars you ever see
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
huge_neg = torch.tensor(-1e9, device=device)
MAX_PERMS_PER_N = 5040  # cap per n; you can keep 5040

LAT_WARN = 15.0
LAT_FORCE = 25.0
REL_WARN = 0.85
REL_FORCE = 0.60

# ---- Lagrangian (dual) hyperparams ----
LAMBDA_LR = 1e-3
LAMBDA_MAX = 10.0

# ---- Constraint thresholds (hard constraints) ----
LAT_TH = LAT_FORCE  # latency <= LAT_FORCE
REL_TH = REL_FORCE  # reliability >= REL_FORCE

# ---- Normalization for violations (optional but建议保留量纲稳定性) ----
LAT_NORM = 10.0  # e.g., 10ms
REL_NORM = 0.10  # e.g., 0.1 reliability


def precompute_perms_by_n(num_stations=NUM_STATIONS, max_cars=MAX_CARS, device=device):
    """
    Precompute permutations of base-station IDs 0..num_stations-1
    for each possible number of active cars n = 0..max_cars.

    Returns:
        perms_by_n: dict mapping n -> tensor [K_n, n], where K_n <= max_perms_per_n.
    """
    perms_by_n = {}
    bs_ids = list(range(num_stations))
    for n in range(1, max_cars + 1):
        # if n == 0:
        #     # no active cars: special trivial case
        #     perms_by_n[0] = torch.empty((1, 0), dtype=torch.long, device=device)
        #     continue

        # all permutations of length n
        perms_iter = permutations(bs_ids, n)
        perms_list = []
        for i, p in enumerate(perms_iter):
            perms_list.append(p)

        if len(perms_list) == 0:
            perms_tensor = torch.empty((0, n), dtype=torch.long, device=device)
        else:
            perms_tensor = torch.tensor(perms_list, dtype=torch.long, device=device)  # [K_n, n]

        print(f"Precomputed n={n}: {perms_tensor.shape[0]} permutations")
        perms_by_n[n] = perms_tensor
    return perms_by_n


# global lookup: n -> [K_n, n] tensor **already on GPU**
PERMS_BY_N = precompute_perms_by_n()


def sample_actions_from_precomputed(
    valid_indices,
    perms_by_n=PERMS_BY_N,
    max_samples=MAX_PERMS_PER_N,
    device=device,
):
    """
    valid_indices: LongTensor of active car slot indices for this state, e.g. [2,3,5]

    Returns:
        actions_bs: [K, NUM_STATIONS] LongTensor on device:
          - positions in valid_indices assigned unique BS IDs per row
          - other positions = -1
        where K = min(max_samples, K_n) and K_n = perms_by_n[num_valid].shape[0].
    """
    total_size = NUM_STATIONS
    num_valid = valid_indices.numel()

    if num_valid == 0:
        # no cars: one dummy action of all -1
        return torch.full((1, total_size), -1, dtype=torch.long, device=device)

    perms_n = perms_by_n[num_valid]  # [K_n, num_valid]
    K_n = perms_n.size(0)

    if K_n == 0:
        # shouldn't happen, but be safe
        return torch.full((1, total_size), -1, dtype=torch.long, device=device)

    K = min(max_samples, K_n)
    if K == K_n:
        # use all precomputed permutations for this n
        row_perms = perms_n  # [K_n, num_valid]
    else:
        # sample K rows from the precomputed table
        idxs = torch.randint(0, K_n, (K,), device=device)
        row_perms = perms_n[idxs]  # [K, num_valid]

    actions = torch.full((row_perms.size(0), total_size), -1, dtype=torch.long, device=device)  # [K,10]
    actions[:, valid_indices] = row_perms  # fill active cars
    return actions


def validate_transition_or_die(
    state_t,
    action_t,
    reward_t,
    state_tp1,
    meta=None,
    enforce_imsi_mapping_when_count_same=True,
):
    """
    state_t/state_tp1: (10,17) 其中 state[...,0] 为 IMSI(0=无车)
    action_t: (10,) 0=无车, 否则 2..11 目标基站
    reward_t: (10,3) 基站维度 reward (inactive 可为 0)
    meta: dict, 用于打印定位信息，比如 {"exp":a,"S":S,"seed":i,"t":timestamp,"idx":j}
    """
    imsi_t = state_t[:, 0].astype(int)
    imsi_tp1 = state_tp1[:, 0].astype(int)

    active_t = imsi_t > 0
    active_tp1 = imsi_tp1 > 0

    # ---- 1) action 值域与 state_t 的 active 集合一致 ----
    # inactive 必须为 0（你现在的数据定义就是 0）
    if not np.all(action_t[~active_t] == 0):
        _die(
            "Inactive station has non-zero action",
            meta,
            imsi_t,
            action_t,
            imsi_tp1,
            extra={
                "bad_idx": np.where((~active_t) & (action_t != 0))[0],
                "bad_action": action_t[(~active_t) & (action_t != 0)],
            },
        )

    # active 必须在 2..11
    a_active = action_t[active_t]
    if not np.all((a_active >= 2) & (a_active <= 11)):
        _die(
            "Active station action out of [2,11]",
            meta,
            imsi_t,
            action_t,
            imsi_tp1,
            extra={"a_active": a_active},
        )

    # ---- 2) reward 至少要是有限数（不做 latency>0 这种硬断言）----
    r_active = reward_t[active_t]
    if r_active.size > 0 and (not np.isfinite(r_active).all()):
        _die(
            "Active reward contains NaN/Inf",
            meta,
            imsi_t,
            action_t,
            imsi_tp1,
            extra={"r_active": r_active},
        )

    # inactive reward 建议为 0；如果你确认可能出现非零，就把这段删掉
    if not np.allclose(reward_t[~active_t], 0.0):
        _die(
            "Inactive reward is not all zero",
            meta,
            imsi_t,
            action_t,
            imsi_tp1,
            extra={
                "bad_idx": np.where(~active_t)[0],
                "bad_reward_rows": reward_t[~active_t],
            },
        )

    # ---- 3) IMSI 对齐校验（只在车数不变的相邻步上强制）----
    if enforce_imsi_mapping_when_count_same and (active_t.sum() == active_tp1.sum()):
        tgt_idx = (action_t[active_t] - 2).astype(int)  # 映射到 0..9
        if not np.all((tgt_idx >= 0) & (tgt_idx < 10)):
            _die(
                "Target index out of [0,9]",
                meta,
                imsi_t,
                action_t,
                imsi_tp1,
                extra={"tgt_idx": tgt_idx},
            )

        imsi_should = imsi_t[active_t]
        imsi_got = imsi_tp1[tgt_idx]

        if not np.all(imsi_got == imsi_should):
            mismatch_mask = (imsi_got != imsi_should)
            _die(
                "IMSI mapping mismatch: state_t IMSI not found at next_state target",
                meta,
                imsi_t,
                action_t,
                imsi_tp1,
                extra={
                    "source_slots": np.where(active_t)[0][mismatch_mask],
                    "imsi_should": imsi_should[mismatch_mask],
                    "target_bs": action_t[active_t][mismatch_mask],
                    "target_slots": tgt_idx[mismatch_mask],
                    "imsi_got": imsi_got[mismatch_mask],
                    "imsi_tp1_full": imsi_tp1,
                },
            )


def _die(msg, meta, imsi_t, action_t, imsi_tp1, extra=None):
    print("\n========== DATA CONSISTENCY ERROR ==========")
    print("Reason:", msg)
    if meta is not None:
        print("Meta:", meta)
    print("state_t IMSI:", imsi_t)
    print("action_t :", action_t.astype(int))
    print("state_tp1 IMSI:", imsi_tp1)
    if extra:
        print("Extra:", extra)
    print("===========================================\n")
    sys.exit(1)


# Replay Buffer
class ReplayBuffer:
    def __init__(self):
        # self.buffer = deque()
        # Two pools for hard resampling:
        # - buffer_trigger: transitions in trigger zone
        # - buffer_normal : other transitions
        self.buffer_trigger = deque()
        self.buffer_normal = deque()

    # def add(self, state, action, reward, next_state, done):
    #     self.buffer.append((state, action, reward, next_state, done))
    def add(self, state, action, reward, next_state, done, is_trigger=False):
        if is_trigger:
            self.buffer_trigger.append((state, action, reward, next_state, done))
        else:
            self.buffer_normal.append((state, action, reward, next_state, done))

    def sample(self, batch_size):
        # batch = random.sample(self.buffer, batch_size)

        # Backward-compatible fallback: uniform over both pools
        all_buf = list(self.buffer_trigger) + list(self.buffer_normal)
        batch = random.sample(all_buf, batch_size)
        states, actions, rewards, next_states, done = zip(*batch)

        states = np.array(states)
        actions = np.array(actions)
        rewards = np.array(rewards)
        next_states = np.array(next_states)
        done = np.array(done)

        return (
            torch.tensor(states, dtype=torch.float32, device=device),
            torch.tensor(actions, dtype=torch.long, device=device),
            # torch.tensor(rewards, dtype=torch.float32, device=device).unsqueeze(-1),
            torch.tensor(rewards, dtype=torch.float32, device=device),  # (1+30, )
            torch.tensor(next_states, dtype=torch.float32, device=device),
            torch.tensor(done, dtype=torch.float32, device=device),
        )

    def sample_mixed(self, batch_size, trigger_ratio=0.5):
        """
        Hard resampling: draw a fixed ratio from trigger pool and the rest from normal pool.
        If either pool is insufficient, automatically fallback to the other pool.
        """
        trigger_ratio = float(np.clip(trigger_ratio, 0.0, 1.0))
        n_tr = int(round(batch_size * trigger_ratio))
        n_no = batch_size - n_tr

        tr = list(self.buffer_trigger)
        no = list(self.buffer_normal)

        # Adjust if pools are insufficient
        if len(tr) < n_tr:
            n_tr = len(tr)
            n_no = batch_size - n_tr
        if len(no) < n_no:
            n_no = len(no)
            n_tr = batch_size - n_no

        batch = []
        if n_tr > 0:
            batch += random.sample(tr, n_tr)
        if n_no > 0:
            batch += random.sample(no, n_no)

        # If still not enough (rare), fallback to uniform over all
        if len(batch) < batch_size:
            all_buf = tr + no
            if len(all_buf) >= batch_size:
                batch = random.sample(all_buf, batch_size)
            else:
                # ultimate fallback: sample with replacement
                batch = [random.choice(all_buf) for _ in range(batch_size)]

        states, actions, rewards, next_states, done = zip(*batch)

        states = np.array(states)
        actions = np.array(actions)
        rewards = np.array(rewards)
        next_states = np.array(next_states)
        done = np.array(done)

        return (
            torch.tensor(states, dtype=torch.float32, device=device),
            torch.tensor(actions, dtype=torch.long, device=device),
            torch.tensor(rewards, dtype=torch.float32, device=device),
            torch.tensor(next_states, dtype=torch.float32, device=device),
            torch.tensor(done, dtype=torch.float32, device=device),
        )

    def __len__(self):
        # return len(self.buffer)
        return len(self.buffer_trigger) + len(self.buffer_normal)

    def __getitem__(self, item):
        # states, actions, rewards, next_states, done = self.buffer[item]
        # return states, actions, rewards, next_states, done

        # Provide deterministic indexing over the concatenated pools.
        # NOTE: this is rarely used in training; kept for compatibility/debugging.
        tr_len = len(self.buffer_trigger)
        if item < tr_len:
            return self.buffer_trigger[item]
        else:
            return self.buffer_normal[item - tr_len]


def analyze_ho_ratio(replay_buffer):
    def count_ho(buffer):
        ho_cnt = 0
        total = len(buffer)
        for (state, action, reward, next_state, done) in buffer:
            imsi = state[:, 0]  # (10,)
            active = imsi != 0
            if not active.any():
                continue

            # 当前连接的 BS（由 next_state 的 IMSI 对齐保证）
            # 但更稳妥：直接用 reward[:,0] 是否 >0（num_ho）
            # 你 reward[:,0] 就是 num_ho
            num_ho = reward[:, 0]
            if (num_ho > 0).any():
                ho_cnt += 1
        ratio = ho_cnt / max(total, 1)
        return ho_cnt, total, ratio

    tr_ho, tr_total, tr_ratio = count_ho(replay_buffer.buffer_trigger)
    no_ho, no_total, no_ratio = count_ho(replay_buffer.buffer_normal)

    print("\n====== HO Statistics ======")
    print(f"Trigger buffer : HO {tr_ho}/{tr_total} = {tr_ratio*100:.2f}%")
    print(f"Normal buffer : HO {no_ho}/{no_total} = {no_ratio*100:.2f}%")
    print("===========================\n")

    return {
        "trigger": tr_ratio,
        "normal": no_ratio,
    }


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
            groups=num_branches,  # 关键参数：实现不共享权重
        )

        self.conv2 = nn.Conv1d(
            in_channels=num_branches * hidden_size,
            out_channels=num_branches * output_size,
            kernel_size=1,
            groups=num_branches,  # 关键参数
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
    def __init__(
        self,
        input_size=(10, 17),
        hidden_for_extraction=32,
        hidden_for_aggregation=256,
        output_for_extraction=32,
        output_for_aggregation=128,
    ):
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
            output_size=output_for_extraction,
        )

        self.aggregation = MLP_for_Aggregation(
            input_size=output_for_extraction * self.num_points,
            hidden_size=hidden_for_aggregation,
            output_size=output_for_aggregation,
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
        extracted_features = torch.where(mask > 0, extracted_features, 0)

        # 4. 聚合
        batch_size = x.size(0)
        concat_features = extracted_features.view(batch_size, -1)  # 展平
        global_feature = self.aggregation(concat_features)

        return mask, extracted_features, global_feature


class DQN(nn.Module):
    def __init__(
        self,
        state_dim=(10, 17),
        action_dim=(10, 10),
        extraction_size=(32, 32),
        aggregation_size=(256, 128),
        hidden_size=64,
    ):
        super(DQN, self).__init__()
        assert state_dim[0] == action_dim[0], "Error: Number of agents in state and action dims must match!"

        self.extraction = Feature_Extraction_and_Aggregation(
            input_size=state_dim,
            hidden_for_extraction=extraction_size[0],
            hidden_for_aggregation=aggregation_size[0],
            output_for_extraction=extraction_size[1],
            output_for_aggregation=aggregation_size[1],
        )

        self.conv1 = nn.Conv1d(
            in_channels=state_dim[0] * (extraction_size[1] + aggregation_size[1]),
            out_channels=state_dim[0] * hidden_size,
            kernel_size=1,
            groups=state_dim[0],
        )

        self.conv2 = nn.Conv1d(
            in_channels=action_dim[0] * hidden_size,
            out_channels=action_dim[0] * action_dim[1],
            kernel_size=1,
            groups=state_dim[0],
        )

        self.register_buffer('huge_neg', torch.tensor(-1e9))
        self.action_dim = action_dim

    def forward(self, state):
        mask, extracted_features, global_feature = self.extraction(state)

        # 准备输入数据
        local_feature = extracted_features
        global_feature = global_feature.unsqueeze(1).expand(-1, self.action_dim[0], -1)
        x = torch.cat([local_feature, global_feature], dim=-1)  # x shape: (Batch, 10, 160)

        b, n, c = x.shape

        # 变形以适应 Conv1d
        # (Batch, 10, 160) -> (Batch, 1600, 1)
        x = x.reshape(b, n * c, 1)
        x = F.relu(self.conv1(x))

        # 输出 logits
        logits = self.conv2(x)

        # 恢复形状: (Batch, 100, 1) -> (Batch, 10, 10)
        logits = logits.view(b, n, -1)

        # Mask logits
        logits = torch.where(mask > 0, logits, self.huge_neg)
        return logits


class Model:
    def __init__(
        self,
        state_dim=(10, 17),
        action_dim=(10, 10),
        extraction_size=(32, 32),
        aggregation_size=(256, 128),
        hidden_size=64,
        lr=3e-4,
        alpha=1.0,
        initial_penalty=10,
        max_update=30000,
        weight=1.0,
    ):
        self.agent = DQN(state_dim, action_dim, extraction_size, aggregation_size, hidden_size).to(device)
        self.agent_target = DQN(state_dim, action_dim, extraction_size, aggregation_size, hidden_size).to(device)
        self.agent_target.load_state_dict(self.agent.state_dict())
        self.agent_optimizer = torch.optim.Adam(self.agent.parameters(), lr=lr)

        self.replay_buffer = ReplayBuffer()

        self.gamma = 0.99
        self.tau = 0.005
        self.alpha = alpha
        self.penalty = initial_penalty
        self.max_update = max_update

        # Cosine annealing
        self.agent_scheduler = optim.lr_scheduler.CosineAnnealingLR(
            self.agent_optimizer,
            T_max=max_update,
            eta_min=1e-5,
        )

        # ---- Dynamic trigger_ratio schedule for hard resampling ----
        # High at early training (force model to see trigger transitions more often),
        # then gradually decay to a lower ratio (avoid overfitting trigger zone).
        self.trigger_ratio_start = 0.50
        self.trigger_ratio_end = 0.10

        # Decay horizon in updates (not episodes of data collection)
        # Using ~25% of max_update as default; adjust as needed.
        self.trigger_ratio_decay_steps = max(1, int(1 * self.max_update))

        self.cql_ho_weight = weight
        self.td_ho_weight = weight

        self.lambda_lat = torch.tensor(0.0, device=device)
        self.lambda_rel = torch.tensor(0.0, device=device)
        self.lambda_lr = LAMBDA_LR
        self.lambda_max = LAMBDA_MAX

    def compute_trigger(self, latency_raw, reli_raw):
        """
        latency_raw, reli_raw: shape [B, 10] (only active entries are meaningful)
        return g: shape [B, 10] in [0,1]
        """
        # ---- thresholds (you can tune later) ----
        # lat_warn, lat_bad = 18.0, 20.0
        # rel_warn, rel_bad = 0.80, 0.70  # note rel_bad < rel_warn

        # Trigger zone definition:
        # - latency: allow slightly larger delay
        # - reliability: stricter requirement
        lat_warn, lat_bad = LAT_WARN, LAT_FORCE
        rel_warn, rel_bad = REL_WARN, REL_FORCE

        # latency trigger: 0 below warn, 1 above bad
        g_lat = ((latency_raw - lat_warn) / (lat_bad - lat_warn)).clamp(0.0, 1.0)

        # reliability trigger: 0 above warn, 1 below bad
        g_rel = ((rel_warn - reli_raw) / (rel_warn - rel_bad)).clamp(0.0, 1.0)

        g = torch.maximum(g_lat, g_rel)
        return g

    def get_trigger_ratio(self, global_step: int) -> float:
        # """
        # Dynamic trigger_ratio for hard resampling.
        # Linear schedule: start -> end over trigger_ratio_decay_steps, then stay at end.
        # """
        # t = float(np.clip(global_step / float(self.trigger_ratio_decay_steps), 0.0, 1.0))
        # return (1.0 - t) * self.trigger_ratio_start + t * self.trigger_ratio_end

        """
        Cosine schedule: start -> end over trigger_ratio_decay_steps, then stay at end.
        """
        # progress in [0, 1]
        t = float(np.clip(global_step / float(self.trigger_ratio_decay_steps), 0.0, 1.0))
        # cosine annealing factor in [1 -> 0]
        c = 0.5 * (1.0 + np.cos(np.pi * t))
        # interpolate: t=0 => start, t=1 => end
        return self.trigger_ratio_end + (self.trigger_ratio_start - self.trigger_ratio_end) * c

    def update(self, batch_size=64, global_step=0):
        if len(self.replay_buffer) < batch_size:
            return

        # states, actions, rewards, next_states, done = self.replay_buffer.sample(batch_size)

        # ---- Hard resampling with dynamic trigger_ratio ----
        trig_ratio = self.get_trigger_ratio(global_step)
        states, actions, rewards, next_states, done = self.replay_buffer.sample_mixed(
            batch_size=batch_size,
            trigger_ratio=trig_ratio,
        )

        if rewards.dim() == 1:
            print(f'{rewards}')
            sys.exit()

        masks = states[:, :, 0]
        next_masks = next_states[:, :, 0]
        masks = (masks != 0).long()
        next_masks = (next_masks != 0).long()

        # ----- reward decomposition (RAW first; do NOT mix with normalized scales) -----
        num_ho = rewards[:, :, 0]
        is_ho = (num_ho > 0).float()
        latency_raw = rewards[:, :, 1]
        reli_raw = rewards[:, :, 2]

        # ----- reward shaping uses NORMALIZED terms (separate from trigger thresholds) -----
        latency = (latency_raw / 20).clamp(max=1)
        failrate = ((1 - reli_raw) / 0.30).clamp(max=1)

        # rewards = -(num_ho + self.penalty * (WEIGHT * latency + (1 - WEIGHT) * failrate))  # basic version

        # 主目标：最小化 HO
        reward_main = -num_ho

        # 约束违约（只在 active 上计入）
        lat_violation = ((latency_raw - LAT_TH).clamp(min=0.0) / LAT_NORM).clamp(max=5.0) * masks
        rel_violation = ((REL_TH - reli_raw).clamp(min=0.0) / REL_NORM).clamp(max=5.0) * masks

        # 拉格朗日奖励：r - lambda * cost
        rewards = reward_main - self.lambda_lat * lat_violation - self.lambda_rel * rel_violation

        denom = masks.sum(dim=0).clamp(min=1)
        print(
            f'At Episode = {global_step}\nnum_ho = {(num_ho*masks).sum(dim=0)/denom}\n'
            f'latency = {(latency*masks).sum(dim=0)/denom}\n'
            f'failrate = {(failrate*masks).sum(dim=0)/denom}\n'
            f'rewards = {(rewards*masks).sum(dim=0)/denom}.'
            f'reward_total = {(rewards * masks).sum(dim=0) / denom}.\n'
        )

        q_current = self.agent(states)  # [masks[i].nonzero(as_tuple=True)]
        active = masks == 1
        inactive = ~active

        # 1) 严格校验
        a_active = actions[active]
        assert (a_active >= 2).all().item()
        assert (a_active <= 11).all().item()

        a_inactive = actions[inactive]
        assert (a_inactive < 2).all().item()  # 这句建议加上，保证数据一致性

        # 2) 转成 0~9 的索引；inactive 位置先填 0 防止负 index
        actions_idx = actions.clone()
        actions_idx[active] = actions_idx[active] - 2
        actions_idx[inactive] = 0  # dummy safe index
        actions_idx = actions_idx.long()

        # 3) gather
        q_values = q_current.gather(dim=-1, index=actions_idx.unsqueeze(-1)).squeeze(-1)

        # 4) 可选：把 inactive 的 q_values 置 0（更干净）
        q_values = torch.where(active, q_values, torch.zeros_like(q_values))

        with torch.no_grad():
            next_q_online = self.agent(next_states)  # 用于 Hungarian 选匹配
            next_q_targ = self.agent_target(next_states)  # 用于取值评估

        q_target = torch.zeros_like(q_values)
        cql_loss_list = []
        cql_w_list = []

        next_q_online = next_q_online.cpu().numpy()
        next_q_targ = next_q_targ.cpu().numpy()
        next_masks_np = next_masks.cpu().numpy()

        for i in range(batch_size):
            valid_idx = np.where(next_masks_np[i] == 1)[0]
            if len(valid_idx) == 0:
                continue

            sub_online = next_q_online[i, valid_idx, :]
            row, col = linear_sum_assignment(-sub_online)

            sub_targ = next_q_targ[i, valid_idx, :]
            q_target[i, valid_idx] = torch.from_numpy(sub_targ[row, col]).to(device)

            idx = masks[i].nonzero().squeeze(-1)  # num_valid
            actions_bs = sample_actions_from_precomputed(
                valid_indices=idx,
                perms_by_n=PERMS_BY_N,
                max_samples=MAX_PERMS_PER_N,
                device=device,
            )  # [K, 10]

            ho_any = (num_ho[i, idx] > 0).float().max()
            w_i = 1.0 + self.cql_ho_weight * ho_any

            K = actions_bs.size(0)

            # q_tmp = self.agent(states[i].unsqueeze(0).expand(K, -1, -1))  # [K, 10, 10]
            q_tmp = q_current[i].unsqueeze(0).expand(K, -1, -1)[:, idx, :]  # [K, num_valid, 10]
            valid_sampled_cols = actions_bs[:, idx]  # [K, num_valid]

            q_sample = q_tmp.gather(dim=-1, index=valid_sampled_cols.unsqueeze(-1)).squeeze(-1)
            q_sample = q_sample.sum(dim=1)

            q_data = q_values[i, idx].sum()

            combined_scores = torch.cat([q_data.view(1), q_sample])
            if torch.isnan(q_sample).any() or torch.isnan(q_data).any():
                print(
                    f'Warning: q_sample is {torch.isnan(q_sample).any()}, '
                    f'q_sample is {torch.isnan(q_data).any()}'
                )
                continue

            cql_loss = torch.logsumexp(combined_scores, dim=0) - q_data
            cql_loss = cql_loss / idx.size(0)

            cql_loss_list.append(cql_loss * w_i)
            cql_w_list.append(w_i.detach())

        # ===== Bellman target 已就绪 =====
        q_target = rewards + self.gamma * q_target * (1 - done).view(-1, 1)

        residual = (q_values.sum(dim=1) - q_target.sum(dim=1)) / masks.sum(dim=1).clamp(min=1)

        # td_error = ((residual ** 2) * td_weight * masks).sum() / masks.sum().clamp(min=1)
        ho_any = ((num_ho > 0).float() * masks).amax(dim=1)
        td_weight = (1.0 + self.td_ho_weight * ho_any).detach()
        td_error = (td_weight * (residual ** 2)).sum() / td_weight.sum().clamp(min=1)

        if len(cql_loss_list) == 0:
            cql_loss_global = torch.tensor(0.0, device=device)
        else:
            # cql_loss_global = torch.stack(cql_loss_list).mean()
            cql_loss_global = torch.stack(cql_loss_list)
            w_stack = torch.stack(cql_w_list)
            cql_loss_global = cql_loss_global.sum() / w_stack.sum()

        total_loss = td_error + self.alpha * cql_loss_global

        writer.add_scalar('Loss/td_error', td_error.item(), global_step)
        writer.add_scalar('Loss/cql_loss', cql_loss_global.item(), global_step)
        writer.add_scalar('Loss/total_loss', total_loss.item(), global_step)

        print(f'TD Error = {td_error}, CQL Loss = {cql_loss_global}, Total Loss = {total_loss}\n')

        # Log dynamic sampling ratio and pool sizes (helps debugging)
        writer.add_scalar('Replay/trigger_ratio', trig_ratio, global_step)
        writer.add_scalar('Replay/buf_trigger', len(self.replay_buffer.buffer_trigger), global_step)
        writer.add_scalar('Replay/buf_normal', len(self.replay_buffer.buffer_normal), global_step)
        writer.add_scalar('Loss/td_weight_mean', td_weight.mean().item(), global_step)
        writer.add_scalar('Loss/td_weight_max', td_weight.max().item(), global_step)

        self.agent_optimizer.zero_grad()
        total_loss.backward()
        self.agent_optimizer.step()
        self.agent_scheduler.step()

        with torch.no_grad():
            # ===== Dual update uses UNBIASED sampling from the whole dataset =====
            s_u, a_u, r_u, ns_u, d_u = self.replay_buffer.sample(batch_size)  # uniform over all data

            m_u = (s_u[:, :, 0] != 0).float()  # use float mask for safe division/clamp
            lat_u = r_u[:, :, 1]
            rel_u = r_u[:, :, 2]

            lat_v_u = ((lat_u - LAT_TH).clamp(min=0.0) / LAT_NORM).clamp(max=5.0) * m_u
            rel_v_u = ((REL_TH - rel_u).clamp(min=0.0) / REL_NORM).clamp(max=5.0) * m_u

            denom_u = m_u.sum().clamp(min=1.0)
            mean_lat_v = lat_v_u.sum() / denom_u
            mean_rel_v = rel_v_u.sum() / denom_u

            self.lambda_lat = (self.lambda_lat + self.lambda_lr * mean_lat_v).clamp(0.0, self.lambda_max)
            self.lambda_rel = (self.lambda_rel + self.lambda_lr * mean_rel_v).clamp(0.0, self.lambda_max)

            writer.add_scalar('Lambda/lambda_lat', self.lambda_lat.item(), global_step)
            writer.add_scalar('Lambda/lambda_rel', self.lambda_rel.item(), global_step)
            writer.add_scalar('Constraint/mean_lat_violation_unbiased', mean_lat_v.item(), global_step)
            writer.add_scalar('Constraint/mean_rel_violation_unbiased', mean_rel_v.item(), global_step)

        for t_param, param in zip(self.agent_target.parameters(), self.agent.parameters()):
            t_param.data.copy_(self.tau * param.data + (1 - self.tau) * t_param.data)


def save_checkpoint(trainer, output_file, episode):
    output_file.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            'episode': episode,
            'agent_state_dict': trainer.agent.state_dict(),
            'agent_target_state_dict': trainer.agent_target.state_dict(),
            'agent_optimizer_state_dict': trainer.agent_optimizer.state_dict(),
            'agent_scheduler_state_dict': trainer.agent_scheduler.state_dict(),
        },
        str(output_file),
    )
    print('Saved checkpoint:', output_file)


def parse_args():
    parser = argparse.ArgumentParser(description='Train the offline CQL-DDQN handover policy.')
    parser.add_argument(
        '--dataset-root',
        type=Path,
        required=True,
        help='directory containing exp=<value>/<strategy>/Seed=<n> datasets',
    )
    parser.add_argument('--log-dir', type=Path, default=Path('logs') / script_stem)
    parser.add_argument('--output-dir', type=Path, default=Path('model'))
    parser.add_argument('--run-name', default=script_stem)
    parser.add_argument('--episodes', type=int, default=MAX_EPISODE)
    parser.add_argument('--checkpoint-interval', type=int, default=4000)
    parser.add_argument('--batch-size', type=int, default=128)
    parser.add_argument('--num-seeds', type=int, default=100)
    parser.add_argument('--random-seed', type=int, default=0)
    parser.add_argument('--experiments', nargs='+', default=['0.1', '0.2', '0.3', '0.4'])
    parser.add_argument(
        '--strategies',
        nargs='+',
        default=['ThresholdSeamless', 'DynamicTttSeamless', 'GreedySeamlessHO'],
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.episodes < 1:
        raise ValueError('--episodes must be positive')
    if args.checkpoint_interval < 1:
        raise ValueError('--checkpoint-interval must be positive')
    if args.batch_size < 1:
        raise ValueError('--batch-size must be positive')
    if args.num_seeds < 1:
        raise ValueError('--num-seeds must be positive')
    if not args.dataset_root.is_dir():
        raise FileNotFoundError('Dataset root not found: {}'.format(args.dataset_root))

    random.seed(args.random_seed)
    np.random.seed(args.random_seed)
    torch.manual_seed(args.random_seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.random_seed)

    args.log_dir.mkdir(parents=True, exist_ok=True)
    writer = SummaryWriter(log_dir=args.log_dir.as_posix())
    print('TensorBoard log directory:', args.log_dir)
    print('Training device:', device)

    trainer = Model(
        state_dim=(10, 17),
        action_dim=(10, 10),
        lr=3e-4,
        alpha=1.0,
        initial_penalty=PENALTY,
        max_update=args.episodes,
    )

    vehnumchange, num_done = 0, 0
    loaded_seed_directories = 0

    for experiment in args.experiments:
        dataset_path = args.dataset_root / ('exp=' + experiment)

        for S, strategy_name in enumerate(args.strategies):
            for i in range(1, args.num_seeds + 1):
                seed_dir = dataset_path / strategy_name / f"Seed={i}"

                state_file = seed_dir / "State.txt"
                action_file = seed_dir / "Action.txt"
                reward_file = seed_dir / "Reward_.txt"

                if not state_file.is_file() or not action_file.is_file() or not reward_file.is_file():
                    print(f"[Skip] Missing file(s): {seed_dir}")
                    continue

                loaded_seed_directories += 1

                state_raw = np.atleast_2d(
                    np.genfromtxt(state_file, skip_header=1, delimiter=',')
                )
                action_raw = np.atleast_2d(
                    np.genfromtxt(action_file, skip_header=1, delimiter=',')
                )
                reward_raw = np.atleast_2d(
                    np.genfromtxt(reward_file, skip_header=1, delimiter=',')
                )

                expected_columns = {'State.txt': 171, 'Action.txt': 11, 'Reward_.txt': 31}
                observed_columns = {
                    'State.txt': state_raw.shape[1],
                    'Action.txt': action_raw.shape[1],
                    'Reward_.txt': reward_raw.shape[1],
                }
                for file_name, expected in expected_columns.items():
                    if observed_columns[file_name] != expected:
                        raise ValueError(
                            '{} in {} has {} columns; expected {}'.format(
                                file_name, seed_dir, observed_columns[file_name], expected
                            )
                        )

                if not (len(state_raw) == len(action_raw) == len(reward_raw)):
                    raise ValueError('Dataset row counts do not match in {}'.format(seed_dir))

                ts_state = state_raw[:, 0]
                ts_action = action_raw[:, 0]
                ts_reward = reward_raw[:, 0]
                if not (
                    np.allclose(ts_state, ts_action, rtol=0.0, atol=1e-6)
                    and np.allclose(ts_state, ts_reward, rtol=0.0, atol=1e-6)
                ):
                    raise ValueError('Dataset timestamps do not align in {}'.format(seed_dir))

                state = state_raw[:, 1:].reshape((len(state_raw), 10, 17))
                action = action_raw[:, 1:]
                reward = reward_raw[:, 1:].reshape((len(reward_raw), 10, 3))

                pending = None  # 缓存上一条“准备加入”的 transition: (s, a, r, s')
                for j in range(len(state) - 1):
                    meta = {
                        "exp": experiment,
                        "S": S,
                        "seed": i,
                        "idx": j,
                        "t_state": float(ts_state[j]),
                        "t_action": float(ts_action[j]),
                        "t_reward": float(ts_reward[j]),
                    }

                    validate_transition_or_die(
                        state[j],
                        action[j],
                        reward[j],
                        state[j + 1],
                        meta=meta,
                        enforce_imsi_mapping_when_count_same=True,
                    )

                    # 如果这一跳车数变化：认为轨迹在 state[j] 处断开
                    if len(state[j][:, 0].nonzero()[0]) != len(state[j + 1][:, 0].nonzero()[0]):
                        vehnumchange += 1

                        # 把 pending 的那条作为片段末尾（done=True）写入
                        if pending is not None:
                            s_p, a_p, r_p, ns_p = pending
                            # trainer.replay_buffer.add(state=s_p, action=a_p, reward=r_p, next_state=ns_p, done=True)

                            # ---- classify trigger transition (numpy) ----
                            # active mask based on IMSI
                            imsi_mask = (s_p[:, 0] != 0)
                            num_ho = r_p[:, 0]  # reward 的第 0 维：10 维向量，发生 HO 的位置为 1
                            is_trigger = bool(np.any((num_ho > 0) & imsi_mask))

                            trainer.replay_buffer.add(
                                state=s_p,
                                action=a_p,
                                reward=r_p,
                                next_state=ns_p,
                                done=True,
                                is_trigger=is_trigger,
                            )
                            num_done += 1

                        pending = None
                        continue

                    # 正常连续：先把上一条 pending 写入（done=False）
                    if pending is not None:
                        s_p, a_p, r_p, ns_p = pending
                        # trainer.replay_buffer.add(state=s_p, action=a_p, reward=r_p, next_state=ns_p, done=False)

                        imsi_mask = (s_p[:, 0] != 0)
                        num_ho = r_p[:, 0]  # reward 的第 0 维：10 维向量，发生 HO 的位置为 1
                        is_trigger = bool(np.any((num_ho > 0) & imsi_mask))

                        trainer.replay_buffer.add(
                            state=s_p,
                            action=a_p,
                            reward=r_p,
                            next_state=ns_p,
                            done=False,
                            is_trigger=is_trigger,
                        )

                    ############################################################
                    # 更新 pending 为当前这条合法 transition
                    pending = (state[j], action[j], reward[j], state[j + 1])
                    ############################################################

                # 轨迹结束：pending 作为最后一条（done=True）
                if pending is not None:
                    s_p, a_p, r_p, ns_p = pending
                    # trainer.replay_buffer.add(state=s_p, action=a_p, reward=r_p, next_state=ns_p, done=True)

                    imsi_mask = (s_p[:, 0] != 0)
                    num_ho = r_p[:, 0]  # reward 的第 0 维：10 维向量，发生 HO 的位置为 1
                    is_trigger = bool(np.any((num_ho > 0) & imsi_mask))

                    trainer.replay_buffer.add(
                        state=s_p,
                        action=a_p,
                        reward=r_p,
                        next_state=ns_p,
                        done=True,
                        is_trigger=is_trigger,
                    )
                    num_done += 1

    replay_buffer_size = len(trainer.replay_buffer)
    print(f'vehicle number changes: {vehnumchange}, number of dones: {num_done}')
    print(f'Loaded seed directories: {loaded_seed_directories}')
    print(f'Length of Replay Buffer: {replay_buffer_size}')

    if replay_buffer_size < args.batch_size:
        writer.close()
        raise RuntimeError(
            'The replay buffer contains {} transitions, fewer than --batch-size {}. '
            'Check --dataset-root and the documented dataset layout.'.format(
                replay_buffer_size, args.batch_size
            )
        )

    analyze_ho_ratio(trainer.replay_buffer)

    for episode in range(1, args.episodes + 1):
        trainer.update(batch_size=args.batch_size, global_step=episode)

        if episode % args.checkpoint_interval == 0 and episode > 0:
            save_checkpoint(
                trainer,
                args.output_dir / '{}_{}.pth'.format(args.run_name, episode),
                episode,
            )

    if args.episodes % args.checkpoint_interval != 0:
        save_checkpoint(
            trainer,
            args.output_dir / '{}_{}.pth'.format(args.run_name, args.episodes),
            args.episodes,
        )
    writer.close()
