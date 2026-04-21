from .base import BaseCamera, CameraConfig


CAMERA_REGISTRY = {
    "oakd":      ("cameras.luxonis", "LuxonisCamera"),
    "oak1":      ("cameras.luxonis", "LuxonisCamera"),
    "gemini_e":  ("cameras.orbbec", "OrbbecCamera"),
    "gemini_2l": ("cameras.orbbec", "OrbbecCamera"),
    "basler":    ("cameras.basler", "BaslerCamera"),
}

# Luxonis 모델별 표시명 (LuxonisCamera 생성자의 model 파라미터로 전달)
LUXONIS_MODELS = {
    "oakd": "OAK-D",
    "oak1": "OAK-1",
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

    if camera_type in LUXONIS_MODELS:
        return cls(config, model=LUXONIS_MODELS[camera_type], **kwargs)
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

    # Luxonis OAK 시리즈 감지 (OAK-D / OAK-1)
    try:
        import depthai as dai
        for info in dai.Device.getAllAvailableDevices():
            model_name = _luxonis_model_name(info)
            if "OAK-1" in model_name.upper():
                cam_type = "oak1"
                display_model = "OAK-1"
            else:
                cam_type = "oakd"  # OAK-D / OAK-D-S2 / OAK-D-Lite 전부 수용
                display_model = "OAK-D"
            found.append((cam_type, f"{display_model} ({info.name})"))
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


def _luxonis_model_name(info) -> str:
    """DeviceInfo에서 Luxonis 모델명 추출. 실패 시 디바이스를 잠깐 열어 조회."""
    # Step A: DeviceInfo 필드 직접 조회 (depthai 2.22+는 productName 노출)
    for attr in ("productName", "getProductName", "name"):
        try:
            val = getattr(info, attr, None)
            val = val() if callable(val) else val
            if val and "OAK" in str(val).upper():
                return str(val)
        except Exception:
            pass

    # Step B: 디바이스 연결해서 모델명 읽기 (수백 ms 지연)
    try:
        import depthai as dai
        with dai.Device(info) as dev:
            for method in ("getDeviceName", "getProductName"):
                try:
                    return getattr(dev, method)()
                except Exception:
                    pass
    except Exception:
        pass

    return ""
