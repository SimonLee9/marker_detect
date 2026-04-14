import numpy as np
from .base import BaseCamera, CameraConfig


class OakDCamera(BaseCamera):
    """OAK-D 카메라 (depthai SDK)"""

    def __init__(self, config: CameraConfig):
        super().__init__(config)
        self._device = None
        self._queue = None

    def open(self) -> None:
        import depthai as dai

        pipeline = dai.Pipeline()

        cam_rgb = pipeline.create(dai.node.ColorCamera)
        # 센서 해상도 선택
        if self.config.width > 1280 or self.config.height > 720:
            cam_rgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
        else:
            cam_rgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
        cam_rgb.setPreviewSize(self.config.width, self.config.height)
        cam_rgb.setInterleaved(False)
        cam_rgb.setFps(self.config.fps)

        xout = pipeline.create(dai.node.XLinkOut)
        xout.setStreamName("rgb")
        cam_rgb.preview.link(xout.input)

        self._device = dai.Device(pipeline)
        self._queue = self._device.getOutputQueue("rgb", maxSize=4, blocking=False)

        # 내장 캘리브레이션
        if self._camera_matrix is None and self.config.calib_file is None:
            calib = self._device.readCalibration()
            intrinsics = calib.getCameraIntrinsics(
                dai.CameraBoardSocket.CAM_A,
                self.config.width, self.config.height
            )
            self._camera_matrix = np.array(intrinsics)
            self._dist_coeffs = np.zeros((5, 1))  # OAK는 보정된 이미지 출력

        print(f"[OAK-D] Opened {self.config.width}x{self.config.height} @ {self.config.fps}fps")

    def read_frame(self) -> np.ndarray:
        if self._queue is None:
            return None
        try:
            in_rgb = self._queue.get()
            return in_rgb.getCvFrame()
        except Exception:
            return None

    def close(self) -> None:
        if self._device is not None:
            self._device.close()
            self._device = None
            self._queue = None
        print("[OAK-D] Closed")
