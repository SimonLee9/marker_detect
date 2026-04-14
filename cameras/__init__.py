from .base import BaseCamera, CameraConfig


CAMERA_REGISTRY = {
    "oakd": ("cameras.oakd", "OakDCamera"),
    "gemini_e": ("cameras.orbbec", "OrbbecCamera"),
    "gemini_2l": ("cameras.orbbec", "OrbbecCamera"),
    "basler": ("cameras.basler", "BaslerCamera"),
}

# Orbbec 모델별 device_filter (pyorbbecsdk에서 디바이스 식별에 사용)
ORBBEC_MODELS = {
    "gemini_e": "Gemini E",
    "gemini_2l": "Gemini 2L",
}


def create_camera(camera_type: str, config: CameraConfig, **kwargs) -> BaseCamera:
    """카메라 타입에 맞는 인스턴스 생성"""
    if camera_type not in CAMERA_REGISTRY:
        available = ", ".join(CAMERA_REGISTRY.keys())
        raise ValueError(f"Unknown camera: '{camera_type}'. Available: {available}")

    module_path, class_name = CAMERA_REGISTRY[camera_type]

    import importlib
    module = importlib.import_module(f"marker_detector.{module_path}")
    cls = getattr(module, class_name)

    if camera_type in ORBBEC_MODELS:
        return cls(config, model=ORBBEC_MODELS[camera_type], **kwargs)
    return cls(config, **kwargs)


def reset_usb_ports():
    """USB 컨트롤러 리셋 (카메라 감지 실패 시 호출)"""
    import subprocess
    import glob

    print("[USB] 포트 리셋 시도...")
    reset_count = 0

    # 모든 USB 버스의 authorized를 0 → 1로 토글
    for auth_path in sorted(glob.glob("/sys/bus/usb/devices/usb*/authorized")):
        try:
            subprocess.run(
                ["sudo", "-n", "sh", "-c", f"echo 0 > {auth_path} && sleep 1 && echo 1 > {auth_path}"],
                timeout=5, capture_output=True
            )
            reset_count += 1
        except Exception:
            pass

    if reset_count == 0:
        # sudo -n 실패 (패스워드 필요) → usbreset 시도
        try:
            subprocess.run(["sudo", "-n", "usbreset", "--all"],
                           timeout=5, capture_output=True)
        except Exception:
            print("[USB] 리셋 실패 (sudo 권한 필요). 수동으로 케이블을 뽑았다 꽂아주세요.")
            return False

    import time
    time.sleep(2)
    print("[USB] 리셋 완료, 재탐색...")
    return True


def detect_cameras(retry_with_reset: bool = True) -> list:
    """연결된 카메라 자동 감지. [(camera_type, display_name), ...] 반환"""
    found = _scan_cameras()

    # 카메라 없으면 USB 리셋 후 재시도
    if len(found) == 0 and retry_with_reset:
        if reset_usb_ports():
            found = _scan_cameras()

    return found


def _scan_cameras() -> list:
    """실제 카메라 스캔"""
    found = []

    # OAK-D 감지
    try:
        import depthai as dai
        devices = dai.Device.getAllAvailableDevices()
        if len(devices) > 0:
            found.append(("oakd", f"OAK-D ({devices[0].name})"))
    except Exception:
        pass

    # Orbbec 감지
    try:
        from pyorbbecsdk import Context
        ctx = Context()
        devices = ctx.query_devices()
        for i in range(devices.get_count()):
            dev = devices.get_device_by_index(i)
            info = dev.get_device_info()
            name = info.get_name()
            if "Gemini 2 L" in name or "Gemini2 L" in name:
                found.append(("gemini_2l", f"Orbbec Gemini 2L ({info.get_serial_number()})"))
            elif "Gemini E" in name:
                found.append(("gemini_e", f"Orbbec Gemini E ({info.get_serial_number()})"))
            else:
                found.append(("gemini_2l", f"Orbbec {name} ({info.get_serial_number()})"))
        del ctx
    except Exception:
        pass

    # Basler 감지
    try:
        from pypylon import pylon
        tl = pylon.TlFactory.GetInstance()
        devices = tl.EnumerateDevices()
        for d in devices:
            found.append(("basler", f"Basler {d.GetModelName()} ({d.GetSerialNumber()})"))
    except Exception:
        pass

    return found
