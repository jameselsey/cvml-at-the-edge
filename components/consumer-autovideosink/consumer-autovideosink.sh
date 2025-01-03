gst-launch-1.0 shmsrc socket-path=/tmp/feed.raw  ! \
	video/x-raw,format=NV12,width=1920,height=1080,framerate=30/1 ! \
	videoconvert ! autovideosink sync=false

