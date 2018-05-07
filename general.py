
import threading
import time
import socket
import select
import Queue
import random
import logging
from exceptions import AttributeError

BUFFER_SIZE = 1024
TCP_IP = '127.0.0.1'
BUFFER_SIZE = 1024
ROUND_TIMEOUT_S = 5

class GeneralParameters():
    def __init__(self, recievingPort, isTraitor):
        self.port = recievingPort
        self.isTraitor = isTraitor

class GeneralProcess(threading.Thread):
    def __init__(self, name, problemStructureDict):
        threading.Thread.__init__(self, name=name)
        self.shutdownFlag = threading.Event()
        self.port = problemStructureDict[name].port
        self._is_traitor=problemStructureDict[name].isTraitor
        self.receiveQueue = Queue.Queue(maxsize=0)
        self.sendQueue = Queue.Queue(maxsize=0)
        self.listenThread = self._ReceiveingThread("%s-listener" % self.name, self.port, self.receiveQueue)
        self.sendThread = self._SendingThread("%s-sender" % self.name, self.port, self.sendQueue)
        self.others = problemStructureDict.copy()
        if self.others.pop(self.name) is None:
            raise AttributeError("Did not find self in soluton")
        #Initialize self state
        self._state="Idle"
        self._round=-1
        self._decision=None

    def getState(self):
        return self.state

    def performOrder(self, value):
        logging.info("%s performing order: %s", self.name, value)
        self._state = "OrderSent"
        self._decision = value

    def getDecision(self):
        return self.decision

    def run(self):
        self.listenThread.start()
        self.sendThread.start()
        t=threading.current_thread()

        # Main solution loop
        while not self.shutdownFlag.is_set():
            # Here is all handling of messages you need Tomek!
            #print "MainLoop %s" % self.name
            data = self.getMessage()

            if data is not None:
                print data
            # Send a random message to someone else
            if random.randint(0,5) == 5:
                receiveingGeneral = random.choice(self.others.keys())
                self.sendMessage("Message to %s from %s" % (receiveingGeneral, self.name), self.others[receiveingGeneral].port)


        #Cleanup worker threads
        #self.sendQueue.join()
        self.sendThread.shutdownFlag.set()
        self.listenThread.shutdownFlag.set()
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
            self.shutdownFlag = threading.Event()
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

            while not self.shutdownFlag.is_set():
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
            self.shutdownFlag = threading.Event()
            self.port = port
            self.queue=sendQueue

        def run(self):

            t = threading.current_thread()
            while not self.shutdownFlag.is_set():
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