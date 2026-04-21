# Marker Detector

OAK-D, Orbbec Gemini E/2L, Basler 카메라를 지원하는 범용 ArUco / AprilTag 마커 감지 프로그램.

## Features

- **멀티 카메라 지원**: Luxonis OAK-D / OAK-1 (depthai), Orbbec Gemini E / Gemini 2L (pyorbbecsdk), Basler (pypylon)
- **자동 감지 및 런타임 전환**: 연결된 카메라 자동 탐색, `C` 키로 전환
- **마커 딕셔너리**: ArUco 4x4_50, 6x6_250, AprilTag 36h11, 25h9
- **6D 포즈 추정**: `rvec` / `tvec` → 회전 (도), 위치 (미터), 거리
- **CSV 기록**: `timestamp, marker_id, dict, tx, ty, tz, rx, ry, rz, distance`
- **실시간 포즈 그래프**: matplotlib 기반 5초 히스토리 플롯 (보간/끊김 토글)
- **런타임 해상도 · FPS 변경**: `F1`~`F4`, `+` / `-`

## Requirements

- Python 3.8+
- `opencv-contrib-python` (ArUco 모듈 포함)
- `numpy`, `matplotlib`
- 사용할 카메라 SDK:
  - OAK-D: `depthai`
  - Orbbec: `pyorbbecsdk`
  - Basler: `pypylon`

## Installation

```bash
git clone https://github.com/SimonLee9/marker_detect.git
cd marker_detect
pip install opencv-contrib-python numpy matplotlib
# 사용할 카메라에 맞춰 설치
pip install depthai pypylon
# pyorbbecsdk는 소스 빌드 필요
```

## Usage

상위 디렉토리에서 모듈로 실행:

```bash
python -m marker_detector                     # 자동 감지
python -m marker_detector --camera oakd       # 명시 지정
python -m marker_detector --camera gemini_e --width 1280 --height 720 --fps 30
python -m marker_detector --marker-size 0.05 --calib calib.yaml
```

### CLI 옵션

| 인자 | 기본값 | 설명 |
|---|---|---|
| `--camera` | 자동 감지 | `oakd`, `oak1`, `gemini_e`, `gemini_2l`, `basler` |
| `--width` | 640 | 해상도 가로 |
| `--height` | 480 | 해상도 세로 |
| `--fps` | 30 | 15 / 30 / 60 |
| `--marker-size` | 0.05 | 마커 한 변 길이 (m) |
| `--calib` | None | OpenCV calibration YAML 경로 |

## Key Controls

| 키 | 동작 |
|---|---|
| `1` ~ `4` | 마커 딕셔너리 전환 (4x4_50 / 6x6_250 / 36h11 / 25h9) |
| `P` | 포즈 추정 토글 |
| `R` | CSV 기록 시작 / 중지 |
| `G` | 실시간 포즈 그래프 토글 |
| `T` | 그래프 모드 전환 |
| `I` | 그래프 보간 토글 |
| `C` | 카메라 전환 (여러 대 연결 시) |
| `F1` ~ `F4` | 해상도 프리셋 (640x360 / 640x480 / 1280x720 / 1920x1080) |
| `+` / `-` | FPS 증감 (15 / 30 / 60) |
| `Q` | 종료 |

## Project Structure

```
marker_detector/
├── __main__.py          # python -m marker_detector 엔트리
├── main.py              # CLI 파싱 + 메인 루프
├── detector.py          # 마커 감지, 포즈 추정, OSD, CSV 기록
├── pose_plot.py         # 실시간 포즈 플롯
├── cameras/
│   ├── __init__.py      # create_camera() 팩토리 + 자동 감지
│   ├── base.py          # CameraConfig + BaseCamera ABC
│   ├── luxonis.py       # OAK-D / OAK-1 (depthai)
│   ├── orbbec.py        # Orbbec Gemini E / 2L (pyorbbecsdk)
│   └── basler.py        # Basler (pypylon)
└── docs/
    └── design.md        # 설계 명세
```
