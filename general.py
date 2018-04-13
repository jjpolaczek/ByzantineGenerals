
import threading
import time
import socket
import random

BUFFER_SIZE = 1024
TCP_IP = '127.0.0.1'
BUFFER_SIZE = 1024

class GeneralProcess(threading.Thread):
    def __init__(self, name, port):
        threading.Thread.__init__(self, name=name)
        self.port=port

    def run(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        #s.connect((TCP_IP, self.port))
        s.bind((TCP_IP, self.port))
        s.listen(5)
        t=threading.current_thread()
        conn, addr = s.accept()

        while getattr(t, "do_run", True):
            print ("working on nothing %s" % self.name)
            time.sleep(1 + random.randint(0, 1))
            self.sendMessage(self.name, 38000+random.randint(1,3))

            data = conn.recv(BUFFER_SIZE)
            if not data:
                break
            else:
                print "received data:", data
        print("Stopping as you wish.")
        s.close()

    def sendMessage(self, msg, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect((TCP_IP, port))
        except socket.error as e:
            print "Exception while sending ::%s" % e
            return
        s.send(msg)
        s.close()