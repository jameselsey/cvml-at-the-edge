gst-launch-1.0 shmsrc socket-path=/tmp/infered.feed do-timestamp=true is-live=true ! \
	video/x-raw, format=NV12, width=640, height=640, framerate=30/1 ! \
	videoconvert ! autovideosink sync=false

