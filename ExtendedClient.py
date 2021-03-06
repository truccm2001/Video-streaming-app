from tkinter import *
from PIL import Image, ImageTk
from tkinter import messagebox
import socket, threading, sys, traceback, os
from RtpPacket import RtpPacket
import time

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"
SESSION_FILE = "session.txt"

class Client:
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    SETUP = 0
    PLAY = 1
    PAUSE = 2
    TEARDOWN = 3
    DESCRIBE = 4

    totalTime = 25

    def __init__(self, master, serveraddr, serverport, rtpport, fileName):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.handler)
        self.createWidgets()
        self.serverAddr = serveraddr
        self.serverPort = int(serverport)
        self.rtpPort = int(rtpport)
        self.fileName = fileName
        self.rtspSeq = 0
        self.sessionId = 0
        self.requestSent = -1
        self.teardownAcked = 0
        self.connectToServer()
        self.frameNbr = 0
        self.bytesReceived = 0
        self.startTime = 0
        self.lossCounter = 0
        self.firstPlay = True
        self.finish_time = 0

	# Initiatio
	# THIS GUI IS JUST FOR REFERENCE ONLY, STUDENTS HAVE TO CREATE THEIR OWN GUI
    def createWidgets(self):
        """Build GUI."""
        # Create Play button		
        self.start = Button(self.master, width=20, padx=3, pady=3)
        self.start["text"] = "Play"
        self.start["command"] = self.playMovie
        self.start.grid(row=2, column=0, padx=2, pady=2)    

        # Create Pause button			
        self.pause = Button(self.master, width=20, padx=3, pady=3)
        self.pause["text"] = "Pause"
        self.pause["command"] = self.pauseMovie
        self.pause.grid(row=2, column=1, padx=2, pady=2)
		
        # Create Teardown button
        self.teardown = Button(self.master, width=20, padx=3, pady=3)
        self.teardown["text"] = "Teardown"
        self.teardown["command"] =  self.exitClient
        self.teardown.grid(row=2, column=2, padx=2, pady=2)

        # Create Describe button
        self.describe = Button(self.master, width=20, padx=3, pady=3)
        self.describe["text"] = "Describe"
        self.describe["command"] =  self.describeSession
        self.describe.grid(row=2, column=3, padx=2, pady=2)

        # Create a label to display the movie
        self.label = Label(self.master, height=19)
        self.label.grid(row=0, column=0, columnspan=6, sticky=W+E+N+S, padx=5, pady=5)

        # Create a label to display the total time
        self.timeBox = Label(self.master, width=12)
        self.timeBox.grid(row=1, column=0, columnspan=2, sticky=W+E+N+S, padx=5, pady=5)

        # Create a timebox to display the remaining time
        self.timeBox2 = Label(self.master, width=12)
        self.timeBox2.grid(row=1, column=2, columnspan=2, sticky=W+E+N+S, padx=5, pady=5)

    def exitClient(self):
        """Teardown button handler"""
        self.sendRtspRequest(self.TEARDOWN)
        
        if self.frameNbr != 0:
            f = open(SESSION_FILE, "a")
            
            if self.finish_time == 0:
                self.finish_time = time.time()
            
            #transfer rate:
            dataRate = int(self.bytesReceived / (self.finish_time - self.startTime)) 
            f.write("\n======================= Data Rate ========================\n")
            f.write("Video data rate: " + str(dataRate) + " bytes/sec \n" )
            f.write("Start time (since epoch): " + str(self.startTime) + "s\n")
            f.write("End time (since epoch): " + str(self.finish_time) + "s\n\n")
            print("Video data rate: " + str(dataRate) + " bytes/sec \n")
              
            # loss rate
            lossRate = self.lossCounter / self.frameNbr
            print("RTP Packet Loss Rate: " + str(lossRate) +" %\n")
            f.write("\n==================== Packet Loss Rate ====================\n")
            f.write("RTP Packet Loss Rate: " + str(lossRate) +" %\n\n")
            
        self.master.destroy()
        if self.requestSent != -1:
            os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT)

    def pauseMovie(self):
        """Pause button handler."""
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)

    def playMovie(self):
        """Play button handler"""
        # First time PLAY is clicked, send SETUP
        if self.state == self.INIT and self.firstPlay:
            file = open(SESSION_FILE, "w")
            file.close()
            self.sendRtspRequest(self.SETUP)
            self.firstPlay = False
            while self.state != self.READY:
                pass
        
        self.timeBox.configure(text="Total time:" + "%02d:%02d" % (self.totalTime // 60, self.totalTime % 60))
        
        if self.state == self.READY:
            threading.Thread(target=self.listenRtp).start()
            self.playEvent = threading.Event()
            self.playEvent.clear()
            self.sendRtspRequest(self.PLAY)

    def describeSession(self):
        """Describe button handler"""
        self.sendRtspRequest(self.DESCRIBE)

    def listenRtp(self):
        """Listen for RTP packets."""
        while True:
            try:
                data = self.rtpSocket.recv(20480)
                if data:
                    rtpPacket = RtpPacket()
                    rtpPacket.decode(data)

                    # If sequence number doesn't match, we have a packet loss
                    if self.frameNbr + 1 != rtpPacket.seqNum():
                        self.lossCounter += (rtpPacket.seqNum() - (self.frameNbr + 1))
                        print("Packet loss!")

                    currFrameNbr = rtpPacket.seqNum()
                    #print ("CURRENT SEQUENCE NUM: " + str(currFrameNbr))

                    if currFrameNbr > self.frameNbr: # Accept seq bigger than current frame only
                        # Count the received bytes
                        self.bytesReceived += len(rtpPacket.getPayload())

                        self.frameNbr = currFrameNbr
                        self.updateMovie(self.writeFrame(rtpPacket.getPayload()))

                        # Show the streaming time
                        currentTime = int(currFrameNbr * 0.05)
                        remainingTime = self.totalTime - currentTime
                        if remainingTime <= 0:
                            self.finish_time = time.time()
                        self.timeBox2.configure(text="Remaining time:" + "%02d:%02d" % (remainingTime // 60, remainingTime % 60))
            except:
                if self.playEvent.isSet():
                    break
                if self.teardownAcked == 1:
                    self.rtpSocket.shutdown(socket.SHUT_RDWR)
                    self.rtpSocket.close()
                    break

    def writeFrame(self, data):
        """Write the received frame to a temp image file. Return the image file."""
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        file = open(cachename, "wb")
        file.write(data)
        file.close()
        return cachename

    def updateMovie(self, imageFile):
        """Update the image file as video frame in the GUI."""
        photo = ImageTk.PhotoImage(Image.open(imageFile))
        self.label.configure(image = photo, height=288) 
        self.label.image = photo
		
    def connectToServer(self):
        """Connect to the Server. Start a new RTSP/TCP session."""
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
        except:
            messagebox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.serverAddr)

    def sendRtspRequest(self, requestCode):
        """Send RTSP request to the server."""
        # Setup request
        if requestCode == self.SETUP and self.state == self.INIT:
            threading.Thread(target=self.recvRtspReply).start()
            self.rtspSeq+=1
            request = "SETUP " + str(self.fileName) + " RTSP/1.0\n"
            request+= "CSeq: " + str(self.rtspSeq) + "\n"
            request+= "Transport: RTP/UDP; client_port= " + str(self.rtpPort)
            self.requestSent = self.SETUP
			
		# Play request
        elif requestCode == self.PLAY and self.state == self.READY:
            self.rtspSeq+=1
            request = "PLAY " + str(self.fileName) + " RTSP/1.0\n"
            request += "CSeq: " + str(self.rtspSeq) + "\n"
            request += "Session: " + str(self.sessionId)
            self.requestSent = self.PLAY
            
        # Pause request
        elif requestCode == self.PAUSE and self.state == self.PLAYING:
            self.rtspSeq+=1
            request = "PAUSE " + str(self.fileName) + " RTSP/1.0\n"
            request += "CSeq: " + str(self.rtspSeq) + "\n"
            request += "Session: " + str(self.sessionId)
            self.requestSent = self.PAUSE
			
		# Teardown request
        elif requestCode == self.TEARDOWN and not self.state == self.INIT:
            self.rtspSeq+=1
            request = "TEARDOWN " + str(self.fileName) + " RTSP/1.0\n"
            request += "CSeq: " + str(self.rtspSeq) + "\n"
            request += "Session: " + str(self.sessionId)
            self.requestSent = self.TEARDOWN

        # Describe request
        elif requestCode == self.DESCRIBE and not self.state == self.INIT:
            self.rtspSeq+=1
            request = "DESCRIBE " + str(self.fileName) + " RTSP/1.0\n"
            request += "CSeq: " + str(self.rtspSeq) + "\n"
            request += "Session: " + str(self.sessionId)
            self.requestSent = self.DESCRIBE

        else:
            return
		
		# Send the RTSP request using rtspSocket.
        self.rtspSocket.send(request.encode())
        print ('\nData Sent:\n' + request)
    
    def recvRtspReply(self):
        """Receive RTSP reply from the server."""
        while True:
            reply = self.rtspSocket.recv(1024)
			
            if reply: 
                self.parseRtspReply(reply)

            if self.requestSent == self.TEARDOWN:
                self.rtspSocket.shutdown(socket.SHUT_RDWR)
                self.rtspSocket.close()
                break

    def parseRtspReply(self,data):
        """Parse the RTSP reply from the server"""
        lines = data.decode().split('\n')
        seqNum = int(lines[1].split(' ')[1])
		
        if seqNum == self.rtspSeq:
            session = int(lines[2].split(' ')[1])
			
            if self.sessionId == 0:
                self.sessionId = session
		
            if self.sessionId == session:
                if int(lines[0].split(' ')[1]) == 200: 
                    if self.requestSent == self.SETUP:
                        self.state = self.READY
                        self.openRtpPort() 
					
                    elif self.requestSent == self.PLAY:
                        self.state = self.PLAYING
                        self.startTime = time.time()
                        self.bytesReceived = 0
                    
                    elif self.requestSent == self.PAUSE:
                        self.state = self.READY
                        self.playEvent.set()

                        # Calculate the video data rate
                        dataRate = int(self.bytesReceived / (time.time() - self.startTime))
                        
                        f = open(SESSION_FILE, "a")
                        f.write("\n======================= Data Rate ========================\n")
                        f.write("Video data rate: " + str(dataRate) + " bytes/sec \n" )
                        f.write("Start time (since epoch): " + str(self.startTime) + "s\n")
                        f.write("End time (since epoch): " + str(time.time()) + "s\n\n")
                        print("Video data rate: " + str(dataRate) + " bytes/sec \n")

                    elif self.requestSent == self.TEARDOWN:
                        self.state = self.INIT
                        self.teardownAcked = 1

                    elif self.requestSent == self.DESCRIBE:
                        # Write RTSP payload to session file
                        f = open(SESSION_FILE, "a")
                        for i in range(4, len(lines)):
                            f.write(lines[i] + '\n')
                        f.close()

    def openRtpPort(self):
        """Open RTP socket binded to a specified port."""
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)    
        self.rtpSocket.settimeout(0.5)
		
        try:
            self.state=self.READY
            self.rtpSocket.bind(('',self.rtpPort))
        except:
            messagebox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort)

    def handler(self):
        """Handler on explicitly closing the GUI window."""
        self.pauseMovie()
        if messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.exitClient()
        else:
            self.playMovie()