#!/usr/bin/env python3
"""범용 마커 감지 프로그램 - OAK-D, Orbbec Gemini E/2L, Basler 지원
카메라 자동 감지, 런타임 전환 지원"""

import argparse
import cv2
from marker_detector.cameras import create_camera, detect_cameras, CAMERA_REGISTRY
from marker_detector.cameras.base import CameraConfig
from marker_detector.detector import MarkerDetector

# 해상도 프리셋
RESOLUTION_PRESETS = [
    (640, 360),
    (640, 480),
    (1280, 720),
    (1920, 1080),
]

FPS_OPTIONS = [15, 30, 60]

# Linux GTK에서 F1~F4 키코드
KEY_F1 = 0xFFBE
KEY_F2 = 0xFFBF
KEY_F3 = 0xFFC0
KEY_F4 = 0xFFC1


def parse_args():
    parser = argparse.ArgumentParser(
        description="Universal ArUco / AprilTag Marker Detector"
    )
    parser.add_argument(
        "--camera", required=False, default=None,
        choices=list(CAMERA_REGISTRY.keys()),
        help="Camera type (auto-detect if omitted)"
    )
    parser.add_argument("--width", type=int, default=640, help="Resolution width (default: 640)")
    parser.add_argument("--height", type=int, default=480, help="Resolution height (default: 480)")
    parser.add_argument("--fps", type=int, default=30, choices=[15, 30, 60], help="FPS (default: 30)")
    parser.add_argument("--marker-size", type=float, default=0.05, help="Marker size in meters (default: 0.05)")
    parser.add_argument("--calib", type=str, default=None, help="Calibration YAML file path")
    return parser.parse_args()


def change_resolution(camera, res_idx, fps_idx, calib_file):
    """해상도/FPS 변경 후 카메라 재시작"""
    w, h = RESOLUTION_PRESETS[res_idx]
    fps = FPS_OPTIONS[fps_idx]
    new_config = CameraConfig(width=w, height=h, fps=fps, calib_file=calib_file)
    print(f">> 변경 중: {w}x{h} @ {fps}fps ...")
    try:
        camera.reopen(new_config)
        camera_matrix = camera.get_camera_matrix()
        dist_coeffs = camera.get_dist_coeffs()
        print(f">> 변경 완료: {camera.config.width}x{camera.config.height} @ {camera.config.fps}fps")
        return camera_matrix, dist_coeffs
    except Exception as e:
        print(f">> 변경 실패: {e}")
        return None, None


def switch_camera(available_cameras, cam_idx, config, calib_file):
    """다른 카메라로 전환"""
    cam_type, cam_display = available_cameras[cam_idx]
    print(f">> 카메라 전환: {cam_display} ...")
    new_config = CameraConfig(
        width=config.width, height=config.height,
        fps=config.fps, calib_file=calib_file
    )
    try:
        camera = create_camera(cam_type, new_config)
        camera.open()
        camera_matrix = camera.get_camera_matrix()
        dist_coeffs = camera.get_dist_coeffs()
        print(f">> 전환 완료: {cam_display}")
        return camera, cam_type, camera_matrix, dist_coeffs
    except Exception as e:
        print(f">> 전환 실패: {e}")
        return None, None, None, None


def main():
    args = parse_args()

    # 카메라 감지
    print("카메라 감지 중...")
    available_cameras = detect_cameras()

    if args.camera:
        # 명시적 지정
        camera_type = args.camera
        display_name = args.camera
        for ct, dn in available_cameras:
            if ct == args.camera:
                display_name = dn
                break
    else:
        # 자동 감지
        if len(available_cameras) == 0:
            print("[Error] 연결된 카메라가 없습니다.")
            return

        print(f"\n감지된 카메라 ({len(available_cameras)}개):")
        for i, (ct, dn) in enumerate(available_cameras):
            print(f"  [{i}] {dn}")

        if len(available_cameras) == 1:
            camera_type = available_cameras[0][0]
            display_name = available_cameras[0][1]
            print(f"\n>> 자동 선택: {display_name}")
        else:
            # 여러 대면 첫 번째 자동 선택 (c키로 전환 가능)
            camera_type = available_cameras[0][0]
            display_name = available_cameras[0][1]
            print(f"\n>> 자동 선택: {display_name} (C키로 전환 가능)")

    config = CameraConfig(
        width=args.width,
        height=args.height,
        fps=args.fps,
        calib_file=args.calib,
    )

    camera = create_camera(camera_type, config)
    detector = MarkerDetector(marker_size=args.marker_size)

    try:
        camera.open()
    except Exception as e:
        print(f"[Error] Failed to open camera: {e}")
        return

    camera_matrix = camera.get_camera_matrix()
    dist_coeffs = camera.get_dist_coeffs()

    # 현재 프리셋 인덱스
    res_idx = 0
    for i, (w, h) in enumerate(RESOLUTION_PRESETS):
        if w == camera.config.width and h == camera.config.height:
            res_idx = i
            break

    fps_idx = 0
    for i, f in enumerate(FPS_OPTIONS):
        if f == camera.config.fps:
            fps_idx = i
            break

    cam_idx = 0
    for i, (ct, _) in enumerate(available_cameras):
        if ct == camera_type:
            cam_idx = i
            break

    print("=" * 65)
    print(f" Universal Marker Detector")
    print(f" Camera : {display_name}")
    print(f" Resolution: {camera.config.width}x{camera.config.height} @ {camera.config.fps}fps")
    print(f" Marker size: {args.marker_size}m")
    if camera_matrix is not None:
        print(f" Calibration: OK")
    else:
        print(f" Calibration: None (pose disabled)")
    if len(available_cameras) > 1:
        print(f" Available: {len(available_cameras)} cameras (C to switch)")
    print("=" * 65)
    print(" 1~4: Dict | P: Pose | R: Rec | C: Camera | Q: Quit")
    print(" F1: 640x360  F2: 640x480  F3: 1280x720  F4: 1920x1080")
    print(" +: FPS up  -: FPS down  (15/30/60)")
    print("=" * 65)

    detector.set_camera_info(camera.config, res_idx, fps_idx, camera_type, available_cameras)

    none_count = 0
    try:
        while True:
            frame = camera.read_frame()
            if frame is None:
                none_count += 1
                # 연속 30프레임 실패 → 카메라 재연결 시도
                if none_count > 30:
                    print(">> 카메라 응답 없음, 재연결 시도...")
                    try:
                        camera.close()
                    except Exception:
                        pass
                    # USB 리셋 후 재연결
                    from marker_detector.cameras import reset_usb_ports
                    reset_usb_ports()
                    try:
                        camera = create_camera(camera_type, CameraConfig(
                            width=RESOLUTION_PRESETS[res_idx][0],
                            height=RESOLUTION_PRESETS[res_idx][1],
                            fps=FPS_OPTIONS[fps_idx],
                            calib_file=args.calib,
                        ))
                        camera.open()
                        camera_matrix = camera.get_camera_matrix()
                        dist_coeffs = camera.get_dist_coeffs()
                        none_count = 0
                        print(">> 재연결 성공")
                    except Exception as e:
                        print(f">> 재연결 실패: {e}")
                        import time as _time
                        _time.sleep(3)
                continue

            none_count = 0
            frame = detector.detect_and_draw(frame, camera_matrix, dist_coeffs)
            cv2.imshow("Marker Detector", frame)

            key = cv2.waitKeyEx(1)
            if key == -1:
                continue

            key_lower = key & 0xFF

            if key_lower == ord('q'):
                break
            elif ord('1') <= key_lower <= ord('4'):
                detector.switch_dict(key_lower - ord('1'))
            elif key_lower == ord('p'):
                detector.toggle_pose()
            elif key_lower == ord('r'):
                detector.toggle_recording()
            elif key_lower == ord('g'):
                detector.toggle_graph()
            elif key_lower == ord('t'):
                detector.toggle_graph_mode()
            elif key_lower == ord('i'):
                detector.toggle_interpolate()

            # 카메라 전환: C
            elif key_lower == ord('c'):
                if len(available_cameras) <= 1:
                    print(">> 전환 가능한 카메라가 없습니다")
                else:
                    new_cam_idx = (cam_idx + 1) % len(available_cameras)
                    camera.close()
                    result = switch_camera(
                        available_cameras, new_cam_idx,
                        camera.config, args.calib
                    )
                    if result[0] is not None:
                        camera, camera_type, camera_matrix, dist_coeffs = result
                        cam_idx = new_cam_idx
                        display_name = available_cameras[cam_idx][1]
                        detector.set_camera_info(
                            camera.config, res_idx, fps_idx,
                            camera_type, available_cameras
                        )
                    else:
                        # 실패 시 이전 카메라 다시 열기
                        camera = create_camera(
                            available_cameras[cam_idx][0],
                            CameraConfig(
                                width=RESOLUTION_PRESETS[res_idx][0],
                                height=RESOLUTION_PRESETS[res_idx][1],
                                fps=FPS_OPTIONS[fps_idx],
                                calib_file=args.calib,
                            )
                        )
                        camera.open()
                        camera_matrix = camera.get_camera_matrix()
                        dist_coeffs = camera.get_dist_coeffs()

            # 해상도 변경: F1~F4
            elif key in (KEY_F1, KEY_F2, KEY_F3, KEY_F4):
                new_res_idx = key - KEY_F1
                if new_res_idx != res_idx:
                    res_idx = new_res_idx
                    result = change_resolution(camera, res_idx, fps_idx, args.calib)
                    if result[0] is not None:
                        camera_matrix, dist_coeffs = result
                        detector.set_camera_info(
                            camera.config, res_idx, fps_idx,
                            camera_type, available_cameras
                        )

            # FPS 변경: +/-
            elif key_lower in (ord('+'), ord('=')):
                if fps_idx < len(FPS_OPTIONS) - 1:
                    fps_idx += 1
                    result = change_resolution(camera, res_idx, fps_idx, args.calib)
                    if result[0] is not None:
                        camera_matrix, dist_coeffs = result
                        detector.set_camera_info(
                            camera.config, res_idx, fps_idx,
                            camera_type, available_cameras
                        )

            elif key_lower == ord('-'):
                if fps_idx > 0:
                    fps_idx -= 1
                    result = change_resolution(camera, res_idx, fps_idx, args.calib)
                    if result[0] is not None:
                        camera_matrix, dist_coeffs = result
                        detector.set_camera_info(
                            camera.config, res_idx, fps_idx,
                            camera_type, available_cameras
                        )

    finally:
        if detector.recording:
            detector.stop_recording()
        detector.close_graph()
        camera.close()
        cv2.destroyAllWindows()
        print("종료")


if __name__ == "__main__":
    main()
