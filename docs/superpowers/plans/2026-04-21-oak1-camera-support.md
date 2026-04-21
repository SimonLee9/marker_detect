# OAK-1 Camera Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** OAK-1 카메라를 별도 타입으로 감지·라벨링하고, 기존 OAK-D 경로와 공존시키기 위해 `OakDCamera`를 `LuxonisCamera`로 일반화한다.

**Architecture:** `cameras/oakd.py`를 `cameras/luxonis.py`로 리네임하고 `LuxonisCamera(config, model=...)` 시그니처를 도입한다. `CAMERA_REGISTRY`에 `oakd`, `oak1`을 같은 클래스로 등록하되 `LUXONIS_MODELS` 매핑으로 model 문자열을 주입한다(Orbbec 패턴과 동일). 감지 단계에서는 `DeviceInfo.productName`을 먼저 조회하고, 없으면 디바이스를 잠시 열어 `getDeviceName()`으로 모델명을 얻은 뒤 "OAK-1" 포함 여부로 분류한다.

**Tech Stack:** Python 3.8+, depthai SDK, OpenCV (기존과 동일)

**Reference spec:** [2026-04-21-oak1-camera-support-design.md](../specs/2026-04-21-oak1-camera-support-design.md)

---

## File Structure

- **Rename**: `marker_detector/cameras/oakd.py` → `marker_detector/cameras/luxonis.py`
- **Modify**: `marker_detector/cameras/luxonis.py` — `OakDCamera` → `LuxonisCamera`, add `model` param
- **Modify**: `marker_detector/cameras/__init__.py` — add `oak1` to registry, add `LUXONIS_MODELS`, update `create_camera()` and `_scan_cameras()`, add `_luxonis_model_name()` helper
- **Modify**: `marker_detector/README.md` — Features / CLI table / Project Structure tree

No new tests (기존 코드베이스에 테스트 인프라 없음, depthai 모킹 비용 큼 — spec의 결정). 검증은 실기 수동 테스트로.

---

## Task 1: Rename OakDCamera to LuxonisCamera with model parameter

**Files:**
- Create: `marker_detector/cameras/luxonis.py` (from renamed `oakd.py`)
- Delete: `marker_detector/cameras/oakd.py`

- [ ] **Step 1: Move file**

```bash
git mv marker_detector/cameras/oakd.py marker_detector/cameras/luxonis.py
```

- [ ] **Step 2: Rewrite `luxonis.py` with generalized class**

Replace entire contents of `marker_detector/cameras/luxonis.py`:

```python
import numpy as np
from .base import BaseCamera, CameraConfig


class LuxonisCamera(BaseCamera):
    """Luxonis OAK 시리즈 카메라 (depthai SDK) — OAK-D / OAK-1 공용."""

    def __init__(self, config: CameraConfig, model: str = "OAK-D"):
        super().__init__(config)
        self.model = model
        self._device = None
        self._queue = None

    def open(self) -> None:
        import depthai as dai

        pipeline = dai.Pipeline()

        cam_rgb = pipeline.create(dai.node.ColorCamera)
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

        if self._camera_matrix is None and self.config.calib_file is None:
            calib = self._device.readCalibration()
            intrinsics = calib.getCameraIntrinsics(
                dai.CameraBoardSocket.CAM_A,
                self.config.width, self.config.height
            )
            self._camera_matrix = np.array(intrinsics)
            self._dist_coeffs = np.zeros((5, 1))

        print(f"[{self.model}] Opened {self.config.width}x{self.config.height} @ {self.config.fps}fps")

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
        print(f"[{self.model}] Closed")
```

- [ ] **Step 3: Verify import works**

Run: `cd /home/rainbow/ws && python -c "from marker_detector.cameras.luxonis import LuxonisCamera; print(LuxonisCamera.__name__)"`
Expected output: `LuxonisCamera`

(depthai는 runtime import이므로 클래스 자체 import은 depthai 없이도 성공해야 한다.)

- [ ] **Step 4: Commit**

```bash
git add marker_detector/cameras/luxonis.py marker_detector/cameras/oakd.py
git commit -m "Rename OakDCamera to LuxonisCamera with model parameter"
```

---

## Task 2: Update camera registry and factory

**Files:**
- Modify: `marker_detector/cameras/__init__.py`

- [ ] **Step 1: Update CAMERA_REGISTRY and add LUXONIS_MODELS**

In `marker_detector/cameras/__init__.py`, replace the existing `CAMERA_REGISTRY` block and `ORBBEC_MODELS` block (lines 4-15) with:

```python
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
```

- [ ] **Step 2: Update `create_camera()` to dispatch Luxonis model**

Replace the body of `create_camera()` (the existing trailing `if camera_type in ORBBEC_MODELS` block) with:

```python
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
```

- [ ] **Step 3: Verify import and factory**

Run: `cd /home/rainbow/ws && python -c "from marker_detector.cameras import CAMERA_REGISTRY, LUXONIS_MODELS; print(sorted(CAMERA_REGISTRY.keys())); print(LUXONIS_MODELS)"`
Expected output:
```
['basler', 'gemini_2l', 'gemini_e', 'oak1', 'oakd']
{'oakd': 'OAK-D', 'oak1': 'OAK-1'}
```

- [ ] **Step 4: Commit**

```bash
git add marker_detector/cameras/__init__.py
git commit -m "Register oak1 camera type with Luxonis model dispatch"
```

---

## Task 3: Replace OAK detection block with per-model classifier

**Files:**
- Modify: `marker_detector/cameras/__init__.py` — `_scan_cameras()` 내부 OAK 블록 + 새 헬퍼 `_luxonis_model_name()`

- [ ] **Step 1: Replace the OAK detection block in `_scan_cameras()`**

Find this block (currently at `marker_detector/cameras/__init__.py:85-92`):

```python
    # OAK-D 감지
    try:
        import depthai as dai
        devices = dai.Device.getAllAvailableDevices()
        if len(devices) > 0:
            found.append(("oakd", f"OAK-D ({devices[0].name})"))
    except Exception:
        pass
```

Replace with:

```python
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
```

- [ ] **Step 2: Add the `_luxonis_model_name()` helper**

Append this function to the end of `marker_detector/cameras/__init__.py`:

```python
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
```

- [ ] **Step 3: Verify helper is importable and callable without device**

Run: `cd /home/rainbow/ws && python -c "from marker_detector.cameras import _luxonis_model_name; print(_luxonis_model_name(object()))"`
Expected output: `` (빈 문자열, 더미 객체라 모든 attribute/open 시도가 실패해서 `""` 반환)

- [ ] **Step 4: Commit**

```bash
git add marker_detector/cameras/__init__.py
git commit -m "Classify Luxonis devices into OAK-1 and OAK-D at detection"
```

---

## Task 4: Update README

**Files:**
- Modify: `marker_detector/README.md`

- [ ] **Step 1: Update Features bullet for 멀티 카메라 지원**

Replace [README.md:7](../../../README.md#L7):

```markdown
- **멀티 카메라 지원**: OAK-D (depthai), Orbbec Gemini E / Gemini 2L (pyorbbecsdk), Basler (pypylon)
```

With:

```markdown
- **멀티 카메라 지원**: Luxonis OAK-D / OAK-1 (depthai), Orbbec Gemini E / Gemini 2L (pyorbbecsdk), Basler (pypylon)
```

- [ ] **Step 2: Update CLI options table `--camera` row**

Replace [README.md:51](../../../README.md#L51):

```markdown
| `--camera` | 자동 감지 | `oakd`, `gemini_e`, `gemini_2l`, `basler` |
```

With:

```markdown
| `--camera` | 자동 감지 | `oakd`, `oak1`, `gemini_e`, `gemini_2l`, `basler` |
```

- [ ] **Step 3: Update Project Structure tree**

Replace [README.md:84](../../../README.md#L84):

```markdown
│   ├── oakd.py          # OAK-D (depthai)
```

With:

```markdown
│   ├── luxonis.py       # OAK-D / OAK-1 (depthai)
```

- [ ] **Step 4: Commit**

```bash
git add marker_detector/README.md
git commit -m "Document OAK-1 support in README"
```

---

## Task 5: Manual verification with hardware

**Files:** (none — verification only)

- [ ] **Step 1: Auto-detection with OAK-1 connected**

Run: `cd /home/rainbow/ws && python -m marker_detector`
Expected console output (among other lines):
```
감지된 카메라 (1개):
  [0] OAK-1 (<mxid>)

>> 자동 선택: OAK-1 (<mxid>)
[OAK-1] Opened 640x480 @ 30fps
```

Close the app (press `Q` in the OpenCV window, or Ctrl-C). Expected exit log:
```
[OAK-1] Closed
종료
```

If detection still shows "OAK-D", capture the output of the following diagnostic and report back:

```bash
cd /home/rainbow/ws && python -c "
import depthai as dai
for info in dai.Device.getAllAvailableDevices():
    for a in ('productName','getProductName','name','mxid','getMxId'):
        v = getattr(info, a, None)
        v = v() if callable(v) else v
        print(a, '=', repr(v))
"
```

This tells us which `DeviceInfo` attribute exposes the model on this depthai version, so Step A of `_luxonis_model_name()` can be tuned if needed.

- [ ] **Step 2: Explicit `--camera oak1` works**

Run: `cd /home/rainbow/ws && python -m marker_detector --camera oak1`
Expected: `[OAK-1] Opened ...` appears and app launches normally.

- [ ] **Step 3: Explicit `--camera oakd` still accepted (backward compat)**

Run: `cd /home/rainbow/ws && python -m marker_detector --camera oakd`
Expected: `[OAK-D] Opened ...` appears (same hardware, label only differs — OAK-D intrinsics call may still succeed since OAK-1 also has CAM_A).

If the `readCalibration()` call on `CAM_A` fails for OAK-1 under the `--camera oakd` label, this is out of scope for this plan (the spec's non-goal is "backward-compat on `oakd`" at the CLI level, not identical runtime behavior). Document the failure mode and move on.

- [ ] **Step 4: Help text mentions oak1**

Run: `cd /home/rainbow/ws && python -m marker_detector --help | grep -A1 camera`
Expected: argparse choices list contains `oak1` (e.g. `{oakd,oak1,gemini_e,gemini_2l,basler}`). [main.py:34](../../../main.py#L34) uses `choices=list(CAMERA_REGISTRY.keys())` so it auto-populates from Task 2's registry change — no additional code change expected.

---

## Self-Review Checklist

- [x] **Spec coverage**: All spec sections mapped to tasks — class rename (Task 1), registry (Task 2), detection (Task 3), docs (Task 4), manual verification (Task 5). Multiple-device감지 버그 수정 is covered in Task 3 (for loop replaces `if len > 0`).
- [x] **No placeholders**: All code blocks contain complete code. Verification commands have exact expected output.
- [x] **Type/name consistency**: `LuxonisCamera`, `LUXONIS_MODELS`, `_luxonis_model_name` used consistently across Tasks 1-3. `model` parameter name matches `self.model` usage in `open()` / `close()`.
