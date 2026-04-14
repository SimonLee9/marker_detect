from abc import ABC, abstractmethod
from dataclasses import dataclass
import numpy as np


@dataclass
class CameraConfig:
    width: int = 640
    height: int = 480
    fps: int = 30
    calib_file: str = None  # 외부 캘리브레이션 YAML 경로


class BaseCamera(ABC):
    """모든 카메라 드라이버가 구현해야 하는 공통 인터페이스"""

    def __init__(self, config: CameraConfig):
        self.config = config
        self._camera_matrix = None
        self._dist_coeffs = None

    @abstractmethod
    def open(self) -> None:
        """카메라 초기화 및 스트리밍 시작"""
        pass

    @abstractmethod
    def read_frame(self) -> np.ndarray:
        """BGR 프레임 반환. 실패 시 None 반환."""
        pass

    @abstractmethod
    def close(self) -> None:
        """카메라 리소스 정리"""
        pass

    def get_camera_matrix(self) -> np.ndarray:
        """3x3 카메라 내부 파라미터 행렬"""
        if self._camera_matrix is not None:
            return self._camera_matrix
        # calib_file이 있으면 YAML에서 로드
        if self.config.calib_file:
            self._load_calibration(self.config.calib_file)
            return self._camera_matrix
        return None

    def get_dist_coeffs(self) -> np.ndarray:
        """왜곡 계수 벡터"""
        if self._dist_coeffs is not None:
            return self._dist_coeffs
        if self.config.calib_file:
            self._load_calibration(self.config.calib_file)
            return self._dist_coeffs
        return np.zeros((5, 1))

    def _load_calibration(self, path: str):
        """OpenCV YAML 캘리브레이션 파일 로드"""
        import cv2
        fs = cv2.FileStorage(path, cv2.FILE_STORAGE_READ)
        self._camera_matrix = fs.getNode("camera_matrix").mat()
        dist_node = fs.getNode("dist_coeffs")
        if not dist_node.empty():
            self._dist_coeffs = dist_node.mat()
        else:
            self._dist_coeffs = np.zeros((5, 1))
        fs.release()
        print(f"[Calib] Loaded from {path}")

    def reopen(self, config: CameraConfig) -> None:
        """설정 변경 후 카메라 재시작"""
        self.close()
        self.config = config
        self._camera_matrix = None
        self._dist_coeffs = None
        self.open()

    @property
    def name(self) -> str:
        return self.__class__.__name__
