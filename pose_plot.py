"""실시간 6D 포즈 그래프 (matplotlib, 별도 창)"""

import collections
import time
import numpy as np
import matplotlib
matplotlib.use('GTK3Agg')
import matplotlib.pyplot as plt


# 축별 고정 색상 (X=빨강, Y=초록, Z=파랑) — 3D 관례
T_COLORS = {'x': '#FF3333', 'y': '#33CC33', 'z': '#3366FF'}
R_COLORS = {'x': '#FF6666', 'y': '#66DD66', 'z': '#6699FF'}

# 마커 ID별 선 굵기 (여러 마커 동시 감지 시 구분)
MARKER_LINEWIDTHS = [2.5, 1.5, 1.0, 0.8]
MARKER_STYLES = ['-', '--', '-.', ':']

# 시간축 모드
MODE_ROLLING = "rolling"        # 최근 N초, X축: -5~0
MODE_CUMULATIVE = "cumulative"  # 0초부터 누적, X축: 0~elapsed


class PosePlot:
    def __init__(self, history_sec: float = 5.0):
        self.history_sec = history_sec
        self._active = False
        self._fig = None
        self._ax_t = None
        self._ax_r = None
        self._data = {}           # {marker_id: deque of (timestamp, tx, ty, tz, rx, ry, rz)}
        self._marker_order = []
        self._mode = MODE_ROLLING
        self._start_time = None   # cumulative 모드 기준 시각
        self._interpolate = False  # 보간 OFF가 기본

    @property
    def active(self):
        return self._active

    @property
    def mode(self):
        return self._mode

    @property
    def tracked_markers(self):
        """현재 추적 중인 마커 ID set"""
        return set(self._data.keys())

    @property
    def interpolate(self):
        return self._interpolate

    def toggle_interpolate(self):
        self._interpolate = not self._interpolate
        state = "ON (보간)" if self._interpolate else "OFF (끊김)"
        print(f">> 그래프 보간: {state}")

    def toggle(self):
        if self._active:
            self.close()
        else:
            self.open()

    def toggle_mode(self):
        """rolling ↔ cumulative 전환"""
        if self._mode == MODE_ROLLING:
            self._mode = MODE_CUMULATIVE
            self._start_time = time.time()
            # cumulative: 제한 없이 저장 (maxlen 늘리기)
            for mid in self._data:
                old = self._data[mid]
                self._data[mid] = collections.deque(old, maxlen=50000)
            print(">> 그래프 모드: Cumulative (0초부터 누적)")
        else:
            self._mode = MODE_ROLLING
            self._start_time = None
            # rolling: 다시 500으로 제한
            for mid in self._data:
                old = self._data[mid]
                self._data[mid] = collections.deque(old, maxlen=500)
            print(">> 그래프 모드: Rolling (최근 5초)")

    def open(self):
        if self._active:
            return
        plt.ion()
        self._fig, (self._ax_t, self._ax_r) = plt.subplots(
            2, 1, figsize=(9, 6), num="6D Pose Plot"
        )
        self._fig.set_facecolor('#1e1e1e')
        for ax in (self._ax_t, self._ax_r):
            ax.set_facecolor('#2a2a2a')
            ax.tick_params(colors='#cccccc')
            ax.xaxis.label.set_color('#cccccc')
            ax.yaxis.label.set_color('#cccccc')
            ax.title.set_color('#ffffff')
            for spine in ax.spines.values():
                spine.set_color('#555555')

        self._ax_t.set_title("Translation (m)", fontsize=12, fontweight='bold')
        self._ax_t.set_ylabel("meters")
        self._ax_r.set_title("Rotation (deg)", fontsize=12, fontweight='bold')
        self._ax_r.set_ylabel("degrees")
        self._ax_r.set_xlabel("time (s)")
        self._fig.tight_layout(pad=2.5)
        self._active = True
        self._mode = MODE_ROLLING
        self._start_time = None
        self._data.clear()
        self._marker_order.clear()
        print(">> 그래프 ON (Rolling 모드, T키로 전환)")

    def close(self):
        if self._fig is not None:
            plt.close(self._fig)
            self._fig = None
            self._ax_t = None
            self._ax_r = None
        self._active = False
        print(">> 그래프 OFF")

    def _get_marker_style(self, marker_id):
        if marker_id not in self._marker_order:
            self._marker_order.append(marker_id)
        idx = self._marker_order.index(marker_id)
        lw = MARKER_LINEWIDTHS[idx % len(MARKER_LINEWIDTHS)]
        ls = MARKER_STYLES[idx % len(MARKER_STYLES)]
        return lw, ls

    def add_pose(self, marker_id, tx, ty, tz, rx, ry, rz):
        """포즈 데이터 추가"""
        if not self._active:
            return
        now = time.time()
        if marker_id not in self._data:
            maxlen = 50000 if self._mode == MODE_CUMULATIVE else 500
            self._data[marker_id] = collections.deque(maxlen=maxlen)
        self._data[marker_id].append((now, tx, ty, tz, rx, ry, rz))

    def update(self):
        """그래프 갱신 (메인 루프에서 주기적 호출)"""
        if not self._active or self._fig is None:
            return

        if not plt.fignum_exists(self._fig.number):
            self._active = False
            self._fig = None
            return

        now = time.time()

        self._ax_t.cla()
        self._ax_r.cla()

        # 다크 테마 재적용
        for ax in (self._ax_t, self._ax_r):
            ax.set_facecolor('#2a2a2a')
            ax.tick_params(colors='#cccccc')
            ax.xaxis.label.set_color('#cccccc')
            ax.yaxis.label.set_color('#cccccc')
            ax.title.set_color('#ffffff')

        mode_label = "Rolling" if self._mode == MODE_ROLLING else "Cumulative"
        self._ax_t.set_title(f"Translation (m)  [{mode_label}]", fontsize=12, fontweight='bold')
        self._ax_t.set_ylabel("meters")
        self._ax_r.set_title(f"Rotation (deg)  [{mode_label}]", fontsize=12, fontweight='bold')
        self._ax_r.set_ylabel("degrees")
        self._ax_r.set_xlabel("time (s)")

        for marker_id, dq in self._data.items():
            # rolling 모드: 오래된 데이터 제거
            if self._mode == MODE_ROLLING:
                cutoff = now - self.history_sec
                while dq and dq[0][0] < cutoff:
                    dq.popleft()

            if len(dq) < 2:
                continue

            lw, ls = self._get_marker_style(marker_id)
            arr = np.array(list(dq))

            # 시간축 계산
            if self._mode == MODE_ROLLING:
                t_axis = arr[:, 0] - now  # -5 ~ 0
            else:
                base = self._start_time if self._start_time else arr[0, 0]
                t_axis = arr[:, 0] - base  # 0 ~ elapsed

            prefix = f"ID:{marker_id} " if len(self._data) > 1 else ""

            # Translation
            self._ax_t.plot(t_axis, arr[:, 1], ls, color=T_COLORS['x'],
                            linewidth=lw, alpha=0.95, label=f"{prefix}tx")
            self._ax_t.plot(t_axis, arr[:, 2], ls, color=T_COLORS['y'],
                            linewidth=lw, alpha=0.95, label=f"{prefix}ty")
            self._ax_t.plot(t_axis, arr[:, 3], ls, color=T_COLORS['z'],
                            linewidth=lw, alpha=0.95, label=f"{prefix}tz")

            # Rotation
            self._ax_r.plot(t_axis, arr[:, 4], ls, color=R_COLORS['x'],
                            linewidth=lw, alpha=0.95, label=f"{prefix}rx")
            self._ax_r.plot(t_axis, arr[:, 5], ls, color=R_COLORS['y'],
                            linewidth=lw, alpha=0.95, label=f"{prefix}ry")
            self._ax_r.plot(t_axis, arr[:, 6], ls, color=R_COLORS['z'],
                            linewidth=lw, alpha=0.95, label=f"{prefix}rz")

        # X축 범위
        if self._mode == MODE_ROLLING:
            self._ax_t.set_xlim(-self.history_sec, 0)
            self._ax_r.set_xlim(-self.history_sec, 0)
        else:
            elapsed = now - (self._start_time or now)
            self._ax_t.set_xlim(0, max(elapsed, 1))
            self._ax_r.set_xlim(0, max(elapsed, 1))

        self._ax_t.legend(loc='upper left', fontsize=8, ncol=3,
                          facecolor='#333333', edgecolor='#555555',
                          labelcolor='#eeeeee')
        self._ax_r.legend(loc='upper left', fontsize=8, ncol=3,
                          facecolor='#333333', edgecolor='#555555',
                          labelcolor='#eeeeee')
        self._ax_t.grid(True, alpha=0.2, color='#888888')
        self._ax_r.grid(True, alpha=0.2, color='#888888')

        self._fig.canvas.draw_idle()
        self._fig.canvas.flush_events()
