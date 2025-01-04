gst-launch-1.0 \
libcamerasrc  ! \
decodebin ! videoconvert n-threads=1 qos=false ! video/x-raw,format=RGB ! \
hailocropper so-path=/local/workspace/tappas/apps/gstreamer/libs/post_processes//cropping_algorithms/libwhole_buffer.so function-name=create_crops use-letterbox=true resize-method=inter-area internal-offset=true name=cropper1 \
hailoaggregator name=agg1 \
cropper1. ! queue name=bypess1_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! agg1. \
cropper1. ! \
queue leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! \
videoscale qos=false n-threads=2 ! \
video/x-raw, pixel-aspect-ratio=1/1 ! \
queue leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! \
hailonet hef-path=/local/workspace/tappas/apps/gstreamer/general/detection/resources/yolov8m.hef batch-size=1 ! \
queue leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! \
hailofilter function-name=yolov5 so-path=/local/workspace/tappas/apps/gstreamer/libs/post_processes//libyolo_post.so config-path=/local/workspace/tappas/apps/gstreamer/general/detection/resources/configs/yolov5.json qos=false ! \
queue leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! agg1. \
agg1. ! hailotracker name=hailo_tracker class-id=1 kalman-dist-thr=0.8 iou-thr=0.8 init-iou-thr=0.8 keep-new-frames=4 keep-tracked-frames=10 keep-lost-frames=8 qos=false ! \
queue leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! \
hailooverlay qos=false ! \
queue leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! \
videoconvert n-threads=2 qos=false ! \
fpsdisplaysink video-sink=xvimagesink name=hailo_display sync=false
