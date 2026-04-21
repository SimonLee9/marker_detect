# OAK-1 Camera Support — Design

**Date:** 2026-04-21
**Status:** Approved

## Problem

현재 marker_detector의 카메라 감지 로직은 depthai SDK로 발견되는 Luxonis 디바이스를 무조건 `"OAK-D"`로 라벨링한다. 신규로 추가된 OAK-1은 물리적으로는 OAK-D가 아니라 단일 RGB 카메라 제품이지만, 기존 코드는 이를 구분하지 못하고 `oakd` 타입으로만 처리한다.

관련 코드 ([cameras/__init__.py:86-92](../../../cameras/__init__.py#L86-L92)):

```python
import depthai as dai
devices = dai.Device.getAllAvailableDevices()
if len(devices) > 0:
    found.append(("oakd", f"OAK-D ({devices[0].name})"))
```

- `devices[0].name`은 MxID/IP 문자열이라 모델 구분 불가
- OAK-1만 연결해도 `OAK-D`로 표시됨
- 첫 번째 디바이스만 집어넣는 버그도 존재 (for loop이 아님)

## Goals

1. 감지 시 OAK-1과 OAK-D 계열을 정확히 구분해 라벨·카메라 타입으로 분류한다.
2. CLI에서 `--camera oak1`로 명시 지정할 수 있어야 한다.
3. 기존 `--camera oakd` 경로는 하위호환을 유지한다.
4. 연결된 모든 Luxonis 디바이스를 감지한다 (첫 번째만 X).

## Non-Goals

- OAK-D의 스테레오/depth 스트림 활용 (현재 코드도 RGB만 사용)
- OAK-D-Lite, OAK-D-S2 등 OAK-D 파생 모델별 독립 라벨링 (모두 `oakd` 계열로 수용)
- depthai 파이프라인의 근본적 리팩토링

## Design

### 1. 클래스 재구성

[cameras/oakd.py](../../../cameras/oakd.py) → [cameras/luxonis.py](../../../cameras/luxonis.py)로 파일 리네임.
`OakDCamera` → `LuxonisCamera`로 클래스 리네임하고 생성자에 `model` 파라미터 추가.

```python
class LuxonisCamera(BaseCamera):
    def __init__(self, config: CameraConfig, model: str = "OAK-D"):
        super().__init__(config)
        self.model = model
        ...

    def open(self) -> None:
        ...
        print(f"[{self.model}] Opened {self.config.width}x{self.config.height} @ {self.config.fps}fps")

    def close(self) -> None:
        ...
        print(f"[{self.model}] Closed")
```

depthai 파이프라인 (ColorCamera + XLinkOut) 자체는 OAK-1과 OAK-D 모두에서 동일하게 동작하므로 클래스 내부 로직은 변경 없음. 출력 라벨만 모델별로 분기된다.

기존 `OakDCamera` 심볼은 삭제한다. 코드베이스 내 import 참조는 [cameras/__init__.py](../../../cameras/__init__.py) 한 곳뿐이며 registry 업데이트로 해소된다.

### 2. Registry 업데이트

[cameras/__init__.py](../../../cameras/__init__.py)에 Orbbec 패턴과 동일한 구조로 Luxonis 모델 테이블을 추가한다.

```python
CAMERA_REGISTRY = {
    "oakd":      ("cameras.luxonis", "LuxonisCamera"),
    "oak1":      ("cameras.luxonis", "LuxonisCamera"),
    "gemini_e":  ("cameras.orbbec", "OrbbecCamera"),
    "gemini_2l": ("cameras.orbbec", "OrbbecCamera"),
    "basler":    ("cameras.basler", "BaslerCamera"),
}

LUXONIS_MODELS = {
    "oakd": "OAK-D",
    "oak1": "OAK-1",
}

ORBBEC_MODELS = {
    "gemini_e": "Gemini E",
    "gemini_2l": "Gemini 2L",
}
```

`create_camera()`는 Orbbec 분기와 동일한 방식으로 Luxonis 분기를 추가한다.

```python
def create_camera(camera_type: str, config: CameraConfig, **kwargs) -> BaseCamera:
    ...
    if camera_type in LUXONIS_MODELS:
        return cls(config, model=LUXONIS_MODELS[camera_type], **kwargs)
    if camera_type in ORBBEC_MODELS:
        return cls(config, model=ORBBEC_MODELS[camera_type], **kwargs)
    return cls(config, **kwargs)
```

### 3. 감지 로직

`_scan_cameras()`의 OAK 블록을 아래처럼 수정한다. 핵심 전략: **`DeviceInfo` 필드를 먼저 조회하고, 모델명을 얻지 못하면 디바이스를 잠깐 열어 `getDeviceName()` / `getProductName()`으로 fallback한다.**

```python
try:
    import depthai as dai
    for info in dai.Device.getAllAvailableDevices():
        model_name = _luxonis_model_name(info)
        if "OAK-1" in model_name.upper():
            cam_type = "oak1"
            display_model = "OAK-1"
        else:
            cam_type = "oakd"  # OAK-D, OAK-D-S2, OAK-D-Lite 등 전부 수용
            display_model = "OAK-D"
        found.append((cam_type, f"{display_model} ({info.name})"))
except Exception:
    pass
```

모델명 조회 헬퍼:

```python
def _luxonis_model_name(info) -> str:
    """DeviceInfo에서 모델명 추출. 실패 시 디바이스를 잠깐 열어 조회."""
    # Step A: DeviceInfo 필드 직접 조회 (depthai 2.22+는 productName 노출)
    for attr in ("productName", "getProductName", "name"):
        try:
            val = getattr(info, attr, None)
            val = val() if callable(val) else val
            if val and "OAK" in str(val).upper():
                return str(val)
        except Exception:
            pass

    # Step B: 디바이스 연결해서 모델명 읽기 (수백 ms)
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
```

반환값이 빈 문자열이면 `oakd`로 fallback된다. 미지의 Luxonis 모델은 전부 OAK-D 계열로 수용되어 깨지지 않는다.

### 4. 감지 버그 수정

기존 코드는 `if len(devices) > 0: found.append(... devices[0] ...)`로 첫 번째 디바이스만 기록했다. 위의 for loop으로 바꾸면서 연결된 모든 Luxonis 디바이스가 감지 목록에 포함된다.

## Testing

유닛 테스트는 depthai 모킹 비용이 커서 기존에도 없다. 수동 검증 중심으로 진행:

- **OAK-1 연결 상태에서 자동 감지**: `python -m marker_detector` 실행 → `감지된 카메라` 목록에 `OAK-1 (xxx)` 출력 확인, 메인 루프에서 `[OAK-1] Opened ...` 로그 확인.
- **CLI 명시 지정**: `python -m marker_detector --camera oak1` 정상 기동, `--camera oakd` 도 유지.
- **OAK-D 회귀 검증**: 실기 연결 가능 시 `OAK-D (xxx)`로 분류 확인. 이번 세션에는 OAK-D 실물이 없으므로 감지 코드의 분기 로직은 코드 리뷰로만 확인.
- **다중 디바이스 감지**: 2대 이상 연결 시 모두 목록에 나타나는지 확인 (기존 버그 수정 검증).

## Docs

- [README.md](../../../README.md) 업데이트:
  - Features 섹션의 "멀티 카메라 지원" 문장에 OAK-1 추가
  - CLI 옵션 표의 `--camera` 행에 `oak1` 값 추가
  - Project Structure 트리에서 `oakd.py` → `luxonis.py` 반영

## Risks

- **depthai 버전 의존성**: `DeviceInfo.productName` 필드가 구버전에서 없을 수 있음 → Step B fallback이 이를 커버.
- **Step B 오픈 비용**: 감지 시 디바이스를 잠깐 여는 과정이 수백 ms 지연을 유발. 사용자가 기다려야 하는 감지 초기화 단계이므로 수용 가능한 수준.
- **미래 Luxonis 신모델**: OAK-D가 아닌 새 모델(e.g., OAK-4)이 출시될 경우 현재 로직은 `oakd`로 분류한다. 대부분의 경우 문제없음. 필요 시 추후 분기 확장.
