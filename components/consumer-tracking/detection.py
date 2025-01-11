import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import os
import numpy as np
import cv2
import hailo
import pprint
import supervision as sv
from hailo_rpi_common import (
    get_caps_from_pad,
    get_numpy_from_buffer,
    app_callback_class,
)
from detection_pipeline import GStreamerDetectionApp

tracker = sv.ByteTrack()
label_annotator = sv.LabelAnnotator()

# Set to keep track of emitted tracking IDs
emitted_ids = set()

# Define the target classes for detection
# this should align to the COCO list of objects
target_classes = {'car', 'bus', 'truck', 'motorcycle'}

# -----------------------------------------------------------------------------------------------
# User-defined class to be used in the callback function
# -----------------------------------------------------------------------------------------------
# Inheritance from the app_callback_class
class user_app_callback_class(app_callback_class):
    def __init__(self):
        super().__init__()
        self.new_variable = 42  # New variable example

    def new_function(self):  # New function example
        return "The meaning of life is: "

# -----------------------------------------------------------------------------------------------
# User-defined callback function
# -----------------------------------------------------------------------------------------------

# This is the callback function that will be called when data is available from the pipeline
def app_callback(pad, info, user_data):
    # Get the GstBuffer from the probe info
    buffer = info.get_buffer()
    if buffer is None:
        return Gst.PadProbeReturn.OK

    # Increment frame count
    user_data.increment()

    # Get the caps from the pad
    format, width, height = get_caps_from_pad(pad)

    # Retrieve the video frame if required
    frame = None
    if user_data.use_frame and format and width and height:
        frame = get_numpy_from_buffer(buffer, format, width, height)

    # Extract detections from the buffer
    roi = hailo.get_roi_from_buffer(buffer)
    hailo_detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    # Filter detections to include only target classes
    filtered_detections = [
        detection for detection in hailo_detections
        if detection.get_label() in target_classes
    ]

    # Prepare detection data for Supervision
    boxes = []
    confidences = []
    class_ids = []

    for detection in filtered_detections:
        tracking_id = detection.get_objects_typed(hailo.HAILO_UNIQUE_ID)[0].get_id()
        # Emit event only if the tracking ID hasn't been emitted before
        if tracking_id not in emitted_ids:
            print(f"Detection!: {tracking_id} {detection.get_label()} {detection.get_confidence():.2f}\n")
            emitted_ids.add(tracking_id)
    
        label = detection.get_label()
        bbox = detection.get_bbox()
        confidence = detection.get_confidence()
        boxes.append([bbox.xmin() * width, bbox.ymin() * height, bbox.xmax() * width, bbox.ymax() * height])
        confidences.append(confidence)
        class_ids.append(label)  # Ensure label is an integer class ID

    return Gst.PadProbeReturn.OK


if __name__ == "__main__":
    # Create an instance of the user app callback class
    user_data = user_app_callback_class()
    app = GStreamerDetectionApp(app_callback, user_data)
    app.run()
