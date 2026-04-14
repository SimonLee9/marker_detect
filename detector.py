"""마커 감지 + 6D 포즈 추정 + OSD + CSV 기록 + 실시간 그래프 (카메라 독립)"""

import cv2
import numpy as np
import csv
import time
from datetime import datetime
from marker_detector.pose_plot import PosePlot


MARKER_DICTS = {
    "ArUco 4x4_50":   cv2.aruco.DICT_4X4_50,
    "ArUco 6x6_250":  cv2.aruco.DICT_6X6_250,
    "AprilTag 36h11": cv2.aruco.DICT_APRILTAG_36H11,
    "AprilTag 25h9":  cv2.aruco.DICT_APRILTAG_25H9,
}

DICT_NAMES = list(MARKER_DICTS.keys())
DICT_VALUES = list(MARKER_DICTS.values())


RESOLUTION_LABELS = ["640x360", "640x480", "1280x720", "1920x1080"]
FPS_LABELS = ["15", "30", "60"]


class MarkerDetector:
    def __init__(self, marker_size: float = 0.05):
        self.marker_size = marker_size
        self.current_dict_idx = 0
        self.show_pose = True
        self.recording = False
        self._csv_file = None
        self._csv_writer = None
        self._aruco_dict, self._det_params = self._make_detector(0)
        self._pose_plot = PosePlot(history_sec=5.0)
        self._plot_update_counter = 0
        self._cam_config = None
        self._res_idx = 0
        self._fps_idx = 0
        self._camera_type = ""
        self._available_cameras = []

    def set_camera_info(self, cam_config, res_idx, fps_idx, camera_type="", available_cameras=None):
        self._cam_config = cam_config
        self._res_idx = res_idx
        self._fps_idx = fps_idx
        self._camera_type = camera_type
        if available_cameras is not None:
            self._available_cameras = available_cameras

    def _make_detector(self, dict_idx):
        aruco_dict = cv2.aruco.getPredefinedDictionary(DICT_VALUES[dict_idx])
        params = cv2.aruco.DetectorParameters_create()
        if "AprilTag" in DICT_NAMES[dict_idx]:
            # AprilTag: SUBPIX 사용 (APRILTAG 리파인은 매우 느림)
            params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
            params.cornerRefinementMaxIterations = 10
            # 검출 속도 향상: 적응 임계값 윈도우/스텝 축소
            params.adaptiveThreshWinSizeMin = 5
            params.adaptiveThreshWinSizeMax = 21
            params.adaptiveThreshWinSizeStep = 4
        else:
            params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        return aruco_dict, params

    def switch_dict(self, idx: int):
        if 0 <= idx < len(DICT_NAMES):
            self.current_dict_idx = idx
            self._aruco_dict, self._det_params = self._make_detector(idx)
            print(f">> 딕셔너리 변경: {DICT_NAMES[idx]}")

    def toggle_pose(self):
        self.show_pose = not self.show_pose
        print(f">> 포즈 추정: {'ON' if self.show_pose else 'OFF'}")

    def toggle_graph(self):
        self._pose_plot.toggle()

    def toggle_graph_mode(self):
        if self._pose_plot.active:
            self._pose_plot.toggle_mode()
        else:
            print(">> 그래프가 꺼져있습니다 (G키로 켜기)")

    def toggle_interpolate(self):
        if self._pose_plot.active:
            self._pose_plot.toggle_interpolate()
        else:
            print(">> 그래프가 꺼져있습니다 (G키로 켜기)")

    def close_graph(self):
        if self._pose_plot.active:
            self._pose_plot.close()

    # ── CSV 기록 ──

    def start_recording(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"pose_log_{ts}.csv"
        self._csv_file = open(filename, "w", newline="")
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow([
            "timestamp", "marker_id", "dict",
            "tx", "ty", "tz", "rx", "ry", "rz", "distance"
        ])
        self.recording = True
        print(f">> 기록 시작: {filename}")

    def stop_recording(self):
        if self._csv_file:
            self._csv_file.close()
            self._csv_file = None
            self._csv_writer = None
        self.recording = False
        print(">> 기록 중지")

    def toggle_recording(self):
        if self.recording:
            self.stop_recording()
        else:
            self.start_recording()

    # ── 감지 + 그리기 ──

    def detect_and_draw(self, frame, camera_matrix, dist_coeffs):
        """프레임에서 마커 감지, OSD 그리기, 포즈 기록. 수정된 frame 반환."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = cv2.aruco.detectMarkers(
            gray, self._aruco_dict, parameters=self._det_params
        )

        detected_ids = set()
        if ids is not None and len(ids) > 0:
            cv2.aruco.drawDetectedMarkers(frame, corners, ids)
            self._draw_pose(frame, corners, ids, camera_matrix, dist_coeffs)
            detected_ids = set(int(mid[0]) for mid in ids)

        # 보간 OFF일 때: 감지 안 된 마커에 NaN 삽입 → 그래프에서 선 끊김
        if self._pose_plot.active and not self._pose_plot.interpolate:
            nan = float('nan')
            for mid in list(self._pose_plot.tracked_markers):
                if mid not in detected_ids:
                    self._pose_plot.add_pose(mid, nan, nan, nan, nan, nan, nan)

        self._draw_status(frame, ids)

        # 그래프 갱신 (매 5프레임마다 — 성능 부담 완화)
        self._plot_update_counter += 1
        if self._pose_plot.active and self._plot_update_counter % 5 == 0:
            self._pose_plot.update()

        return frame

    def _draw_pose(self, frame, corners, ids, camera_matrix, dist_coeffs):
        dict_name = DICT_NAMES[self.current_dict_idx]

        for i, corner in enumerate(corners):
            marker_id = ids[i][0]
            pts = corner[0]
            cx = int(pts[:, 0].mean())
            cy = int(pts[:, 1].mean())

            cv2.putText(frame, f"ID:{marker_id}", (cx - 20, cy - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            if self.show_pose and camera_matrix is not None:
                rvecs, tvecs, _ = cv2.aruco.estimatePoseSingleMarkers(
                    [corner], self.marker_size, camera_matrix, dist_coeffs
                )
                cv2.drawFrameAxes(frame, camera_matrix, dist_coeffs,
                                  rvecs[0], tvecs[0], self.marker_size * 0.7)

                tx, ty, tz = tvecs[0][0]
                rx, ry, rz = np.degrees(rvecs[0][0])
                dist = np.linalg.norm(tvecs[0])

                cv2.putText(frame, f"{dist:.2f}m", (cx - 20, cy + 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                cv2.putText(frame, f"T({tx:.3f},{ty:.3f},{tz:.3f})",
                            (cx - 20, cy + 45),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 200, 0), 1)
                cv2.putText(frame, f"R({rx:.1f},{ry:.1f},{rz:.1f})",
                            (cx - 20, cy + 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 200, 0), 1)

                # 그래프에 데이터 추가
                self._pose_plot.add_pose(marker_id, tx, ty, tz, rx, ry, rz)

                if self.recording and self._csv_writer:
                    self._csv_writer.writerow([
                        f"{time.time():.6f}", marker_id, dict_name,
                        f"{tx:.6f}", f"{ty:.6f}", f"{tz:.6f}",
                        f"{rx:.4f}", f"{ry:.4f}", f"{rz:.4f}",
                        f"{dist:.6f}"
                    ])

    def _draw_status(self, frame, ids):
        """좌상단 상태 HUD + 하단 키 도움말"""
        h, w = frame.shape[:2]

        # ── 상단 상태 ──
        cv2.rectangle(frame, (0, 0), (500, 130), (40, 40, 40), -1)

        # 카메라 이름
        cam_label = self._camera_type
        for ct, dn in self._available_cameras:
            if ct == self._camera_type:
                cam_label = dn
                break
        cv2.putText(frame, f"Cam: {cam_label}",
                    (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)

        cv2.putText(frame, f"Dict: {DICT_NAMES[self.current_dict_idx]}",
                    (10, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        detected = 0 if ids is None else len(ids)
        color = (0, 255, 0) if detected > 0 else (100, 100, 100)
        cv2.putText(frame, f"Detected: {detected} marker(s)",
                    (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        cv2.putText(frame, f"Pose: {'ON' if self.show_pose else 'OFF'}",
                    (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        rec_color = (0, 0, 255) if self.recording else (100, 100, 100)
        cv2.putText(frame, f"REC: {'ON' if self.recording else 'OFF'}",
                    (150, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    rec_color, 2 if self.recording else 1)

        # 해상도/FPS 표시
        if self._cam_config:
            res_text = f"{self._cam_config.width}x{self._cam_config.height} @ {self._cam_config.fps}fps"
            cv2.putText(frame, res_text, (10, 125),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 2)

        # 그래프 상태
        graph_color = (0, 255, 0) if self._pose_plot.active else (100, 100, 100)
        if self._pose_plot.active:
            interp = "interp" if self._pose_plot.interpolate else "no-interp"
            mode_str = f"{self._pose_plot.mode}/{interp}"
        else:
            mode_str = "OFF"
        cv2.putText(frame, f"Graph: {mode_str}",
                    (280, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.45, graph_color, 1)

        # ── 하단 키 도움말 (2줄) ──
        cv2.rectangle(frame, (0, h - 50), (w, h), (40, 40, 40), -1)
        line1 = "[1]4x4 [2]6x6 [3]36h11 [4]25h9 | [P]ose [R]ec [G]raph [T]ime [I]nterp [Q]uit"
        line2 = "[F1]360 [F2]480 [F3]720 [F4]1080 | [+/-]FPS | [C]amera"
        cv2.putText(frame, line1, (10, h - 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.43, (180, 180, 180), 1)
        cv2.putText(frame, line2, (10, h - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.43, (180, 180, 180), 1)
