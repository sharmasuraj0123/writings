"""Every number that appears in a figure of game-timers/. Pure stdlib.

Nothing here is a measurement of a shipped game. Each block states its own
assumptions; the outputs are what those assumptions imply, nothing more.
"""
import json, math
R = {}

# 1 — the player record ---------------------------------------------------------
# packed encoding: type u16, x u8, y u8, level u8, finish_at u32
B_BUILDING = 2 + 1 + 1 + 1 + 4          # 9 bytes
B_WALL     = 2 + 1 + 1                   # type+pos, level folded into type
N_BUILDINGS, N_WALLS = 100, 300
resources  = 4 * (4 + 4)                 # amount u32 + last_collected u32
army       = 200                         # queues, lab, hero levels
progress   = 200                         # counters, unlocks, achievements
packed = N_BUILDINGS*B_BUILDING + N_WALLS*B_WALL + resources + army + progress
json_per_building = len('{"t":123,"x":12,"y":30,"l":8,"f":1790000000},')
json_bytes = (N_BUILDINGS+N_WALLS)*json_per_building + 600
R['record'] = {
  'buildings': N_BUILDINGS, 'walls': N_WALLS,
  'bytes_building': B_BUILDING, 'bytes_wall': B_WALL,
  'packed_bytes': packed, 'packed_kib': round(packed/1024,2),
  'json_bytes': json_bytes, 'json_kib': round(json_bytes/1024,1),
  'json_over_packed': round(json_bytes/packed,1),
}
POP, DAU = 100_000_000, 10_000_000
R['fleet'] = {
  'population': POP, 'dau': DAU,
  'all_players_packed_GB': round(POP*packed/1e9,1),
  'all_players_json_GB': round(POP*json_bytes/1e9,1),
  'dau_resident_GB': round(DAU*packed/1e9,2),
  'machines_at_64GB': math.ceil(DAU*packed/1e9/64),
}

# 2 — lazy resolution against a tick loop ---------------------------------------
OBJ = N_BUILDINGS + N_WALLS            # timer-bearing or accruing fields per player
SESSIONS_PER_DAY = 3
tick_all   = POP * OBJ                        # per second, if every player ticked at 1 Hz
tick_dau   = DAU * OBJ
lazy_res   = DAU * SESSIONS_PER_DAY / 86400   # resolutions per second
lazy_field = lazy_res * OBJ                   # field touches per second
R['lazy'] = {
  'objects_per_player': OBJ, 'sessions_per_day': SESSIONS_PER_DAY,
  'tick_1hz_whole_population_ops_per_s': tick_all,
  'tick_1hz_dau_only_ops_per_s': tick_dau,
  'lazy_resolutions_per_s': round(lazy_res,1),
  'lazy_field_ops_per_s': round(lazy_field),
  'ratio_vs_dau_tick': round(tick_dau/lazy_field),
  'ratio_vs_full_tick': round(tick_all/lazy_field),
  'writes_per_day_lazy': DAU*SESSIONS_PER_DAY,
  'writes_per_s_lazy': round(DAU*SESSIONS_PER_DAY/86400,1),
}

# 3 — a battle as data ----------------------------------------------------------
CMD = 4 + 2 + 1 + 1            # tick u32, unit u16, x u8, y u8
N_CMD = 60
snapshot = packed
replay = snapshot + N_CMD*CMD + 64
VIDEO_S, VIDEO_MBPS = 180, 2.0
video_bytes = VIDEO_S * VIDEO_MBPS*1e6/8
R['replay'] = {
  'bytes_per_command': CMD, 'commands': N_CMD,
  'snapshot_bytes': snapshot, 'replay_bytes': replay, 'replay_kib': round(replay/1024,1),
  'video_seconds': VIDEO_S, 'video_mbps': VIDEO_MBPS,
  'video_bytes': int(video_bytes), 'video_MB': round(video_bytes/1e6,1),
  'ratio': round(video_bytes/replay),
  'attacks_per_dau_per_day': 5,
  'replay_traffic_GB_per_day': round(DAU*5*replay/1e9,1),
  'video_traffic_TB_per_day': round(DAU*5*video_bytes/1e12,1),
}

# 4 — retention arithmetic ------------------------------------------------------
def life(r): return 1/(1-r)
ARPDAU = 0.05
R['retention'] = [{
  'daily_retention': r,
  'expected_days': round(life(r),1),
  'alive_at_d30_pct': round(100*r**30,1),
  'alive_at_d90_pct': round(100*r**90,2),
  'ltv_usd_at_5c': round(life(r)*ARPDAU,2),
} for r in (0.93,0.95,0.96,0.97,0.98,0.99)]
R['retention_note'] = {
  'arpdau_usd': ARPDAU,
  'lift_95_to_96_pct': round(100*(life(0.96)/life(0.95)-1),1),
  'lift_97_to_98_pct': round(100*(life(0.98)/life(0.97)-1),1),
}

# 5 — appointment density -------------------------------------------------------
# a mid-game player's concurrent timers, in hours
timers = {'troop training': 0.25, 'collector overflow': 16.0, 'builder A': 4.0,
          'builder B': 8.0, 'builder C': 24.0, 'builder D': 48.0, 'builder E': 72.0}
rate = sum(24.0/h for h in timers.values())     # completions per day
R['appointments'] = {
  'timers_hours': timers,
  'events_per_day': round(rate,1),
  'mean_gap_hours': round(24/rate,2),
  'without_short_timers_per_day': round(sum(24.0/h for k,h in timers.items() if h >= 4),2),
  'without_short_gap_hours': round(24/sum(24.0/h for k,h in timers.items() if h >= 4),1),
}
# collector overflow: capacity / rate
R['overflow'] = [{'capacity': c, 'rate_per_hour': rt, 'hours_to_full': round(c/rt,1)}
                 for c, rt in ((200_000,12_500),(200_000,6_000),(1_500_000,150_000))]

# 6 — an illustrative skip-price curve ------------------------------------------
# MODEL ONLY: g(t) = K * t^alpha with alpha < 1, anchored so one day costs 500.
alpha, anchor_h, anchor_g = 0.6, 24, 500
K = anchor_g / anchor_h**alpha
USD_PER_GEM = 10.0/1200
def g(h): return round(K*h**alpha)
R['skip'] = {'model': 'gems = K * hours^0.6', 'K': round(K,2), 'usd_per_gem': round(USD_PER_GEM,5),
  'rows': [{'hours': h, 'gems': g(h), 'gems_per_hour': round(g(h)/h,1),
            'usd': round(g(h)*USD_PER_GEM,2), 'usd_per_hour_saved': round(g(h)*USD_PER_GEM/h,3)}
           for h in (1,6,12,24,72,168)]}

print(json.dumps(R, indent=1))
