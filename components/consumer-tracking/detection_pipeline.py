import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import os
import argparse
import multiprocessing
import numpy as np
import setproctitle
import cv2
import time
import hailo
import supervision as sv
from hailo_rpi_common import (
    get_default_parser,
    QUEUE,
    SOURCE_PIPELINE,
    INFERENCE_PIPELINE,
    INFERENCE_PIPELINE_WRAPPER,
    USER_CALLBACK_PIPELINE,
    DISPLAY_PIPELINE,
    GStreamerApp,
    app_callback_class,
    dummy_callback,
    detect_hailo_arch,
)



# -----------------------------------------------------------------------------------------------
# User Gstreamer Application
# -----------------------------------------------------------------------------------------------

# This class inherits from the hailo_rpi_common.GStreamerApp class
class GStreamerDetectionApp(GStreamerApp):
    def __init__(self, app_callback, user_data):
        parser = get_default_parser()
        parser.add_argument(
            "--labels-json",
            default=None,
            help="Path to costume labels JSON file",
        )
        args = parser.parse_args()
        # Call the parent class constructor
        super().__init__(args, user_data)
        # Additional initialization code can be added here
        # Set Hailo parameters these parameters should be set based on the model used
        self.batch_size = 2
        self.network_width = 640
        self.network_height = 640
        self.network_format = "RGB"
        nms_score_threshold = 0.3
        nms_iou_threshold = 0.45


        # Determine the architecture if not specified
        if args.arch is None:
            detected_arch = detect_hailo_arch()
            if detected_arch is None:
                raise ValueError("Could not auto-detect Hailo architecture. Please specify --arch manually.")
            self.arch = detected_arch
            print(f"Auto-detected Hailo architecture: {self.arch}")
        else:
            self.arch = args.arch


        if args.hef_path is not None:
            self.hef_path = args.hef_path
        # Set the HEF file path based on the arch
        elif self.arch == "hailo8":
            self.hef_path = os.path.join(self.current_path, '../resources/yolov8m.hef')
        else:  # hailo8l
            self.hef_path = os.path.join(self.current_path, '../resources/yolov8s_h8l.hef')

        # Set the post-processing shared object file
        self.post_process_so = os.path.join(self.current_path, 'libyolo_hailortpp_postprocess.so')

        # User-defined label JSON file
        self.labels_json = args.labels_json

        self.app_callback = app_callback

        self.thresholds_str = (
            f"nms-score-threshold={nms_score_threshold} "
            f"nms-iou-threshold={nms_iou_threshold} "
            f"output-format-type=HAILO_FORMAT_TYPE_FLOAT32"
        )

        # Set the process title
        setproctitle.setproctitle("Hailo Detection App")

        self.create_pipeline()

    def get_pipeline_string(self):
        source_pipeline = SOURCE_PIPELINE(self.video_source)
        detection_pipeline = INFERENCE_PIPELINE(
            hef_path=self.hef_path,
            post_process_so=self.post_process_so,
            batch_size=self.batch_size,
            config_json=self.labels_json,
            additional_params=self.thresholds_str)
        user_callback_pipeline = USER_CALLBACK_PIPELINE()
        display_pipeline = DISPLAY_PIPELINE(video_sink=self.video_sink, sync=self.sync, show_fps=self.show_fps)
        pipeline_string = (
            f'{source_pipeline} '
            f'{detection_pipeline} ! '
            f'{user_callback_pipeline} ! '
            f'{display_pipeline}'
        )


        #override the pipeline string to use tracking
        pipeline_string = (
           source_pipeline
           + "tee name=t ! "
           + QUEUE("bypass_queue", max_size_buffers=20)
           + "! mux.sink_0 "
           + "t. ! "
           + QUEUE("queue_hailonet")
           + "! videoconvert n-threads=3 ! "
           + f"hailonet hef-path={self.hef_path} batch-size={self.batch_size} {self.thresholds_str} force-writable=true ! "
           + QUEUE("queue_hailofilter")
           + f"! hailofilter so-path={self.post_process_so} qos=false ! "
           + QUEUE("queue_hailotracker")
           + "! hailotracker keep-tracked-frames=3 keep-new-frames=3 keep-lost-frames=3 ! "
           + QUEUE("queue_hmuc")
           + "! mux.sink_1 "
           + "hailomuxer name=mux ! "
           + QUEUE("queue_hailo_python")
           + " ! "
           + QUEUE("queue_user_callback")
           + "! identity name=identity_callback ! "
           + QUEUE("queue_hailooverlay")
           + "! hailooverlay ! "
           + QUEUE("queue_videoconvert")
           + "! videoconvert n-threads=3 qos=false ! "
           + QUEUE("queue_textoverlay")
           + "! textoverlay name=hailo_text text='' valignment=top halignment=center ! "
           + QUEUE("queue_hailo_display")
           + f"! fpsdisplaysink video-sink={self.video_sink} name=hailo_display sync={self.sync} text-overlay={self.show_fps} signal-fps-measurements=true "
        )

        print(pipeline_string)
        return pipeline_string

if __name__ == "__main__":
    # Create an instance of the user app callback class
    user_data = app_callback_class()

    START = sv.Point(0, 340)
    END = sv.Point(640, 340)

    line_zone = sv.LineZone(start=START, end=END, triggering_anchors=(sv.Position.BOTTOM_LEFT, sv.Position.BOTTOM_RIGHT))

    app_callback = dummy_callback
    app = GStreamerDetectionApp(app_callback, user_data)
    app.run()
