
import threading
import time
import socket
import select
import random
import logging

BUFFER_SIZE = 1024
TCP_IP = '127.0.0.1'
BUFFER_SIZE = 1024

class GeneralProcess(threading.Thread):
    def __init__(self, name, port):
        threading.Thread.__init__(self, name=name)
        self.port=port

    def run(self):
        t=threading.current_thread()

        readSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        readSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        readSocket.bind((TCP_IP, self.port))
        readSocket.listen(5)
        logging.debug("%s Listening on port %d", self.name, self.port)
        readableSockets=[readSocket]

        while getattr(t, "do_run", True):
            readable, writeable, errored = select.select(readableSockets,[],[],0.1)
            print ("working on nothing %s" % self.name)
            for s in readable:
                if s is readSocket:
                    client_socket, address = readSocket.accept()
                    readableSockets.append(client_socket)
                    print "Connection from", address
                else:
                    data = s.recv(BUFFER_SIZE)
                    print data

            time.sleep(1 + random.randint(0, 1))
            self.sendMessage(self.name, 38000+random.randint(1,3))

        print("Stopping as you wish.")
        readSocket.close()

    def sendMessage(self, msg, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect((TCP_IP, port))
            s.send(msg)
            print "Send message to port %d" % port
        except socket.error as e:
            print "Exception while sending ::%s" % e
            return
        s.close()

