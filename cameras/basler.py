import numpy as np
import cv2
from .base import BaseCamera, CameraConfig


class BaslerCamera(BaseCamera):
    """Basler 카메라 (pypylon SDK)"""

    def __init__(self, config: CameraConfig):
        super().__init__(config)
        self._camera = None
        self._converter = None

    def open(self) -> None:
        from pypylon import pylon

        tl_factory = pylon.TlFactory.GetInstance()
        devices = tl_factory.EnumerateDevices()
        if len(devices) == 0:
            raise RuntimeError("[Basler] No camera found")

        self._camera = pylon.InstantCamera(tl_factory.CreateDevice(devices[0]))
        self._camera.Open()

        # GigE 패킷 크기 자동 협상
        if self._camera.GetDeviceInfo().GetDeviceClass() == "BaslerGigE":
            try:
                self._camera.GevSCPSPacketSize.SetValue(
                    self._camera.GevSCPSPacketSize.Max
                )
            except Exception:
                pass  # 실패해도 기본값으로 동작

        # 해상도 설정
        try:
            self._camera.Width.SetValue(self.config.width)
            self._camera.Height.SetValue(self.config.height)
        except Exception as e:
            # 지원하지 않는 해상도면 최대값 사용
            self.config.width = self._camera.Width.GetValue()
            self.config.height = self._camera.Height.GetValue()
            print(f"[Basler] Requested resolution not supported, using {self.config.width}x{self.config.height}")

        # FPS 설정
        try:
            node = self._camera.AcquisitionFrameRateEnable
            if hasattr(node, 'IsWritable') and node.IsWritable():
                node.SetValue(True)
            elif hasattr(node, 'SetValue'):
                node.SetValue(True)
        except Exception:
            pass
        try:
            node = self._camera.AcquisitionFrameRate
            if hasattr(node, 'IsWritable') and node.IsWritable():
                node.SetValue(float(self.config.fps))
            elif hasattr(node, 'SetValue'):
                node.SetValue(float(self.config.fps))
        except Exception:
            pass

        # Mono/Color 감지 후 변환기 설정
        self._converter = pylon.ImageFormatConverter()
        pixel_type = self._camera.PixelFormat.GetValue()
        self._is_mono = "Mono" in str(pixel_type) or "Bayer" in str(pixel_type)
        if self._is_mono:
            self._converter.OutputPixelFormat = pylon.PixelType_Mono8
            print(f"[Basler] Mono camera detected, will convert to BGR for display")
        else:
            self._converter.OutputPixelFormat = pylon.PixelType_BGR8packed
        self._converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

        self._camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

        # 캘리브레이션: Basler는 내장 캘리브레이션이 없으므로 파일 필수 또는 기본값
        if self._camera_matrix is None and self.config.calib_file is None:
            print("[Basler] No calibration file, using estimated intrinsics")
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

        model = self._camera.GetDeviceInfo().GetModelName()
        print(f"[Basler] Opened {model} {self.config.width}x{self.config.height} @ {self.config.fps}fps")

    def read_frame(self) -> np.ndarray:
        from pypylon import pylon

        if self._camera is None or not self._camera.IsGrabbing():
            return None

        try:
            grab_result = self._camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
        except Exception:
            return None

        if not grab_result.GrabSucceeded():
            grab_result.Release()
            return None

        image = self._converter.Convert(grab_result)
        frame = image.GetArray()
        grab_result.Release()

        # Mono → BGR 변환 (마커 감지는 gray로 하지만 OSD 표시를 위해 BGR 필요)
        if self._is_mono:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        return frame

    def close(self) -> None:
        if self._camera is not None:
            if self._camera.IsGrabbing():
                self._camera.StopGrabbing()
            self._camera.Close()
            self._camera = None
        print("[Basler] Closed")
