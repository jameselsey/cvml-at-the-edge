gst-launch-1.0 shmsrc socket-path=/tmp/infered.feed do-timestamp=true is-live=true ! \
	video/x-raw, format=RGB, width=1920, height=1080, framerate=30/1 ! \
	videoconvert ! autovideosink sync=false

