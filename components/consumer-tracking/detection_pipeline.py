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
        
        self.cropper_process_so = os.path.join(self.current_path, 'libwhole_buffer.so')

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

        source_pipeline2 = "shmsrc socket-path=/tmp/feed.raw do-timestamp=true is-live=true ! "
        source_pipeline2 += "video/x-raw, format=NV12, width=1920, height=1080, framerate=30/1 ! "
        #source_pipeline2 += "videoconvert ! "
        #source_pipeline2 += "identity name=source_video_convert silent=false ! "
        #source_pipeline2 += "queue name=source_scale_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! "
        #source_pipeline2 += "videoscale name=source_videoscale n-threads=2 ! "
        #source_pipeline2 += "queue name=source_convert_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! "
        #source_pipeline2 += "videoconvert n-threads=3 name=source_convert qos=false ! "
        #source_pipeline += "video/x-raw, format=RGB, pixel-aspect-ratio=1/1 ! "
        #override the pipeline string to use tracking

       
        access_key = os.getenv("AWS_ACCESS_KEY")
        secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        region = os.getenv("AWS_REGION")

        kvs_element = (
            "video/x-raw,format=NV12,width=1920,height=1080,framerate=30/1 ! "
    	    + "queue max-size-buffers=2 leaky=downstream ! "
	        + "videorate ! video/x-raw,framerate=30/1 ! "
	        + "videoconvert ! video/x-raw,format=I420 ! "
	        + "x264enc key-int-max=25 tune=zerolatency speed-preset=ultrafast bitrate=1000 ! "
	        + "h264parse ! "
	        + f"kvssink stream-name=\"demo_stream\" access-key=\"{access_key}\" secret-key=\"{secret_access_key}\" aws-region=\"{region}\" max-latency=100 "
        )

        pipeline_string2 = (
           source_pipeline2
           + "tee name=t ! "
           + QUEUE("bypass_queue", max_size_buffers=20)
#           + "! video/x-raw,format=NV12,width=1920,height=1080,framerate=30/1 "
           + "! identity name=sink_0_end silent=false "
           + "! mux.sink_0 "
           + "t. ! "
           + "queue leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! "
           + "videoscale n-threads=2 ! "
           + "queue leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! "
           + "videoconvert n-threads=3 qos=false ! "
           + "video/x-raw, format=RGB, pixel-aspect-ratio=1/1 ! "
           + QUEUE("queue_hailonet")
           + f"! hailonet hef-path={self.hef_path} batch-size={self.batch_size} {self.thresholds_str} force-writable=true ! "
           + QUEUE("queue_hailofilter")
           + f"! hailofilter so-path={self.post_process_so} qos=false ! "
           + QUEUE("queue_hailotracker")
           + "! hailotracker keep-tracked-frames=3 keep-new-frames=3 keep-lost-frames=3 ! "
           + QUEUE("queue_hmuc")
           + "! mux.sink_1 "
           + "hailomuxer name=mux ! "
           + "identity name=mux_inspector silent=false ! "
           + QUEUE("queue_hailo_python")
           + " ! "
           + QUEUE("queue_user_callback")
           + "! identity name=identity_callback ! "
           + QUEUE("queue_hailooverlay")
           + "! hailooverlay ! "
           + QUEUE("queue_videoconvert")
           + "! videoconvert n-threads=3 qos=false ! "
      #     + QUEUE("queue_textoverlay")
      #     + "! textoverlay name=hailo_text text='test text' valignment=top halignment=center ! "
           + QUEUE("queue_hailo_display")
           + "! identity name=identity_inspect silent=false  "
           #+ "! video/x-raw, format=NV12,width=1920,height=1080,framerate=30/1  "
           #+ "! shmsink socket-path=/tmp/infered.feed sync=false wait-for-connection=false"
           #+ kvs_element
           + f"! fpsdisplaysink video-sink={self.video_sink} name=hailo_display sync={self.sync} text-overlay={self.show_fps} signal-fps-measurements=true "
        )


        jarno_pipeline = (
            "shmsrc socket-path=/tmp/feed.raw do-timestamp=true is-live=true ! "
            + "video/x-raw, format=NV12, width=1920, height=1080, framerate=30/1 ! "
            + "videoconvert ! "
            + "video/x-raw, format=RGB, width=1920, height=1080, framerate=30/1 ! "
            + f"hailocropper so-path={self.cropper_process_so} function-name=create_crops use-letterbox=true resize-method=inter-area internal-offset=true name=cropper1 "
            + "hailoaggregator name=agg1 "
            + "cropper1. ! queue name=bypess1_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! agg1. "
            + "cropper1. ! "
            + "queue leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! "
            + "videoscale qos=false n-threads=2 ! "
            + "video/x-raw, pixel-aspect-ratio=1/1 ! "
            + "queue leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! "
            + "hailonet hef-path=yolov8m.hef batch-size=1 ! "
            + "queue leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! "
            + f"hailofilter so-path={self.post_process_so} qos=false ! "
            + "queue leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! agg1. "
            + "agg1. ! hailotracker name=hailo_tracker keep-tracked-frames=3 keep-new-frames=3 keep-lost-frames=3 ! "
            + "queue leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! "
            + "hailooverlay qos=false ! "
            + "queue leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! "
            + "videoconvert n-threads=2 qos=false ! "
            
            # fps displaysink
            #+ "fpsdisplaysink video-sink=xvimagesink name=hailo_display sync=false"
            
            # OR try the shared memory sink
            + "shmsink socket-path=/tmp/infered.feed sync=false wait-for-connection=false"
            
        )
        print(jarno_pipeline)
        return jarno_pipeline

if __name__ == "__main__":
    # Create an instance of the user app callback class
    user_data = app_callback_class()

    START = sv.Point(0, 340)
    END = sv.Point(640, 340)

    line_zone = sv.LineZone(start=START, end=END, triggering_anchors=(sv.Position.BOTTOM_LEFT, sv.Position.BOTTOM_RIGHT))

    app_callback = dummy_callback
    app = GStreamerDetectionApp(app_callback, user_data)
    app.run()
