gst-launch-1.0 shmsrc socket-path=/tmp/feed.raw do-timestamp=1 ! \
	video/x-raw,format=NV12,width=1920,height=1080,framerate=30/1 ! \
	queue max-size-buffers=2 leaky=downstream ! \
	videorate ! video/x-raw,framerate=30/1 ! \
	videoconvert ! video/x-raw,format=I420 ! \
	x264enc key-int-max=25 tune=zerolatency speed-preset=ultrafast bitrate=1000 ! \
	h264parse ! \
	kvssink stream-name="demo_stream" access-key="$AWS_ACCESS_KEY" secret-key="$AWS_SECRET_ACCESS_KEY" aws-region="$AWS_REGION" max-latency=100
