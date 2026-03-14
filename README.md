# Traffic Recorder Project

This project provides a simple framework for capturing and recording live camera
feeds along West Virginia’s Interstate 64 corridor.  It is intended as a
baseline from which more sophisticated features—such as object detection or
analytics—can be added later.  At its core the recorder simply opens a
streaming feed, writes the frames to disk, and optionally reconnects if the
connection drops.

## Key Features

- **Camera configuration** – A JSON file in the `config` directory lists each
  camera by name, county code, route and a streaming URL placeholder.  You
  should replace the `stream_url` values with the actual stream endpoints
  extracted from the WV511 site or other sources.
- **Recording** – The recorder opens each configured stream and writes it to a
  timestamped video file in the `recordings` directory.  It will attempt to
  reconnect if the stream drops.
- **Duration control** – You can specify how long the recorder should run for
  via a command‑line argument.  For example, `--duration 7200` will record
  for two hours.
- **Extensible design** – The project is structured so that future tasks
  (e.g. downloading stream URLs, threading multiple recorders, or adding
  analytics) can be added without major refactoring.

## Directory Structure

```
traffic_recorder/
├── README.md             # this file
├── requirements.txt       # Python dependencies
├── config/
│   └── cameras.json       # camera definitions (update with real stream URLs)
├── recordings/            # destination for saved video files
├── src/
│   ├── __init__.py        # makes src a module
│   ├── camera_recorder.py # class for connecting to and recording a camera
│   ├── main.py            # CLI entry point
│   └── utils.py           # helper utilities
└── data/                  # placeholder for other assets or logs
```

## Getting Started

1. **Install dependencies.**  From within the project root run:

   ```bash
   pip install -r requirements.txt
   ```

2. **Edit `config/cameras.json`.**  Replace the `stream_url` placeholders
   with actual streaming URLs.  You can obtain these by inspecting the
   network traffic on the WV511 camera pages or by using a tool like
   *youtube-dl* or browser developer tools.

3. **Run the recorder.**  To record all configured cameras for two hours:

   ```bash
   python -m traffic_recorder.src.main --duration 7200
   ```

   The recorded files will be saved in the `recordings` directory with
   timestamped filenames.

## Notes

- This implementation uses OpenCV (`cv2`) for opening and writing video
  streams.  OpenCV supports many common streaming formats (RTSP, HTTP MJPEG,
  etc.), but you may need to install additional codecs depending on your
  environment.
- If a stream drops, the recorder will attempt to reconnect every few
  seconds.  Adjust the retry logic in `camera_recorder.py` if needed.
- The project is intentionally minimal.  It does not perform object
  detection or any analytics; it simply records the raw video.  You can
  extend it by adding your own processing pipeline in the `CameraRecorder`
  class.