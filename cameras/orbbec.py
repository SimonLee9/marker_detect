import numpy as np
import cv2
from .base import BaseCamera, CameraConfig


class OrbbecCamera(BaseCamera):
    """Orbbec Gemini E / Gemini 2L 카메라 (pyorbbecsdk v1)"""

    def __init__(self, config: CameraConfig, model: str = "Gemini E"):
        super().__init__(config)
        self._model = model
        self._pipeline = None

    @staticmethod
    def _detect_usb2() -> bool:
        """lsusb -t에서 Orbbec 장치가 480M(USB2.0)인지 확인"""
        import subprocess
        try:
            result = subprocess.run(["lsusb", "-t"], capture_output=True, text=True, timeout=3)
            # 480M = USB 2.0, 5000M/10000M = USB 3.x
            for line in result.stdout.splitlines():
                if "2bc5" in line.lower() or "orbbec" in line.lower():
                    if "480M" in line:
                        return True
                    return False
            # Orbbec 장치를 못 찾으면 Bus 속도로 추정
            # lsusb -t에서 vendor가 안 나올 수 있으므로, lsusb로 bus 번호 찾기
            result2 = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=3)
            for line in result2.stdout.splitlines():
                if "2bc5" in line.lower():
                    # "Bus 005" 추출
                    bus = line.split()[1]
                    # lsusb -t에서 해당 Bus의 속도 확인
                    for tline in result.stdout.splitlines():
                        if f"Bus {bus}" in tline:
                            if "480M" in tline:
                                return True
                            return False
        except Exception:
            pass
        return True  # 판단 불가 시 USB 2.0으로 가정 (안전)

    def open(self) -> None:
        from pyorbbecsdk import Pipeline, Config, OBSensorType, OBFormat

        self._pipeline = Pipeline()
        device = self._pipeline.get_device()
        device_info = device.get_device_info()
        is_usb2 = self._detect_usb2()
        usb_label = "USB2.0" if is_usb2 else "USB3.0+"
        print(f"[Orbbec] Device: {device_info.get_name()} (target: {self._model}, {usb_label})")

        # USB 2.0이면 해상도/FPS 제한 (대역폭 부족 방지)
        if is_usb2:
            if self.config.width > 640 or self.config.fps > 15:
                print(f"[Orbbec] USB 2.0 감지 — 해상도를 640x360@15fps로 제한합니다")
                self.config.width = 640
                self.config.height = 360
                self.config.fps = 15

        # Color 스트림 프로필 선택 (MJPG 우선 — 대역폭 절약)
        profiles = self._pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
        color_profile = None

        # 요청한 해상도/fps로 MJPG 프로필 검색
        try:
            color_profile = profiles.get_video_stream_profile(
                self.config.width, self.config.height, OBFormat.MJPG, self.config.fps
            )
        except Exception:
            pass

        # MJPG 없으면 RGB888로 시도
        if color_profile is None:
            try:
                color_profile = profiles.get_video_stream_profile(
                    self.config.width, self.config.height, OBFormat.RGB888, self.config.fps
                )
            except Exception:
                pass

        # 그래도 없으면 기본 프로필
        if color_profile is None:
            print(f"[Orbbec] Exact profile {self.config.width}x{self.config.height}@{self.config.fps} "
                  f"not found, using default")
            color_profile = profiles.get_default_video_stream_profile()

        vp = color_profile
        self.config.width = vp.get_width()
        self.config.height = vp.get_height()
        self.config.fps = vp.get_fps()
        self._format = vp.get_format()

        config = Config()
        config.enable_stream(color_profile)
        self._pipeline.start(config)

        # 내장 캘리브레이션
        if self._camera_matrix is None and self.config.calib_file is None:
            self._load_intrinsics_from_device()

        print(f"[Orbbec] Opened {self.config.width}x{self.config.height} @ {self.config.fps}fps "
              f"(format: {self._format})")

    def _load_intrinsics_from_device(self):
        """디바이스 내장 캘리브레이션 파라미터 로드"""
        try:
            camera_params = self._pipeline.get_camera_param()
            intr = camera_params.rgb_intrinsic
            # fx=0이면 유효하지 않은 캘리브레이션
            if intr.fx > 0 and intr.fy > 0:
                self._camera_matrix = np.array([
                    [intr.fx, 0, intr.cx],
                    [0, intr.fy, intr.cy],
                    [0, 0, 1]
                ], dtype=np.float64)
                try:
                    dist = camera_params.rgb_distortion
                    self._dist_coeffs = np.array([
                        [dist.k1], [dist.k2], [dist.p1], [dist.p2], [dist.k3]
                    ], dtype=np.float64)
                except Exception:
                    self._dist_coeffs = np.zeros((5, 1))
                print(f"[Orbbec] Intrinsics loaded: fx={intr.fx:.1f} fy={intr.fy:.1f}")
                return
            raise ValueError("Invalid intrinsics (fx=0)")
        except Exception as e:
            print(f"[Orbbec] Failed to load intrinsics: {e}, using defaults")
            fx = self.config.width * 0.8
            fy = fx
            cx = self.config.width / 2.0
            cy = self.config.height / 2.0
            self._camera_matrix = np.array([
                [fx, 0, cx],
                [0, fy, cy],
                [0, 0, 1]
            ], dtype=np.float64)
            self._dist_coeffs = np.zeros((5, 1))

    def read_frame(self) -> np.ndarray:
        if self._pipeline is None:
            return None
        try:
            frames = self._pipeline.wait_for_frames(1000)
        except Exception:
            return None
        if frames is None:
            return None
        color_frame = frames.get_color_frame()
        if color_frame is None:
            return None

        data = np.asanyarray(color_frame.get_data())
        fmt = color_frame.get_format()

        from pyorbbecsdk import OBFormat
        if fmt == OBFormat.MJPG:
            return cv2.imdecode(data, cv2.IMREAD_COLOR)
        elif fmt == OBFormat.RGB888:
            img = data.reshape((self.config.height, self.config.width, 3))
            return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        elif fmt == OBFormat.BGRA:
            img = data.reshape((self.config.height, self.config.width, 4))
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        elif fmt == OBFormat.YUYV:
            img = data.reshape((self.config.height, self.config.width, 2))
            return cv2.cvtColor(img, cv2.COLOR_YUV2BGR_YUYV)
        else:
            return data.reshape((self.config.height, self.config.width, 3))

    def close(self) -> None:
        if self._pipeline is not None:
            self._pipeline.stop()
            self._pipeline = None
        print(f"[Orbbec] Closed ({self._model})")
