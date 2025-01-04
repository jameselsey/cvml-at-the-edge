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
    string_to_print = f"Frame count: {user_data.get_count()}\n"

    # Get the caps from the pad
    format, width, height = get_caps_from_pad(pad)

    # Retrieve the video frame if required
    frame = None
    if user_data.use_frame and format and width and height:
        frame = get_numpy_from_buffer(buffer, format, width, height)

    # Extract detections from the buffer
    roi = hailo.get_roi_from_buffer(buffer)
    hailo_detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    # Prepare detection data for Supervision
    boxes = []
    confidences = []
    class_ids = []

    for detection in hailo_detections:
        print(f"Detection: {detection.get_label()} {detection.get_confidence():.2f}\n")
        label = detection.get_label()
        bbox = detection.get_bbox()
        confidence = detection.get_confidence()
        boxes.append([bbox.xmin() * width, bbox.ymin() * height, bbox.xmax() * width, bbox.ymax() * height])
        confidences.append(confidence)
        class_ids.append(label)  # Ensure label is an integer class ID

    if boxes:
        # Convert lists to numpy arrays
        boxes = np.array(boxes)
        confidences = np.array(confidences)
        class_ids = np.array(class_ids)


        # Create Supervision Detections object
        detections = sv.Detections(
            xyxy=boxes,
            confidence=confidences,
            class_id=class_ids
        )
    else:
        #init with empty
        detections = sv.Detections.empty()

    # Update tracker with current detections
    # tracked_objects = byte_tracker.update(detections=detections)

    # Annotate frame with tracking information if frame is available
    frame = None
    if frame is not None:
        # Initialize annotator
        box_annotator = sv.BoxAnnotator()

        # Annotate frame
        frame = box_annotator.annotate(scene=frame, detections=tracked_objects)

        # Display additional information
        cv2.putText(frame, f"Detections: {len(tracked_objects)}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(frame, f"{user_data.new_function()} {user_data.new_variable}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        # Convert frame to BGR for display
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        user_data.set_frame(frame)

    # Print frame and detection information
    print(string_to_print)
    return Gst.PadProbeReturn.OK


if __name__ == "__main__":
    # Create an instance of the user app callback class
    user_data = user_app_callback_class()
    app = GStreamerDetectionApp(app_callback, user_data)
    app.run()
