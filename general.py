
import threading
import time
import socket
import select
import Queue
import random
import logging

BUFFER_SIZE = 1024
TCP_IP = '127.0.0.1'
BUFFER_SIZE = 1024

class GeneralProcess(threading.Thread):
    def __init__(self, name, port):
        threading.Thread.__init__(self, name=name)
        self.port = port
        self.receiveQueue = Queue.Queue(maxsize=0)
        self.sendQueue = Queue.Queue(maxsize=0)
        self.listenThread = self._ReceiveingThread("%s-listener" % self.name, port, self.receiveQueue)
        self.sendThread = self._SendingThread("%s-sender" % self.name, port, self.sendQueue)


    def run(self):
        self.listenThread.start()
        self.sendThread.start()
        t=threading.current_thread()

        # Main solution loop
        while getattr(t, "do_run", True):
            # Here is all handling of messages you need Tomek!
            #print "MainLoop %s" % self.name
            data = self.getMessage()

            if data is not None:
                print data
            # Send a random message to someone else
            if random.randint(0,5) == 5:
                self.sendMessage("XDXDXD", 38000+random.randint(0, 2))


        #Cleanup worker threads
        #self.sendQueue.join()
        self.sendThread.do_run = False
        self.listenThread.do_run = False
        self.listenThread.join()
        self.sendThread.join()

    def sendMessage(self, msg, targetId):
        # Put the targetId / message tuple to the queue
        self.sendQueue.put((targetId, msg))

    def getMessage(self):
        try:
            data = self.receiveQueue.get(True, 0.1)
            # Waits for 0.1 seconds, otherwise throws `Queue.Empty`
        except Queue.Empty:
            data = None
        return data

    class _ReceiveingThread(threading.Thread):

        def __init__(self, name, port, receiveQueue):
            threading.Thread.__init__(self, name=name)
            self.port = port
            self.queue = receiveQueue

        def run(self):
            t = threading.current_thread()

            readSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            readSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            readSocket.bind((TCP_IP, self.port))
            readSocket.listen(5)
            logging.debug("%s Listening on port %d", self.name, self.port)
            readableSockets = [readSocket]

            while getattr(t, "do_run", True):
                readable, writeable, errored = select.select(readableSockets, [], [], 0.5)
                #print ("working on nothing %s" % self.name)
                for s in readable:
                    if s is readSocket:
                        client_socket, address = readSocket.accept()
                        readableSockets.append(client_socket)
                        print "Connection from", address
                    else:
                        data = s.recv(BUFFER_SIZE)
                        if len(data) > 0:
                            self.queue.put(data)

            print("Stopping %s as you wish." % self.name)
            readSocket.close()

    class _SendingThread(threading.Thread):

        def __init__(self, name, port, sendQueue):
            threading.Thread.__init__(self, name=name)
            self.port = port
            self.queue=sendQueue

        def run(self):

            t = threading.current_thread()
            while getattr(t, "do_run", True):
                try:
                    item = self.queue.get(block=True, timeout=0.1)
                    self.sendMessage(item[0], item[1])
                    self.queue.task_done()
                except Queue.Empty:
                    pass

            print("Stopping %s as you wish." % self.name)


        def sendMessage(self, port, msg):
            # For now connect on each message send (will be improved in the future to maintain connections)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.connect((TCP_IP, port))
                s.send(msg)
                print "Send message to port %d" % port
            except socket.error as e:
                print "Exception while sending (%d -> %d) ::%s" % (self.port, port,e)

                return
            s.close()