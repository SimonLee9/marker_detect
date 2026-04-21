# Universal Marker Detector - Design Spec

## Overview
Luxonis OAK-D / OAK-1, Orbbec Gemini E/2L, Basler 카메라를 지원하는 범용 ArUco/AprilTag 마커 감지 프로그램.

## Architecture
```
marker_detector/
  __main__.py          # python -m marker_detector 지원
  main.py              # CLI argparse entry point
  detector.py           # 마커 감지 + 포즈 추정 + OSD + CSV 기록
  cameras/
    __init__.py         # create_camera() 팩토리
    base.py             # CameraConfig + BaseCamera ABC
    luxonis.py          # depthai (OAK-D / OAK-1)
    orbbec.py           # pyorbbecsdk (Gemini E, Gemini 2L)
    basler.py           # pypylon
```

## Camera Interface
- `open(config: CameraConfig)` — 카메라 초기화, 스트리밍 시작
- `read_frame() -> np.ndarray` — BGR 프레임 반환
- `get_camera_matrix() -> np.ndarray` — 3x3 intrinsics
- `get_dist_coeffs() -> np.ndarray` — 왜곡 계수
- `close()` — 리소스 정리

## CLI Arguments
| Arg | Default | Description |
|-----|---------|-------------|
| --camera | auto-detect | oakd, oak1, gemini_e, gemini_2l, basler |
| --width | 1280 | Resolution width |
| --height | 720 | Resolution height |
| --fps | 30 | 15, 30, 60 |
| --marker-size | 0.05 | Marker size in meters |
| --calib | None | Calibration YAML path |

## Marker Detection
- Dictionaries: ArUco 4x4_50, 6x6_250, AprilTag 36h11, 25h9
- 6D pose estimation (rvec/tvec → rx,ry,rz degrees + tx,ty,tz meters)
- CSV logging: timestamp, marker_id, dict, tx, ty, tz, rx, ry, rz, distance

## Key Controls
1~4: dictionary switch, p: pose toggle, r: record toggle, q: quit
